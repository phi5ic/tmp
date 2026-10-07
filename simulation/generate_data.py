#!/usr/bin/env python3
"""
generate_qgis_data.py
─────────────────────
Reads the existing routes.geojson + routes.json produced by the PI-GNN
pipeline and emits a set of QGIS-ready GeoJSON files inside ./data/.

Each file is tagged with:
  • scenario_stage  (int 0-5  — mirrors the React demo stages)
  • stage_label     (str      — human-readable)
  • begin_time / end_time     — ISO-8601 strings for QGIS Temporal Controller
  • hazard_coefficient        — float m²/s
  • hazard_class              — "SAFE" | "WARNING" | "CRITICAL"
  • is_critical               — bool

Output files
────────────
  data/nh544_original.geojson   — NH544 route, all segments, per-stage hazard
  data/nh544_reroute.geojson    — PI-GNN reroute path (visible from stage 5)
  data/flood_basin.geojson      — Chalakudy Basin flood polygon (stage 2+)
  data/vehicles.geojson         — FMCG truck + fleeing vehicle point track
  data/sensor_nodes.geojson     — NH544-A and NH544-B sensor positions

Run from the repo root:
  python3 qgis-demo/generate_qgis_data.py
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE      = os.path.dirname(os.path.abspath(__file__))
OUT_DIR   = os.path.join(HERE, "data")
os.makedirs(OUT_DIR, exist_ok=True)

# Source GeoJSON files are bundled inside data/ for self-containment.
# If the original digital-twin-archived folder is still present the script
# can also be pointed there; the bundled copies are the canonical source.
GEOJSON   = os.path.join(OUT_DIR, "routes_source.geojson")
ROUTES_JS = os.path.join(OUT_DIR, "routes_coords.json")

# Fallback to archived digital-twin folder if bundled copies are missing
if not os.path.exists(GEOJSON):
    ROOT    = os.path.dirname(HERE)
    for candidate in ["digital-twin", "digital-twin-archived"]:
        p = os.path.join(ROOT, candidate, "public", "routes.geojson")
        if os.path.exists(p):
            GEOJSON = p
            break
if not os.path.exists(ROUTES_JS):
    ROOT    = os.path.dirname(HERE)
    for candidate in ["digital-twin", "digital-twin-archived"]:
        p = os.path.join(ROOT, candidate, "src", "routes.json")
        if os.path.exists(p):
            ROUTES_JS = p
            break

# ── PI-GNN inference (mirrors webhook_server.py exactly) ─────────────────────
# Try to import the real model; fall back to hard-coded deterministic values
# so this script runs even without PyTorch installed.
try:
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "pi-gnn"))
    import torch
    from core.model import PIGNN, calculate_hazard_coefficient, seed_and_train

    _model = PIGNN(node_features=4, hidden_dim=16, output_features=2)
    seed_and_train(_model)

    def run_inference(S0: float, n: float) -> tuple[float, bool]:
        x   = torch.tensor([[100.0, S0, n, 20.0]], dtype=torch.float32)
        adj = torch.tensor([[1.0]])
        with torch.no_grad():
            pred = _model(x, adj)
        d, v = pred[0, 0].item(), pred[0, 1].item()
        hazard, critical = calculate_hazard_coefficient(d, v)
        return round(hazard, 4), bool(critical)

    print("[generate] Using real PI-GNN model for inference.")

except ImportError:
    # Deterministic fallback — matches seed_and_train output exactly
    def run_inference(S0: float, n: float) -> tuple[float, bool]:  # type: ignore[misc]
        if n > 0.04:
            return 3.0800, True   # flood scenario  (S0=0.05, n=0.065)
        return 0.1100, False      # normal scenario (S0=0.01, n=0.015)

    print("[generate] PyTorch not available — using hard-coded PI-GNN values.")

# ── Demo scenario timeline ────────────────────────────────────────────────────
# Each stage maps to a 60-second window so judges can scrub slowly.
# T0 is an arbitrary fixed reference so the project is reproducible.
T0 = datetime(2026, 7, 15, 9, 0, 0, tzinfo=timezone.utc)

STAGES = [
    # (stage, label,               duration_s, S0,   n_rough, description)
    (0, "Pre-Event: Normal",        60,  0.010, 0.015, "Baseline — NH544 normal traffic, no flood signal"),
    (1, "Fleet En-Route",           60,  0.010, 0.015, "FMCG-01 truck moving along NH544, conditions nominal"),
    (2, "Cloudburst Detected",      60,  0.050, 0.065, "Unpredicted cloudburst — Manning n rises, depth/velocity spike"),
    (3, "Cellular Failure / VDTN",  60,  0.050, 0.065, "Infrastructure failure — nodes switch to VDTN offline mesh"),
    (4, "Hazard Confirmed Critical",60,  0.050, 0.065, "PI-GNN hazard coefficient 3.08 m²/s — CRITICAL threshold breached"),
    (5, "Reroute Executed",         120, 0.010, 0.015, "PI-GNN offline reroute manoeuvre complete — truck on safe path"),
]

def stage_window(stage_idx: int) -> tuple[datetime, datetime]:
    offset = sum(s[2] for s in STAGES[:stage_idx])
    t_start = T0 + timedelta(seconds=offset)
    t_end   = t_start + timedelta(seconds=STAGES[stage_idx][2])
    return t_start, t_end

def hazard_class(h: float) -> str:
    if h < 0.4:  return "SAFE"
    if h < 0.8:  return "WARNING"
    return "CRITICAL"

# ── Load source data ──────────────────────────────────────────────────────────
with open(GEOJSON) as f:
    source_gj = json.load(f)

with open(ROUTES_JS) as f:
    routes_js = json.load(f)

orig_features    = [ft for ft in source_gj["features"] if ft["properties"]["segment_id"].startswith("ORIG-SEG-")]
reroute_features = [ft for ft in source_gj["features"] if ft["properties"]["segment_id"].startswith("REROUTE-SEG-")]

ORIG_TOTAL    = len(orig_features)
REROUTE_TOTAL = len(reroute_features)

# Sensor coverage (mirrors webhook_server.py SENSOR_SEGMENT_MAP)
SENSOR_A_RANGE = (0,   206)   # approach zone
SENSOR_B_RANGE = (164, 618)   # flood zone

print(f"[generate] Loaded {ORIG_TOTAL} ORIG segments, {REROUTE_TOTAL} REROUTE segments.")

# ── 1. NH544 Original route ───────────────────────────────────────────────────
print("[generate] Building nh544_original.geojson …")
orig_out_features = []
for stage_idx, (stage, label, dur, S0, n, desc) in enumerate(STAGES):
    hazard, critical = run_inference(S0, n)
    t_start, t_end = stage_window(stage_idx)
    for ft in orig_features:
        seg_num = int(ft["properties"]["segment_id"].split("-")[-1])
        # Sensor B covers the flood zone — segments outside that range are safe
        # during flood stages (only the bridge corridor is affected)
        in_flood_zone = SENSOR_B_RANGE[0] <= seg_num <= SENSOR_B_RANGE[1]
        seg_hazard  = hazard  if (stage >= 2 and in_flood_zone) else round(hazard * 0.08, 4)
        seg_critical = seg_hazard > 0.8

        orig_out_features.append({
            "type": "Feature",
            "geometry": ft["geometry"],
            "properties": {
                "segment_id":        ft["properties"]["segment_id"],
                "scenario_stage":    stage,
                "stage_label":       label,
                "description":       desc,
                "begin_time":        t_start.isoformat(),
                "end_time":          t_end.isoformat(),
                "hazard_coefficient": seg_hazard,
                "hazard_class":      hazard_class(seg_hazard),
                "is_critical":       seg_critical,
                "manning_n":         n,
                "bed_slope_S0":      S0,
                "in_flood_zone":     in_flood_zone,
            }
        })

with open(os.path.join(OUT_DIR, "nh544_original.geojson"), "w") as f:
    json.dump({"type": "FeatureCollection", "features": orig_out_features}, f)
print(f"  → {len(orig_out_features)} features written.")

# ── 2. Reroute path ───────────────────────────────────────────────────────────
print("[generate] Building nh544_reroute.geojson …")
# Reroute only exists from stage 5 onward
reroute_out_features = []
stage_idx = 5
stage, label, dur, S0, n, desc = STAGES[stage_idx]
hazard, _ = run_inference(S0, n)
t_start, t_end = stage_window(stage_idx)
for ft in reroute_features:
    reroute_out_features.append({
        "type": "Feature",
        "geometry": ft["geometry"],
        "properties": {
            "segment_id":        ft["properties"]["segment_id"],
            "scenario_stage":    stage,
            "stage_label":       label,
            "description":       desc,
            "begin_time":        t_start.isoformat(),
            "end_time":          t_end.isoformat(),
            "hazard_coefficient": round(hazard * 0.05, 4),  # reroute is safe
            "hazard_class":      "SAFE",
            "is_critical":       False,
            "route_type":        "PI-GNN_REROUTE",
        }
    })

with open(os.path.join(OUT_DIR, "nh544_reroute.geojson"), "w") as f:
    json.dump({"type": "FeatureCollection", "features": reroute_out_features}, f)
print(f"  → {len(reroute_out_features)} features written.")

# ── 3. Flood Basin polygon ────────────────────────────────────────────────────
print("[generate] Building flood_basin.geojson …")
# Polygon ring — coords from App.jsx COORDS.basin (lat,lon) → GeoJSON (lon,lat)
BASIN_COORDS_LATLON = [
    [10.32, 76.32], [10.35, 76.35], [10.34, 76.38], [10.30, 76.40], [10.28, 76.35]
]
basin_ring = [[c[1], c[0]] for c in BASIN_COORDS_LATLON]
basin_ring.append(basin_ring[0])  # close ring

basin_features = []
for stage_idx, (stage, label, dur, S0, n, desc) in enumerate(STAGES):
    if stage < 2:
        continue   # basin polygon only visible from stage 2 onward
    t_start, t_end = stage_window(stage_idx)
    basin_features.append({
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [basin_ring]},
        "properties": {
            "name":           "Chalakudy Flood Basin",
            "scenario_stage": stage,
            "stage_label":    label,
            "description":    desc,
            "begin_time":     t_start.isoformat(),
            "end_time":       t_end.isoformat(),
        }
    })

with open(os.path.join(OUT_DIR, "flood_basin.geojson"), "w") as f:
    json.dump({"type": "FeatureCollection", "features": basin_features}, f)
print(f"  → {len(basin_features)} features written.")

# ── 4. Vehicle track points ───────────────────────────────────────────────────
print("[generate] Building vehicles.geojson …")
orig_coords  = routes_js["original"]   # [[lat, lon], …]
reroute_coords = routes_js["reroute"]

# Sample ~20 evenly-spaced positions per stage per vehicle for a readable track
def sample_coords(coords, start_frac, end_frac, n_pts=20):
    total = len(coords)
    start_i = int(total * start_frac)
    end_i   = int(total * end_frac)
    indices = [start_i + int((end_i - start_i) * k / (n_pts - 1)) for k in range(n_pts)]
    return [coords[min(i, total-1)] for i in indices]

vehicle_features = []

# FMCG Truck — stages 0–4 on original route, stage 5 on reroute
truck_stage_positions = {
    0: sample_coords(orig_coords, 0.0,  0.05),
    1: sample_coords(orig_coords, 0.0,  0.23),
    2: sample_coords(orig_coords, 0.05, 0.23),
    3: sample_coords(orig_coords, 0.10, 0.23),
    4: sample_coords(orig_coords, 0.15, 0.23),
    5: sample_coords(reroute_coords, 0.0, 1.0),
}

for stage_idx, (stage, label, dur, S0, n, desc) in enumerate(STAGES):
    t_start, t_end  = stage_window(stage_idx)
    positions = truck_stage_positions[stage]
    n_pts = len(positions)
    for k, pos in enumerate(positions):
        frac = k / max(n_pts - 1, 1)
        pt_time = t_start + timedelta(seconds=dur * frac)
        vehicle_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [pos[1], pos[0]]},
            "properties": {
                "vehicle_id":     "FMCG-Truck-01",
                "vehicle_type":   "FMCG Logistics Truck",
                "network_mode":   "VDTN" if stage == 3 else "LTE/5G",
                "scenario_stage": stage,
                "stage_label":    label,
                "begin_time":     pt_time.isoformat(),
                "end_time":      (pt_time + timedelta(seconds=dur/n_pts)).isoformat(),
            }
        })

# Fleeing Vehicle — stages 2–4 on original route (coming from flood zone)
fleeing_stage_positions = {
    2: sample_coords(orig_coords, 0.28, 0.50),
    3: sample_coords(orig_coords, 0.28, 0.45),
    4: sample_coords(orig_coords, 0.28, 0.40),
}
for stage_idx, (stage, label, dur, S0, n, desc) in enumerate(STAGES):
    if stage not in fleeing_stage_positions:
        continue
    t_start, t_end = stage_window(stage_idx)
    positions = fleeing_stage_positions[stage]
    n_pts = len(positions)
    for k, pos in enumerate(positions):
        frac = k / max(n_pts - 1, 1)
        pt_time = t_start + timedelta(seconds=dur * frac)
        vehicle_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [pos[1], pos[0]]},
            "properties": {
                "vehicle_id":     "Fleeing-Vehicle-02",
                "vehicle_type":   "Civilian Vehicle (Fleeing)",
                "network_mode":   "VDTN" if stage >= 3 else "LTE/5G",
                "scenario_stage": stage,
                "stage_label":    label,
                "begin_time":     pt_time.isoformat(),
                "end_time":      (pt_time + timedelta(seconds=dur/n_pts)).isoformat(),
            }
        })

with open(os.path.join(OUT_DIR, "vehicles.geojson"), "w") as f:
    json.dump({"type": "FeatureCollection", "features": vehicle_features}, f)
print(f"  → {len(vehicle_features)} features written.")

# ── 5. Sensor node positions ──────────────────────────────────────────────────
print("[generate] Building sensor_nodes.geojson …")
# Sensor positions: midpoint of their respective segment ranges
def seg_midpoint(features, idx):
    ft = features[idx]
    coords = ft["geometry"]["coordinates"]
    mid = coords[len(coords)//2]
    return mid  # [lon, lat]

sensor_a_mid = seg_midpoint(orig_features, (SENSOR_A_RANGE[0] + SENSOR_A_RANGE[1]) // 2)
sensor_b_mid = seg_midpoint(orig_features, (SENSOR_B_RANGE[0] + SENSOR_B_RANGE[1]) // 2)

sensor_features = []
for stage_idx, (stage, label, dur, S0, n, desc) in enumerate(STAGES):
    t_start, t_end = stage_window(stage_idx)
    hazard, critical = run_inference(S0, n)
    for sensor_id, pos, seg_range in [
        ("Sensor-NH544-A", sensor_a_mid, SENSOR_A_RANGE),
        ("Sensor-NH544-B", sensor_b_mid, SENSOR_B_RANGE),
    ]:
        active = stage >= 2
        h = hazard if (active and sensor_id == "Sensor-NH544-B") else round(hazard * 0.08, 4)
        sensor_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": pos},
            "properties": {
                "sensor_id":          sensor_id,
                "segment_range":      f"ORIG-SEG-{seg_range[0]} → ORIG-SEG-{seg_range[1]}",
                "scenario_stage":     stage,
                "stage_label":        label,
                "begin_time":         t_start.isoformat(),
                "end_time":           t_end.isoformat(),
                "hazard_coefficient": h,
                "hazard_class":       hazard_class(h),
                "manning_n":          n,
                "bed_slope_S0":       S0,
                "status":             "ACTIVE" if active else "MONITORING",
            }
        })

with open(os.path.join(OUT_DIR, "sensor_nodes.geojson"), "w") as f:
    json.dump({"type": "FeatureCollection", "features": sensor_features}, f)
print(f"  → {len(sensor_features)} features written.")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("✅ All QGIS data files written to:", OUT_DIR)
print()
print("Temporal range:")
t_first, _ = stage_window(0)
_, t_last   = stage_window(len(STAGES) - 1)
print(f"  Start : {t_first.isoformat()}")
print(f"  End   : {t_last.isoformat()}")
print()
print("PI-GNN inference results (for verification):")
for S0, n, label in [(0.010, 0.015, "Normal  "), (0.050, 0.065, "Flood   ")]:
    h, c = run_inference(S0, n)
    print(f"  {label} S0={S0} n={n}  →  hazard={h:.4f} m²/s  critical={c}")
print()
print("Next step: open QGIS and run  qgis-demo/build_qgis_project.py  in the Python console.")
