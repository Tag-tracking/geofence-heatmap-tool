import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
from shapely.strtree import STRtree
from folium.plugins import HeatMap
import streamlit.components.v1 as components

st.set_page_config(layout="wide")

st.title("Geofence Heatmap Analyzer")

# -----------------------------
# FILE UPLOAD
# -----------------------------

points_file = st.file_uploader("Upload Heatmap CSV")
geo_file = st.file_uploader("Upload Geofence CSV")

show_heatmap = st.checkbox("Show Heatmap", True)
show_zones = st.checkbox("Show Geofences", True)

if not points_file or not geo_file:
    st.stop()

# -----------------------------
# LOAD HEATMAP DATA
# -----------------------------

points_df = pd.read_csv(points_file)

lat_col = [c for c in points_df.columns if "lat" in c.lower()][0]
lon_col = [c for c in points_df.columns if "lon" in c.lower()][0]

points = []

for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
    try:
        points.append(Point(float(lon), float(lat)))
    except:
        pass

# -----------------------------
# LOAD GEOFENCE CSV (YOUR FORMAT: lon, lat)
# -----------------------------

geo_df = pd.read_csv(geo_file)

polygons = []

for _, row in geo_df.iterrows():

    zone = str(row.iloc[0]).strip()
    values = row.iloc[1:].dropna().values

    coords = []

    # ✅ Your format: lon, lat pairs
    for i in range(0, len(values) - 1, 2):
        try:
            lon = float(values[i])
            lat = float(values[i + 1])

            coords.append((lon, lat))

        except:
            continue

    if len(coords) < 3:
        continue

    # close polygon
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    try:
        poly = Polygon(coords)

        if poly.is_valid:
            polygons.append({
                "zone": zone,
                "polygon": poly
            })

    except:
        continue

st.write(f"Loaded {len(polygons)} valid geofences")

# -----------------------------
# CALCULATE MAP BOUNDS (KEY FIX)
# -----------------------------

if len(polygons) > 0:
    all_bounds = [poly["polygon"].bounds for poly in polygons]

    min_lon = min(b[0] for b in all_bounds)
    min_lat = min(b[1] for b in all_bounds)
    max_lon = max(b[2] for b in all_bounds)
    max_lat = max(b[3] for b in all_bounds)

    map_bounds = [[min_lat, min_lon], [max_lat, max_lon]]
else:
    map_bounds = None

# -----------------------------
# MAP SETUP
# -----------------------------

center_lat = points_df[lat_col].mean()
center_lon = points_df[lon_col].mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=16
)

# 🔥 FORCE MAP TO SHOW GEOFENCES
if map_bounds:
    m.fit_bounds(map_bounds)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite"
).add_to(m)

# -----------------------------
# HEATMAP (RESTORED STRONG VISUAL)
# -----------------------------

if show_heatmap:

    heat_data = []

    for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
        try:
            heat_data.append([float(lat), float(lon)])
        except:
            pass

    if heat_data:
        HeatMap(
            heat_data,
            radius=20,
            blur=15,
            min_opacity=0.5
        ).add_to(m)

# -----------------------------
# DRAW GEOFENCES
# -----------------------------

if show_zones:

    for poly in polygons:

        coords = [(p[1], p[0]) for p in poly["polygon"].exterior.coords]

        folium.Polygon(
            coords,
            color="lime",
            weight=4,
            fill=True,
            fill_opacity=0.2
        ).add_to(m)

# -----------------------------
# RENDER MAP
# -----------------------------

st.subheader("Map")

components.html(
    m._repr_html_(),
    height=650
)
