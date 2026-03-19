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
    st.warning("Please upload both files")
    st.stop()

points_df = pd.read_csv(points_file)
geo_df = pd.read_csv(geo_file)

# -----------------------------
# DETECT LAT/LON COLUMNS
# -----------------------------
lat_col = None
lon_col = None

for c in points_df.columns:
    cl = c.lower()
    if "lat" in cl:
        lat_col = c
    if "lon" in cl or "lng" in cl:
        lon_col = c

if lat_col is None or lon_col is None:
    st.error("Could not detect latitude/longitude columns")
    st.stop()

# -----------------------------
# PARSE POINTS
# -----------------------------
points = []
heat_data = []

for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
    try:
        lat = float(lat)
        lon = float(lon)

        if -90 <= lat <= 90 and -180 <= lon <= 180:
            pt = Point(lon, lat)
            points.append(pt)
            heat_data.append([lat, lon])
    except:
        continue

if len(heat_data) == 0:
    st.error("No valid GPS points found")
    st.stop()

st.success(f"Valid GPS points used: {len(heat_data)}")

center_lat = sum(p[0] for p in heat_data) / len(heat_data)
center_lon = sum(p[1] for p in heat_data) / len(heat_data)

# -----------------------------
# BUILD GEOFENCES (ROBUST)
# -----------------------------
def build_polygons():

    polys = []

    for _, row in geo_df.iterrows():

        zone = str(row.iloc[0]).strip()
        values = row.iloc[1:].dropna().values

        coords_lonlat = []
        coords_latlon = []

        for i in range(0, len(values)-1, 2):
            try:
                a = float(values[i])
                b = float(values[i+1])

                coords_lonlat.append((a, b))  # lon, lat
                coords_latlon.append((b, a))  # lon, lat flipped
            except:
                continue

        # Try BOTH interpretations
        for coords in [coords_lonlat, coords_latlon]:

            if len(coords) < 3:
                continue

            if coords[0] != coords[-1]:
                coords.append(coords[0])

            try:
                poly = Polygon(coords)

                if poly.is_valid:
                    polys.append({
                        "zone": zone,
                        "polygon": poly
                    })
                    break
            except:
                continue

    return polys

polygons = build_polygons()

if len(polygons) == 0:
    st.error("No valid geofences detected")
    st.stop()

st.success(f"Loaded {len(polygons)} geofences")

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
# UI CONTROLS
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
m = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles=None)

# FIXED TILE PROVIDERS
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri Satellite",
    name="Satellite",
    control=True
).add_to(m)

folium.TileLayer(
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr="OpenStreetMap",
    name="Street",
    control=True
).add_to(m)

folium.LayerControl().add_to(m)

# HEATMAP
if show_heatmap:
    HeatMap(heat_data, radius=18, blur=12).add_to(m)

# GEOFENCES
if show_zones:

    for poly in polygons:

        if poly["zone"] not in selected_zones:
            continue

        coords = [(y, x) for x, y in poly["polygon"].exterior.coords]

        color = "yellow" if poly["zone"] == highlight_zone else "lime"

        folium.Polygon(
            coords,
            color=color,
            weight=3,
            fill=True,
            fill_opacity=0.2
        ).add_to(m)

        # 5m buffer
        buffer_coords = [(y, x) for x, y in poly["buffer"].exterior.coords]

        folium.PolyLine(
            buffer_coords,
            color="orange",
            weight=2,
            dash_array="5,5"
        ).add_to(m)

        c = poly["polygon"].centroid

        popup_html = f"""
        <div style="font-size:13px;padding:6px;min-width:140px;">
            <b>{poly['zone']}</b><br>
            Inside: {poly['count']}<br>
            Within 5m: {poly['near_count']}
        </div>
        """

        folium.Marker(
            [c.y, c.x],
            popup=folium.Popup(popup_html),
            tooltip=popup_html,
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:24px;height:24px;text-align:center;border:1px solid black'>{poly['count']}</div>"
            )
        ).add_to(m)

        folium.Marker(
            [c.y + 0.00005, c.x],
            tooltip=f"5m: {poly['near_count']}",
            icon=folium.DivIcon(
                html=f"<div style='background:#ffe5b4;border-radius:50%;width:24px;height:24px;text-align:center;border:1px solid orange'>{poly['near_count']}</div>"
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
]).sort_values("inside", ascending=False)

st.dataframe(df, use_container_width=True)

st.download_button(
    "Download CSV",
    df.to_csv(index=False),
    "geofence_counts.csv"
)

# -----------------------------
# DOWNLOAD MAP
# -----------------------------
if st.button("Download Interactive Map"):

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    m.save(tmp.name)

    with open(tmp.name, "rb") as f:
        st.download_button(
            "Download Map",
            f,
            "map.html"
        )
