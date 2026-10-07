#!/usr/bin/env python3
"""
sensor_emitter.py
─────────────────
Synthetic telemetry emitter for the Hydro-Kinematic real-time demo.

Drives the PI-GNN webhook server (or writes GeoJSON directly as a fallback)
by POSTing sensor readings that replay the 6-stage flood scenario at
wall-clock speed.

Usage
─────
  # Standard — requires webhook_server.py to be running on localhost:8080
  python3 qgis-demo/sensor_emitter.py

  # Offline fallback — writes updated GeoJSON files directly, no Flask needed
  python3 qgis-demo/sensor_emitter.py --offline

  # Custom server / interval
  python3 qgis-demo/sensor_emitter.py --server http://localhost:8080 --interval 3

Scenario timeline (mirrors generate_qgis_data.py STAGES)
─────────────────────────────────────────────────────────
  Stage 0 — Pre-Event: Normal          (15 s)  S0=0.010, n=0.015
  Stage 1 — Fleet En-Route             (15 s)  S0=0.010, n=0.015
  Stage 2 — Cloudburst Detected        (15 s)  S0=0.050, n=0.065  ← hazard spikes
  Stage 3 — Cellular Failure / VDTN   (15 s)  S0=0.050, n=0.065
  Stage 4 — Hazard Confirmed Critical  (15 s)  S0=0.050, n=0.065
  Stage 5 — Reroute Executed           (30 s)  S0=0.010, n=0.015  ← hazard drops

Each stage emits one telemetry reading per --interval seconds (default 3 s).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# ── Scenario stages ───────────────────────────────────────────────────────────
# (stage, label, duration_s, S0, n_rough, network_mode)
STAGES = [
    (0, "Pre-Event: Normal",         15,  0.010, 0.015, "LTE/5G"),
    (1, "Fleet En-Route",            15,  0.010, 0.015, "LTE/5G"),
    (2, "Cloudburst Detected",       15,  0.050, 0.065, "LTE/5G"),
    (3, "Cellular Failure / VDTN",   15,  0.050, 0.065, "VDTN"),
    (4, "Hazard Confirmed Critical",  15,  0.050, 0.065, "VDTN"),
    (5, "Reroute Executed",          30,  0.010, 0.015, "LTE/5G"),
]

# Sensor nodes — both are always emitting; B is in the flood zone
SENSOR_NODES = [
    {"id": "Sensor-NH544-A", "zone": "approach",   "depth_normal": 0.20, "vel_normal": 0.50,
     "depth_flood": 0.35, "vel_flood": 0.70},
    {"id": "Sensor-NH544-B", "zone": "flood_zone", "depth_normal": 0.20, "vel_normal": 0.50,
     "depth_flood": 1.40, "vel_flood": 2.20},
]

# ── Hazard helpers (mirrors webhook_server.py) ─────────────────────────────────
def hazard_class(h: float) -> str:
    if h < 0.4:  return "SAFE"
    if h < 0.8:  return "WARNING"
    return "CRITICAL"

def calculate_hazard(depth: float, velocity: float) -> tuple[float, bool]:
    h = depth * velocity
    return round(h, 4), h > 0.8

# ── Sensor segment coverage (mirrors webhook_server.py SENSOR_SEGMENT_MAP) ────
SENSOR_SEGMENT_MAP = {
    "Sensor-NH544-A": (0,   206),
    "Sensor-NH544-B": (164, 618),
}

# ── Offline fallback: write updated GeoJSON directly ──────────────────────────

def _load_sensor_template() -> list[dict]:
    """Load the last-written sensor_nodes.geojson as a feature template."""
    path = os.path.join(DATA_DIR, "sensor_nodes.geojson")
    if os.path.exists(path):
        with open(path) as f:
            gj = json.load(f)
        # Return only the first occurrence of each sensor (stage-0 features)
        seen = set()
        features = []
        for ft in gj["features"]:
            sid = ft["properties"]["sensor_id"]
            if sid not in seen:
                seen.add(sid)
                features.append(ft)
        return features
    # Minimal fallback geometry if data/ hasn't been generated yet
    return [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [76.3900, 10.3100]},
         "properties": {"sensor_id": "Sensor-NH544-A"}},
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [76.3700, 10.3050]},
         "properties": {"sensor_id": "Sensor-NH544-B"}},
    ]


def write_offline_update(stage: int, label: str, network_mode: str,
                         readings: list[dict]) -> None:
    """
    Offline fallback: overwrite sensor_nodes.geojson with current readings.
    QGIS realtime_file_bridge.py watches this file and reloads the layer.
    """
    templates = _load_sensor_template()
    now = datetime.now(timezone.utc).isoformat()

    features = []
    for tmpl in templates:
        sid = tmpl["properties"]["sensor_id"]
        reading = next((r for r in readings if r["node_id"] == sid), None)
        if reading is None:
            continue
        h, critical = calculate_hazard(reading["depth"], reading["velocity"])
        features.append({
            "type": "Feature",
            "geometry": tmpl["geometry"],
            "properties": {
                "sensor_id":          sid,
                "scenario_stage":     stage,
                "stage_label":        label,
                "network_mode":       network_mode,
                "timestamp":          now,
                "hazard_coefficient": h,
                "hazard_class":       hazard_class(h),
                "is_critical":        critical,
                "manning_n":          reading["n"],
                "bed_slope_S0":       reading["S0"],
                "depth":              reading["depth"],
                "velocity":           reading["velocity"],
                "status":             "ACTIVE" if stage >= 2 else "MONITORING",
                # Level 1 bridge: always set begin/end to now so the Temporal
                # Controller (if enabled) shows this as the current feature.
                "begin_time":         now,
                "end_time":           now,
            }
        })

    out = {"type": "FeatureCollection", "features": features,
           "_realtime": True, "_last_update": now}
    path = os.path.join(DATA_DIR, "sensor_nodes.geojson")
    with open(path, "w") as f:
        json.dump(out, f, indent=2)


# ── Main emitter loop ─────────────────────────────────────────────────────────

def run(server: str, interval: float, offline: bool, loop: bool) -> None:
    infer_url = f"{server.rstrip('/')}/infer"
    health_url = f"{server.rstrip('/')}/health"

    # Auto-detect offline mode if the server isn't reachable
    if not offline:
        try:
            r = requests.get(health_url, timeout=2)
            if r.status_code != 200:
                raise ConnectionError(f"status {r.status_code}")
            print(f"[emitter] ✓ Server reachable at {server}")
        except Exception as exc:
            print(f"[emitter] ⚠  Server not reachable ({exc}) — falling back to offline file mode.")
            offline = True

    if offline:
        print("[emitter] Running in OFFLINE mode → writing sensor_nodes.geojson directly.")
        print(f"          QGIS: open realtime_file_bridge.py in the Python Console.")
    else:
        print("[emitter] Running in LIVE mode → POST to /infer, events pushed via /stream SSE.")
        print(f"          QGIS: open realtime_qgis_plugin.py in the Python Console.")

    print()

    iteration = 0
    while True:
        iteration += 1
        print(f"{'─'*60}")
        print(f"[emitter] ▶ Run #{iteration}  ({len(STAGES)} stages, {interval:.0f}s interval)")
        print()

        for stage, label, duration_s, S0, n_rough, network_mode in STAGES:
            ticks = max(1, int(duration_s / interval))
            print(f"  Stage {stage}: {label}  [{network_mode}]  ({ticks} readings × {interval}s)")

            for tick in range(ticks):
                # Build readings for both sensors
                readings = []
                for sensor in SENSOR_NODES:
                    is_flood = (S0 > 0.03)
                    if is_flood and sensor["zone"] == "flood_zone":
                        depth = sensor["depth_flood"]
                        vel   = sensor["vel_flood"]
                    else:
                        depth = sensor["depth_normal"]
                        vel   = sensor["vel_normal"]

                    readings.append({
                        "node_id":  sensor["id"],
                        "depth":    depth,
                        "velocity": vel,
                        "S0":       S0,
                        "n":        n_rough,
                    })

                if offline:
                    write_offline_update(stage, label, network_mode, readings)
                    for r in readings:
                        h, crit = calculate_hazard(r["depth"], r["velocity"])
                        flag = " ⚠  CRITICAL" if crit else ""
                        print(f"    [{r['node_id']}]  hazard={h:.4f} m²/s  {hazard_class(h)}{flag}")
                else:
                    for r in readings:
                        payload = {
                            "node_id":   r["node_id"],
                            "timestamp": time.time(),
                            "metrics": {
                                "depth":    r["depth"],
                                "velocity": r["velocity"],
                                "S0":       r["S0"],
                                "n":        r["n"],
                            },
                        }
                        try:
                            resp = requests.post(infer_url, json=payload, timeout=5)
                            if resp.status_code == 200:
                                result = resp.json()
                                h = result.get("hazard_coefficient", 0)
                                crit = result.get("is_critical", False)
                                flag = " ⚠  CRITICAL" if crit else ""
                                print(f"    [{r['node_id']}]  hazard={h:.4f} m²/s  {hazard_class(h)}{flag}")
                            else:
                                print(f"    [{r['node_id']}]  server error {resp.status_code}")
                        except requests.exceptions.RequestException as exc:
                            print(f"    [{r['node_id']}]  POST failed: {exc} — switching to offline")
                            offline = True
                            write_offline_update(stage, label, network_mode, readings)

                time.sleep(interval)

        print()
        if not loop:
            break
        print(f"[emitter] ↺  Scenario complete — looping (Ctrl-C to stop)\n")

    print("[emitter] ✅ Done.")


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Synthetic telemetry emitter for the Hydro-Kinematic real-time demo."
    )
    parser.add_argument(
        "--server", default="http://localhost:8080",
        help="Webhook server base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--interval", type=float, default=3.0,
        help="Seconds between readings within each stage (default: 3)"
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="Skip the server entirely — write GeoJSON files directly"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="Run the scenario once and exit (default: loop continuously)"
    )
    args = parser.parse_args()

    try:
        run(
            server=args.server,
            interval=args.interval,
            offline=args.offline,
            loop=not args.once,
        )
    except KeyboardInterrupt:
        print("\n[emitter] Stopped.")
        sys.exit(0)
