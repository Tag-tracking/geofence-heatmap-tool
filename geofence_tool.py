import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
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
# LOAD HEATMAP
# -----------------------------
points_df = pd.read_csv(points_file)

lat_col = [c for c in points_df.columns if "lat" in c.lower()][0]
lon_col = [c for c in points_df.columns if "lon" in c.lower()][0]

points = []
heat_data = []

for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
    try:
        lat = float(lat)
        lon = float(lon)

        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue

        points.append(Point(lon, lat))
        heat_data.append([lat, lon])

    except:
        continue

st.write(f"Valid GPS points used: {len(points)}")

center_lat = sum(p[0] for p in heat_data) / len(heat_data)
center_lon = sum(p[1] for p in heat_data) / len(heat_data)

# -----------------------------
# LOAD GEOFENCES
# -----------------------------
geo_df = pd.read_csv(geo_file)

def build_polygons(latlon_mode=False):

    polygons = []

    for _, row in geo_df.iterrows():

        zone = str(row.iloc[0]).strip()
        values = row.iloc[1:].dropna().values

        coords = []

        for i in range(0, len(values)-1, 2):
            try:
                a = float(values[i])
                b = float(values[i+1])

                if not latlon_mode:
                    lon, lat = a, b
                else:
                    lat, lon = a, b

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

    return polygons

polygons = build_polygons(latlon_mode=False)

if len(polygons) == 0:
    polygons = build_polygons(latlon_mode=True)
    st.warning("Fallback to lat/lon parsing")

st.write(f"Loaded {len(polygons)} geofences")

# -----------------------------
# PROXIMITY
# -----------------------------
BUFFER_DEGREES = 5 / 111320

for poly in polygons:

    inside = 0
    near = 0

    buffer_poly = poly["polygon"].buffer(BUFFER_DEGREES)

    for p in points:
        if poly["polygon"].contains(p):
            inside += 1
        elif buffer_poly.contains(p):
            near += 1

    poly["count"] = inside
    poly["near_count"] = near
    poly["buffer"] = buffer_poly

# -----------------------------
# ZONE FILTER
# -----------------------------
zones = [p["zone"] for p in polygons]

selected_zones = st.multiselect(
    "Select geofences to display",
    zones,
    default=zones
)

highlight_zone = st.selectbox(
    "Highlight a zone",
    ["None"] + zones
)

# -----------------------------
# MAP
# -----------------------------
m = folium.Map(location=[center_lat, center_lon], zoom_start=16)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri Satellite",
    max_zoom=21
).add_to(m)

# heatmap
if show_heatmap:
    HeatMap(
        heat_data,
        radius=25,
        blur=12,
        min_opacity=0.4
    ).add_to(m)

# geofences
if show_zones:

    for poly in polygons:

        if poly["zone"] not in selected_zones:
            continue

        coords = [(y, x) for x, y in poly["polygon"].exterior.coords]

        color = "yellow" if poly["zone"] == highlight_zone else "lime"

        folium.Polygon(
            coords,
            color=color,
            weight=4,
            fill=True,
            fill_opacity=0.15
        ).add_to(m)

        # buffer
        buffer_coords = [(y, x) for x, y in poly["buffer"].exterior.coords]

        folium.PolyLine(
            buffer_coords,
            color="orange",
            weight=2,
            dash_array="6,6"
        ).add_to(m)

        c = poly["polygon"].centroid

        # hover popup (tooltip)
        popup = f"""
        <div style="font-size:14px;padding:8px;min-width:140px;">
            <b>{poly['zone']}</b><br>
            <hr style="margin:4px 0;">
            Inside: <b>{poly['count']}</b><br>
            Within 5m: <b>{poly['near_count']}</b>
        </div>
        """

        # inside marker
        folium.Marker(
            [c.y, c.x],
            tooltip=popup,
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    background:white;
                    border-radius:50%;
                    width:26px;
                    height:26px;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    border:2px solid black;
                    font-size:12px;
                    font-weight:bold;
                ">
                    {poly['count']}
                </div>
                """
            )
        ).add_to(m)

        # 5m marker
        folium.Marker(
            [c.y + 0.00006, c.x],
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    background:#ffe5b4;
                    border-radius:50%;
                    width:24px;
                    height:24px;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    border:2px solid orange;
                    font-size:11px;
                ">
                    {poly['near_count']}
                </div>
                """
            )
        ).add_to(m)

# -----------------------------
# RENDER
# -----------------------------
components.html(m._repr_html_(), height=650)

# -----------------------------
# BREAKDOWN TABLE (ADDED BACK)
# -----------------------------
st.subheader("Geofence Breakdown")

results_df = pd.DataFrame([
    {
        "zone": p["zone"],
        "inside": p["count"],
        "within_5m": p["near_count"]
    }
    for p in polygons
]).sort_values("inside", ascending=False)

st.dataframe(results_df, use_container_width=True)

st.download_button(
    "Download CSV",
    results_df.to_csv(index=False),
    "geofence_counts.csv"
)

import tempfile

st.subheader("Export")

tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
m.save(tmp.name)

with open(tmp.name, "rb") as f:
    st.download_button(
        "Download Interactive Map (Client)",
        f,
        file_name="geofence_map.html"
    )
