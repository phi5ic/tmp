"""
realtime_qgis_plugin.py  —  Level 2: SSE stream → in-memory QGIS layers
─────────────────────────────────────────────────────────────────────────
Run this inside the QGIS Python Console:
  Plugins → Python Console → Show Editor → open file → Run Script

What it does
────────────
1. Creates two in-memory vector layers (sensor nodes + road segments) inside
   QGIS — no files on disk are touched at runtime.
2. Opens a persistent HTTP connection to the /stream SSE endpoint on the
   webhook server (default: http://localhost:8080/stream).
3. A background daemon thread reads SSE events from the stream and pushes
   HAZARD_UPDATE payloads into a thread-safe queue.
4. A QTimer fires every 250 ms on the QGIS main thread, drains the queue,
   and applies the updates:
     • Sensor node features  → hazard_coefficient, hazard_class, is_critical
     • Road segment features → hazard_coefficient, hazard_class (colour)
5. Canvas repaints immediately after each batch of updates.

Requirements
────────────
  • webhook_server.py running on localhost:8080  (or set SERVER_URL below)
  • sensor_emitter.py running to drive the scenario
  • QGIS 3.28+  (for stable QgsMemoryProviderUtils API)

To stop the stream cleanly:
  In the QGIS Python Console run:  stop_realtime_stream()
"""

import json
import queue
import threading

import requests
from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsField,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsCoordinateReferenceSystem,
    QgsSymbol,
    QgsRuleBasedRenderer,
    QgsRasterLayer,
)
from qgis.PyQt.QtCore import QTimer, QVariant
from qgis.PyQt.QtGui import QColor

# ── Configuration ─────────────────────────────────────────────────────────────
SERVER_URL      = "http://localhost:8080"
POLL_INTERVAL_MS = 250   # how often the QTimer drains the queue (milliseconds)

# Colour scheme (matches static demo QML styles)
COLOUR_SAFE     = QColor("#00F0FF")  # cyan
COLOUR_WARNING  = QColor("#FFAA00")  # amber
COLOUR_CRITICAL = QColor("#FF3366")  # red
COLOUR_UNKNOWN  = QColor("#888888")  # grey (no data yet)

# Sensor node fixed positions (lon, lat) — matches generate_qgis_data.py
SENSOR_POSITIONS = {
    "Sensor-NH544-A": (76.3900, 10.3100),
    "Sensor-NH544-B": (76.3700, 10.3050),
}

# Sensor → road segment index range (mirrors webhook_server.py)
SENSOR_SEGMENT_MAP = {
    "Sensor-NH544-A": (0,   206),
    "Sensor-NH544-B": (164, 618),
}

# ── Shared state ──────────────────────────────────────────────────────────────
_event_queue: queue.Queue = queue.Queue()
_stop_flag    = threading.Event()
_timer        = None   # QTimer — kept in module scope to prevent GC
_stream_thread = None


# ─────────────────────────────────────────────────────────────────────────────
# Layer creation helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_sensor_layer() -> QgsVectorLayer:
    """Create an in-memory Point layer for the two NH544 sensor nodes."""
    uri = "Point?crs=EPSG:4326"
    lyr = QgsVectorLayer(uri, "🔴 Sensor Nodes (Live)", "memory")
    pr  = lyr.dataProvider()
    pr.addAttributes([
        QgsField("sensor_id",          QVariant.String),
        QgsField("hazard_coefficient", QVariant.Double),
        QgsField("hazard_class",       QVariant.String),
        QgsField("is_critical",        QVariant.Bool),
        QgsField("stage_label",        QVariant.String),
        QgsField("network_mode",       QVariant.String),
        QgsField("last_update",        QVariant.String),
    ])
    lyr.updateFields()

    # Seed one feature per sensor so the layer is visible immediately
    for sid, (lon, lat) in SENSOR_POSITIONS.items():
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        f.setAttributes([sid, None, "UNKNOWN", False, "Awaiting data…", "—", "—"])
        pr.addFeature(f)
    lyr.updateExtents()
    return lyr


def _make_segment_layer() -> QgsVectorLayer:
    """
    Create an in-memory LineString layer for road segments.
    """
    uri = "LineString?crs=EPSG:4326"
    lyr = QgsVectorLayer(uri, "🛣  NH544 Segments (Live)", "memory")
    pr  = lyr.dataProvider()
    pr.addAttributes([
        QgsField("segment_id",         QVariant.String),
        QgsField("hazard_coefficient", QVariant.Double),
        QgsField("hazard_class",       QVariant.String),
        QgsField("is_critical",        QVariant.Bool),
        QgsField("sensor_source",      QVariant.String),
    ])
    lyr.updateFields()
    return lyr


