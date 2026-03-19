import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import tempfile

st.set_page_config(layout="wide")

st.title("Geofence Heatmap Tool")

# =========================
# FILE UPLOADS
# =========================
fixes_file = st.file_uploader("Upload Fixes CSV", type=["csv"])
geo_file = st.file_uploader("Upload Geofences CSV", type=["csv"])

if fixes_file and geo_file:

    df = pd.read_csv(fixes_file)
    geo_df = pd.read_csv(geo_file)

    st.success(f"Valid GPS points used: {len(df)}")

    # =========================
    # DETECT LAT/LON FORMAT
    # =========================
    def detect_lat_lon(df):
        cols = df.columns.tolist()
        for lat in ["lat", "latitude", "Latitude"]:
            for lon in ["lon", "lng", "longitude", "Longitude"]:
                if lat in cols and lon in cols:
                    return lat, lon
        return cols[0], cols[1]

    lat_col, lon_col = detect_lat_lon(df)

    df = df[[lat_col, lon_col]].dropna()
    df.columns = ["lat", "lon"]

    points = [Point(xy) for xy in zip(df["lon"], df["lat"])]

    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()

    # =========================
    # MAP
    # =========================
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=16,
        control_scale=True,
        tiles=None
    )

    # Satellite (deep zoom, no grey tiles)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="Satellite",
        max_zoom=21
    ).add_to(m)

    folium.LayerControl().add_to(m)

    # =========================
    # HEATMAP
    # =========================
    heat_data = df[["lat", "lon"]].values.tolist()
    HeatMap(heat_data, radius=8).add_to(m)

    # =========================
    # LOAD GEOFENCES
    # =========================
    polygons = []

    for name, group in geo_df.groupby("zone"):
        coords = list(zip(group["lon"], group["lat"]))
        poly = Polygon(coords)

        polygons.append({
            "zone": name,
            "polygon": poly,
            "count": 0,
            "near_count": 0
        })

    st.success(f"Loaded {len(polygons)} geofences")

    # =========================
    # COUNT POINTS
    # =========================
    for pt in points:
        for poly in polygons:
            if poly["polygon"].contains(pt):
                poly["count"] += 1
            elif poly["polygon"].buffer(0.00005).contains(pt):  # ~5m
                poly["near_count"] += 1

    # =========================
    # UI SELECT
    # =========================
    zones = [p["zone"] for p in polygons]

    selected = st.multiselect(
        "Select geofences to display",
        zones,
        default=zones
    )

    # =========================
    # DRAW GEOFENCES
    # =========================
    for poly in polygons:
        if poly["zone"] not in selected:
            continue

        coords = [(y, x) for x, y in poly["polygon"].exterior.coords]

        # Main geofence
        folium.Polygon(
            locations=coords,
            color="green",
            weight=3,
            fill=True,
            fill_opacity=0.2
        ).add_to(m)

        # 5m buffer
        buffer_coords = [(y, x) for x, y in poly["polygon"].buffer(0.00005).exterior.coords]

        folium.Polygon(
            locations=buffer_coords,
            color="orange",
            weight=2,
            dash_array="5,5",
            fill=False
        ).add_to(m)

        # Center point
        c = poly["polygon"].centroid

        # Popup
        popup_html = f"""
        <div style="font-size:14px; padding:10px; min-width:160px;">
            <b>{poly['zone']}</b><br>
            <hr>
            Inside: {poly['count']}<br>
            Within 5m: {poly['near_count']}
        </div>
        """

        folium.Marker(
            [c.y, c.x],
            popup=folium.Popup(popup_html, max_width=250),
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

        # 5m label (orange)
        folium.Marker(
            [c.y + 0.00003, c.x],
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    background:orange;
                    border-radius:50%;
                    width:22px;
                    height:22px;
                    display:flex;
                    align-items:center;
                    justify-content:center;
                    font-size:11px;
                    font-weight:bold;
                ">
                    {poly['near_count']}
                </div>
                """
            )
        ).add_to(m)

    # =========================
    # DISPLAY MAP
    # =========================
    st_folium(m, width=1400, height=700)

    # =========================
    # BREAKDOWN TABLE
    # =========================
    st.subheader("Geofence Breakdown")

    breakdown = pd.DataFrame([
        {
            "zone": p["zone"],
            "inside": p["count"],
            "within_5m": p["near_count"]
        }
        for p in polygons if p["zone"] in selected
    ])

    st.dataframe(breakdown)

    # =========================
    # HTML EXPORT
    # =========================
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    m.save(tmp.name)

    with open(tmp.name, "rb") as f:
        st.download_button(
            "Download Map (Client View)",
            f,
            file_name="map.html"
        )
