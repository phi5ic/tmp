"""
router.py
─────────
Real-time Physics-Informed A* Router for the Hydro-Kinematic Logistics Mesh.

This module builds a weighted directed graph from the NH544 road network
(routes_source.geojson) and computes the minimum-hazard path using A* search.
It is called by webhook_server.py after every PI-GNN inference result and
returns a GeoJSON LineString of the optimal route.

Graph structure
───────────────
Nodes  : unique coordinate endpoints of every LineString segment (lon, lat).
Edges  : one directed edge per segment endpoint pair; each segment may
         contribute multiple edges if it has >2 coordinates (polyline).

Edge weight formula
───────────────────
  w(seg) = physical_length_m × (1 + HAZARD_PENALTY × hazard_coefficient)

  HAZARD_PENALTY = 50  (tunable)

  Normal  conditions (h ≈ 0.11 m²/s): weight ≈ physical length only.
  Flood   conditions (h ≈ 3.08 m²/s): weight = length × 155  → effectively
          forces A* around the entire flood corridor.
  CRITICAL segments (h > 0.8 m²/s)  : weight = +inf (impassable).

Heuristic
─────────
  Haversine distance from current node to goal — geographically admissible
  (never overestimates; straight-line distance ≤ road distance always).

Network topology (discovered from data analysis)
─────────────────────────────────────────────────
  Segments 0–194   : shared prefix (both corridors identical)
  Junction A        : node (76.347983, 10.270611) at seg index 195
  ORIG corridor     : segs 195–823  (29.4 km total, includes flood zone 164–618)
  REROUTE corridor  : reroute segs 195–1014 (50.4 km, avoids flood zone)
  Junction B        : node (76.411746, 10.344711) — reroute[1014] rejoins orig[646]
  Shared suffix     : orig segs 646–823

Public API
──────────
  router = HydroRouter(geojson_path)
  router.update_hazard("Sensor-NH544-B", hazard_coefficient=3.08)
  result = router.find_path(
      origin=(76.319778, 10.249946),   # ORIG-SEG-0 start
      destination=(76.390489, 10.379903)  # route end
  )
  # result.geojson   → GeoJSON FeatureCollection ready to write/push
  # result.segments  → ordered list of segment_id strings
  # result.length_m  → total path length in metres
  # result.is_rerouted → True when flood corridor was avoided
"""

import heapq
import json
import math
import os
import threading
from dataclasses import dataclass, field
from typing import Optional

# ── Constants ─────────────────────────────────────────────────────────────────
HAZARD_PENALTY = 50.0       # weight multiplier coefficient (α)
CRITICAL_THRESHOLD = 0.8    # m²/s — segments above this are impassable
SNAP_DECIMALS = 6           # coordinate rounding for node identity
EARTH_RADIUS_M = 6_371_000  # metres

# Sensor → segment index range (mirrors webhook_server.py)
SENSOR_SEGMENT_MAP: dict[str, tuple[int, int]] = {
    "Sensor-NH544-A": (0,   206),
    "Sensor-NH544-B": (164, 618),
}


# ── Haversine geometry ─────────────────────────────────────────────────────────

