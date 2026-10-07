"""
webhook_server.py
─────────────────
IBM Cloud Code Engine entry-point.

This Flask application receives IBM Event Streams webhook POST calls
(configured as a "Subscription" trigger in Code Engine) and runs PI-GNN
inference on each telemetry payload.

IBM Event Streams Subscription → Code Engine Job/App:
  • Code Engine injects the Kafka message body as the HTTP POST body.
  • Headers include CE-* CloudEvents attributes (source, type, topic, partition).
  • On a successful 2xx response the message is committed; on 5xx it is retried.

Scale-to-zero behaviour:
  • When no webhooks arrive the Code Engine app scales to 0 replicas.
  • On the first incoming call Code Engine cold-starts one replica of this image.
  • The PIGNN model is loaded ONCE at module level (--preload in Gunicorn) so
    the model weights are already in memory when the first request is processed.
"""

import os
import json
import logging

import queue
import time
import threading

import requests
import torch
from flask import Flask, request, jsonify
from flask_cors import CORS

from model import PIGNN, calculate_hazard_coefficient, seed_and_train

# BAW connector — called asynchronously when a critical threshold is breached
BAW_ENDPOINT = os.environ.get(
    "BAW_ENDPOINT",
    "http://localhost:9090/baw/trigger",  # override with Code Engine BAW app URL
)
# Shared secret sent as X-Trigger-Token; must match BAW_TRIGGER_TOKEN in the
# BAW service. Leave empty in local/demo mode (check is bypassed by the BAW).
BAW_TRIGGER_TOKEN = os.environ.get("BAW_TRIGGER_TOKEN", "")

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Pre-load model (executed once at worker start via Gunicorn --preload) ────
# seed_and_train fixes random weights to a deterministic, physically-calibrated
# state (DEMO_SEED=1, 2 000 Adam steps) so every cold-start produces the same
# inference values and the demo narrative is always consistent.
_MODEL = PIGNN(node_features=4, hidden_dim=16, output_features=2)
seed_and_train(_MODEL)
log.info("[Code Engine] PI-GNN model loaded, seeded, and ready (DEMO_SEED=1).")

app = Flask(__name__)
# Allow browser clients (digital-twin WebGL canvas) to consume the SSE stream
# from a different origin.  Only the /stream endpoint needs CORS; all other
# routes remain restricted to same-origin (Code Engine internal) callers.
CORS(app, resources={r"/stream": {"origins": "*"}})

# ── Sensor → road-segment mapping ────────────────────────────────────────────
# Maps each sensor node ID to the range of ORIG-SEG-{i} IDs it covers.
# Derived from routes.geojson: 824 ORIG segments total.
#   Sensor-NH544-A: approach zone, segments 0–206 (first 25% of route)
#   Sensor-NH544-B: flood zone,    segments 164–618 (middle 55% — Chalakudy bridge area)
# Any unknown sensor defaults to the full original route (0–823).
SENSOR_SEGMENT_MAP: dict[str, tuple[int, int]] = {
    "Sensor-NH544-A": (0,   206),
    "Sensor-NH544-B": (164, 618),
}
ORIG_SEG_TOTAL = 824


def _segment_ids_for_node(node_id: str) -> list[str]:
    start, end = SENSOR_SEGMENT_MAP.get(node_id, (0, ORIG_SEG_TOTAL - 1))
    return [f"ORIG-SEG-{i}" for i in range(start, end + 1)]


# ── SSE Client Queues ────────────────────────────────────────────────────────
# Lock guards the clients list against concurrent mutations under Gunicorn
# --threads N (multiple threads sharing one process).
_clients_lock = threading.Lock()
clients: list[queue.Queue] = []


def notify_clients(data: dict):
    msg = f"data: {json.dumps(data)}\n\n"
    with _clients_lock:
        snapshot = list(clients)
    for q in snapshot:
        try:
            q.put_nowait(msg)
        except queue.Full:
            pass


@app.route("/stream")
def stream():
    def event_stream():
        q: queue.Queue = queue.Queue(maxsize=20)
        with _clients_lock:
            clients.append(q)
        try:
            while True:
                yield q.get()
        except GeneratorExit:
            with _clients_lock:
                try:
                    clients.remove(q)
                except ValueError:
                    pass  # already removed — harmless

    from flask import Response
    resp = Response(event_stream(), mimetype="text/event-stream")
    # Disable proxy/browser buffering so events are flushed immediately.
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Cache-Control"] = "no-cache"
    return resp

# ─────────────────────────────────────────────────────────────────────────────
# Health endpoint — required by Code Engine liveness / readiness probes
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# ─────────────────────────────────────────────────────────────────────────────
# IBM Event Streams webhook endpoint
#
# Expected JSON body (produced by IBMEventStreamsMock.produce_telemetry):
# {
#   "node_id": "Sensor-NH544-A",
#   "timestamp": 1700000000.0,
#   "metrics": { "depth": 1.5, "velocity": 2.5, "S0": 0.05, "n": 0.065 }
# }
# ─────────────────────────────────────────────────────────────────────────────
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

    # Build single-node input tensor: [elevation (fixed ref), S0, n, width]
    x   = torch.tensor([[100.0, S0, n_rough, 20.0]], dtype=torch.float32)
    adj = torch.tensor([[1.0]])  # Self-loop adjacency for single-node inference

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

    # Derive severity class for the HUD badge
    if hazard < 0.4:
        severity_class = "SAFE"
    elif hazard < 0.8:
        severity_class = "WARNING"
    else:
        severity_class = "CRITICAL"

    # Push to all connected digital twin WebGL canvases via SSE
    # Segment IDs are derived from the sensor node's geographic coverage
    notify_clients({
        "type":                  "HAZARD_UPDATE",
        "node_id":               node_id,
        "hazard_coefficient":    round(hazard, 4),
        "is_critical":           bool(is_critical),
        "severity_class":        severity_class,
        "affected_segment_ids":  _segment_ids_for_node(node_id),
    })

    # HTTP 200 commits the Kafka offset; HTTP 5xx causes Event Streams retry
    return jsonify(result), 200


def _trigger_baw_async(node_id: str, hazard: float):
    """
    Fire-and-forget POST to the BAW flood-response endpoint.
    Runs in a daemon thread so the webhook response is not held up.
    """
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
        except Exception as exc:  # noqa: BLE001
            log.error("[BAW] Trigger POST failed (non-blocking): %s", exc)

    threading.Thread(target=_post, daemon=True).start()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
