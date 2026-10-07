"""
watsonx_orchestrate_connector.py
─────────────────────────────────
MCP (Model Context Protocol) connector for IBM watsonx Orchestrate.

This module exposes the KSDMA (Kinematic Stability Domain Mapping Algorithm)
and IBM Event Streams tools so that watsonx Orchestrate skill-flows can call
them as first-class actions without custom code in the orchestration layer.

Architecture:
  watsonx Orchestrate skill-flow
        │
        ▼  HTTP/MCP JSON-RPC
  MCP Connector (this file — hosted as a Code Engine App or local server)
        │                      │
        ▼                      ▼
  KSDMA Tool             IBM Event Streams Tool
  (calls webhook_server  (publishes telemetry /
   /infer endpoint)       reads Kafka offsets)

Environment variables required (set as Code Engine secrets):
  INFER_ENDPOINT        Full URL of the webhook_server /infer endpoint
                        e.g. https://hydro-pi-gnn.abcde.us-south.codeengine.appdomain.cloud/infer
  EVENT_STREAMS_URL     IBM Event Streams REST endpoint
                        e.g. https://<broker>.eventstreams.cloud.ibm.com
  EVENT_STREAMS_APIKEY  IBM Event Streams / IKS API key
  EVENT_STREAMS_TOPIC   Target Kafka topic  (default: chalakudy-basin-telemetry)
  MCP_API_KEY           Secret used to authenticate requests from watsonx Orchestrate
  PORT                  Listening port injected by Code Engine (default: 8080)
"""

import os
import json
import logging
import hmac
import hashlib
import uuid
from typing import Any

import requests
from flask import Flask, request, jsonify, abort

from baw_flood_response import run_flood_response_workflow

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = Flask(__name__)

# ── Configuration from environment ───────────────────────────────────────────
INFER_ENDPOINT       = os.environ.get("INFER_ENDPOINT", "http://localhost:8080/infer")
ES_URL               = os.environ.get("EVENT_STREAMS_URL", "")
ES_APIKEY            = os.environ.get("EVENT_STREAMS_APIKEY", "")
ES_TOPIC             = os.environ.get("EVENT_STREAMS_TOPIC", "chalakudy-basin-telemetry")
MCP_API_KEY          = os.environ.get("MCP_API_KEY", "dev-insecure-key")
# Shared secret between webhook_server and the BAW trigger endpoint.
# When empty (default / demo mode) the check is bypassed so local runs work
# without any configuration. Set in Code Engine secrets for production.
BAW_TRIGGER_TOKEN    = os.environ.get("BAW_TRIGGER_TOKEN", "")


# ─────────────────────────────────────────────────────────────────────────────
# Auth helper — watsonx Orchestrate sends MCP_API_KEY in X-Api-Key header
# ─────────────────────────────────────────────────────────────────────────────
def _require_api_key():
    provided = request.headers.get("X-Api-Key", "")
    if not hmac.compare_digest(provided, MCP_API_KEY):
        log.warning("Unauthorised MCP call from %s", request.remote_addr)
        abort(401, description="Invalid or missing X-Api-Key header.")


