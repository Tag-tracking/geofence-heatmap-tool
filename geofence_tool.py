import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
from folium.plugins import HeatMap
import streamlit.components.v1 as components

st.set_page_config(layout="wide")

st.title("Geofence Heatmap Analyzer")

# Upload files
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
# LOAD GEOFENCE CSV
# -----------------------------

geo_df = pd.read_csv(geo_file)

polygons = []

for _, row in geo_df.iterrows():

    zone = str(row.iloc[0]).strip()
    coords = []

    values = row.iloc[1:].dropna().values

    for i in range(0, len(values) - 1, 2):

        try:
            lon = float(values[i])
            lat = float(values[i + 1])

            if abs(lat) > 90 or abs(lon) > 180:
                continue

            coords.append((lon, lat))

        except:
            continue

    coords = list(dict.fromkeys(coords))

    if len(coords) >= 3:

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
            pass

# -----------------------------
# PROXIMITY ANALYSIS
# -----------------------------

BUFFER_METERS = 5
BUFFER_DEGREES = BUFFER_METERS / 111320

for poly in polygons:

    inside_count = 0
    near_count = 0

    buffer_poly = poly["polygon"].buffer(BUFFER_DEGREES)

    for p in points:

        if poly["polygon"].contains(p):
            inside_count += 1

        elif buffer_poly.contains(p):
            near_count += 1

    poly["count"] = inside_count
    poly["near_count"] = near_count
    poly["buffer"] = buffer_poly

# -----------------------------
# RESULTS TABLE
# -----------------------------

results = pd.DataFrame(polygons)

if len(results) == 0:
    st.error("No geofences detected in file.")
    st.stop()

results["zone"] = results["zone"].astype(str)

# -----------------------------
# ZONE VISIBILITY CONTROLS
# -----------------------------

all_zones = list(results["zone"].unique())

if "visible_zones" not in st.session_state:
    st.session_state.visible_zones = all_zones

col1, col2 = st.columns(2)

with col1:
    if st.button("Select All"):
        st.session_state.visible_zones = all_zones

with col2:
    if st.button("Clear All"):
        st.session_state.visible_zones = []

visible_zones = st.multiselect(
    "Select geofences to display",
    options=all_zones,
    default=st.session_state.visible_zones
)

st.session_state.visible_zones = visible_zones

# -----------------------------
# ZONE HIGHLIGHT
# -----------------------------

selected_zone = st.selectbox(
    "Highlight a zone",
    visible_zones if visible_zones else ["None"]
)

# -----------------------------
# MAP
# -----------------------------

center_lat = points_df[lat_col].mean()
center_lon = points_df[lon_col].mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=16
)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite"
).add_to(m)

# -----------------------------
# HEATMAP
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

        if poly["zone"] not in visible_zones:
            continue

        coords = [(p[1], p[0]) for p in poly["polygon"].exterior.coords]

        if poly["zone"] == selected_zone:
            color = "yellow"
            weight = 6
        else:
            color = "red"
            weight = 3

        folium.Polygon(
            coords,
            color=color,
            weight=weight,
            fill=False
        ).add_to(m)

        # dashed proximity boundary
        buffer_coords = [(p[1], p[0]) for p in poly["buffer"].exterior.coords]

        folium.PolyLine(
            buffer_coords,
            color="orange",
            weight=2,
            dash_array="6,6"
        ).add_to(m)

        c = poly["polygon"].centroid

        # main geofence count
        folium.Marker(
            [c.y, c.x],
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid grey;font-size:12px;line-height:22px'>{poly['count']}</div>"
            )
        ).add_to(m)

        # proximity count
        folium.Marker(
            [c.y + 0.00003, c.x],
            icon=folium.DivIcon(
                html=f"<div style='background:#ffe5b4;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid orange;font-size:12px;line-height:22px'>{poly['near_count']}</div>"
            )
        ).add_to(m)

# -----------------------------
# RENDER MAP
# -----------------------------

st.subheader("Map")

components.html(
    m._repr_html_(),
    height=650
)

# -----------------------------
# RESULTS TABLE
# -----------------------------

results_table = results[results["zone"].isin(visible_zones)][["zone", "count"]].sort_values(
    "count",
    ascending=False
).reset_index(drop=True)

st.subheader("Zone Infringement Ranking")

st.dataframe(results_table, use_container_width=True)

# -----------------------------
# DOWNLOAD RESULTS
# -----------------------------

st.download_button(
    "Download Zone Counts CSV",
    results_table.to_csv(index=False),
    "zone_counts.csv"
)
