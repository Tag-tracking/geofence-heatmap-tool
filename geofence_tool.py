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

center_lat = sum(p[0] for p in heat_data) / len(heat_data)
center_lon = sum(p[1] for p in heat_data) / len(heat_data)

st.success(f"Valid GPS points: {len(heat_data)}")

# -----------------------------
# GEOFENCES
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
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=15,
    tiles=None
)

folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri Satellite",
    max_zoom=21
).add_to(m)

# -----------------------------
# HEATMAP
# -----------------------------
HeatMap(
    heat_data,
    radius=25,
    blur=10,
    min_opacity=0.4
).add_to(m)

# -----------------------------
# GEOFENCES
# -----------------------------
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

    # Popup
    popup_html = f"""
    <div style="font-size:14px;padding:10px;min-width:160px;">
        <b>{poly['zone']}</b><br>
        <hr style="margin:4px 0;">
        Inside: <b>{poly['count']}</b><br>
        Within 5m: <b>{poly['near_count']}</b>
    </div>
    """

    c = poly["polygon"].centroid

    # Main count marker (centered)
    folium.Marker(
        [c.y, c.x],
        popup=folium.Popup(popup_html, max_width=250),
        tooltip=poly["zone"],
        icon=folium.DivIcon(
            html=f"""
            <div style="
                background:white;
                border-radius:50%;
                width:28px;
                height:28px;
                display:flex;
                align-items:center;
                justify-content:center;
                border:2px solid black;
                font-size:13px;
                font-weight:bold;
            ">
                {poly['count']}
            </div>
            """
        )
    ).add_to(m)

    # 5m marker (orange)
    folium.Marker(
        [c.y + 0.00006, c.x],
        tooltip=f"5m: {poly['near_count']}",
        icon=folium.DivIcon(
            html=f"""
            <div style="
                background:#ffe5b4;
                border-radius:50%;
                width:26px;
                height:26px;
                display:flex;
                align-items:center;
                justify-content:center;
                border:2px solid orange;
                font-size:12px;
            ">
                {poly['near_count']}
            </div>
            """
        )
    ).add_to(m)

# -----------------------------
# RENDER
# -----------------------------
components.html(m._repr_html_(), height=700)

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
# HTML DOWNLOAD
# -----------------------------
if st.button("Download Interactive Map (Send to Client)"):

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    m.save(tmp.name)

    with open(tmp.name, "rb") as f:
        st.download_button(
            label="Download Map File",
            data=f,
            file_name="geofence_map.html",
            mime="text/html"
        )
