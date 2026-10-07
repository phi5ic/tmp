"""
baw_flood_response.py
──────────────────────
Autonomous Business Automation Workflow (BAW)

Triggered when the PI-GNN predicts that the NH544 route is severed by a flash
flood (hazard coefficient > 0.8 m²/s). Executes ALL three response actions
below with zero human intervention:

  Step 1 — SMS Dispatch
  Step 2 — Warehouse ETA Notification
  Step 3 — ERP Inventory Recalculation
"""

import json
import logging
from typing import Optional
import requests

from .config import DRIVER_PHONE_NUMBERS, WAREHOUSE_WEBHOOK_URLS, BAW_CALLBACK_URL
from .utils import generate_incident_id, now_iso
from .actions import dispatch_driver_sms, notify_warehouses, trigger_erp_rebalance

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
log = logging.getLogger("BAW-FloodResponse")

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
    incident_id = generate_incident_id(sensor_node)

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
        "completed_at": now_iso(),
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