def _make_route_layer() -> QgsVectorLayer:
    """Create an in-memory LineString layer for the live routed path."""
    uri = "LineString?crs=EPSG:4326"
    lyr = QgsVectorLayer(uri, "🚚 Live Route (PI-GNN + A*)", "memory")
    pr  = lyr.dataProvider()
    pr.addAttributes([
        QgsField("route_type", QVariant.String),
        QgsField("is_rerouted", QVariant.Bool),
        QgsField("length_m", QVariant.Double),
    ])
    lyr.updateFields()
    return lyr


def _seed_segments_from_file(lyr: QgsVectorLayer) -> None:
    """
    If qgis-demo/data/nh544_original.geojson is present, load stage-0 segment
    centroids from it so we have real road geometry to colour in real time.
    Falls back silently if the file isn't found.
    """
    import os
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "simulation", "data")
    path = os.path.join(data_dir, "nh544_original.geojson")
    if not os.path.exists(path):
        print("[realtime] ℹ  nh544_original.geojson not found — segment layer will be empty.")
        print("             Run generate_qgis_data.py first to populate it.")
        return

    with open(path) as f:
        gj = json.load(f)

    # Take only stage-0 features (one per segment) for the live layer seed
    stage0 = [ft for ft in gj["features"] if ft["properties"].get("scenario_stage") == 0]
    pr = lyr.dataProvider()
    features = []
    for ft in stage0:
        geom_type = ft["geometry"]["type"]
        coords    = ft["geometry"]["coordinates"]
        
        if geom_type != "LineString":
            continue

        props = ft["properties"]
        qf = QgsFeature(lyr.fields())
        
        geom = QgsGeometry.fromPolylineXY([QgsPointXY(c[0], c[1]) for c in coords])
        qf.setGeometry(geom)
            
        # Derive which sensor covers this segment
        seg_num = int(props["segment_id"].split("-")[-1])
        source  = "none"
        for sid, (s, e) in SENSOR_SEGMENT_MAP.items():
            if s <= seg_num <= e:
                source = sid
        qf.setAttributes([
            props["segment_id"],
            props.get("hazard_coefficient", 0.0),
            props.get("hazard_class", "SAFE"),
            bool(props.get("is_critical", False)),
            source,
        ])
        features.append(qf)

    pr.addFeatures(features)
    lyr.updateExtents()
    print(f"[realtime] ✓ Seeded {len(features)} segment centroids from nh544_original.geojson")


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based renderer helpers
# ─────────────────────────────────────────────────────────────────────────────

def _apply_hazard_renderer(lyr: QgsVectorLayer, geom_type: str = "point") -> None:
    """Apply a rule-based renderer that colours features by hazard_class."""
    rules = [
        ("SAFE",     "\"hazard_class\" = 'SAFE'",     COLOUR_SAFE),
        ("WARNING",  "\"hazard_class\" = 'WARNING'",  COLOUR_WARNING),
        ("CRITICAL", "\"hazard_class\" = 'CRITICAL'", COLOUR_CRITICAL),
        ("Unknown",  "ELSE",                           COLOUR_UNKNOWN),
    ]

    root_rule = QgsRuleBasedRenderer.Rule(None)
    for label, expr, colour in rules:
        sym = QgsSymbol.defaultSymbol(lyr.geometryType())
        sym.setColor(colour)
        if geom_type == "point":
            sym.setSize(4.0 if "Sensor" in lyr.name() else 2.0)
        elif geom_type == "line":
            sym.setWidth(2.5)
        rule = QgsRuleBasedRenderer.Rule(sym)
        rule.setLabel(label)
        rule.setFilterExpression(expr)
        root_rule.appendChild(rule)

    renderer = QgsRuleBasedRenderer(root_rule)
    lyr.setRenderer(renderer)
    lyr.triggerRepaint()


