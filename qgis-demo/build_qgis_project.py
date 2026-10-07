"""
build_qgis_project.py
─────────────────────
PyQGIS script — run this inside the QGIS Python Console
(Plugins → Python Console → open editor → paste → Run).

What it does:
  1. Loads all 5 GeoJSON data files as vector layers
  2. Applies the QML styles from the styles/ folder
  3. Configures Temporal Controller on every layer
     (begin_time / end_time ISO-8601 fields)
  4. Adds a CartoCDN Dark-Matter XYZ basemap
  5. Sets the map canvas to the NH544 extent
  6. Saves the project as  hydro_kinematic_demo.qgz

Usage
─────
  1. Open QGIS 3.28+
  2. Go to  Plugins → Python Console
  3. Click the "Show Editor" button (pencil icon)
  4. Open (or paste) this file
  5. Click  Run Script  (green triangle)
  6. The project is saved as  qgis-demo/hydro_kinematic_demo.qgz

Requirements
────────────
  • QGIS 3.28 or newer (for stable Temporal Controller API)
  • Run  generate_qgis_data.py  first to create data/ files
"""

import os
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsCoordinateReferenceSystem,
    QgsRectangle,
    QgsVectorLayerTemporalProperties,
    QgsDateTimeRange,
)
from qgis.PyQt.QtCore import QDateTime, Qt

# ── Resolve paths relative to THIS file ──────────────────────────────────────
HERE      = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(HERE, "data")
STYLE_DIR = os.path.join(HERE, "styles")
PROJECT_PATH = os.path.join(HERE, "hydro_kinematic_demo.qgz")

def data(name):
    return os.path.join(DATA_DIR, name)

def style(name):
    return os.path.join(STYLE_DIR, name)

# ── Layer definitions ─────────────────────────────────────────────────────────
# (geojson_file, layer_name, qml_file, draw_order_bottom_to_top)
LAYER_DEFS = [
    # Bottom → top
    ("nh544_original.geojson", "NH544 Original Route",    "nh544_original.qml"),
    ("nh544_reroute.geojson",  "PI-GNN Reroute Path",     "nh544_reroute.qml"),
    ("flood_basin.geojson",    "Chalakudy Flood Basin",   "flood_basin.qml"),
    ("sensor_nodes.geojson",   "Sensor Nodes (NH544)",    "sensor_nodes.qml"),
    ("vehicles.geojson",       "Vehicle Track",           "vehicles.qml"),
]

# ── Temporal Controller field names (must match generate_qgis_data.py) ────────
BEGIN_FIELD = "begin_time"
END_FIELD   = "end_time"

# ── Project CRS ───────────────────────────────────────────────────────────────
WGS84 = QgsCoordinateReferenceSystem("EPSG:4326")

# ─────────────────────────────────────────────────────────────────────────────
print("[build] Starting QGIS project build …")

project = QgsProject.instance()
project.clear()
project.setCrs(WGS84)
project.setTitle("Hydro-Kinematic Logistics Mesh — NH544 Flood Scenario")

# ── 1. XYZ Basemap (ESRI World Imagery — satellite) ──────────────────────────
basemap_url = (
    "type=xyz"
    "&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    "&zmax=19&zmin=0"
)
basemap = QgsRasterLayer(basemap_url, "ESRI World Imagery (Satellite)", "wms")
if basemap.isValid():
    project.addMapLayer(basemap)
    print("[build] ✓ ESRI satellite basemap added.")
else:
    print("[build] ✗ Basemap failed to load — check your internet connection.")
    print("          You can add it manually: Layer → Add XYZ Tile Layer")
    print("          URL: https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}")

