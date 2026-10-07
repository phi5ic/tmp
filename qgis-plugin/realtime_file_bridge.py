"""
realtime_file_bridge.py  —  Level 1: file watcher → QGIS layer reload
───────────────────────────────────────────────────────────────────────
Run this inside the QGIS Python Console:
  Plugins → Python Console → Show Editor → open file → Run Script

What it does
────────────
1. Loads qgis-demo/data/sensor_nodes.geojson as a standard file-backed
   vector layer (not in-memory).
2. Uses Qt's QFileSystemWatcher to detect when sensor_emitter.py (running
   in offline mode, or when the Flask server writes the file) updates the
   GeoJSON on disk.
3. On every file change, reloads the layer data and repaints the canvas.
4. A QTimer polls the file mtime every 500 ms as a secondary fallback in
   case QFileSystemWatcher misses rapid successive writes.

This is the Level 1 fallback — use it when the Flask webhook server isn't
running, or as a simpler alternative to the SSE plugin.

Usage
─────
  # Terminal 1 — run the emitter in offline mode (no Flask needed):
  python3 qgis-demo/sensor_emitter.py --offline

  # QGIS Python Console — load this script:
  # Plugins → Python Console → Show Editor → open realtime_file_bridge.py → Run

To stop:
  stop_file_bridge()

Requirements
────────────
  • sensor_emitter.py --offline running (or Flask server writing the file)
  • QGIS 3.28+
  • qgis-demo/data/sensor_nodes.geojson must exist
    (run generate_qgis_data.py once first if it doesn't)
"""

import os

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsSymbol,
    QgsRuleBasedRenderer,
)
from qgis.PyQt.QtCore import QFileSystemWatcher, QTimer
from qgis.PyQt.QtGui import QColor

# ── Configuration ─────────────────────────────────────────────────────────────
HERE     = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "simulation", "data")

# Files to watch (Level 1 bridge only needs sensor_nodes; extend if wanted)
WATCH_FILES = {
    "sensor_nodes.geojson": "Sensor Nodes (File Bridge)",
}

POLL_INTERVAL_MS = 500   # mtime-poll fallback interval

# Colour scheme (matches static demo + realtime plugin)
COLOUR_SAFE     = QColor("#00F0FF")
COLOUR_WARNING  = QColor("#FFAA00")
COLOUR_CRITICAL = QColor("#FF3366")
COLOUR_UNKNOWN  = QColor("#888888")

# ── Shared state ──────────────────────────────────────────────────────────────
_watcher       = None   # QFileSystemWatcher
_poll_timer    = None   # QTimer (mtime fallback)
_layer_map: dict[str, QgsVectorLayer] = {}   # file path → layer
_mtime_cache: dict[str, float] = {}          # file path → last seen mtime


# ─────────────────────────────────────────────────────────────────────────────
# Renderer helper
# ─────────────────────────────────────────────────────────────────────────────

def _apply_hazard_renderer(lyr: QgsVectorLayer) -> None:
    """Rule-based renderer colouring features by hazard_class field."""
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
        sym.setSize(6.0)
        rule = QgsRuleBasedRenderer.Rule(sym)
        rule.setLabel(label)
        rule.setFilterExpression(expr)
        root_rule.appendChild(rule)

    lyr.setRenderer(QgsRuleBasedRenderer(root_rule))
    lyr.triggerRepaint()


# ─────────────────────────────────────────────────────────────────────────────
# Layer reload
# ─────────────────────────────────────────────────────────────────────────────

def _reload_layer(path: str) -> None:
    """
    Reload the layer bound to `path`.

    QgsVectorLayer backed by a GeoJSON file re-reads the file when
    dataProvider().reloadData() is called — no need to remove and re-add
    the layer, which would break any saved style or label settings.
    """
    lyr = _layer_map.get(path)
    if lyr is None or not lyr.isValid():
        return

    lyr.dataProvider().reloadData()
    lyr.triggerRepaint()

    # Update mtime so the poll timer doesn't fire again immediately
    try:
        _mtime_cache[path] = os.path.getmtime(path)
    except OSError:
        pass

    # Log current hazard values for console feedback
    lines = []
    for feat in lyr.getFeatures():
        sid = feat["sensor_id"] if "sensor_id" in feat.fields().names() else "?"
        h   = feat["hazard_coefficient"] if "hazard_coefficient" in feat.fields().names() else "?"
        cls = feat["hazard_class"]        if "hazard_class"       in feat.fields().names() else "?"
        lines.append(f"  {sid}  hazard={h}  {cls}")
    if lines:
        print(f"[bridge] ↻ Reloaded {os.path.basename(path)}")
        for l in lines:
            print(l)


