import json
import logging
import uuid
import os
from typing import Any
import requests
from flask import jsonify

from watsonx_config import INFER_ENDPOINT, ES_URL, ES_APIKEY, ES_TOPIC

log = logging.getLogger(__name__)

def tool_ksdma_infer(args: dict[str, Any]):
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

def tool_es_publish(args: dict[str, Any]):
    """
    Publishes a telemetry record to IBM Event Streams via its REST Producer API.
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

def tool_es_latest_offset(args: dict[str, Any]):
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

def tool_drone_dispatch(args: dict[str, Any]):
    """
    Dispatches a reconnaissance UAV to the dead-zone sector.
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

    callback_url = os.environ.get("BAW_CALLBACK_URL", "")
    if callback_url:
        try:
            requests.post(callback_url, json=dispatch, timeout=5)
        except requests.RequestException as exc:
            log.warning("DroneDispatch callback failed (non-blocking): %s", exc)

    return jsonify({"content": [{"type": "text", "text": json.dumps(dispatch)}]}), 200
