"""
baw_flood_response.py
──────────────────────
Autonomous Business Automation Workflow (BAW)

Triggered when the PI-GNN predicts that the NH544 route is severed by a flash
flood (hazard coefficient > 0.8 m²/s). Executes ALL three response actions
below with zero human intervention:

  Step 1 — SMS Dispatch
      Sends SMS alerts to registered truck drivers instructing them to halt at
      the nearest elevated rest area. Uses IBM Watson's Twilio integration
      (or a direct Twilio REST call) via credentials stored in environment.

  Step 2 — Warehouse ETA Notification
      POSTs exact delay estimates to each destination FMCG warehouse via their
      registered webhook URL. Payload includes incident reference, reroute status,
      and the recalculated ETA in ISO-8601 format.

  Step 3 — ERP Inventory Recalculation
      Calls the enterprise ERP REST API (/api/v1/inventory/reallocate) to trigger
      a regional supply-chain rebalance, transferring stock from the Cochin_Hub_02
      fallback warehouse to affected distribution points.

Environment variables (set as IBM Code Engine secrets):
  TWILIO_ACCOUNT_SID     Twilio account SID
  TWILIO_AUTH_TOKEN      Twilio auth token
  TWILIO_FROM_NUMBER     Sender phone number (E.164 format, e.g. +14155238886)
  ERP_BASE_URL           ERP REST API base URL
  ERP_API_KEY            ERP API key / bearer token
  WAREHOUSE_WEBHOOK_URLS Comma-separated list of warehouse webhook URLs
  DRIVER_PHONE_NUMBERS   Comma-separated list of driver phone numbers in E.164 format
  ELEVATED_REST_AREA     Name / coordinates of the nearest elevated rest area
                         (default: "Athirappilly Rest Area — 10.284°N 76.569°E")
  BAW_CALLBACK_URL       Optional URL to POST the final workflow summary to
"""

import os
import json
import logging
import datetime
import time
import hmac
import hashlib
import uuid
from typing import Optional

import requests

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("BAW-FloodResponse")

# ── Configuration ─────────────────────────────────────────────────────────────
TWILIO_ACCOUNT_SID    = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN     = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER    = os.environ.get("TWILIO_FROM_NUMBER", "+10000000000")

ERP_BASE_URL          = os.environ.get("ERP_BASE_URL", "https://erp.example.internal")
ERP_API_KEY           = os.environ.get("ERP_API_KEY", "")

_raw_warehouse_urls   = os.environ.get("WAREHOUSE_WEBHOOK_URLS", "")
WAREHOUSE_WEBHOOK_URLS = [u.strip() for u in _raw_warehouse_urls.split(",") if u.strip()]

_raw_drivers          = os.environ.get("DRIVER_PHONE_NUMBERS", "")
DRIVER_PHONE_NUMBERS  = [p.strip() for p in _raw_drivers.split(",") if p.strip()]

ELEVATED_REST_AREA    = os.environ.get(
    "ELEVATED_REST_AREA", "Athirappilly Rest Area — 10.284°N 76.569°E"
)
BAW_CALLBACK_URL      = os.environ.get("BAW_CALLBACK_URL", "")

# Demo mode: when credentials are absent we log & return mock success
_DEMO_MODE = not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and ERP_API_KEY)


# ─────────────────────────────────────────────────────────────────────────────
# Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _eta_iso(delay_hours: float) -> str:
    eta = datetime.datetime.utcnow() + datetime.timedelta(hours=delay_hours)
    return eta.strftime("%Y-%m-%dT%H:%M:%SZ")


def _incident_id(sensor_node: str) -> str:
    ts = int(time.time())
    tag = hashlib.sha256(f"{sensor_node}:{ts}".encode()).hexdigest()[:8].upper()
    return f"INC-NH544-{tag}"


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: SMS Dispatch via Twilio
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_driver_sms(
    incident_id: str,
    sensor_node: str,
    hazard_coefficient: float,
    phone_numbers: list[str],
) -> list[dict]:
    """
    Sends an SMS alert to each driver in phone_numbers.
    Returns a list of result dicts — one per driver.
    """
    message_body = (
        f"[FLOOD ALERT — {incident_id}] "
        f"NH544 route SEVERED near {sensor_node}. "
        f"Hazard={hazard_coefficient:.2f} m²/s (threshold: 0.80). "
        f"HALT IMMEDIATELY at nearest elevated rest area: {ELEVATED_REST_AREA}. "
        f"Await further instructions. Do NOT proceed. — HydroMesh AutoBAW"
    )

    results = []

    if _DEMO_MODE or not phone_numbers:
        log.info("[Step 1 / DEMO] SMS would be sent to %d driver(s).", len(phone_numbers) or 1)
        log.info("[Step 1 / DEMO] Message: %s", message_body)
        results.append({"mode": "demo", "recipients": phone_numbers or ["<none configured>"], "status": "mock_sent"})
        return results

    twilio_url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    for number in phone_numbers:
        try:
            resp = requests.post(
                twilio_url,
                data={"From": TWILIO_FROM_NUMBER, "To": number, "Body": message_body},
                auth=auth,
                timeout=10,
            )
            resp.raise_for_status()
            sid = resp.json().get("sid", "unknown")
            log.info("[Step 1] SMS sent to %s  sid=%s", number, sid)
            results.append({"to": number, "sid": sid, "status": "sent"})
        except requests.RequestException as exc:
            log.error("[Step 1] SMS FAILED to %s: %s", number, exc)
            results.append({"to": number, "error": str(exc), "status": "failed"})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: Warehouse ETA Notification