def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Return great-circle distance in metres between two (lon, lat) points."""
    lon1, lat1 = math.radians(a[0]), math.radians(a[1])
    lon2, lat2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(x))


def _round_node(lon: float, lat: float) -> tuple[float, float]:
    return (round(lon, SNAP_DECIMALS), round(lat, SNAP_DECIMALS))


# ── Graph data structures ─────────────────────────────────────────────────────

@dataclass
class Edge:
    """A directed edge in the road graph."""
    to: tuple[float, float]          # destination node (lon, lat)
    segment_id: str                  # e.g. "ORIG-SEG-195"
    physical_length_m: float         # Haversine length of this segment
    hazard_coefficient: float = 0.0  # updated by PI-GNN inference
    is_critical: bool = False        # True when hazard > CRITICAL_THRESHOLD

    @property
    def weight(self) -> float:
        if self.is_critical:
            return float("inf")
        return self.physical_length_m * (1.0 + HAZARD_PENALTY * self.hazard_coefficient)


@dataclass(order=True)
class _HeapItem:
    """Priority queue item for A*."""
    f_score: float
    g_score: float = field(compare=False)
    node: tuple[float, float] = field(compare=False)
    came_from: Optional[tuple[float, float]] = field(compare=False, default=None)
    edge_used: Optional[Edge] = field(compare=False, default=None)


@dataclass
class PathResult:
    """Return type from HydroRouter.find_path()."""
    found: bool
    segments: list[str]               # ordered segment IDs
    coordinates: list[list[float]]    # [[lon,lat], …] full path geometry
    length_m: float
    is_rerouted: bool                 # True if alternate corridor was used
    geojson: dict                     # ready-to-use GeoJSON FeatureCollection


# ── Router ────────────────────────────────────────────────────────────────────

class HydroRouter:
    """
    Weighted directed graph + A* router for the NH544 road network.

    Thread-safe: hazard updates and path queries may be called concurrently
    (webhook_server.py handles requests in multiple threads under Gunicorn).
    The internal lock is held only for the brief hazard-update write, not
    during the A* search (which reads a snapshot of edge weights).
    """

    def __init__(self, geojson_path: str):
        self._lock = threading.RLock()
        # adjacency list: node -> list[Edge]
        self._graph: dict[tuple[float, float], list[Edge]] = {}
        # segment_id -> list[Edge] (for bulk hazard updates)
        self._seg_edges: dict[str, list[Edge]] = {}
        # orig segment index range for reroute detection
        self._orig_seg_ids: set[str] = set()
        self._reroute_seg_ids: set[str] = set()

        self._build_graph(geojson_path)

    # ── Graph construction ────────────────────────────────────────────────────

    def _build_graph(self, path: str) -> None:
        with open(path) as f:
            gj = json.load(f)

        features = gj["features"]
        orig_feats = []
        reroute_feats = []
        
        for ft in features:
            fid = ft.get("id") or ft.get("properties", {}).get("segment_id", "")
            if fid.startswith("REROUTE"):
                reroute_feats.append(ft)
                self._reroute_seg_ids.add(fid)
            else:
                orig_feats.append(ft)
                self._orig_seg_ids.add(fid)

        for ft in orig_feats + reroute_feats:
            self._add_segment(ft)

        total_nodes = len(self._graph)
        total_edges = sum(len(v) for v in self._graph.values())
        print(
            f"[router] Graph built: {len(self._seg_edges)} segments, "
            f"{total_nodes} nodes, {total_edges} directed edges."
        )

    def _add_segment(self, feature: dict) -> None:
        seg_id = feature.get("id") or feature.get("properties", {}).get("segment_id", "")
        coords = feature["geometry"]["coordinates"]  # [[lon,lat], ...]

        edges_for_seg: list[Edge] = []

        for i in range(len(coords) - 1):
            src = _round_node(coords[i][0],   coords[i][1])
            dst = _round_node(coords[i+1][0], coords[i+1][1])
            length = haversine(src, dst)

            fwd = Edge(to=dst, segment_id=seg_id, physical_length_m=length)
            rev = Edge(to=src, segment_id=seg_id, physical_length_m=length)

            # Forward direction
            self._graph.setdefault(src, []).append(fwd)
            # Reverse direction (roads are bidirectional)
            self._graph.setdefault(dst, []).append(rev)

            edges_for_seg.append(fwd)
            edges_for_seg.append(rev)

            # Ensure destination node exists in graph even if it has no outgoing edges yet
            self._graph.setdefault(dst, [])

        self._seg_edges[seg_id] = edges_for_seg

    # ── Hazard updates ────────────────────────────────────────────────────────

    def update_hazard(self, sensor_id: str, hazard_coefficient: float) -> None:
        """
        Update edge weights for all segments covered by the given sensor.
        Called by webhook_server.py after each PI-GNN inference.
        Thread-safe.
        """
        seg_range = SENSOR_SEGMENT_MAP.get(sensor_id)
        if seg_range is None:
            return

        start, end = seg_range
        is_critical = hazard_coefficient > CRITICAL_THRESHOLD

        with self._lock:
            for idx in range(start, end + 1):
                # Only block the ORIG corridor — the REROUTE corridor is the
                # safe physical detour and must remain passable even at flood.
                seg_id = f"ORIG-SEG-{idx}"
                edges = self._seg_edges.get(seg_id)
                if edges is None:
                    continue
                for edge in edges:
                    edge.hazard_coefficient = hazard_coefficient
                    edge.is_critical = is_critical

    def update_hazard_by_segment(self, segment_id: str, hazard_coefficient: float) -> None:
        """Fine-grained update for a single segment."""
        is_critical = hazard_coefficient > CRITICAL_THRESHOLD
        with self._lock:
            edges = self._seg_edges.get(segment_id, [])
            for edge in edges:
                edge.hazard_coefficient = hazard_coefficient
                edge.is_critical = is_critical

    def reset_hazards(self) -> None:
        """Reset all edge weights to zero (normal conditions)."""
        with self._lock:
            for edges in self._seg_edges.values():
                for edge in edges:
                    edge.hazard_coefficient = 0.0
                    edge.is_critical = False

    # ── A* search ────────────────────────────────────────────────────────────

    def find_path(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
    ) -> PathResult:
        """
        Run A* from origin to destination using current hazard-weighted edges.

        Parameters
        ──────────
        origin      : (lon, lat) of the truck's current position
        destination : (lon, lat) of the route destination

        Returns
        ───────
        PathResult with full geometry, segment IDs, length, and GeoJSON.
        """
        origin      = _round_node(*origin)
        destination = _round_node(*destination)

        # Snap origin/destination to nearest graph node if not exact
        origin      = self._snap(origin)
        destination = self._snap(destination)

        if origin is None or destination is None:
            return self._no_path("origin or destination could not be snapped to graph")

        # Take a snapshot of edge weights to avoid holding the lock during search
        with self._lock:
            graph_snapshot = {
                node: list(edges)
                for node, edges in self._graph.items()
            }

        # ── A* core ──────────────────────────────────────────────────────────
        open_heap: list[_HeapItem] = []
        g_score: dict[tuple, float] = {origin: 0.0}
        came_from: dict[tuple, tuple] = {}     # node -> (parent_node, edge_used)
        closed: set[tuple] = set()

        h0 = haversine(origin, destination)
        heapq.heappush(open_heap, _HeapItem(f_score=h0, g_score=0.0, node=origin))

        while open_heap:
            item = heapq.heappop(open_heap)
            current = item.node

            if current in closed:
                continue
            closed.add(current)

            if current == destination:
                return self._reconstruct(came_from, origin, destination, graph_snapshot)

            for edge in graph_snapshot.get(current, []):
                if edge.weight == float("inf"):
                    continue  # impassable segment
                neighbor = edge.to
                if neighbor in closed:
                    continue

                tentative_g = g_score.get(current, float("inf")) + edge.weight
                if tentative_g < g_score.get(neighbor, float("inf")):
                    g_score[neighbor] = tentative_g
                    came_from[neighbor] = (current, edge)
                    h = haversine(neighbor, destination)
                    heapq.heappush(
                        open_heap,
                        _HeapItem(
                            f_score=tentative_g + h,
                            g_score=tentative_g,
                            node=neighbor,
                        ),
                    )

        return self._no_path("A* exhausted open set — no path found")

    # ── Path reconstruction ───────────────────────────────────────────────────

    def _reconstruct(
        self,
        came_from: dict,
        origin: tuple,
        destination: tuple,
        graph_snapshot: dict,
    ) -> PathResult:
        """Trace came_from back to origin and build the PathResult."""
        node = destination
        segment_ids: list[str] = []
        coord_path: list[tuple] = [node]
        length_m = 0.0
        uses_reroute = False

        while node in came_from:
            parent, edge = came_from[node]
            segment_ids.append(edge.segment_id)
            length_m += edge.physical_length_m
            coord_path.append(parent)
            if edge.segment_id in self._reroute_seg_ids:
                uses_reroute = True
            node = parent

        segment_ids.reverse()
        coord_path.reverse()

        coords_lonlat = [[lon, lat] for lon, lat in coord_path]

        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords_lonlat,
                    },
                    "properties": {
                        "route_type": "PI-GNN_ASTAR_REROUTE" if uses_reroute else "PI-GNN_ASTAR_ORIGINAL",
                        "segment_count": len(segment_ids),
                        "length_m": round(length_m, 1),
                        "is_rerouted": uses_reroute,
                        "first_segment": segment_ids[0] if segment_ids else None,
                        "last_segment": segment_ids[-1] if segment_ids else None,
                    },
                }
            ],
        }

        return PathResult(
            found=True,
            segments=segment_ids,
            coordinates=coords_lonlat,
            length_m=round(length_m, 1),
            is_rerouted=uses_reroute,
            geojson=geojson,
        )

    def _no_path(self, reason: str) -> PathResult:
        print(f"[router] ✗ No path: {reason}")
        return PathResult(
            found=False,
            segments=[],
            coordinates=[],
            length_m=0.0,
            is_rerouted=False,
            geojson={"type": "FeatureCollection", "features": []},
        )

    # ── Node snapping ─────────────────────────────────────────────────────────

    def _snap(
        self, node: tuple[float, float], tolerance_m: float = 5000.0
    ) -> Optional[tuple[float, float]]:
        """
        Snap an arbitrary coordinate to the nearest graph node within tolerance.
        Returns None if no node is within tolerance_m metres.
        """
        if node in self._graph:
            return node
        best_node = None
        best_dist = float("inf")
        for candidate in self._graph:
            d = haversine(node, candidate)
            if d < best_dist:
                best_dist = d
                best_node = candidate
        if best_dist <= tolerance_m:
            return best_node
        return None

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def node_count(self) -> int:
        return len(self._graph)

    @property
    def segment_count(self) -> int:
        return len(self._seg_edges)

    @property
    def origin(self) -> tuple[float, float]:
        """ORIG-SEG-0 start node — the truck's departure point."""
        return _round_node(76.319778, 10.249946)

    @property
    def destination(self) -> tuple[float, float]:
        """Shared terminal endpoint of both corridors."""
        return _round_node(76.390489, 10.379903)