def _apply_route_renderer(lyr: QgsVectorLayer) -> None:
    """Apply a rule-based renderer that colours the route by is_rerouted."""
    rules = [
        ("Original Route", "\"is_rerouted\" = false OR \"is_rerouted\" IS NULL", QColor("#33FF33")), # Green for original
        ("Rerouted",       "\"is_rerouted\" = true",  QColor("#FF33FF")), # Magenta for reroute
    ]

    root_rule = QgsRuleBasedRenderer.Rule(None)
    for label, expr, colour in rules:
        sym = QgsSymbol.defaultSymbol(lyr.geometryType())
        sym.setColor(colour)
        sym.setWidth(3.5)  # Make it thicker so it renders clearly above static layers
        rule = QgsRuleBasedRenderer.Rule(sym)
        rule.setLabel(label)
        rule.setFilterExpression(expr)
        root_rule.appendChild(rule)

    renderer = QgsRuleBasedRenderer(root_rule)
    lyr.setRenderer(renderer)
    lyr.triggerRepaint()


# ─────────────────────────────────────────────────────────────────────────────
# SSE consumer thread
# ─────────────────────────────────────────────────────────────────────────────

def _sse_reader(stream_url: str, stop: threading.Event, q: queue.Queue) -> None:
    """
    Background daemon thread.  Opens a persistent GET to /stream and pushes
    each parsed HAZARD_UPDATE event into the queue for the main-thread timer
    to consume.
    """
    print(f"[realtime] ⟳ Connecting to SSE stream: {stream_url}")
    while not stop.is_set():
        try:
            with requests.get(stream_url, stream=True, timeout=None) as resp:
                if resp.status_code != 200:
                    print(f"[realtime] ✗ SSE HTTP {resp.status_code} — retrying in 3 s")
                    stop.wait(3)
                    continue
                print("[realtime] ✓ SSE stream connected.")
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if stop.is_set():
                        break
                    if not raw_line or not raw_line.startswith("data:"):
                        continue
                    payload_str = raw_line[len("data:"):].strip()
                    try:
                        payload = json.loads(payload_str)
                        if payload.get("type") in ("HAZARD_UPDATE", "REROUTE_UPDATE"):
                            q.put_nowait(payload)
                    except (json.JSONDecodeError, queue.Full):
                        pass
        except Exception as exc:
            if not stop.is_set():
                print(f"[realtime] ⚠  Stream error: {exc} — retrying in 3 s")
                stop.wait(3)

    print("[realtime] SSE reader thread exiting.")


# ─────────────────────────────────────────────────────────────────────────────
# Main-thread queue drainer (called by QTimer)
# ─────────────────────────────────────────────────────────────────────────────