# ── 2. Vector layers ──────────────────────────────────────────────────────────
loaded_layers = []
for geojson, name, qml in LAYER_DEFS:
    path = data(geojson)
    if not os.path.exists(path):
        print(f"[build] ✗ Missing data file: {path}")
        print(f"          Run  generate_qgis_data.py  first.")
        continue

    lyr = QgsVectorLayer(path, name, "ogr")
    if not lyr.isValid():
        print(f"[build] ✗ Failed to load layer: {name}")
        continue

    # Apply QML style
    qml_path = style(qml)
    if os.path.exists(qml_path):
        lyr.loadNamedStyle(qml_path)
        lyr.triggerRepaint()

    # ── Temporal Controller configuration ────────────────────────────────────
    tp = lyr.temporalProperties()
    tp.setIsActive(True)
    tp.setMode(QgsVectorLayerTemporalProperties.ModeFeatureDateTimeStartAndEndFromFields)
    tp.setStartField(BEGIN_FIELD)
    tp.setEndField(END_FIELD)

    project.addMapLayer(lyr)
    loaded_layers.append(lyr)
    print(f"[build] ✓ Layer loaded: {name}  ({lyr.featureCount()} features)")

if not loaded_layers:
    print("[build] ✗ No layers loaded — aborting.")
    raise SystemExit(1)

# ── 3. Map extent — NH544 corridor ────────────────────────────────────────────
# Lon 76.31–76.50, Lat 10.23–10.38  (generous padding around the route)
extent = QgsRectangle(76.31, 10.23, 76.50, 10.38)
iface.mapCanvas().setExtent(extent)
iface.mapCanvas().refresh()

# ── 4. Temporal Controller — set full animation range ─────────────────────────
# Range matches the output of generate_qgis_data.py:
#   2026-07-15T09:00:00Z  →  2026-07-15T09:07:00Z  (420 seconds)
# Qt6 moved date/time format enums into Qt.DateFormat namespace.
tc = iface.mapCanvas().temporalController()
_ISO = getattr(Qt, "ISODate", None) or getattr(Qt.DateFormat, "ISODate", None)
t_start = QDateTime.fromString("2026-07-15T09:00:00", "yyyy-MM-ddTHH:mm:ss")
t_end   = QDateTime.fromString("2026-07-15T09:07:00", "yyyy-MM-ddTHH:mm:ss")
t_start.setTimeSpec(Qt.UTC if hasattr(Qt, "UTC") else Qt.TimeSpec.UTC)
t_end.setTimeSpec(Qt.UTC if hasattr(Qt, "UTC") else Qt.TimeSpec.UTC)
tc.setTemporalExtents(QgsDateTimeRange(t_start, t_end))
tc.setFrameDuration(
    # Each "frame" = 5 seconds → 84 frames total for smooth scrubbing
    QgsInterval(5, QgsUnitTypes.TemporalSeconds)
    if hasattr(QgsUnitTypes, "TemporalSeconds")
    else QgsInterval(5)   # QGIS 3.34+ simplified constructor
)
tc.setNavigationMode(QgsTemporalNavigationObject.Animated)
print("[build] ✓ Temporal Controller configured (09:00 → 09:07 UTC, 5 s frames).")

# ── 5. Print layer order reminder ────────────────────────────────────────────
print()
print("[build] Layer order (top → bottom in Layers panel):")
for lyr in reversed(loaded_layers):
    print(f"         • {lyr.name()}")
print()

# ── 6. Save project ───────────────────────────────────────────────────────────
project.write(PROJECT_PATH)
print(f"[build] ✅ Project saved → {PROJECT_PATH}")
print()
print("DEMO STEPS:")
print("  1. Open the Temporal Controller panel  (View → Panels → Temporal Controller)")
print("  2. Press ▶ Play — it will animate through the 6 scenario stages")
print("  3. Scrub the slider manually to jump to any stage")
print("  4. Click any road segment → open Identify Results → see hazard_coefficient")
print("  5. Zoom to the NH544-B flood zone to see CRITICAL red segments at stage 2-4")
print("  6. At stage 5 the green dashed reroute appears; original route dims to red")