# ─────────────────────────────────────────────────────────────────────────────
# MCP tool registry — returned by the /mcp/tools/list endpoint so that
# watsonx Orchestrate can auto-discover skills at registration time.
# ─────────────────────────────────────────────────────────────────────────────
MCP_TOOL_REGISTRY = [
    {
        "name": "ksdma_infer",
        "description": (
            "Run PI-GNN inference on a single sensor telemetry payload using the "
            "Kinematic Stability Domain Mapping Algorithm (KSDMA). Returns the "
            "hazard coefficient (m²/s) and a boolean critical flag that triggers "
            "the BAW flood-response workflow when True."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["node_id", "depth", "velocity", "S0", "n"],
            "properties": {
                "node_id":  {"type": "string",  "description": "Sensor / node identifier, e.g. Sensor-NH544-A"},
                "depth":    {"type": "number",  "description": "Flow depth in metres"},
                "velocity": {"type": "number",  "description": "Flow velocity in m/s"},
                "S0":       {"type": "number",  "description": "Bed slope (dimensionless)"},
                "n":        {"type": "number",  "description": "Manning roughness coefficient"},
            },
        },
    },
    {
        "name": "event_streams_publish",
        "description": (
            "Publish a telemetry message directly to the IBM Event Streams "
            "(Kafka) chalakudy-basin-telemetry topic. Used by watsonx Orchestrate "
            "to inject synthetic test events or re-publish stale sensor data."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["node_id", "depth", "velocity", "S0", "n"],
            "properties": {
                "node_id":  {"type": "string"},
                "depth":    {"type": "number"},
                "velocity": {"type": "number"},
                "S0":       {"type": "number"},
                "n":        {"type": "number"},
            },
        },
    },
    {
        "name": "event_streams_latest_offset",
        "description": (
            "Query the latest committed Kafka offset for the "
            "chalakudy-basin-telemetry topic. Useful for auditing whether "
            "all sensor events have been processed before closing an incident."
        ),
        "inputSchema": {
            "type": "object",
            "required": [],
            "properties": {
                "partition": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "drone_dispatch",
        "description": (
            "Dispatch a reconnaissance UAV to the specified NH544 sector when cellular "
            "infrastructure fails and VDTN offline mode is active. Returns a structured "
            "dispatch confirmation including UAV type, flight path, and mission ID."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["node_id", "sector", "priority"],
            "properties": {
                "node_id":  {"type": "string",  "description": "VDTN node that entered the dead zone, e.g. Truck-FMCG-01"},
                "sector":   {"type": "string",  "description": "NH544 sector identifier, e.g. NH544_Sector7_Corridor"},
                "priority": {"type": "string",  "enum": ["emergency", "high", "normal"], "default": "emergency"},
                "uav_type": {"type": "string",  "description": "UAV model override (default: reconnaissance_quadcopter)"},
            },
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# MCP protocol endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/mcp/tools/list", methods=["GET"])
def tools_list():
    """watsonx Orchestrate calls this at skill-import time to discover tools."""
    _require_api_key()
    return jsonify({"tools": MCP_TOOL_REGISTRY}), 200


@app.route("/mcp/tools/call", methods=["POST"])
def tools_call():
    """
    Single dispatch endpoint for all tool invocations.

    Expected request body (MCP JSON-RPC style):
    {
      "name": "<tool_name>",
      "arguments": { ... }
    }
    """
    _require_api_key()
    body = request.get_json(silent=True) or {}
    tool_name = body.get("name")
    arguments  = body.get("arguments", {})

    if tool_name == "ksdma_infer":
        return _tool_ksdma_infer(arguments)

    if tool_name == "event_streams_publish":
        return _tool_es_publish(arguments)

    if tool_name == "event_streams_latest_offset":
        return _tool_es_latest_offset(arguments)

    if tool_name == "drone_dispatch":
        return _tool_drone_dispatch(arguments)

    return jsonify({"error": f"Unknown tool: {tool_name}"}), 404


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────────────────

def _tool_ksdma_infer(args: dict[str, Any]):
    """
    Forwards the sensor payload to the Code Engine /infer endpoint and
    returns the structured KSDMA result to watsonx Orchestrate.
    """
    payload = {
        "node_id": args["node_id"],
        "timestamp": None,  # server fills this
        "metrics": {
            "depth":    args["depth"],
            "velocity": args["velocity"],
            "S0":       args["S0"],
            "n":        args["n"],
        },
    }
    try:
        resp = requests.post(INFER_ENDPOINT, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        log.error("KSDMA infer failed: %s", exc)
        return jsonify({"error": "infer_upstream_error", "detail": str(exc)}), 502

    log.info(
        "[KSDMA] node=%s hazard=%.4f critical=%s",
        data.get("node_id"), data.get("hazard_coefficient"), data.get("is_critical")
    )
    return jsonify({"content": [{"type": "text", "text": json.dumps(data)}]}), 200


def _tool_es_publish(args: dict[str, Any]):
    """
    Publishes a telemetry record to IBM Event Streams via its REST Producer API.
    https://cloud.ibm.com/apidocs/event-streams/adminrest#produce-message
    """
    message_body = {
        "node_id": args["node_id"],
        "metrics": {
            "depth":    args["depth"],
            "velocity": args["velocity"],
            "S0":       args["S0"],
            "n":        args["n"],
        },
    }

    if not ES_URL or not ES_APIKEY:
        # Dev/demo mode: log and return success without a real broker
        log.info("[Event Streams MOCK] Would publish to topic '%s': %s", ES_TOPIC, message_body)
        result = {"published": True, "topic": ES_TOPIC, "mode": "mock"}
        return jsonify({"content": [{"type": "text", "text": json.dumps(result)}]}), 200

    produce_url = f"{ES_URL}/topics/{ES_TOPIC}/records"
    headers = {
        "X-Auth-Token": ES_APIKEY,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(
            produce_url,
            headers=headers,
            json={"records": [{"value": json.dumps(message_body)}]},
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Event Streams publish failed: %s", exc)
        return jsonify({"error": "es_publish_error", "detail": str(exc)}), 502

    result = {"published": True, "topic": ES_TOPIC, "status_code": resp.status_code}
    return jsonify({"content": [{"type": "text", "text": json.dumps(result)}]}), 200


def _tool_es_latest_offset(args: dict[str, Any]):
    """
    Returns the latest offset for a given Kafka partition via Event Streams admin API.
    """
    partition = int(args.get("partition", 0))

    if not ES_URL or not ES_APIKEY:
        result = {"topic": ES_TOPIC, "partition": partition, "latest_offset": -1, "mode": "mock"}
        return jsonify({"content": [{"type": "text", "text": json.dumps(result)}]}), 200

    admin_url = f"{ES_URL}/admin/topics/{ES_TOPIC}"
    headers = {"X-Auth-Token": ES_APIKEY}
    try:
        resp = requests.get(admin_url, headers=headers, timeout=10)
        resp.raise_for_status()
        topic_info = resp.json()
    except requests.RequestException as exc:
        log.error("Event Streams admin query failed: %s", exc)
        return jsonify({"error": "es_admin_error", "detail": str(exc)}), 502

    # Locate the partition record in the response
    partitions = topic_info.get("replication_info", [])
    offset_info = next(
        (p for p in partitions if p.get("id") == partition), {}
    )

    result = {
        "topic":          ES_TOPIC,
        "partition":      partition,
        "latest_offset":  offset_info.get("latest_offset", "unknown"),
        "leader":         offset_info.get("leader", "unknown"),
    }
    return jsonify({"content": [{"type": "text", "text": json.dumps(result)}]}), 200


def _tool_drone_dispatch(args: dict[str, Any]):
    """
    Dispatches a reconnaissance UAV to the dead-zone sector.

    Triggered when a VDTN node reports cellular_dead_zone_entered (mcp.json line 29).
    In demo / no-callback mode the dispatch is logged and a structured confirmation
    is returned. When BAW_CALLBACK_URL is set the confirmation is also POSTed there
    so the watsonx Orchestrate audit log captures the event.
    """
    node_id  = args.get("node_id",  "UNKNOWN")
    sector   = args.get("sector",   "NH544_Sector7_Corridor")
    priority = args.get("priority", "emergency")
    uav_type = args.get("uav_type", "reconnaissance_quadcopter")
    mission_id = f"UAV-{uuid.uuid4().hex[:8].upper()}"

    dispatch = {
        "mission_id":   mission_id,
        "uav_type":     uav_type,
        "flight_path":  sector,
        "priority":     priority,
        "triggered_by": node_id,
        "status":       "DISPATCHED",
        "timestamp_utc": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source":       "HydroMesh-MCP-DroneDispatch",
    }

    log.info(
        "[DroneDispatch] mission=%s uav=%s sector=%s priority=%s node=%s",
        mission_id, uav_type, sector, priority, node_id,
    )

    # Forward to BAW callback URL if configured (non-blocking best-effort)
    callback_url = os.environ.get("BAW_CALLBACK_URL", "")
    if callback_url:
        try:
            requests.post(callback_url, json=dispatch, timeout=5)
        except requests.RequestException as exc:
            log.warning("DroneDispatch callback failed (non-blocking): %s", exc)

    return jsonify({"content": [{"type": "text", "text": json.dumps(dispatch)}]}), 200


# ─────────────────────────────────────────────────────────────────────────────
# BAW trigger endpoint — called by webhook_server._trigger_baw_async when a
# critical hazard coefficient is detected during PI-GNN inference.
# Also callable directly by watsonx Orchestrate for manual incident escalation.
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/baw/trigger", methods=["POST"])
def baw_trigger():
    """
    Accepts a flood-alert trigger and executes the full autonomous BAW workflow.

    Expected JSON body:
    {
      "sensor_node":        "Sensor-NH544-B",
      "hazard_coefficient": 3.75,
      "delay_hours":        4.0,           // optional, default 4.0
      "affected_skus":      ["SKU-1", ...] // optional
    }
    """
    # Token check — bypass in demo mode (empty token), enforce in production.
    if BAW_TRIGGER_TOKEN:
        provided = request.headers.get("X-Trigger-Token", "")
        if not hmac.compare_digest(provided, BAW_TRIGGER_TOKEN):
            log.warning("Unauthorised BAW trigger attempt from %s", request.remote_addr)
            abort(401, description="Invalid or missing X-Trigger-Token header.")

    body = request.get_json(silent=True) or {}
    sensor_node        = body.get("sensor_node", "UNKNOWN")
    hazard_coefficient = float(body.get("hazard_coefficient", 0.0))
    delay_hours        = float(body.get("delay_hours", 4.0))
    affected_skus      = body.get("affected_skus")

    if hazard_coefficient <= 0.8:
        return jsonify({"skipped": True, "reason": "hazard below critical threshold"}), 200

    summary = run_flood_response_workflow(
        sensor_node=sensor_node,
        hazard_coefficient=hazard_coefficient,
        delay_hours=delay_hours,
        affected_skus=affected_skus,
    )
    status_code = 200 if summary["workflow_status"] == "SUCCESS" else 207
    return jsonify(summary), status_code


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 9090))
    app.run(host="0.0.0.0", port=port, debug=False)
