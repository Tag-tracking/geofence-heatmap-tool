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

points_df = pd.read_csv(points_file)
geo_df = pd.read_csv(geo_file, header=None)
geo_df = geo_df.astype(str)

# Detect lat/lon columns
lat_col = [c for c in points_df.columns if "lat" in c.lower()][0]
lon_col = [c for c in points_df.columns if "lon" in c.lower()][0]

# Build shapely points
points = []
for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
    try:
        points.append(Point(float(lon), float(lat)))
    except:
        pass

# Parse geofences
polygons = []

for row in geo_df.iloc[:,0]:

    parts = str(row).replace('"','').split(",")

    if len(parts) < 10:
        continue

    zone = parts[1]
    coords = []

    i = 5
    while i < len(parts)-1:

        try:
            lon = float(parts[i])
            lat = float(parts[i+1])

            # skip clearly invalid points
            if lon == 0 and lat == 0:
                i += 2
                continue

            if abs(lat) > 90 or abs(lon) > 180:
                i += 2
                continue

            coords.append((lon, lat))

        except:
            pass

        i += 2

    # create polygon only if valid
    if len(coords) >= 3:
        try:
            poly = Polygon(coords)
            if poly.is_valid:
                polygons.append({
                    "zone": zone,
                    "polygon": poly
                })
        except:
            pass
# Count infringements
for poly in polygons:

    count = 0

    for p in points:
        if poly["polygon"].contains(p):
            count += 1

    poly["count"] = count

results = pd.DataFrame(polygons)

if len(results) == 0:
    st.error("No geofences detected in file.")
    st.stop()

results["zone"] = results["zone"].astype(str)

results_table = results[["zone","count"]].sort_values(
    "count",
    ascending=False
).reset_index(drop=True)

selected_zone = st.selectbox(
    "Highlight a zone",
    results_table["zone"]
)

# Map center
center_lat = points_df[lat_col].mean()
center_lon = points_df[lon_col].mean()

m = folium.Map(
    location=[center_lat,center_lon],
    zoom_start=16
)

# Satellite imagery
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satellite"
).add_to(m)

# Heatmap
if show_heatmap:

    heat_data = []

    for lat, lon in zip(points_df[lat_col], points_df[lon_col]):
        try:
            heat_data.append([float(lat), float(lon)])
        except:
            pass

    if len(heat_data) > 0:

        HeatMap(
            heat_data,
            radius=20,
            blur=15,
            min_opacity=0.5
        ).add_to(m)

# Draw polygons
if show_zones:

    for poly in polygons:

        coords = [(lat, lon) for lon, lat in poly["polygon"].exterior.coords]

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

        c = poly["polygon"].centroid

        folium.Marker(
            [c.y,c.x],
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid grey;font-size:12px;line-height:22px'>{poly['count']}</div>"
            )
        ).add_to(m)

# Render map
st.subheader("Map")

components.html(
    m._repr_html_(),
    height=650
)

# Table
st.subheader("Zone Infringement Ranking")

st.dataframe(results_table, use_container_width=True)

# Download CSV
st.download_button(
    "Download Zone Counts CSV",
    results_table.to_csv(index=False),
    "zone_counts.csv"

)
















