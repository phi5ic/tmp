import requests
import json
import os

print("Querying Overpass API for Kerala major highways (trunk & primary)...")
overpass_url = "http://overpass-api.de/api/interpreter"
overpass_query = """
[out:json][timeout:90];
area["name"="Kerala"]["admin_level"="4"]->.searchArea;
(
  way["highway"~"trunk|primary"](area.searchArea);
);
out geom;
"""

headers = {'User-Agent': 'Antigravity/1.0'}
response = requests.post(overpass_url, data={'data': overpass_query}, headers=headers)
if response.status_code != 200:
    print(f"Error: {response.status_code}")
    exit(1)

data = response.json()

features = []
seg_id = 0
for element in data['elements']:
    if element['type'] == 'way':
        coords = [[node['lon'], node['lat']] for node in element['geometry']]
        features.append({
            "type": "Feature",
            "properties": {
                "segment_id": f"KERALA-SEG-{seg_id}",
                "highway": element.get("tags", {}).get("highway", "unknown")
            },
            "geometry": {
                "type": "LineString",
                "coordinates": coords
            }
        })
        seg_id += 1

geojson = {
    "type": "FeatureCollection",
    "features": features
}

out_path = "qgis-demo/data/routes_source_kerala.geojson"
with open(out_path, "w") as f:
    json.dump(geojson, f)

print(f"Successfully saved {len(features)} road segments to {out_path}.")