# ─────────────────────────────────────────────────────────────────────────────

def notify_warehouses(
    incident_id: str,
    sensor_node: str,
    hazard_coefficient: float,
    delay_hours: float,
    webhook_urls: list[str],
) -> list[dict]:
    """
    POSTs a structured incident notification to each FMCG warehouse webhook.
    Returns a list of result dicts.
    """
    payload = {
        "incident_id":          incident_id,
        "event_type":           "route_severed_flash_flood",
        "timestamp":            _now_iso(),
        "affected_route":       "NH544-Chalakudy-Basin",
        "sensor_node":          sensor_node,
        "hazard_coefficient":   hazard_coefficient,
        "status":               "SEVERED",
        "delay_hours":          delay_hours,
        "estimated_resume_eta": _eta_iso(delay_hours),
        "fallback_action":      "Inventory rebalance initiated via Cochin_Hub_02",
        "source":               "HydroMesh-BAW-AutoDispatch",
    }

    results = []

    if _DEMO_MODE or not webhook_urls:
        log.info("[Step 2 / DEMO] Warehouse notification payload:\n%s", json.dumps(payload, indent=2))
        results.append({"mode": "demo", "recipients": webhook_urls or ["<none configured>"], "status": "mock_sent"})
        return results

    headers = {"Content-Type": "application/json"}
    for url in webhook_urls:
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            log.info("[Step 2] Warehouse notified: %s  status=%d", url, resp.status_code)
            results.append({"url": url, "http_status": resp.status_code, "status": "notified"})
        except requests.RequestException as exc:
            log.error("[Step 2] Warehouse notification FAILED for %s: %s", url, exc)
            results.append({"url": url, "error": str(exc), "status": "failed"})

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: ERP Inventory Recalculation
# ─────────────────────────────────────────────────────────────────────────────

