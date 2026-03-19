import streamlit as st
import pandas as pd
import folium
from shapely.geometry import Point, Polygon
from folium.plugins import HeatMap
import streamlit.components.v1 as components
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Spacer, Table
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
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
# LOAD HEATMAP
# -----------------------------
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

center_lat = sum(p[0] for p in heat_data) / len(heat_data)
center_lon = sum(p[1] for p in heat_data) / len(heat_data)

# -----------------------------
# BUILD GEOFENCES
# -----------------------------
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

polygons = build_polygons(False)

if len(polygons) == 0:
    polygons = build_polygons(True)

# -----------------------------
# PROXIMITY ANALYSIS
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
# ZONE CONTROLS
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
    attr="Esri"
).add_to(m)

if show_heatmap:
    HeatMap(heat_data, radius=20, blur=15).add_to(m)

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

        buffer_coords = [(y, x) for x, y in poly["buffer"].exterior.coords]

        folium.PolyLine(
            buffer_coords,
            color="orange",
            weight=2,
            dash_array="6,6"
        ).add_to(m)

        c = poly["polygon"].centroid

        popup_html = f"""
        <div style="font-size:13px;padding:6px;min-width:140px;">
            <b>{poly['zone']}</b><br>
            Inside: {poly['count']}<br>
            Within 5m: {poly['near_count']}
        </div>
        """

        popup = folium.Popup(popup_html, max_width=250)

        folium.Marker(
            [c.y, c.x],
            popup=popup,
            tooltip=popup_html,
            icon=folium.DivIcon(
                html=f"<div style='background:white;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid black'>{poly['count']}</div>"
            )
        ).add_to(m)

        folium.Marker(
            [c.y + 0.00006, c.x],
            tooltip=f"Within 5m: {poly['near_count']}",
            icon=folium.DivIcon(
                html=f"<div style='background:#ffe5b4;border-radius:50%;width:22px;height:22px;text-align:center;border:1px solid orange'>{poly['near_count']}</div>"
            )
        ).add_to(m)

# -----------------------------
# RENDER MAP
# -----------------------------
components.html(m._repr_html_(), height=650)

# -----------------------------
# RESULTS TABLE + CSV
# -----------------------------
results_df = pd.DataFrame([
    {
        "zone": p["zone"],
        "inside_count": p["count"],
        "within_5m": p["near_count"]
    }
    for p in polygons
]).sort_values("inside_count", ascending=False)

st.subheader("Geofence Breakdown")
st.dataframe(results_df, use_container_width=True)

st.download_button(
    "Download CSV",
    results_df.to_csv(index=False),
    "geofence_counts.csv"
)

# -----------------------------
# PDF GENERATION
# -----------------------------
def create_zone_image(poly, points, filename):

    fig, ax = plt.subplots(figsize=(3, 3))

    x, y = poly["polygon"].exterior.xy
    ax.plot(x, y)

    xs = [p.x for p in points]
    ys = [p.y for p in points]

    ax.scatter(xs, ys, s=1)

    minx, miny, maxx, maxy = poly["polygon"].bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)

    ax.axis('off')

    plt.savefig(filename, bbox_inches='tight')
    plt.close()


def generate_pdf(polygons, points):

    styles = getSampleStyleSheet()
    elements = []

    cols = 4
    rows = 5

    grid = []
    temp_files = []

    for poly in polygons:

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_files.append(tmp.name)

        create_zone_image(poly, points, tmp.name)

        img = Image(tmp.name, width=120, height=120)

        text = Paragraph(
            f"<b>{poly['zone']}</b><br/>"
            f"Inside: {poly['count']}<br/>"
            f"Within 5m: {poly['near_count']}",
            styles["Normal"]
        )

        grid.append([img, text])

        if len(grid) == cols * rows:
            table = Table([grid[i:i+cols] for i in range(0, len(grid), cols)])
            elements.append(table)
            elements.append(Spacer(1, 20))
            grid = []

    if grid:
        table = Table([grid[i:i+cols] for i in range(0, len(grid), cols)])
        elements.append(table)

    pdf_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")

    doc = SimpleDocTemplate(pdf_file.name, pagesize=letter)
    doc.build(elements)

    return pdf_file.name


if st.button("📄 Generate PDF Report"):

    with st.spinner("Generating PDF..."):

        pdf_path = generate_pdf(polygons, points)

        with open(pdf_path, "rb") as f:
            st.download_button(
                "Download PDF",
                f,
                file_name="geofence_report.pdf"
            )
