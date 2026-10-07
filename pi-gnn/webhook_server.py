import os
import logging
import threading
import time
import uuid
import requests
import torch
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

from model import PIGNN, calculate_hazard_coefficient, seed_and_train
from sse_server import notify_clients, create_event_stream
from router import get_router

BAW_ENDPOINT = os.environ.get(
    "BAW_ENDPOINT",
    "http://localhost:9090/baw/trigger",
)
BAW_TRIGGER_TOKEN = os.environ.get("BAW_TRIGGER_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

_MODEL = PIGNN(node_features=4, hidden_dim=16, output_features=2)
seed_and_train(_MODEL)
log.info("[Code Engine] PI-GNN model loaded, seeded, and ready (DEMO_SEED=1).")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

SENSOR_SEGMENT_MAP: dict[str, tuple[int, int]] = {
    "Sensor-NH544-A": (0,   206),
    "Sensor-NH544-B": (164, 618),
}
ORIG_SEG_TOTAL = 824

def _segment_ids_for_node(node_id: str) -> list[str]:
    start, end = SENSOR_SEGMENT_MAP.get(node_id, (0, ORIG_SEG_TOTAL - 1))
    return [f"ORIG-SEG-{i}" for i in range(start, end + 1)]

_current_origin = None
_current_destination = None

@app.route("/set_route", methods=["POST"])
def set_route():
    global _current_origin, _current_destination
    body = request.get_json(silent=True) or {}
    origin = body.get("origin")
    destination = body.get("destination")
    
    if origin and destination:
        _current_origin = tuple(origin)
        _current_destination = tuple(destination)
        
    router = get_router()
    orig = _current_origin or router.origin
    dest = _current_destination or router.destination
    
    result = router.find_path(orig, dest)
    
    if result.found:
        notify_clients({
            "type": "REROUTE_UPDATE",
            "geojson": result.geojson,
            "is_rerouted": result.is_rerouted,
            "length_m": result.length_m
        })
        
    return jsonify({
        "found": result.found,
        "length_m": result.length_m,
        "is_rerouted": result.is_rerouted,
        "geojson": result.geojson,
    }), 200

@app.route("/reports", methods=["POST"])
def reports():
    """Accept a driver/community report and fan it out to connected clients."""
    body = request.get_json(silent=True) or {}
    event_type = body.get("type")
    location = body.get("location")
    description = body.get("description")
    coordinates = body.get("coordinates")

    if not all(isinstance(value, str) and value.strip() for value in (event_type, location, description)):
        return jsonify({"error": "type_location_description_required"}), 422
    if not isinstance(coordinates, list) or len(coordinates) != 2:
        return jsonify({"error": "coordinates_required"}), 422
    try:
        coordinates = [float(coordinates[0]), float(coordinates[1])]
    except (TypeError, ValueError):
        return jsonify({"error": "invalid_coordinates"}), 422

    report = {
        "type": "USER_REPORT",
        "event_type": event_type.strip(),
        "location": location.strip(),
        "description": description.strip(),
        "coordinates": coordinates,
        "timestamp": time.time(),
        "source": "community",
    }
    notify_clients(report)
    return jsonify({"accepted": True, "report": report}), 201

@app.route("/stream")
def stream():
    resp = Response(create_event_stream(), mimetype="text/event-stream")
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/infer", methods=["POST"])
def infer():
    body = request.get_json(silent=True)
    if body is None:
        log.warning("Received non-JSON payload — rejecting.")
        return jsonify({"error": "invalid_payload"}), 400

    node_id = body.get("node_id", "unknown")
    metrics = body.get("metrics", {})

    try:
        depth    = float(metrics["depth"])
        velocity = float(metrics["velocity"])
        S0       = float(metrics["S0"])
        n_rough  = float(metrics["n"])
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Missing or malformed metric fields: %s", exc)
        return jsonify({"error": "missing_metrics", "detail": str(exc)}), 422

    x   = torch.tensor([[100.0, S0, n_rough, 20.0]], dtype=torch.float32)
    adj = torch.tensor([[1.0]])

    with torch.no_grad():
        predictions = _MODEL(x, adj)

    predicted_depth = predictions[0, 0].item()
    predicted_vel   = predictions[0, 1].item()

    hazard, is_critical = calculate_hazard_coefficient(predicted_depth, predicted_vel)

    result = {
        "node_id":          node_id,
        "hazard_coefficient": round(hazard, 4),
        "is_critical":      bool(is_critical),
        "predicted_depth":  round(predicted_depth, 4),
        "predicted_velocity": round(predicted_vel, 4),
    }

    if is_critical:
        log.warning(
            "[CRITICAL] node=%s hazard=%.4f m²/s — dispatching BAW flood response.",
            node_id, hazard
        )
        _trigger_baw_async(node_id, hazard)
    else:
        log.info(
            "[OK] node=%s hazard=%.4f m²/s", node_id, hazard
        )

    if hazard < 0.4:
        severity_class = "SAFE"
    elif hazard < 0.8:
        severity_class = "WARNING"
    else:
        severity_class = "CRITICAL"

    notify_clients({
        "type":                  "HAZARD_UPDATE",
        "node_id":               node_id,
        "hazard_coefficient":    round(hazard, 4),
        "is_critical":           bool(is_critical),
        "severity_class":        severity_class,
        "affected_segment_ids":  _segment_ids_for_node(node_id),
    })

    router = get_router()
    router.update_hazard(node_id, hazard)
    
    global _current_origin, _current_destination
    orig = _current_origin or router.origin
    dest = _current_destination or router.destination
    
    route_result = router.find_path(orig, dest)
    if route_result.found:
        notify_clients({
            "type": "REROUTE_UPDATE",
            "geojson": route_result.geojson,
            "is_rerouted": route_result.is_rerouted,
            "length_m": route_result.length_m
        })

    return jsonify(result), 200

def _trigger_baw_async(node_id: str, hazard: float):
    def _post():
        try:
            headers = {}
            if BAW_TRIGGER_TOKEN:
                headers["X-Trigger-Token"] = BAW_TRIGGER_TOKEN
            requests.post(
                BAW_ENDPOINT,
                json={"sensor_node": node_id, "hazard_coefficient": hazard},
                headers=headers,
                timeout=5,
            )
            log.info("[BAW] Trigger POSTed to %s for node=%s", BAW_ENDPOINT, node_id)
        except Exception as exc:
            log.error("[BAW] Trigger POST failed (non-blocking): %s", exc)

    threading.Thread(target=_post, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
