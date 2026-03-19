import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
from folium.plugins import HeatMap
import streamlit.components.v1 as components
import tempfile

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

points_df = pd.read_csv(points_file)
geo_df = pd.read_csv(geo_file)

# -----------------------------
# HEATMAP PARSING (STRICT)
# -----------------------------
lat_col = [c for c in points_df.columns if "lat" in c.lower()][0]
lon_col = [c for c in points_df.columns if "lon" in c.lower() or "lng" in c.lower()][0]

heat_data = []
points = []

for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
    try:
        lat = float(lat)
        lon = float(lon)

        if -90 <= lat <= 90 and -180 <= lon <= 180:
            heat_data.append([lat, lon])
            points.append(Point(lon, lat))
    except:
        continue

if len(heat_data) == 0:
    st.error("No valid heatmap points")
    st.stop()

center_lat = sum(p[0] for p in heat_data) / len(heat_data)
center_lon = sum(p[1] for p in heat_data) / len(heat_data)

st.success(f"Valid GPS points used: {len(heat_data)}")

# -----------------------------
# GEOFENCE PARSING (FIXED)
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
            polygons.append({
                "zone": zone,
                "polygon": poly
            })

if len(polygons) == 0:
    st.error("No valid geofences detected")
    st.stop()

st.success(f"Loaded {len(polygons)} geofences")

# -----------------------------
# PROXIMITY (5m)
# -----------------------------
BUFFER = 5 / 111320

for poly in polygons:

    inside = 0
    near = 0

    buffer_poly = poly["polygon"].buffer(BUFFER)

    for p in points:
        if poly["polygon"].contains(p):
            inside += 1
        elif buffer_poly.contains(p):
            near += 1

    poly["count"] = inside
    poly["near_count"] = near
    poly["buffer"] = buffer_poly

# -----------------------------
# UI
# -----------------------------
zones = [p["zone"] for p in polygons]

selected = st.multiselect(
    "Select geofences to display",
    zones,
    default=zones
)

highlight = st.selectbox(
    "Highlight a zone",
    ["None"] + zones
)

# -----------------------------
# MAP
# -----------------------------
m = folium.Map(location=[center_lat, center_lon], zoom_start=15)

folium.TileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite"
).add_to(m)

folium.LayerControl().add_to(m)

# Heatmap
if show_heatmap:
    HeatMap(heat_data, radius=18, blur=12).add_to(m)

# Geofences
if show_zones:

    for poly in polygons:

        if poly["zone"] not in selected:
            continue

        coords = [(y, x) for x, y in poly["polygon"].exterior.coords]

        color = "yellow" if poly["zone"] == highlight else "lime"

        folium.Polygon(
            coords,
            color=color,
            weight=3,
            fill=True,
            fill_opacity=0.2
        ).add_to(m)

        buffer_coords = [(y, x) for x, y in poly["buffer"].exterior.coords]

        folium.PolyLine(
            buffer_coords,
            color="orange",
            weight=2,
            dash_array="5,5"
        ).add_to(m)

        c = poly["polygon"].centroid

        popup = f"""
        <b>{poly['zone']}</b><br>
        Inside: {poly['count']}<br>
        5m: {poly['near_count']}
        """

        folium.Marker(
            [c.y, c.x],
            popup=popup,
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:24px;height:24px;text-align:center;border:1px solid black'>{poly['count']}</div>"
            )
        ).add_to(m)

# -----------------------------
# RENDER
# -----------------------------
components.html(m._repr_html_(), height=650)

# -----------------------------
# TABLE
# -----------------------------
st.subheader("Geofence Breakdown")

df = pd.DataFrame([
    {
        "zone": p["zone"],
        "inside": p["count"],
        "within_5m": p["near_count"]
    }
    for p in polygons
])

st.dataframe(df, use_container_width=True)

st.download_button(
    "Download CSV",
    df.to_csv(index=False),
    "geofence_counts.csv"
)
