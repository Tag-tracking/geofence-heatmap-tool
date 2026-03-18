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
heat_data = []

def clean_coord(val):
    try:
        if pd.isna(val):
            return None
        val = str(val).strip()
        if val == "" or val.lower() in ["null", "none"]:
            return None
        return float(val)
    except:
        return None

for lat_raw, lon_raw in zip(points_df[lat_col], points_df[lon_col]):

    lat = clean_coord(lat_raw)
    lon = clean_coord(lon_raw)

    if lat is None or lon is None:
        continue

    if lat == 0 or lon == 0:
        continue

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        continue

    points.append(Point(lon, lat))
    heat_data.append([lat, lon])

st.write(f"Total rows: {len(points_df)}")
st.write(f"Valid GPS points used: {len(points)}")

# -----------------------------
# GEOFENCE AUTO-DETECTION (ROBUST)
# -----------------------------

geo_df = pd.read_csv(geo_file)

def build_polygons(coord_order):

    polys = []

    for _, row in geo_df.iterrows():

        zone = str(row.iloc[0]).strip()
        values = row.iloc[1:].dropna().values

        coords = []

        for i in range(0, len(values) - 1, 2):
            try:
                a = float(values[i])
                b = float(values[i + 1])

                if coord_order == "lonlat":
                    lon, lat = a, b
                else:
                    lat, lon = a, b

                coords.append((lon, lat))
            except:
                continue

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
        except:
            continue

    return polys


def count_hits(polygons, points):

    count = 0

    for poly in polygons:
        for p in points:
            if poly["polygon"].contains(p):
                count += 1

    return count


polygons_lonlat = build_polygons("lonlat")
polygons_latlon = build_polygons("latlon")

hits_lonlat = count_hits(polygons_lonlat, points)
hits_latlon = count_hits(polygons_latlon, points)

if hits_lonlat == 0 and hits_latlon == 0:
    st.warning("⚠️ No GPS points intersect geofences — check dataset alignment")

if hits_lonlat >= hits_latlon:
    polygons = polygons_lonlat
    st.success(f"Geofence format detected: lon, lat (hits: {hits_lonlat})")
else:
    polygons = polygons_latlon
    st.success(f"Geofence format detected: lat, lon (hits: {hits_latlon})")

# -----------------------------
# PROXIMITY ANALYSIS
# -----------------------------

def compute_stats(polygons, points):

    BUFFER_METERS = 5
    BUFFER_DEGREES = BUFFER_METERS / 111320

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

    return polygons

polygons = compute_stats(polygons, points)

st.write(f"Loaded {len(polygons)} valid geofences")

# -----------------------------
# ZONE CONTROLS
# -----------------------------

results = pd.DataFrame(polygons)
results["zone"] = results["zone"].astype(str)

all_zones = list(results["zone"].unique())

if "visible_zones" not in st.session_state:
    st.session_state.visible_zones = all_zones

col1, col2 = st.columns(2)

if col1.button("Select All"):
    st.session_state.visible_zones = all_zones

if col2.button("Clear All"):
    st.session_state.visible_zones = []

visible_zones = st.multiselect(
    "Select geofences to display",
    options=all_zones,
    key="visible_zones"
)

selected_zone = st.selectbox(
    "Highlight a zone",
    visible_zones if visible_zones else ["None"]
)

# -----------------------------
# MAP
# -----------------------------

center_lat = sum(p[1] for p in [(pt.y, pt.x) for pt in points]) / len(points)
center_lon = sum(p[0] for p in [(pt.y, pt.x) for pt in points]) / len(points)

m = folium.Map(location=[center_lat, center_lon], zoom_start=16)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri"
).add_to(m)

# -----------------------------
# HEATMAP
# -----------------------------

if show_heatmap:
    HeatMap(heat_data, radius=20, blur=15).add_to(m)

# -----------------------------
# DRAW GEOFENCES
# -----------------------------

if show_zones:

    for poly in polygons:

        if poly["zone"] not in visible_zones:
            continue

        coords = [(p[1], p[0]) for p in poly["polygon"].exterior.coords]

        color = "yellow" if poly["zone"] == selected_zone else "lime"

        folium.Polygon(
            coords,
            color=color,
            weight=4,
            fill=True,
            fill_opacity=0.15
        ).add_to(m)

        # buffer
        buffer_coords = [(p[1], p[0]) for p in poly["buffer"].exterior.coords]

        folium.PolyLine(
            buffer_coords,
            color="orange",
            weight=2,
            dash_array="6,6"
        ).add_to(m)

        c = poly["polygon"].centroid

        popup_html = f"""
        <b>Zone:</b> {poly['zone']}<br>
        <b>Inside:</b> {poly['count']}<br>
        <b>Within 5m:</b> {poly['near_count']}
        """

        # inside marker
        folium.Marker(
            [c.y, c.x],
            popup=popup_html,
            tooltip=popup_html,
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid grey;font-size:12px;line-height:22px'>{poly['count']}</div>"
            )
        ).add_to(m)

        # 🔥 5m marker
        folium.Marker(
            [c.y + 0.00006, c.x],
            tooltip=f"Within 5m: {poly['near_count']}",
            icon=folium.DivIcon(
                html=f"<div style='background:#ffe5b4;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid orange;font-size:12px;line-height:22px'>{poly['near_count']}</div>"
            )
        ).add_to(m)

# -----------------------------
# RENDER
# -----------------------------

st.subheader("Map")
components.html(m._repr_html_(), height=650)

# -----------------------------
# TABLE
# -----------------------------

results_table = results[
    results["zone"].isin(visible_zones)
][["zone", "count"]].sort_values("count", ascending=False)

st.subheader("Zone Infringement Ranking")
st.dataframe(results_table, use_container_width=True)
