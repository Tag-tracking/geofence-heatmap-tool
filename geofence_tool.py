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
# LOAD HEATMAP DATA (ROBUST)
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
# LOAD GEOFENCE CSV (lon, lat)
# -----------------------------

geo_df = pd.read_csv(geo_file)

polygons = []

for _, row in geo_df.iterrows():

    zone = str(row.iloc[0]).strip()
    values = row.iloc[1:].dropna().values

    coords = []

    for i in range(0, len(values) - 1, 2):
        try:
            lon = float(values[i])
            lat = float(values[i + 1])
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
            polygons.append({
                "zone": zone,
                "polygon": poly
            })
    except:
        continue

# -----------------------------
# SMART ALIGNMENT (SAFE)
# -----------------------------

def distance_meters(lat1, lon1, lat2, lon2):
    return ((lat1 - lat2) * 111320) ** 2 + ((lon1 - lon2) * 111320) ** 2

if heat_data and polygons:

    avg_lat = sum(p[0] for p in heat_data) / len(heat_data)
    avg_lon = sum(p[1] for p in heat_data) / len(heat_data)

    geo_lat = sum(p["polygon"].centroid.y for p in polygons) / len(polygons)
    geo_lon = sum(p["polygon"].centroid.x for p in polygons) / len(polygons)

    dist = distance_meters(avg_lat, avg_lon, geo_lat, geo_lon)

    st.write(f"Alignment distance: {int(dist**0.5)} meters")

    if dist**0.5 > 200:

        st.warning("Applying heatmap alignment (datasets were far apart)")

        lat_offset = geo_lat - avg_lat
        lon_offset = geo_lon - avg_lon

        aligned_heat_data = []
        aligned_points = []

        for lat, lon in heat_data:
            new_lat = lat + lat_offset
            new_lon = lon + lon_offset

            aligned_heat_data.append([new_lat, new_lon])
            aligned_points.append(Point(new_lon, new_lat))

        heat_data = aligned_heat_data
        points = aligned_points

    else:
        st.success("No alignment needed (datasets already aligned)")

# -----------------------------
# PROXIMITY ANALYSIS
# -----------------------------

def compute_stats(_polygons, _points):

    BUFFER_METERS = 5
    BUFFER_DEGREES = BUFFER_METERS / 111320

    tree = STRtree(_points)

    for poly in _polygons:

        inside_count = 0
        near_count = 0

        buffer_poly = poly["polygon"].buffer(BUFFER_DEGREES)

        candidate_indexes = tree.query(buffer_poly)

        for idx in candidate_indexes:

            p = _points[idx]

            if poly["polygon"].contains(p):
                inside_count += 1
            elif buffer_poly.contains(p):
                near_count += 1

        poly["count"] = inside_count
        poly["near_count"] = near_count
        poly["buffer"] = buffer_poly

    return _polygons


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
# COMBINED MAP BOUNDS
# -----------------------------

bounds_list = []

for poly in polygons:
    b = poly["polygon"].bounds
    bounds_list.append((b[1], b[0]))
    bounds_list.append((b[3], b[2]))

for lat, lon in heat_data:
    bounds_list.append((lat, lon))

if bounds_list:
    min_lat = min(p[0] for p in bounds_list)
    max_lat = max(p[0] for p in bounds_list)
    min_lon = min(p[1] for p in bounds_list)
    max_lon = max(p[1] for p in bounds_list)

    map_bounds = [[min_lat, min_lon], [max_lat, max_lon]]
else:
    map_bounds = None

# -----------------------------
# MAP
# -----------------------------

center_lat = points_df[lat_col].mean()
center_lon = points_df[lon_col].mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=16)

if map_bounds:
    m.fit_bounds(map_bounds)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri"
).add_to(m)

# -----------------------------
# HEATMAP
# -----------------------------

if show_heatmap and heat_data:

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
        <b>Inside fixes:</b> {poly['count']}<br>
        <b>Within 5m:</b> {poly['near_count']}
        """

        folium.Marker(
            [c.y, c.x],
            popup=folium.Popup(popup_html, max_width=250),
            tooltip=popup_html,
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid grey;font-size:12px;line-height:22px'>{poly['count']}</div>"
            )
        ).add_to(m)

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
