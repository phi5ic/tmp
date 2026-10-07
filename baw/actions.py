import json
import logging
import uuid
from typing import Optional
import requests

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_FROM_NUMBER,
    ERP_BASE_URL,
    ERP_API_KEY,
    ELEVATED_REST_AREA,
    DEMO_MODE,
)
from utils import now_iso, eta_iso

log = logging.getLogger("BAW-Actions")

# ─────────────────────────────────────────────────────────────────────────────
# Step 1: SMS Dispatch via Twilio
# ─────────────────────────────────────────────────────────────────────────────
def dispatch_driver_sms(
    incident_id: str,
    sensor_node: str,
    hazard_coefficient: float,
    phone_numbers: list[str],
) -> list[dict]:
    message_body = (
        f"[FLOOD ALERT — {incident_id}] "
        f"NH544 route SEVERED near {sensor_node}. "
        f"Hazard={hazard_coefficient:.2f} m²/s (threshold: 0.80). "
        f"HALT IMMEDIATELY at nearest elevated rest area: {ELEVATED_REST_AREA}. "
        f"Await further instructions. Do NOT proceed. — HydroMesh AutoBAW"
    )

    results = []

    if DEMO_MODE or not phone_numbers:
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
    payload = {
        "incident_id":          incident_id,
        "event_type":           "route_severed_flash_flood",
        "timestamp":            now_iso(),
        "affected_route":       "NH544-Chalakudy-Basin",
        "sensor_node":          sensor_node,
        "hazard_coefficient":   hazard_coefficient,
        "status":               "SEVERED",
        "delay_hours":          delay_hours,
        "estimated_resume_eta": eta_iso(delay_hours),
        "fallback_action":      "Inventory rebalance initiated via Cochin_Hub_02",
        "source":               "HydroMesh-BAW-AutoDispatch",
    }

    results = []

    if DEMO_MODE or not webhook_urls:
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
        "timestamp":         now_iso(),
        "source":            "HydroMesh-BAW-AutoDispatch",
    }

    if DEMO_MODE:
        log.info("[Step 3 / DEMO] ERP rebalance payload:\n%s", json.dumps(erp_payload, indent=2))
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
