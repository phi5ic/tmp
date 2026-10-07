from math import cos, sin, pi, radians

def make_circle(lon, lat, radius_m=150, points=48):
    """
    Create an approximate 150 m radius circle around a lon/lat point.
    Returns GeoJSON polygon coordinates.
    """
    coords = []

    # Approximate metres → degrees
    lat_scale = 111_320
    lon_scale = 111_320 * cos(radians(lat))

    for i in range(points + 1):
        angle = 2 * pi * i / points

        dx = radius_m * cos(angle)
        dy = radius_m * sin(angle)

        new_lon = lon + dx / lon_scale
        new_lat = lat + dy / lat_scale

        coords.append([new_lon, new_lat])

    return coords