import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
from folium.plugins import HeatMap
import streamlit.components.v1 as components

st.set_page_config(layout="wide")
st.title("Geofence Heatmap Analyzer")

# -----------------------------
# UPLOAD
# -----------------------------
points_file = st.file_uploader("Upload Heatmap CSV")
geo_file = st.file_uploader("Upload Geofence CSV")

if not points_file or not geo_file:
    st.stop()

points_df = pd.read_csv(points_file)
geo_df = pd.read_csv(geo_file)

# -----------------------------
# HEATMAP
# -----------------------------
lat_col = [c for c in points_df.columns if "lat" in c.lower()][0]
lon_col = [c for c in points_df.columns if "lon" in c.lower() or "lng" in c.lower()][0]

heat_data = []
points = []

for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
    try:
        lat = float(lat)
        lon = float(lon)
        heat_data.append([lat, lon])
        points.append(Point(lon, lat))
    except:
        continue

st.write(f"DEBUG: Heat points = {len(heat_data)}")

center_lat = sum(p[0] for p in heat_data) / len(heat_data)
center_lon = sum(p[1] for p in heat_data) / len(heat_data)

# -----------------------------
# GEOFENCES (STRICT lon,lat)
# -----------------------------
polygons = []

for _, row in geo_df.iterrows():

    zone = str(row.iloc[0]).strip()
    values = row.iloc[1:].dropna().values

    coords = []

    for i in range(0, len(values)-1, 2):
        try:
            lon = float(values[i])
            lat = float(values[i+1])
            coords.append((lon, lat))
        except:
            continue

    if len(coords) >= 3:
        if coords[0] != coords[-1]:
            coords.append(coords[0])

        poly = Polygon(coords)

        if poly.is_valid:
            polygons.append({"zone": zone, "polygon": poly})

st.write(f"DEBUG: Polygons = {len(polygons)}")

# -----------------------------
# MAP (IMPORTANT FIX)
# -----------------------------
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=15,
    tiles=None  # 🔥 CRITICAL FIX
)

# Satellite only (clean + reliable)
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
).add_to(m)

# -----------------------------
# HEATMAP (VISIBLE AGAIN)
# -----------------------------
HeatMap(
    heat_data,
    radius=25,      # 🔥 bigger = visible
    blur=10,
    min_opacity=0.4
).add_to(m)

# -----------------------------
# GEOFENCES (VISIBLE AGAIN)
# -----------------------------
BUFFER = 5 / 111320

for poly in polygons:

    buffer_poly = poly["polygon"].buffer(BUFFER)

    coords = [(y, x) for x, y in poly["polygon"].exterior.coords]

    folium.Polygon(
        coords,
        color="lime",
        weight=5,        # 🔥 thicker
        fill=True,
        fill_opacity=0.2
    ).add_to(m)

    buffer_coords = [(y, x) for x, y in buffer_poly.exterior.coords]

    folium.PolyLine(
        buffer_coords,
        color="orange",
        weight=3
    ).add_to(m)

# -----------------------------
# RENDER
# -----------------------------
components.html(m._repr_html_(), height=700)
