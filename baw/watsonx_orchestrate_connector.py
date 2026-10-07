"""
watsonx_orchestrate_connector.py
─────────────────────────────────
MCP (Model Context Protocol) connector for IBM watsonx Orchestrate.
"""

import os
import json
import logging
import hmac
from flask import Flask, request, jsonify, abort

from baw_flood_response import run_flood_response_workflow
from watsonx_config import MCP_API_KEY, BAW_TRIGGER_TOKEN
from mcp_registry import MCP_TOOL_REGISTRY
from mcp_tools import (
    tool_ksdma_infer,
    tool_es_publish,
    tool_es_latest_offset,
    tool_drone_dispatch,
)

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = Flask(__name__)

def _require_api_key():
    provided = request.headers.get("X-Api-Key", "")
    if not hmac.compare_digest(provided, MCP_API_KEY):
        log.warning("Unauthorised MCP call from %s", request.remote_addr)
        abort(401, description="Invalid or missing X-Api-Key header.")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/mcp/tools/list", methods=["GET"])
def tools_list():
    _require_api_key()
    return jsonify({"tools": MCP_TOOL_REGISTRY}), 200

@app.route("/mcp/tools/call", methods=["POST"])
def tools_call():
    _require_api_key()
    body = request.get_json(silent=True) or {}
    tool_name = body.get("name")
    arguments  = body.get("arguments", {})

    if tool_name == "ksdma_infer":
        return tool_ksdma_infer(arguments)
    if tool_name == "event_streams_publish":
        return tool_es_publish(arguments)
    if tool_name == "event_streams_latest_offset":
        return tool_es_latest_offset(arguments)
    if tool_name == "drone_dispatch":
        return tool_drone_dispatch(arguments)

    return jsonify({"error": f"Unknown tool: {tool_name}"}), 404

@app.route("/baw/trigger", methods=["POST"])
def baw_trigger():
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
