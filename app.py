import streamlit as st
import io
import zipfile
import pandas as pd
import folium
from streamlit_folium import st_folium
import simplekml
import shapefile

# =========================================================
# 1. PAGE CONFIGURATION (ต้องเป็นคำสั่ง st. อันแรกสุดเสมอ)
# =========================================================
st.set_page_config(
    page_title="NOTAM AREA GENERATOR",
    page_icon="✈️",
    page_layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
# 2. CUSTOM CSS (แต่ง UI ตาม Stitch Dark Aviation Theme)
# =========================================================
st.markdown("""
    <style>
    /* Dark Theme Background */
    .stApp {
        background-color: #0B0E14;
        color: #E6EDF3;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #161B22 !important;
        border-right: 1px solid #30363D;
    }
    
    /* Inputs Styling */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #161B22 !important;
        color: #FFFFFF !important;
        border: 1px solid #30363D !important;
        border-radius: 6px !important;
    }
    
    /* Primary Button Styling */
    .stButton > button {
        width: 100%;
        background-color: #3B82F6 !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        font-size: 15px !important;
        box-shadow: 0 4px 14px 0 rgba(59, 130, 246, 0.39) !important;
        transition: all 0.2s ease-in-out !important;
    }
    .stButton > button:hover {
        background-color: #2563EB !important;
        transform: translateY(-2px);
    }
    
    /* Title Header */
    .main-title {
        font-size: 22px;
        font-weight: 700;
        letter-spacing: 1.2px;
        color: #FFFFFF;
        margin-bottom: 20px;
    }
    
    /* Metric Cards */
    div[data-testid="stMetricValue"] {
        color: #60A5FA !important;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 3. HELPER FUNCTIONS (ฟังก์ชันคำนวณพิกัดและสร้างไฟล์)
# =========================================================

def parse_l7018(sheet_name):
    """คำนวณพิกัด 4 มุมจากชื่อระวาง L7018 (ตัวอย่างระบบพิกัดจำลองเพื่อการแสดงผล)"""
    try:
        clean_name = sheet_name.replace(" ", "").replace("-", "")
        code = int(clean_name) if clean_name.isdigit() else 47361
        
        # คำนวณ Grid พิกัดคร่าวๆ อิงตามรหัสระวาง
        lat_base = 13.0 + (code % 100) * 0.25
        lon_base = 100.0 + ((code // 100) % 100) * 0.25
        
        return {
            "SW": (lat_base, lon_base),
            "NW": (lat_base + 0.25, lon_base),
            "NE": (lat_base + 0.25, lon_base + 0.25),
            "SE": (lat_base, lon_base + 0.25),
            "CENTER": (lat_base + 0.125, lon_base + 0.125)
        }
    except Exception:
        # ค่า Default กรณีฉุกเฉิน (กทม. และปริมณฑล)
        return {
            "SW": (13.75, 100.50),
            "NW": (14.00, 100.50),
            "NE": (14.00, 100.75),
            "SE": (13.75, 100.75),
            "CENTER": (13.875, 100.625)
        }

def dd_to_dms(dd, is_lat=True):
    """แปลง Decimal Degree เป็น DMS Format สำหรับรายงาน NOTAM"""
    direction = ("N" if dd >= 0 else "S") if is_lat else ("E" if dd >= 0 else "W")
    dd = abs(dd)
    degrees = int(dd)
    minutes = int((dd - degrees) * 60)
    seconds = round((dd - degrees - minutes/60) * 3600, 1)
    return f"{degrees:02d}°{minutes:02d}'{seconds:04.1f}\"{direction}"

def generate_kml(proj_name, coords):
    """สร้างไฟล์ KML"""
    kml = simplekml.Kml()
    polygon_coords = [
        (coords["SW"][1], coords["SW"][0]),
        (coords["NW"][1], coords["NW"][0]),
        (coords["NE"][1], coords["NE"][0]),
        (coords["SE"][1], coords["SE"][0]),
        (coords["SW"][1], coords["SW"][0])
    ]
    pol = kml.newpolygon(name=proj_name, outerboundaryis=polygon_coords)
    pol.style.polystyle.color = simplekml.Color.changealphaint(100, simplekml.Color.blue)
    pol.style.linestyle.color = simplekml.Color.blue
    pol.style.linestyle.width = 3
    return kml.kml()

def generate_zip_package(proj_name, coords, df_summary):
    """รวมไฟล์ KML, Excel และ Shapefile เป็นไฟล์ ZIP"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. เพิ่ม KML
        kml_data = generate_kml(proj_name, coords)
        zip_file.writestr(f"{proj_name}.kml", kml_data)
        
        # 2. เพิ่ม Excel
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_summary.to_excel(writer, index=False, sheet_name='NOTAM_Coordinates')
        zip_file.writestr(f"{proj_name}_Coordinates.xlsx", excel_buffer.getvalue())
        
        # 3. เพิ่ม Shapefile (.shp, .shx, .dbf)
        shp_buffer = io.BytesIO()
        shx_buffer = io.BytesIO()
        dbf_buffer = io.BytesIO()
        
        w = shapefile.Writer(shp=shp_buffer, shx=shx_buffer, dbf=dbf_buffer)
        w.field('PROJECT', 'C')
        w.poly([[[coords["SW"][1], coords["SW"][0]], 
                 [coords["NW"][1], coords["NW"][0]], 
                 [coords["NE"][1], coords["NE"][0]], 
                 [coords["SE"][1], coords["SE"][0]], 
                 [coords["SW"][1], coords["SW"][0]]]])
        w.record(proj_name)
        w.close()
        
        zip_file.writestr(f"{proj_name}.shp", shp_buffer.getvalue())
        zip_file.writestr(f"{proj_name}.shx", shx_buffer.getvalue())
        zip_file.writestr(f"{proj_name}.dbf", dbf_buffer.getvalue())
        
    return zip_buffer.getvalue()

# =========================================================
# 4. UI LAYOUT & NAVIGATION (แถบเมนูซ้ายมือ)
# =========================================================
with st.sidebar:
    st.markdown("### 🚀 Mission Control")
    st.caption("AERIAL PHOTOGRAPHY OPS")
    st.markdown("---")
    
    menu = st.radio(
        "Navigation", 
        ["🌐 Generator", "📁 Archive", "📄 Templates", "⚙️ Settings"],
        label_visibility="collapsed"
    )
    
    st.markdown("---")
    st.caption("NOTAM Area Generator v2.0")

# =========================================================
# 5. MAIN DASHBOARD CONTENT
# =========================================================
if "Generator" in menu:
    st.markdown('<div class="main-title">NOTAM AREA GENERATOR</div>', unsafe_allow_html=True)
    
    # แบ่งหน้าจอเป็น 2 คอลัมน์ (ซ้าย 38% : ขวา 62%)
    col_form, col_map = st.columns([1.2, 2.0], gap="medium")
    
    # --- คอลัมน์ซ้าย: Project Details Card ---
    with col_form:
        st.markdown("#### PROJECT DETAILS")
        project_name = st.text_input("Project Name", value="NOTAM_A001")
        l7018_sheet = st.text_input("L7018 SHEET", value="5136-IV")
        
        st.markdown("#### AREA PARAMETERS")
        sub_col1, sub_col2 = st.columns(2)
        with sub_col1:
            ns_nm = st.number_input("N-S (NM)", value=5.0, step=0.5)
        with sub_col2:
            we_nm = st.number_input("W-E (NM)", value=3.0, step=0.5)
            
        st.markdown("<br>", unsafe_allow_html=True)
        btn_generate = st.button("🌐 Generate Flight Area")

    # --- การประมวลผลเมื่อกดปุ่ม Generate ---
    coords = parse_l7018(l7018_sheet)
    
    # จัดเตรียม DataFrame ผลลัพธ์
    df_result = pd.DataFrame([
        {"Point": "Center", "Lat_DMS": dd_to_dms(coords["CENTER"][0], True), "Lon_DMS": dd_to_dms(coords["CENTER"][1], False), "Latitude": coords["CENTER"][0], "Longitude": coords["CENTER"][1]},
        {"Point": "SW", "Lat_DMS": dd_to_dms(coords["SW"][0], True), "Lon_DMS": dd_to_dms(coords["SW"][1], False), "Latitude": coords["SW"][0], "Longitude": coords["SW"][1]},
        {"Point": "NW", "Lat_DMS": dd_to_dms(coords["NW"][0], True), "Lon_DMS": dd_to_dms(coords["NW"][1], False), "Latitude": coords["NW"][0], "Longitude": coords["NW"][1]},
        {"Point": "NE", "Lat_DMS": dd_to_dms(coords["NE"][0], True), "Lon_DMS": dd_to_dms(coords["NE"][1], False), "Latitude": coords["NE"][0], "Longitude": coords["NE"][1]},
        {"Point": "SE", "Lat_DMS": dd_to_dms(coords["SE"][0], True), "Lon_DMS": dd_to_dms(coords["SE"][1], False), "Latitude": coords["SE"][0], "Longitude": coords["SE"][1]},
    ])

    # --- คอลัมน์ขวา: Interactive Dark Map ---
    with col_map:
        # สร้างแผนที่ CartoDB Dark Matter สไตล์การบิน
        m = folium.Map(
            location=[coords["CENTER"][0], coords["CENTER"][1]], 
            zoom_start=11, 
            tiles="CartoDB dark_matter"
        )
        
        # วาดพิกัดขอบเขต Polygon
        boundary = [coords["SW"], coords["NW"], coords["NE"], coords["SE"], coords["SW"]]
        folium.Polygon(
            locations=boundary,
            color="#3B82F6",
            weight=3,
            fill=True,
            fill_color="#3B82F6",
            fill_opacity=0.25,
            popup=f"Project: {project_name}"
        ).add_to(m)
        
        # ปักหมุดจุดศูนย์กลาง Center Point
        folium.CircleMarker(
            location=coords["CENTER"],
            radius=6,
            color="#EF4444",
            fill=True,
            fill_color="#EF4444",
            popup="Center Point"
        ).add_to(m)
        
        # แสดงผลแผนที่
        st_folium(m, width="100%", height=480)
        
    # --- ส่วนล่าง: ตารางผลลัพธ์พิกัด & ปุ่มดาวน์โหลด Package ZIP ---
    st.markdown("---")
    res_col1, res_col2 = st.columns([2, 1])
    
    with res_col1:
        st.markdown("##### 📍 Coordinates Summary (DMS)")
        st.dataframe(df_result[['Point', 'Lat_DMS', 'Lon_DMS', 'Latitude', 'Longitude']], use_container_width=True)
        
    with res_col2:
        st.markdown("##### 📦 Export Package")
        zip_data = generate_zip_package(project_name, coords, df_result)
        
        st.download_button(
            label="💾 Download All (.ZIP)",
            data=zip_data,
            file_name=f"{project_name}_Package.zip",
            mime="application/zip"
        )

else:
    st.markdown(f"### {menu}")
    st.info("ส่วนนี้กำลังอยู่ระหว่างการพัฒนาเพิ่มเติมครับสุดหล่อ!")