# ─────────────────────────────────────────────────────────────────────────────
# File system watcher callback
# ─────────────────────────────────────────────────────────────────────────────

def _on_file_changed(path: str) -> None:
    """
    Called by QFileSystemWatcher when the watched file is modified.

    Some editors / write patterns (atomic rename) cause the watcher to lose
    track of the file after a single notification.  Re-add it defensively.
    """
    # Re-watch in case the watcher dropped it after an atomic overwrite
    if path not in _watcher.files():
        _watcher.addPath(path)
    _reload_layer(path)


# ─────────────────────────────────────────────────────────────────────────────
# Fallback mtime poll
# ─────────────────────────────────────────────────────────────────────────────

def _poll_mtimes() -> None:
    """
    Called every POLL_INTERVAL_MS by a QTimer.  Detects file changes that
    QFileSystemWatcher may have missed (e.g., rapid successive writes where
    only the last inotify event is delivered).
    """
    for path in list(_layer_map.keys()):
        try:
            current = os.path.getmtime(path)
        except OSError:
            continue
        if current != _mtime_cache.get(path):
            _mtime_cache[path] = current
            _reload_layer(path)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def start_file_bridge() -> None:
    """
    Entry point — call once from the QGIS Python Console.
    Loads the watched GeoJSON files as vector layers, applies the hazard
    renderer, and starts the QFileSystemWatcher + fallback poll timer.
    """
    global _watcher, _poll_timer

    stop_file_bridge()

    project = QgsProject.instance()
    _watcher = QFileSystemWatcher()

    for filename, layer_name in WATCH_FILES.items():
        path = os.path.join(DATA_DIR, filename)

        if not os.path.exists(path):
            print(f"[bridge] ✗ File not found: {path}")
            print(f"           Run  generate_qgis_data.py  first (or use --offline emitter).")
            continue

        lyr = QgsVectorLayer(path, layer_name, "ogr")
        if not lyr.isValid():
            print(f"[bridge] ✗ Failed to load layer from: {path}")
            continue

        _apply_hazard_renderer(lyr)
        project.addMapLayer(lyr)
        _layer_map[path] = lyr

        try:
            _mtime_cache[path] = os.path.getmtime(path)
        except OSError:
            _mtime_cache[path] = 0.0

        _watcher.addPath(path)
        print(f"[bridge] ✓ Watching: {path}  ({lyr.featureCount()} features)")

    if not _layer_map:
        print("[bridge] ✗ No files loaded — bridge not started.")
        return

    # Connect file-change signal
    _watcher.fileChanged.connect(_on_file_changed)

    # Arm mtime poll fallback
    _poll_timer = QTimer()
    _poll_timer.setInterval(POLL_INTERVAL_MS)
    _poll_timer.timeout.connect(_poll_mtimes)
    _poll_timer.start()

    # Zoom to sensor layer extent
    first_lyr = next(iter(_layer_map.values()))
    iface.mapCanvas().setExtent(first_lyr.extent().buffered(0.05))
    iface.mapCanvas().refresh()

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║  Hydro-Kinematic File Bridge  —  ACTIVE                  ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print("║  Mode    : QFileSystemWatcher + mtime poll (500 ms)      ║")
    print(f"║  Watching: {len(_layer_map)} file(s)                              ║")
    print("║                                                          ║")
    print("║  Colour key:                                             ║")
    print("║    Cyan   #00F0FF  →  SAFE     (< 0.4 m²/s)             ║")
    print("║    Amber  #FFAA00  →  WARNING  (0.4–0.8 m²/s)           ║")
    print("║    Red    #FF3366  →  CRITICAL (≥ 0.8 m²/s)             ║")
    print("║                                                          ║")
    print("║  To stop:  stop_file_bridge()                            ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("  ▶  Now run:  python3 qgis-demo/sensor_emitter.py --offline")
    print()


def stop_file_bridge() -> None:
    """Stop the file watcher and poll timer cleanly."""
    global _watcher, _poll_timer

    if _poll_timer is not None:
        _poll_timer.stop()
        _poll_timer = None

    if _watcher is not None:
        try:
            _watcher.fileChanged.disconnect()
        except (TypeError, RuntimeError):
            pass
        _watcher = None

    _layer_map.clear()
    _mtime_cache.clear()
    print("[bridge] ✅ File bridge stopped.")


# ── Auto-start when the script is Run from the QGIS editor ───────────────────
start_file_bridge()