def trigger_erp_rebalance(
    incident_id: str,
    sensor_node: str,
    delay_hours: float,
    affected_skus: Optional[list[str]] = None,
) -> dict:
    """
    Calls the ERP /api/v1/inventory/reallocate endpoint to trigger a regional
    supply-chain rebalance, moving stock to compensate for the NH544 disruption.

    Returns the ERP response dict (or a mock dict in demo mode).
    """
    erp_payload = {
        "incident_id":       incident_id,
        "trigger":           "fmcg_inventory_delayed",
        "sensor_node":       sensor_node,
        "affected_route":    "NH544-Chalakudy-Basin",
        "delay_hours":       delay_hours,
        "fallback_warehouse": "Cochin_Hub_02",
        "reallocation_mode": "regional_buffer_fill",
        "affected_skus":     affected_skus or ["ALL"],
        "notify_roles":      ["warehouse_director", "procurement"],
        "timestamp":         _now_iso(),
        "source":            "HydroMesh-BAW-AutoDispatch",
    }

    if _DEMO_MODE:
        log.info(
            "[Step 3 / DEMO] ERP rebalance payload:\n%s",
            json.dumps(erp_payload, indent=2),
        )
        return {
            "mode": "demo",
            "erp_reference": f"ERP-MOCK-{uuid.uuid4().hex[:8].upper()}",
            "status": "mock_accepted",
            "reallocation_initiated": True,
        }

    erp_url = f"{ERP_BASE_URL}/api/v1/inventory/reallocate"
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Bearer {ERP_API_KEY}",
    }
    try:
        resp = requests.post(erp_url, json=erp_payload, headers=headers, timeout=15)
        resp.raise_for_status()
        erp_result = resp.json()
        log.info("[Step 3] ERP rebalance accepted: %s", erp_result)
        return {"status": "accepted", **erp_result}
    except requests.RequestException as exc:
        log.error("[Step 3] ERP call FAILED: %s", exc)
        return {"status": "failed", "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# BAW Orchestrator — main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_flood_response_workflow(
    sensor_node: str,
    hazard_coefficient: float,
    delay_hours: float = 4.0,
    affected_skus: Optional[list[str]] = None,
) -> dict:
    """
    Executes all three BAW steps autonomously with zero human intervention.

    Parameters
    ----------
    sensor_node         : Sensor ID that triggered the critical threshold.
    hazard_coefficient  : Measured/predicted hazard coefficient (m²/s).
    delay_hours         : Estimated delivery delay caused by the flood (hours).
    affected_skus       : Optional list of FMCG SKUs to target in ERP rebalance.

    Returns
    -------
    A summary dict covering all three step outcomes + a final status flag.
    """
    incident_id = _incident_id(sensor_node)

    log.warning(
        "═══════════════════════════════════════════════════════════\n"
        "  BAW FLOOD RESPONSE TRIGGERED\n"
        "  Incident  : %s\n"
        "  Sensor    : %s\n"
        "  Hazard    : %.4f m²/s  (threshold 0.80)\n"
        "  Delay est.: %.1f hours\n"
        "═══════════════════════════════════════════════════════════",
        incident_id, sensor_node, hazard_coefficient, delay_hours,
    )

    # ── Step 1: SMS ───────────────────────────────────────────────────────────
    log.info("[BAW] Step 1/3 — Dispatching driver SMS alerts …")
    sms_results = dispatch_driver_sms(
        incident_id, sensor_node, hazard_coefficient, DRIVER_PHONE_NUMBERS
    )
    log.info("[BAW] Step 1/3 — COMPLETE. %d SMS dispatched.", len(sms_results))

    # ── Step 2: Warehouse notifications ──────────────────────────────────────
    log.info("[BAW] Step 2/3 — Notifying FMCG warehouses of ETA delay …")
    wh_results = notify_warehouses(
        incident_id, sensor_node, hazard_coefficient, delay_hours, WAREHOUSE_WEBHOOK_URLS
    )
    log.info("[BAW] Step 2/3 — COMPLETE. %d warehouse(s) notified.", len(wh_results))

    # ── Step 3: ERP rebalance ─────────────────────────────────────────────────
    log.info("[BAW] Step 3/3 — Triggering ERP inventory rebalance …")
    erp_result = trigger_erp_rebalance(
        incident_id, sensor_node, delay_hours, affected_skus
    )
    log.info("[BAW] Step 3/3 — COMPLETE. ERP status: %s", erp_result.get("status"))

    # ── Summary ───────────────────────────────────────────────────────────────
    all_ok = (
        all(r.get("status") not in ("failed",) for r in sms_results)
        and all(r.get("status") not in ("failed",) for r in wh_results)
        and erp_result.get("status") not in ("failed",)
    )

    summary = {
        "incident_id":         incident_id,
        "sensor_node":         sensor_node,
        "hazard_coefficient":  hazard_coefficient,
        "delay_hours":         delay_hours,
        "workflow_status":     "SUCCESS" if all_ok else "PARTIAL_FAILURE",
        "steps": {
            "sms_dispatch":           sms_results,
            "warehouse_notification": wh_results,
            "erp_rebalance":          erp_result,
        },
        "completed_at": _now_iso(),
    }

    log.info(
        "[BAW] Workflow complete — status=%s  incident=%s",
        summary["workflow_status"], incident_id,
    )

    # Optional callback — watsonx Orchestrate or a dashboard can listen here
    if BAW_CALLBACK_URL:
        try:
            requests.post(BAW_CALLBACK_URL, json=summary, timeout=5)
            log.info("[BAW] Callback posted to %s", BAW_CALLBACK_URL)
        except requests.RequestException as exc:
            log.warning("[BAW] Callback failed (non-blocking): %s", exc)

    return summary


# ─────────────────────────────────────────────────────────────────────────────
# CLI / standalone demo
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Simulate a PI-GNN critical prediction on Sensor-NH544-B (cloudburst scenario)
    demo_result = run_flood_response_workflow(
        sensor_node="Sensor-NH544-B",
        hazard_coefficient=3.75,   # 1.5 m depth × 2.5 m/s velocity
        delay_hours=4.0,
        affected_skus=["RICE-50KG-BAG", "PALM-OIL-15L", "BISCUIT-ASSORTED"],
    )

    print("\n" + "═" * 60)
    print("  WORKFLOW SUMMARY")
    print("═" * 60)
    print(json.dumps(demo_result, indent=2))
    sys.exit(0 if demo_result["workflow_status"] == "SUCCESS" else 1)
