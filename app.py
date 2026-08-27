import streamlit as st

# 1. PAGE CONFIG (ต้องอยู่อันดับ 1 เสมอ)
st.set_page_config(
    page_title="NOTAM AREA GENERATOR",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

import io
import zipfile
import pandas as pd
import folium
from streamlit_folium import st_folium
import simplekml
import shapefile

# =========================================================
# 2. ADVANCED CUSTOM CSS (สไตล์ Dark Aviation Dashboard)
# =========================================================
st.markdown("""
    <style>
    /* พื้นหลังหลัก Dark Mode */
    .stAppViewContainer, .stApp {
        background-color: #0A0D12 !important;
        color: #C9D1D9 !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }
    
    header[data-testid="stHeader"] { display: none !important; }
    footer { display: none !important; }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #11151C !important;
        border-right: 1px solid #1F242D !important;
    }
    
    /* Panel Left Box */
    div[data-testid="column"]:first-child {
        background: #11151C !important;
        border: 1px solid #1F293D !important;
        border-radius: 12px !important;
        padding: 24px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5) !important;
    }

    .panel-header {
        font-size: 13px !important;
        font-weight: 700 !important;
        letter-spacing: 1.5px !important;
        color: #8B949E !important;
        margin-bottom: 12px !important;
        text-transform: uppercase;
    }
    
    .main-header {
        font-size: 20px !important;
        font-weight: 700 !important;
        letter-spacing: 1px !important;
        color: #FFFFFF !important;
        margin-bottom: 20px !important;
    }
    
    /* Style Inputs & Selectbox */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #161B22 !important;
        color: #58A6FF !important;
        border: 1px solid #30363D !important;
        border-radius: 6px !important;
    }
    
    .stTextInput label, .stSelectbox label, .stNumberInput label {
        color: #8B949E !important;
        font-size: 12px !important;
        font-weight: 600 !important;
    }

    /* Button Neon Blue */
    .stButton > button {
        width: 100% !important;
        background: linear-gradient(185deg, #3B82F6 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #60A5FA !important;
        border-radius: 8px !important;
        padding: 12px 20px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4) !important;
        margin-top: 15px !important;
        transition: all 0.2s ease-in-out !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(185deg, #60A5FA 0%, #2563EB 100%) !important;
        box-shadow: 0 6px 25px rgba(59, 130, 246, 0.6) !important;
    }

    div[data-testid="stDataFrame"] {
        background-color: #11151C !important;
        border: 1px solid #1F242D !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 3. CORE GIS FUNCTIONS & L7018 DATABASE
# =========================================================

# ฐานข้อมูลตัวอย่างระวาง L7018 (พิกัดขอบเขตจริง)
L7018_DATABASE = {
    "5136-IV (กรุงเทพมหานคร)": {"lat_min": 13.75, "lat_max": 14.00, "lon_min": 100.50, "lon_max": 100.75},
    "5136-III (นนทบุรี-ปทุมธานี)": {"lat_min": 13.85, "lat_max": 14.10, "lon_min": 100.40, "lon_max": 100.65},
    "5236-I (ฉะเชิงเทรา)": {"lat_min": 13.60, "lat_max": 13.85, "lon_min": 100.90, "lon_max": 101.15},
    "4736-I (เชียงใหม่)": {"lat_min": 18.70, "lat_max": 18.95, "lon_min": 98.90, "lon_max": 99.15},
    "5336-IV (ร้อยเอ็ด)": {"lat_min": 16.00, "lat_max": 16.25, "lon_min": 103.60, "lon_max": 103.85},
    "4725-II (ภูเก็ต)": {"lat_min": 7.80, "lat_max": 8.05, "lon_min": 98.25, "lon_max": 98.50},
}

def calculate_flight_area(sheet_key, ns_nm, we_nm):
    """คำนวณพิกัด Center และการขยายขอบเขต Buffer ตามระยะ Nautical Miles (NM)"""
    sheet = L7018_DATABASE[sheet_key]
    
    # พิกัดกึ่งกลางระวาง
    center_lat = (sheet["lat_min"] + sheet["lat_max"]) / 2.0
    center_lon = (sheet["lon_min"] + sheet["lon_max"]) / 2.0
    
    # แปลง NM เป็น Degree (โดยประมาณ: 1 NM ≈ 1/60 องศา Latitude)
    lat_buffer = (ns_nm / 2.0) / 60.0
    # Longitude Buffer ปรับตามค่า Cosine ของ Latitude
    import math
    lon_buffer = (we_nm / 2.0) / (60.0 * math.cos(math.radians(center_lat)))
    
    sw = (center_lat - lat_buffer, center_lon - lon_buffer)
    nw = (center_lat + lat_buffer, center_lon - lon_buffer)
    ne = (center_lat + lat_buffer, center_lon + lon_buffer)
    se = (center_lat - lat_buffer, center_lon + lon_buffer)
    center = (center_lat, center_lon)
    
    return {"SW": sw, "NW": nw, "NE": ne, "SE": se, "CENTER": center}

def dd_to_dms(dd, is_lat=True):
    """แปลง Decimal Degree เป็น Degrees Minutes Seconds (DMS)"""
    direction = ("N" if dd >= 0 else "S") if is_lat else ("E" if dd >= 0 else "W")
    dd = abs(dd)
    degrees = int(dd)
    minutes = int((dd - degrees) * 60)
    seconds = round((dd - degrees - minutes/60) * 3600, 1)
    return f"{degrees:02d}°{minutes:02d}'{seconds:04.1f}\"{direction}"

def generate_kml(proj_name, coords):
    """สร้างไฟล์ KML สำหรับเปิดใน Google Earth"""
    kml = simplekml.Kml()
    polygon_coords = [
        (coords["SW"][1], coords["SW"][0]),
        (coords["NW"][1], coords["NW"][0]),
        (coords["NE"][1], coords["NE"][0]),
        (coords["SE"][1], coords["SE"][0]),
        (coords["SW"][1], coords["SW"][0])
    ]
    pol = kml.newpolygon(name=proj_name, outerboundaryis=polygon_coords)
    pol.style.polystyle.color = simplekml.Color.changealphaint(80, simplekml.Color.blue)
    pol.style.linestyle.color = simplekml.Color.cyan
    pol.style.linestyle.width = 3
    return kml.kml()

def generate_zip_package(proj_name, coords, df_summary):
    """รวมไฟล์ KML, Excel และ Shapefile เข้า ZIP"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. KML File
        zip_file.writestr(f"{proj_name}.kml", generate_kml(proj_name, coords))
        
        # 2. Excel File
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_summary.to_excel(writer, index=False, sheet_name='NOTAM_Coordinates')
        zip_file.writestr(f"{proj_name}_Coordinates.xlsx", excel_buffer.getvalue())
        
        # 3. Shapefile
        shp_b, shx_b, dbf_b = io.BytesIO(), io.BytesIO(), io.BytesIO()
        w = shapefile.Writer(shp=shp_b, shx=shx_b, dbf=dbf_b)
        w.field('PROJECT', 'C')
        w.poly([[[coords["SW"][1], coords["SW"][0]], 
                 [coords["NW"][1], coords["NW"][0]], 
                 [coords["NE"][1], coords["NE"][0]], 
                 [coords["SE"][1], coords["SE"][0]], 
                 [coords["SW"][1], coords["SW"][0]]]])
        w.record(proj_name)
        w.close()
        
        zip_file.writestr(f"{proj_name}.shp", shp_b.getvalue())
        zip_file.writestr(f"{proj_name}.shx", shx_b.getvalue())
        zip_file.writestr(f"{proj_name}.dbf", dbf_b.getvalue())
        
    return zip_buffer.getvalue()

# =========================================================
# 4. SIDEBAR NAVIGATION
# =========================================================
with st.sidebar:
    st.markdown('<div class="main-header">🚀 Mission Control</div>', unsafe_allow_html=True)
    st.caption("AERIAL PHOTOGRAPHY OPS")
    st.markdown("---")
    
    menu = st.radio(
        "Navigation", 
        ["🌐 Generator", "📁 Archive", "📄 Templates", "⚙️ Settings"],
        label_visibility="collapsed"
    )
    st.markdown("<br><br><br>", unsafe_allow_html=True)
    st.caption("💬 Support & Help")

# =========================================================
# 5. MAIN GENERATOR INTERFACE
# =========================================================
if "Generator" in menu:
    st.markdown('<div class="main-header">NOTAM AREA GENERATOR</div>', unsafe_allow_html=True)
    
    col_form, col_map = st.columns([1.2, 2.0], gap="large")
    
    # --- ฝั่งซ้าย: Form Card ---
    with col_form:
        st.markdown('<div class="panel-header">PROJECT DETAILS</div>', unsafe_allow_html=True)
        project_name = st.text_input("Project Name", value="NOTAM_A00")
        
        # ✅ ดรอปดาวน์เลือกระวาง L7018 กลับมาแล้วครับ!
        selected_sheet = st.selectbox(
            "L7018 SHEET", 
            options=list(L7018_DATABASE.keys()),
            index=0
        )
        
        st.markdown('<div class="panel-header" style="margin-top:20px;">AREA PARAMETERS</div>', unsafe_allow_html=True)
        sub1, sub2 = st.columns(2)
        with sub1:
            ns_nm = st.number_input("N-S (NM)", value=5.0, step=0.5, min_value=0.5)
        with sub2:
            we_nm = st.number_input("W-E (NM)", value=3.0, step=0.5, min_value=0.5)
            
        btn_generate = st.button("🌐 Generate Flight Area")

    # คำนวณพิกัดพื้นที่บินตามค่าที่เลือก
    coords = calculate_flight_area(selected_sheet, ns_nm, we_nm)
    
    # ตารางสรุปพิกัด DMS
    df_result = pd.DataFrame([
        {"Point": "Center Point", "Lat_DMS": dd_to_dms(coords["CENTER"][0], True), "Lon_DMS": dd_to_dms(coords["CENTER"][1], False), "Latitude": coords["CENTER"][0], "Longitude": coords["CENTER"][1]},
        {"Point": "South-West (SW)", "Lat_DMS": dd_to_dms(coords["SW"][0], True), "Lon_DMS": dd_to_dms(coords["SW"][1], False), "Latitude": coords["SW"][0], "Longitude": coords["SW"][1]},
        {"Point": "North-West (NW)", "Lat_DMS": dd_to_dms(coords["NW"][0], True), "Lon_DMS": dd_to_dms(coords["NW"][1], False), "Latitude": coords["NW"][0], "Longitude": coords["NW"][1]},
        {"Point": "North-East (NE)", "Lat_DMS": dd_to_dms(coords["NE"][0], True), "Lon_DMS": dd_to_dms(coords["NE"][1], False), "Latitude": coords["NE"][0], "Longitude": coords["NE"][1]},
        {"Point": "South-East (SE)", "Lat_DMS": dd_to_dms(coords["SE"][0], True), "Lon_DMS": dd_to_dms(coords["SE"][1], False), "Latitude": coords["SE"][0], "Longitude": coords["SE"][1]},
    ])

    # --- ฝั่งขวา: Interactive Dark Map ---
    with col_map:
        m = folium.Map(
            location=[coords["CENTER"][0], coords["CENTER"][1]], 
            zoom_start=11, 
            tiles="CartoDB dark_matter"
        )
        
        # วาดกรอบพื้นที่บิน Polygon
        boundary = [coords["SW"], coords["NW"], coords["NE"], coords["SE"], coords["SW"]]
        folium.Polygon(
            locations=boundary,
            color="#60A5FA",
            weight=2,
            fill=True,
            fill_color="#3B82F6",
            fill_opacity=0.25,
            popup=f"Project: {project_name}"
        ).add_to(m)
        
        # ปักหมุด Center Point
        folium.CircleMarker(
            location=coords["CENTER"],
            radius=6,
            color="#EF4444",
            fill=True,
            fill_color="#EF4444",
            popup="Center Point"
        ).add_to(m)
        
        st_folium(m, width="100%", height=520)

    # --- สรุปพิกัด & ปุ่ม Export Package ---
    st.markdown("---")
    res1, res2 = st.columns([2, 1])
    with res1:
        st.markdown('<div class="panel-header">COORDINATES SUMMARY (DMS)</div>', unsafe_allow_html=True)
        st.dataframe(df_result[['Point', 'Lat_DMS', 'Lon_DMS', 'Latitude', 'Longitude']], use_container_width=True)
        
    with res2:
        st.markdown('<div class="panel-header">EXPORT PACKAGE</div>', unsafe_allow_html=True)
        zip_data = generate_zip_package(project_name, coords, df_result)
        st.download_button(
            label="💾 Download Package (.ZIP)",
            data=zip_data,
            file_name=f"{project_name}_Package.zip",
            mime="application/zip"
        )

else:
    st.markdown(f"### {menu}")
    st.info("ส่วนนี้กำลังอยู่ระหว่างการพัฒนาเพิ่มเติมครับ")
