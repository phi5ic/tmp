# Hydro-Kinematic Logistics Mesh — QGIS Demo

> **Verifiable GIS demonstration** of the PI-GNN flood-hazard rerouting system  
> on NH544 (Chalakudy, Kerala). Everything runs locally in QGIS — no browser,  
> no web server, no dependencies beyond QGIS itself.

---

## What you are looking at

| Layer | Description |
|---|---|
| **NH544 Original Route** | 824 road segments coloured by PI-GNN hazard coefficient per scenario stage |
| **PI-GNN Reroute Path** | 1 275 segments of the computed safe alternate route (visible from Stage 5) |
| **Chalakudy Flood Basin** | Polygon marking the cloudburst inundation area (visible from Stage 2) |
| **Sensor Nodes** | NH544-A (approach) and NH544-B (flood zone) — diamond markers coloured by hazard class |
| **Vehicle Track** | FMCG Truck + Fleeing Vehicle point positions throughout the scenario |
| **CartoCDN Dark Matter** | XYZ basemap (requires internet; replaceable with any OSM tile layer) |

---

## Colour legend

| Colour | Meaning | Hazard threshold |
|---|---|---|
| 🔵 Cyan `#00F0FF` | **SAFE** | < 0.4 m²/s |
| 🟡 Amber `#FFAA00` | **WARNING** | 0.4 – 0.8 m²/s |
| 🔴 Red `#FF3366` | **CRITICAL** | ≥ 0.8 m²/s |
| 🟢 Dashed green `#00FF9D` | PI-GNN reroute (safe) | — |

---

## Scenario stages

| Stage | Time window | Event |
|---|---|---|
| **0** | 09:00 – 09:01 | Pre-event: normal traffic, hazard = 0.11 m²/s (SAFE) |
| **1** | 09:01 – 09:02 | FMCG-01 truck en route via NH544 |
| **2** | 09:02 – 09:03 | Cloudburst detected — Manning's n → 0.065, hazard spikes to **3.03 m²/s** |
| **3** | 09:03 – 09:04 | Cellular infrastructure failure — nodes switch to **VDTN offline mesh** |
| **4** | 09:04 – 09:05 | Hazard confirmed CRITICAL via VDTN peer handshake |
| **5** | 09:05 – 09:07 | PI-GNN executes offline reroute — green dashed path appears, original dims red |

All hazard values are produced by the **real PI-GNN model** (`pi-gnn/model.py`) at  
data-generation time and stored verbatim in the GeoJSON `hazard_coefficient` field.

---

## Quick start (pre-built project)

If `hydro_kinematic_demo.qgz` already exists in this folder:

1. Open QGIS 3.28 or newer
2. **File → Open Project** → select `hydro_kinematic_demo.qgz`
3. Open **View → Panels → Temporal Controller**
4. Press **▶ Play** and watch the scenario animate
5. Scrub the slider to any stage; click any road segment and open  
   **View → Identify Results** to inspect `hazard_coefficient`, `hazard_class`, `manning_n`

---

## Building the project from scratch

### Step 1 — Generate the data files

Run from the **repo root** (requires Python 3.10+ and optionally PyTorch):

```bash
python3 qgis-demo/generate_qgis_data.py
```

This reads `digital-twin/public/routes.geojson` and `digital-twin/src/routes.json`,  
runs PI-GNN inference for each scenario stage, and writes five GeoJSON files to `qgis-demo/data/`:

```
qgis-demo/data/
  nh544_original.geojson   — 4 944 features  (824 segments × 6 stages)
  nh544_reroute.geojson    — 1 275 features  (reroute segments, stage 5 only)
  flood_basin.geojson      —     4 features  (basin polygon, stages 2–5)
  vehicles.geojson         —   180 features  (vehicle track points)
  sensor_nodes.geojson     —    12 features  (2 sensors × 6 stages)
```

Expected output (verification):
```
PI-GNN inference results:
  Normal   S0=0.01 n=0.015  →  hazard=0.1114 m²/s  critical=False
  Flood    S0=0.05 n=0.065  →  hazard=3.0329 m²/s  critical=True
```

### Step 2 — Build the QGIS project

1. Open **QGIS 3.28+**
2. Go to **Plugins → Python Console**
3. Click the **Show Editor** button (pencil icon)
4. Click **Open Script** and open `qgis-demo/build_qgis_project.py`
5. Click **Run Script** (green ▶ triangle)
6. The project is saved as `qgis-demo/hydro_kinematic_demo.qgz`

### Step 3 — Apply styles manually (optional fallback)

If the PyQGIS script isn't available, you can apply styles by hand:

1. Right-click each layer → **Properties → Symbology**
2. Click **Load Style…** at the bottom → load the matching `.qml` from `qgis-demo/styles/`

---

## Verifying the PI-GNN output

Everything in the GeoJSON properties is auditable:

```bash
# Check that CRITICAL segments are only in the Sensor-NH544-B flood zone
python3 -c "
import json
with open('qgis-demo/data/nh544_original.geojson') as f:
    gj = json.load(f)
critical = [
    f['properties'] for f in gj['features']
    if f['properties']['is_critical']
]
print(f'Critical segments: {len(critical)}')
print('Sample:', critical[0])
"
```

```bash
# Confirm reroute path is always SAFE
python3 -c "
import json
with open('qgis-demo/data/nh544_reroute.geojson') as f:
    gj = json.load(f)
not_safe = [f for f in gj['features'] if f['properties']['hazard_class'] != 'SAFE']
print('Unsafe reroute segments:', len(not_safe))  # should be 0
"
```

---

## File structure

```
qgis-demo/
  generate_qgis_data.py      ← run this first (standalone Python)
  build_qgis_project.py      ← run inside QGIS Python Console
  hydro_kinematic_demo.qgz   ← pre-built project (if generated)
  DEMO_GUIDE.md              ← this file
  data/
    nh544_original.geojson
    nh544_reroute.geojson
    flood_basin.geojson
    vehicles.geojson
    sensor_nodes.geojson
  styles/
    nh544_original.qml
    nh544_reroute.qml
    flood_basin.qml
    vehicles.qml
    sensor_nodes.qml

pi-gnn/
  model.py                   ← PI-GNN model (PyTorch) — source of truth for hazard values
  webhook_server.py          ← IBM Code Engine entry point (Flask SSE server)
  vdtn_simulation.py         ← VDTN offline mesh simulation
```

---

## Tip — no internet / offline basemap

If the CartoCDN basemap fails, add a local OSM tile layer:

1. **Layer → Add Layer → Add XYZ Layer**
2. URL: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
3. Name: `OpenStreetMap`

Or load any raster / TIFF you have for the Kerala area.