def _drain_queue(sensor_lyr: QgsVectorLayer, segment_lyr: QgsVectorLayer, route_lyr: QgsVectorLayer) -> None:
    """Drain all pending events from the queue and apply them to the layers."""
    if _event_queue.empty():
        return

    # Collect all pending events
    events = []
    while not _event_queue.empty():
        try:
            events.append(_event_queue.get_nowait())
        except queue.Empty:
            break

    if not events:
        return

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    sensor_pr  = sensor_lyr.dataProvider()
    segment_pr = segment_lyr.dataProvider()
    route_pr   = route_lyr.dataProvider()

    # Field index maps
    s_fields = {f.name(): i for i, f in enumerate(sensor_lyr.fields())}
    r_fields = {f.name(): i for i, f in enumerate(segment_lyr.fields())}
    route_fields = {f.name(): i for i, f in enumerate(route_lyr.fields())}

    sensor_edits  = {}   # fid → {field_idx: value}
    segment_edits = {}   # fid → {field_idx: value}

    for ev in events:
        if ev.get("type") == "REROUTE_UPDATE":
            route_pr.deleteFeatures([f.id() for f in route_lyr.getFeatures()])
            
            geojson = ev.get("geojson", {})
            if not geojson or not geojson.get("features"):
                continue
                
            ft = geojson["features"][0]
            coords = ft["geometry"]["coordinates"]
            geom = QgsGeometry.fromPolylineXY([QgsPointXY(c[0], c[1]) for c in coords])
            
            # MUST initialize with fields otherwise setAttributes maps nothing!
            qf = QgsFeature(route_lyr.fields())
            qf.setGeometry(geom)
            props = ft["properties"]
            qf.setAttributes([
                props.get("route_type", ""),
                props.get("is_rerouted", False),
                props.get("length_m", 0.0)
            ])
            route_pr.addFeature(qf)
            route_lyr.updateExtents()
            route_lyr.triggerRepaint()
            continue

        node_id     = ev.get("node_id", "")
        hazard      = float(ev.get("hazard_coefficient", 0.0))
        is_critical = bool(ev.get("is_critical", False))
        sev_class   = ev.get("severity_class", "SAFE")
        seg_ids     = set(ev.get("affected_segment_ids", []))
        stage_label = ev.get("stage_label", "")
        net_mode    = ev.get("network_mode", "")

        # ── Update matching sensor node feature ───────────────────────────────
        for feat in sensor_lyr.getFeatures():
            if feat["sensor_id"] == node_id:
                sensor_edits[feat.id()] = {
                    s_fields["hazard_coefficient"]: hazard,
                    s_fields["hazard_class"]:       sev_class,
                    s_fields["is_critical"]:        is_critical,
                    s_fields["last_update"]:        now,
                }
                if stage_label and "stage_label" in s_fields:
                    sensor_edits[feat.id()][s_fields["stage_label"]] = stage_label
                if net_mode and "network_mode" in s_fields:
                    sensor_edits[feat.id()][s_fields["network_mode"]] = net_mode

        # ── Update road segment features covered by this sensor ───────────────
        if seg_ids:
            for feat in segment_lyr.getFeatures():
                if feat["segment_id"] in seg_ids:
                    segment_edits[feat.id()] = {
                        r_fields["hazard_coefficient"]: hazard,
                        r_fields["hazard_class"]:       sev_class,
                        r_fields["is_critical"]:        is_critical,
                        r_fields["sensor_source"]:      node_id,
                    }

    # Commit attribute changes
    if sensor_edits:
        sensor_pr.changeAttributeValues(sensor_edits)
        sensor_lyr.triggerRepaint()

    if segment_edits:
        segment_pr.changeAttributeValues(segment_edits)
        segment_lyr.triggerRepaint()

    # Log the latest event for visibility in the console
    if events:
        latest = events[-1]
        if latest.get("type") == "REROUTE_UPDATE":
            is_rerouted = latest.get("is_rerouted", False)
            length = latest.get("length_m", 0)
            status = "DIVERTED" if is_rerouted else "ORIGINAL"
            print(f"[realtime] 🚚 Route updated: {status} ({length/1000:.2f} km)  ({len(events)} event(s) applied)")
        else:
            h   = latest.get("hazard_coefficient", 0)
            cls = latest.get("severity_class", "?")
            nid = latest.get("node_id", "?")
            flag = "  ⚠  CRITICAL" if latest.get("is_critical") else ""
            print(f"[realtime] {nid}  hazard={h:.4f} m²/s  {cls}{flag}  ({len(events)} event(s) applied)")


# ─────────────────────────────────────────────────────────────────────────────
# Public API — call these from the QGIS Python Console
# ─────────────────────────────────────────────────────────────────────────────