# ── Module-level singleton (loaded once at server startup) ────────────────────

_router_instance: Optional[HydroRouter] = None
_router_lock = threading.Lock()


def get_router(geojson_path: Optional[str] = None) -> HydroRouter:
    """
    Return the module-level router singleton.
    On first call, builds the graph from geojson_path.
    Subsequent calls return the cached instance.
    """
    global _router_instance
    if _router_instance is not None:
        return _router_instance
    with _router_lock:
        if _router_instance is not None:
            return _router_instance
        if geojson_path is None:
            here = os.path.dirname(os.path.abspath(__file__))
            local_path = os.path.join(
                os.path.dirname(here), "qgis-demo", "data", "routes_source.geojson"
            )
            kerala_path = os.path.join(
                os.path.dirname(here), "qgis-demo", "data", "routes_source_kerala.geojson"
            )
            geojson_path = kerala_path if os.path.exists(kerala_path) else local_path
        _router_instance = HydroRouter(geojson_path)
    return _router_instance


# ── CLI smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import time

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    geojson = os.path.join(root, "qgis-demo", "data", "routes_source.geojson")

    print("=" * 60)
    print("  PI-GNN A* Router — Smoke Test")
    print("=" * 60)

    router = HydroRouter(geojson)
    origin      = router.origin
    destination = router.destination
    print(f"  Origin     : {origin}")
    print(f"  Destination: {destination}")
    print()

    # ── Scenario 1: Normal conditions ────────────────────────────────────────
    print("─" * 60)
    print("SCENARIO 1: Normal conditions (hazard = 0.0)")
    t0 = time.perf_counter()
    result = router.find_path(origin, destination)
    t1 = time.perf_counter()
    print(f"  Found      : {result.found}")
    print(f"  Rerouted   : {result.is_rerouted}")
    print(f"  Segments   : {len(result.segments)}")
    print(f"  Length     : {result.length_m/1000:.2f} km")
    print(f"  Time       : {(t1-t0)*1000:.1f} ms")
    print(f"  First seg  : {result.segments[0] if result.segments else 'N/A'}")
    print(f"  Last seg   : {result.segments[-1] if result.segments else 'N/A'}")
    print()

    # ── Scenario 2: Flood — Sensor-NH544-B CRITICAL ──────────────────────────
    print("─" * 60)
    print("SCENARIO 2: Flood conditions — Sensor-NH544-B hazard = 3.08 m²/s (CRITICAL)")
    router.update_hazard("Sensor-NH544-B", 3.08)
    t0 = time.perf_counter()
    result2 = router.find_path(origin, destination)
    t1 = time.perf_counter()
    print(f"  Found      : {result2.found}")
    print(f"  Rerouted   : {result2.is_rerouted}")
    print(f"  Segments   : {len(result2.segments)}")
    print(f"  Length     : {result2.length_m/1000:.2f} km")
    print(f"  Time       : {(t1-t0)*1000:.1f} ms")
    print(f"  First seg  : {result2.segments[0] if result2.segments else 'N/A'}")
    print(f"  Last seg   : {result2.segments[-1] if result2.segments else 'N/A'}")

    # Verify: no flood-zone ORIG segments in result
    flood_segs = [s for s in result2.segments
                  if s.startswith("ORIG-SEG-") and
                  164 <= int(s.split("-")[-1]) <= 618]
    print(f"  Flood-zone ORIG segs in path : {len(flood_segs)}  (should be 0)")

    # Verify: reroute segments present
    reroute_segs = [s for s in result2.segments if s.startswith("REROUTE")]
    print(f"  REROUTE segments in path     : {len(reroute_segs)}  (should be > 0)")
    print()

    # ── Scenario 3: Full recovery — all hazards reset to zero ────────────────
    print("─" * 60)
    print("SCENARIO 3: Full recovery — reset_hazards() → all weights nominal")
    router.reset_hazards()
    t0 = time.perf_counter()
    result3 = router.find_path(origin, destination)
    t1 = time.perf_counter()
    print(f"  Found      : {result3.found}")
    print(f"  Rerouted   : {result3.is_rerouted}")
    print(f"  Length     : {result3.length_m/1000:.2f} km")
    print(f"  Time       : {(t1-t0)*1000:.1f} ms")
    print()

    # ── GeoJSON output ────────────────────────────────────────────────────────
    out_path = os.path.join(root, "qgis-demo", "data", "computed_reroute.geojson")
    with open(out_path, "w") as f:
        json.dump(result2.geojson, f)
    print(f"✅ Flood-scenario GeoJSON written → {out_path}")
    print()

    # Final summary
    ok = (
        result.found and not result.is_rerouted and
        result2.found and result2.is_rerouted and len(flood_segs) == 0 and
        result3.found and not result3.is_rerouted
    )
    print("=" * 60)
    print(f"  Smoke test: {'✅ PASSED' if ok else '❌ FAILED'}")
    print("=" * 60)
    sys.exit(0 if ok else 1)
