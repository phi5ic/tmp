"""
generate_qgis_data.py

Generate QGIS-ready GeoJSON layers for the Hydro-Kinematic /
PI-GNN / VDTN flood-response demonstration.

Outputs:
    data/nh544_original.geojson
    data/nh544_reroute.geojson
    data/flood_basin.geojson
    data/vehicles.geojson
    data/sensor_nodes.geojson
    data/mesh_rings.geojson

Mesh rings:
    During Stage 3 and Stage 4, vehicles are surrounded by a
    circular polygon representing the local VDTN mesh communication
    coverage area.

The mesh ring radius can be changed with:
    MESH_RADIUS_M = 150
"""

from pathlib import Path
import json
import math
from datetime import datetime, timedelta

# ---------------------------------------------------------------------
# Optional PI-GNN import
# ---------------------------------------------------------------------

try:
    import torch
    PI_GNN_AVAILABLE = True
except ImportError:
    torch = None
    PI_GNN_AVAILABLE = False


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

ROUTES_SOURCE = BASE_DIR / "routes_source.geojson"
ROUTES_COORDS = BASE_DIR / "routes_coords.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

# VDTN communication radius around each vehicle.
# Change this value if you want a larger/smaller mesh coverage area.
MESH_RADIUS_M = 150

# Number of vertices used to draw each mesh circle.
# Higher = smoother circle.
MESH_CIRCLE_POINTS = 48

# Approximate conversion from meters to longitude/latitude degrees.
# This is sufficient for a visualization-scale demo.
METERS_PER_DEGREE_LAT = 111_320.0


# ---------------------------------------------------------------------
# Scenario stages
# ---------------------------------------------------------------------

STAGES = [
    {
        "stage": 0,
        "label": "Pre-Event Normal",
        "duration": 60,
    },
    {
        "stage": 1,
        "label": "Fleet En-Route",
        "duration": 60,
    },
    {
        "stage": 2,
        "label": "Cloudburst Detected",
        "duration": 60,
    },
    {
        "stage": 3,
        "label": "Cellular Failure / VDTN",
        "duration": 60,
    },
    {
        "stage": 4,
        "label": "Hazard Confirmed Critical",
        "duration": 60,
    },
    {
        "stage": 5,
        "label": "Reroute Executed",
        "duration": 120,
    },
]


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def ensure_feature_collection(obj):
    """
    Make sure an object is a GeoJSON FeatureCollection.
    """
    if obj.get("type") == "FeatureCollection":
        return obj

    if obj.get("type") == "Feature":
        return {
            "type": "FeatureCollection",
            "features": [obj],
        }

    raise ValueError("Unsupported GeoJSON structure")