def start_realtime_stream(server_url: str = SERVER_URL) -> None:
    """
    Entry point — call this once from the QGIS Python Console.
    Creates the in-memory layers, starts the SSE reader thread,
    and arms the QTimer update loop.
    """
    global _timer, _stream_thread, _stop_flag

    # Clean up any previous run
    stop_realtime_stream()
    _stop_flag = threading.Event()

    stream_url = f"{server_url.rstrip('/')}/stream"

    # ── Build layers ──────────────────────────────────────────────────────────
    sensor_lyr  = _make_sensor_layer()
    segment_lyr = _make_segment_layer()
    route_lyr   = _make_route_layer()
    _seed_segments_from_file(segment_lyr)

    _apply_hazard_renderer(sensor_lyr,  geom_type="point")
    _apply_hazard_renderer(segment_lyr, geom_type="line")
    _apply_route_renderer(route_lyr)

    project = QgsProject.instance()

    # ── Add basemap if it doesn't exist ──────────────────────────────────────
    basemap_name = "ESRI World Imagery (Satellite)"
    if not project.mapLayersByName(basemap_name):
        basemap_url = (
            "type=xyz"
            "&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            "&zmax=19&zmin=0"
        )
        basemap = QgsRasterLayer(basemap_url, basemap_name, "wms")
        if basemap.isValid():
            project.addMapLayer(basemap, False)
            project.layerTreeRoot().addLayer(basemap)
            print("[realtime] ✓ ESRI World Imagery basemap added.")

    project.addMapLayer(route_lyr)
    project.addMapLayer(segment_lyr)
    project.addMapLayer(sensor_lyr)   # sensors on top

    # Zoom to NH544 corridor
    iface.mapCanvas().setExtent(
        iface.mapCanvas().mapSettings().fullExtent()
        if not segment_lyr.featureCount()
        else segment_lyr.extent().buffered(0.02)
    )
    iface.mapCanvas().refresh()

    # ── Start SSE reader thread ───────────────────────────────────────────────
    _stream_thread = threading.Thread(
        target=_sse_reader,
        args=(stream_url, _stop_flag, _event_queue),
        daemon=True,
        name="SSE-reader",
    )
    _stream_thread.start()

    # ── Arm QTimer (main thread) ──────────────────────────────────────────────
    _timer = QTimer()
    _timer.setInterval(POLL_INTERVAL_MS)
    _timer.timeout.connect(lambda: _drain_queue(sensor_lyr, segment_lyr, route_lyr))
    _timer.start()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Hydro-Kinematic Real-Time Stream  —  LIVE               ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║  Server  : {server_url:<46}║")
    print(f"║  Stream  : {stream_url:<46}║")
    print("║  Layers  : 🔴 Sensor Nodes (Live)                        ║")
    print("║            🛣  NH544 Segments (Live)                      ║")
    print("║                                                          ║")
    print("║  Colour key:                                             ║")
    print("║    Cyan   #00F0FF  →  SAFE     (< 0.4 m²/s)             ║")
    print("║    Amber  #FFAA00  →  WARNING  (0.4–0.8 m²/s)           ║")
    print("║    Red    #FF3366  →  CRITICAL (≥ 0.8 m²/s)             ║")
    print("║                                                          ║")
    print("║  To stop:  stop_realtime_stream()                        ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("  ▶  Now run:  python3 qgis-demo/sensor_emitter.py")
    print()


def stop_realtime_stream() -> None:
    """Stop the SSE reader thread and QTimer cleanly."""
    global _timer, _stream_thread

    if _timer is not None:
        _timer.stop()
        _timer = None

    _stop_flag.set()

    if _stream_thread is not None and _stream_thread.is_alive():
        _stream_thread.join(timeout=2)
        _stream_thread = None

    # Drain any leftover events
    while not _event_queue.empty():
        try:
            _event_queue.get_nowait()
        except queue.Empty:
            break

    print("[realtime] ✅ Stream stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# Custom Dynamic Routing Tool
# ─────────────────────────────────────────────────────────────────────────────

from qgis.gui import QgsMapToolEmitPoint
from qgis.utils import iface

class RouteMapTool(QgsMapToolEmitPoint):
    def __init__(self, canvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.clicks = 0
        self.origin = None
        self.destination = None

    def canvasReleaseEvent(self, e):
        point = self.toMapCoordinates(e.pos())
        if self.clicks == 0:
            self.origin = [point.x(), point.y()]
            self.clicks += 1
            print(f"[realtime] 📍 Origin set to ({self.origin[0]:.4f}, {self.origin[1]:.4f}). Click again to set the destination.")
        else:
            self.destination = [point.x(), point.y()]
            self.clicks = 0
            print(f"[realtime] 📍 Destination set to ({self.destination[0]:.4f}, {self.destination[1]:.4f}). Routing...")
            self.request_route()
            
    def request_route(self):
        url = f"{SERVER_URL.rstrip('/')}/set_route"
        def _do_req():
            try:
                res = requests.post(url, json={"origin": self.origin, "destination": self.destination})
                data = res.json()
                if not data.get("found"):
                    print("[realtime] ❌ No valid path found between those points! (Note: The highway is a directed graph, make sure to route upstream → downstream).")
            except Exception as ex:
                print(f"[realtime] Failed to set route: {ex}")
        threading.Thread(target=_do_req, daemon=True).start()

_route_tool = None

def enable_custom_routing() -> None:
    """Activates the map tool to click and dynamically set routing start/end points."""
    global _route_tool
    canvas = iface.mapCanvas()
    _route_tool = RouteMapTool(canvas)
    canvas.setMapTool(_route_tool)
    print()
    print("=========================================================================")
    print("  🖱️  CUSTOM ROUTING ENABLED")
    print("  Click anywhere on the map to set the START location.")
    print("  Click a second time to set the END location.")
    print("  The PI-GNN router will snap points to the nearest known graph node.")
    print("=========================================================================")
    print()


# ── Auto-start when the script is Run from the QGIS editor ───────────────────
start_realtime_stream()