def write_geojson(path, feature_collection):
    """
    Write GeoJSON with readable formatting.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            feature_collection,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"[OK] Wrote: {path}")


def interpolate_point(coords, fraction):
    """
    Linear interpolation between coordinates.

    coords:
        [(lon, lat), (lon, lat), ...]

    fraction:
        0.0 -> start
        1.0 -> end
    """

    if not coords:
        raise ValueError("Cannot interpolate an empty coordinate list.")

    if len(coords) == 1:
        return coords[0]

    fraction = max(0.0, min(1.0, fraction))

    # Calculate total route length.
    lengths = []

    total_length = 0.0

    for i in range(len(coords) - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]

        dx = x2 - x1
        dy = y2 - y1

        length = math.sqrt(dx * dx + dy * dy)

        lengths.append(length)
        total_length += length

    if total_length == 0:
        return coords[0]

    target_distance = fraction * total_length

    travelled = 0.0

    for i, segment_length in enumerate(lengths):
        if travelled + segment_length >= target_distance:
            local_distance = target_distance - travelled

            if segment_length == 0:
                return coords[i]

            local_fraction = local_distance / segment_length

            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]

            x = x1 + (x2 - x1) * local_fraction
            y = y1 + (y2 - y1) * local_fraction

            return [x, y]

        travelled += segment_length

    return coords[-1]


def make_circle(lon, lat, radius_m=MESH_RADIUS_M, points=MESH_CIRCLE_POINTS):
    """
    Create a circular polygon around a longitude/latitude point.

    radius_m:
        Radius of VDTN communication coverage in meters.

    Returns:
        List of [lon, lat] coordinates forming a closed polygon ring.
    """

    # Latitude conversion.
    radius_lat = radius_m / METERS_PER_DEGREE_LAT

    # Longitude conversion depends on latitude.
    cos_lat = math.cos(math.radians(lat))

    if abs(cos_lat) < 1e-9:
        cos_lat = 1e-9

    meters_per_degree_lon = METERS_PER_DEGREE_LAT * cos_lat

    radius_lon = radius_m / meters_per_degree_lon

    ring = []

    for i in range(points):
        angle = 2.0 * math.pi * i / points

        dx = radius_lon * math.cos(angle)
        dy = radius_lat * math.sin(angle)

        ring.append([
            lon + dx,
            lat + dy,
        ])

    # Close polygon.
    ring.append(ring[0])

    return ring


def build_stage_times(start_time):
    """
    Build begin/end timestamps for every scenario stage.
    """

    stage_times = []

    current_time = start_time

    for stage_info in STAGES:
        duration = stage_info["duration"]

        begin = current_time
        end = current_time + timedelta(seconds=duration)

        stage_times.append({
            "stage": stage_info["stage"],
            "label": stage_info["label"],
            "begin_time": begin.isoformat(),
            "end_time": end.isoformat(),
        })

        current_time = end

    return stage_times


def stage_time(stage_times, stage):
    """
    Get begin/end timestamps for a stage.
    """

    for item in stage_times:
        if item["stage"] == stage:
            return item

    raise ValueError(f"Stage {stage} not found.")


# ---------------------------------------------------------------------
# PI-GNN / hazard calculation
# ---------------------------------------------------------------------

def calculate_hazard(depth, velocity):
    """
    Calculate a simple hydraulic hazard indicator.

    hazard = depth * velocity

    The PI-GNN model can be inserted here when available.
    """

    hazard = depth * velocity

    return hazard


def run_pi_gnn_or_fallback(depth, velocity):
    """
    Run the PI-GNN model if the project environment provides it.

    If the model is unavailable, use the existing fallback values
    used by the demonstration.
    """

    # -----------------------------------------------------------------
    # Existing demonstration fallback
    # -----------------------------------------------------------------

    hazard = calculate_hazard(depth, velocity)

    if hazard > 0.04:
        return {
            "hazard": 3.0800,
            "risk_level": "critical",
            "model": "fallback",
        }

    return {
        "hazard": 0.1100,
        "risk_level": "not_critical",
        "model": "fallback",
    }


# ---------------------------------------------------------------------
# Load route data
# ---------------------------------------------------------------------

print("\n==============================================")
print("Hydro-Kinematic QGIS Data Generator")
print("==============================================\n")


if not ROUTES_SOURCE.exists():
    raise FileNotFoundError(
        f"Missing route file: {ROUTES_SOURCE}"
    )


if not ROUTES_COORDS.exists():
    raise FileNotFoundError(
        f"Missing coordinate file: {ROUTES_COORDS}"
    )


with open(ROUTES_SOURCE, "r", encoding="utf-8") as f:
    routes_source = json.load(f)


with open(ROUTES_COORDS, "r", encoding="utf-8") as f:
    routes_coords = json.load(f)


routes_source = ensure_feature_collection(routes_source)


# ---------------------------------------------------------------------
# Extract original / reroute routes
# ---------------------------------------------------------------------

original_route = None
reroute_route = None


for feature in routes_source.get("features", []):

    properties = feature.get("properties", {}) or {}

    name = str(
        properties.get("name")
        or properties.get("route")
        or properties.get("id")
        or ""
    ).lower()

    if (
        "reroute" in name
        or "alternate" in name
        or "alternative" in name
    ):
        if reroute_route is None:
            reroute_route = feature

    else:
        if original_route is None:
            original_route = feature


# ---------------------------------------------------------------------
# If route GeoJSON did not contain identifiable route names,
# use routes_coords.json.
# ---------------------------------------------------------------------

def extract_coords_from_feature(feature):
    geometry = feature.get("geometry", {})

    if not geometry:
        return []

    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if geometry_type == "LineString":
        return coordinates

    if geometry_type == "MultiLineString":
        if coordinates:
            return coordinates[0]

    return []


original_coords = extract_coords_from_feature(original_route) if original_route else []
reroute_coords = extract_coords_from_feature(reroute_route) if reroute_route else []


# ---------------------------------------------------------------------
# Try routes_coords.json when needed
# ---------------------------------------------------------------------

if not original_coords or not reroute_coords:

    if isinstance(routes_coords, dict):

        possible_original = (
            routes_coords.get("original")
            or routes_coords.get("original_route")
            or routes_coords.get("nh544_original")
            or routes_coords.get("route")
        )

        possible_reroute = (
            routes_coords.get("reroute")
            or routes_coords.get("rerouted")
            or routes_coords.get("reroute_route")
            or routes_coords.get("nh544_reroute")
        )

        if not original_coords and possible_original:
            original_coords = possible_original

        if not reroute_coords and possible_reroute:
            reroute_coords = possible_reroute


# ---------------------------------------------------------------------
# Normalize coordinates
# ---------------------------------------------------------------------

def normalize_coords(coords):
    """
    Normalize coordinate arrays to [[lon, lat], ...].
    """

    if not coords:
        return []

    normalized = []

    for point in coords:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            try:
                normalized.append([
                    float(point[0]),
                    float(point[1]),
                ])
            except (ValueError, TypeError):
                continue

    return normalized


original_coords = normalize_coords(original_coords)
reroute_coords = normalize_coords(reroute_coords)


if not original_coords:
    raise ValueError(
        "Could not find original NH544 route coordinates."
    )


if not reroute_coords:
    # If a separate reroute was not supplied, use the original route
    # as a fallback so the script can still generate the data.
    reroute_coords = list(original_coords)

    print(
        "[WARNING] No separate reroute coordinates found. "
        "Using original route as reroute fallback."
    )


print(f"Original route points: {len(original_coords)}")
print(f"Reroute route points:  {len(reroute_coords)}")


# ---------------------------------------------------------------------
# Create route GeoJSON layers
# ---------------------------------------------------------------------

original_route_feature = {
    "type": "Feature",
    "geometry": {
        "type": "LineString",
        "coordinates": original_coords,
    },
    "properties": {
        "route_id": "NH544-ORIGINAL",
        "route_type": "original",
        "description": "Original NH544 route",
    },
}


reroute_route_feature = {
    "type": "Feature",
    "geometry": {
        "type": "LineString",
        "coordinates": reroute_coords,
    },
    "properties": {
        "route_id": "NH544-REROUTE",
        "route_type": "reroute",
        "description": "Emergency reroute",
    },
}


write_geojson(
    DATA_DIR / "nh544_original.geojson",
    {
        "type": "FeatureCollection",
        "features": [original_route_feature],
    },
)


write_geojson(
    DATA_DIR / "nh544_reroute.geojson",
    {
        "type": "FeatureCollection",
        "features": [reroute_route_feature],
    },
)


# ---------------------------------------------------------------------
# Scenario time
# ---------------------------------------------------------------------

START_TIME = datetime(2026, 1, 1, 10, 0, 0)

stage_times = build_stage_times(START_TIME)


# ---------------------------------------------------------------------
# Flood basin
# ---------------------------------------------------------------------

# Build a simple flood basin around the first section of the route.
#
# This is intentionally a visualization polygon rather than a
# hydrodynamic flood simulation.

flood_center = original_coords[len(original_coords) // 4]

center_lon = flood_center[0]
center_lat = flood_center[1]


flood_radius_lon = 0.0030
flood_radius_lat = 0.0020


flood_polygon = [
    [
        center_lon - flood_radius_lon,
        center_lat - flood_radius_lat,
    ],
    [
        center_lon + flood_radius_lon,
        center_lat - flood_radius_lat,
    ],
    [
        center_lon + flood_radius_lon,
        center_lat + flood_radius_lat,
    ],
    [
        center_lon - flood_radius_lon,
        center_lat + flood_radius_lat,
    ],
    [
        center_lon - flood_radius_lon,
        center_lat - flood_radius_lat,
    ],
]


flood_feature = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [flood_polygon],
    },
    "properties": {
        "basin_id": "Flood-Basin-01",
        "hazard_type": "Cloudburst Flood",
        "description": "Simulated flood hazard zone",
    },
}


write_geojson(
    DATA_DIR / "flood_basin.geojson",
    {
        "type": "FeatureCollection",
        "features": [flood_feature],
    },
)


# ---------------------------------------------------------------------
# Sensor nodes
# ---------------------------------------------------------------------

sensor_features = []


# Sensor positions are placed near the flood section.
sensor_a_pos = interpolate_point(original_coords, 0.28)
sensor_b_pos = interpolate_point(original_coords, 0.40)


sensor_definitions = [
    {
        "sensor_id": "Sensor-A",
        "position": sensor_a_pos,
        "normal_depth": 0.20,
        "normal_velocity": 0.50,
        "flood_depth": 0.35,
        "flood_velocity": 0.70,
    },
    {
        "sensor_id": "Sensor-B",
        "position": sensor_b_pos,
        "normal_depth": 0.20,
        "normal_velocity": 0.50,
        "flood_depth": 1.40,
        "flood_velocity": 2.20,
    },
]


for sensor in sensor_definitions:

    lon, lat = sensor["position"]

    for stage_info in STAGES:

        stage = stage_info["stage"]

        times = stage_time(stage_times, stage)

        # -------------------------------------------------------------
        # Normal conditions
        # -------------------------------------------------------------

        if stage < 2:

            depth = sensor["normal_depth"]
            velocity = sensor["normal_velocity"]

        # -------------------------------------------------------------
        # Cloudburst
        # -------------------------------------------------------------

        elif stage == 2:

            depth = sensor["flood_depth"]
            velocity = sensor["flood_velocity"]

        # -------------------------------------------------------------
        # VDTN / critical stages
        # -------------------------------------------------------------

        elif stage in (3, 4):

            depth = sensor["flood_depth"]
            velocity = sensor["flood_velocity"]

        # -------------------------------------------------------------
        # After reroute
        # -------------------------------------------------------------

        else:

            depth = sensor["normal_depth"]
            velocity = sensor["normal_velocity"]

        result = run_pi_gnn_or_fallback(
            depth,
            velocity,
        )

        sensor_features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    lon,
                    lat,
                ],
            },
            "properties": {
                "sensor_id": sensor["sensor_id"],
                "depth_m": depth,
                "velocity_ms": velocity,
                "hazard": result["hazard"],
                "risk_level": result["risk_level"],
                "model": result["model"],
                "scenario_stage": stage,
                "stage_label": stage_info["label"],
                "network_mode": (
                    "VDTN"
                    if stage in (3, 4)
                    else "LTE/5G"
                ),
                "begin_time": times["begin_time"],
                "end_time": times["end_time"],
            },
        })


write_geojson(
    DATA_DIR / "sensor_nodes.geojson",
    {
        "type": "FeatureCollection",
        "features": sensor_features,
    },
)


# ---------------------------------------------------------------------
# Vehicle tracks
# ---------------------------------------------------------------------

vehicle_features = []


# ---------------------------------------------------------------------
# Mesh ring features
#
# IMPORTANT:
# This is the new layer.
#
# Each ring is a Polygon around the vehicle.
# Rings exist only during stages 3 and 4, when VDTN is active.
# ---------------------------------------------------------------------

mesh_ring_features = []


# ---------------------------------------------------------------------
# Helper for adding a vehicle mesh ring
# ---------------------------------------------------------------------

def add_mesh_ring(
    vehicle_id,
    vehicle_type,
    lon,
    lat,
    stage,
    stage_info,
    times,
):
    """
    Add a VDTN mesh communication-radius polygon around a vehicle.
    """

    # Only show mesh communication during VDTN stages.
    if stage not in (3, 4):
        return

    ring = make_circle(
        lon=lon,
        lat=lat,
        radius_m=MESH_RADIUS_M,
        points=MESH_CIRCLE_POINTS,
    )

    mesh_ring_features.append({
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                ring
            ],
        },
        "properties": {
            "vehicle_id": vehicle_id,
            "vehicle_type": vehicle_type,
            "network_mode": "VDTN",
            "mesh_type": "Local VDTN Mesh",
            "radius_m": MESH_RADIUS_M,
            "scenario_stage": stage,
            "stage_label": stage_info["label"],
            "begin_time": times["begin_time"],
            "end_time": times["end_time"],
        },
    })


# ---------------------------------------------------------------------
# FMCG logistics truck
# ---------------------------------------------------------------------

truck_id = "FMCG-Truck-01"
truck_type = "FMCG Logistics Truck"


for stage_info in STAGES:

    stage = stage_info["stage"]

    times = stage_time(
        stage_times,
        stage,
    )

    # -------------------------------------------------------------
    # Determine truck route and position
    # -------------------------------------------------------------

    if stage == 0:

        route = original_coords
        fraction = 0.00

    elif stage == 1:

        route = original_coords
        fraction = 0.23

    elif stage == 2:

        route = original_coords
        fraction = 0.23

    elif stage == 3:

        route = original_coords
        fraction = 0.23

    elif stage == 4:

        route = original_coords
        fraction = 0.23

    elif stage == 5:

        route = reroute_coords
        fraction = 1.00

    else:

        route = original_coords
        fraction = 0.0

    lon, lat = interpolate_point(
        route,
        fraction,
    )

    # -------------------------------------------------------------
    # Network mode
    # -------------------------------------------------------------

    network_mode = (
        "VDTN"
        if stage in (3, 4)
        else "LTE/5G"
    )

    # -------------------------------------------------------------
    # Vehicle point
    # -------------------------------------------------------------

    vehicle_features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                lon,
                lat,
            ],
        },
        "properties": {
            "vehicle_id": truck_id,
            "vehicle_type": truck_type,
            "scenario_stage": stage,
            "stage_label": stage_info["label"],
            "network_mode": network_mode,
            "route_type": (
                "reroute"
                if stage == 5
                else "original"
            ),
            "begin_time": times["begin_time"],
            "end_time": times["end_time"],
        },
    })

    # -------------------------------------------------------------
    # NEW:
    # Add VDTN mesh communication ring
    # -------------------------------------------------------------

    add_mesh_ring(
        vehicle_id=truck_id,
        vehicle_type=truck_type,
        lon=lon,
        lat=lat,
        stage=stage,
        stage_info=stage_info,
        times=times,
    )


# ---------------------------------------------------------------------
# Fleeing / civilian vehicle
# ---------------------------------------------------------------------

fleeing_vehicle_id = "Civilian-Vehicle-01"
fleeing_vehicle_type = "Civilian Vehicle"


for stage_info in STAGES:

    stage = stage_info["stage"]

    # Fleeing vehicle only appears during cloudburst / VDTN stages.
    if stage not in (2, 3, 4):
        continue

    times = stage_time(
        stage_times,
        stage,
    )

    # -------------------------------------------------------------
    # Vehicle moves further along the route as hazard develops.
    # -------------------------------------------------------------

    if stage == 2:

        fraction = 0.32

    elif stage == 3:

        fraction = 0.38

    elif stage == 4:

        fraction = 0.43

    else:

        fraction = 0.32

    lon, lat = interpolate_point(
        original_coords,
        fraction,
    )

    network_mode = (
        "VDTN"
        if stage >= 3
        else "LTE/5G"
    )

    vehicle_features.append({
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                lon,
                lat,
            ],
        },
        "properties": {
            "vehicle_id": fleeing_vehicle_id,
            "vehicle_type": fleeing_vehicle_type,
            "scenario_stage": stage,
            "stage_label": stage_info["label"],
            "network_mode": network_mode,
            "route_type": "original",
            "begin_time": times["begin_time"],
            "end_time": times["end_time"],
        },
    })

    # -------------------------------------------------------------
    # NEW:
    # Add VDTN mesh ring during stages 3 and 4.
    # -------------------------------------------------------------

    add_mesh_ring(
        vehicle_id=fleeing_vehicle_id,
        vehicle_type=fleeing_vehicle_type,
        lon=lon,
        lat=lat,
        stage=stage,
        stage_info=stage_info,
        times=times,
    )


# ---------------------------------------------------------------------
# Write vehicle layer
# ---------------------------------------------------------------------

write_geojson(
    DATA_DIR / "vehicles.geojson",
    {
        "type": "FeatureCollection",
        "features": vehicle_features,
    },
)


# ---------------------------------------------------------------------
# Write mesh ring layer
# ---------------------------------------------------------------------

write_geojson(
    DATA_DIR / "mesh_rings.geojson",
    {
        "type": "FeatureCollection",
        "features": mesh_ring_features,
    },
)


# ---------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------

print("\n==============================================")
print("Generation complete")
print("==============================================")

print(f"Vehicles generated : {len(vehicle_features)}")
print(f"Mesh rings generated: {len(mesh_ring_features)}")
print(f"Mesh radius         : {MESH_RADIUS_M} m")

print("\nGenerated files:")

print("  data/nh544_original.geojson")
print("  data/nh544_reroute.geojson")
print("  data/flood_basin.geojson")
print("  data/vehicles.geojson")
print("  data/sensor_nodes.geojson")
print("  data/mesh_rings.geojson")

print("\nVDTN mesh rings are active during:")

for stage_info in STAGES:

    if stage_info["stage"] in (3, 4):

        print(
            f"  Stage {stage_info['stage']}: "
            f"{stage_info['label']}"
        )

print("\nDone.")