import streamlit as st

# =========================================================
# 1. PAGE CONFIG
# =========================================================
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
# 2. ADVANCED CUSTOM CSS (ถอดแบบ Stitch 100%)
# =========================================================
st.markdown("""
    <style>
    /* 1. พื้นหลังหลักสีดำเข้มแบบ Aviation Control Room */
    .stAppViewContainer, .stApp {
        background-color: #0A0D12 !important;
        color: #C9D1D9 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    
    /* ซ่อน Header และ Footer มาตรฐานของ Streamlit */
    header[data-testid="stHeader"] { display: none !important; }
    footer { display: none !important; }
    
    /* 2. Sidebar ฝั่งซ้ายสุดเนี๊ยบ */
    section[data-testid="stSidebar"] {
        background-color: #11151C !important;
        border-right: 1px solid #1F242D !important;
        width: 260px !important;
    }
    
    /* 3. กล่อง Project Details ฝั่งซ้าย (Floating Glassmorphism Card) */
    div[data-testid="column"]:first-child {
        background: #11151C !important;
        border: 1px solid #1F293D !important;
        border-radius: 12px !important;
        padding: 24px !important;
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5) !important;
    }

    /* 4. หัวข้อกล่อง & ตัวหนังสือ */
    .panel-header {
        font-size: 13px !important;
        font-weight: 700 !important;
        letter-spacing: 1.5px !important;
        color: #8B949E !important;
        margin-bottom: 16px !important;
        text-transform: uppercase;
    }
    
    .main-header {
        font-size: 20px !important;
        font-weight: 700 !important;
        letter-spacing: 1px !important;
        color: #FFFFFF !important;
        margin-bottom: 24px !important;
    }
    
    /* 5. Custom Input Fields ให้มืดเนี๊ยบสไตล์ Dashboard */
    .stTextInput input, .stSelectbox div[data-baseweb="select"], .stNumberInput input {
        background-color: #161B22 !important;
        color: #58A6FF !important;
        border: 1px solid #30363D !important;
        border-radius: 6px !important;
        font-family: monospace !important;
    }
    
    .stTextInput label, .stSelectbox label, .stNumberInput label {
        color: #8B949E !important;
        font-size: 12px !important;
        font-weight: 600 !important;
    }

    /* 6. ปุ่ม Generate Flight Area สีกระแทกตาแบบ Neon Blue */
    .stButton > button {
        width: 100% !important;
        background: linear-gradient(185deg, #3B82F6 0%, #1D4ED8 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #60A5FA !important;
        border-radius: 8px !important;
        padding: 12px 20px !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        letter-spacing: 0.5px !important;
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4) !important;
        margin-top: 15px !important;
        transition: all 0.2s ease-in-out !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(185deg, #60A5FA 0%, #2563EB 100%) !important;
        box-shadow: 0 6px 25px rgba(59, 130, 246, 0.6) !important;
        transform: translateY(-1px) !important;
    }

    /* 7. ปรับตารางข้อมูลพิกัดข้างล่าง */
    div[data-testid="stDataFrame"] {
        background-color: #11151C !important;
        border: 1px solid #1F242D !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# =========================================================
# 3. HELPER FUNCTIONS
# =========================================================
def parse_l7018(sheet_name):
    try:
        clean_name = sheet_name.replace(" ", "").replace("-", "")
        code = int(clean_name) if clean_name.isdigit() else 47361
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
        return {
            "SW": (13.75, 100.50), "NW": (14.00, 100.50),
            "NE": (14.00, 100.75), "SE": (13.75, 100.75),
            "CENTER": (13.875, 100.625)
        }

def dd_to_dms(dd, is_lat=True):
    direction = ("N" if dd >= 0 else "S") if is_lat else ("E" if dd >= 0 else "W")
    dd = abs(dd)
    degrees = int(dd)
    minutes = int((dd - degrees) * 60)
    seconds = round((dd - degrees - minutes/60) * 3600, 1)
    return f"{degrees:02d}°{minutes:02d}'{seconds:04.1f}\"{direction}"

def generate_kml(proj_name, coords):
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
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr(f"{proj_name}.kml", generate_kml(proj_name, coords))
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_summary.to_excel(writer, index=False, sheet_name='NOTAM_Coordinates')
        zip_file.writestr(f"{proj_name}_Coordinates.xlsx", excel_buffer.getvalue())
        
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
# 4. SIDEBAR MENU
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
# 5. MAIN CONTENT AREA
# =========================================================
if "Generator" in menu:
    st.markdown('<div class="main-header">NOTAM AREA GENERATOR</div>', unsafe_allow_html=True)
    
    # 2 Columns (Left Panel : Right Map)
    col_form, col_map = st.columns([1.1, 2.2], gap="large")
    
    # --- Form Card (Left) ---
    with col_form:
        st.markdown('<div class="panel-header">PROJECT DETAILS</div>', unsafe_allow_html=True)
        project_name = st.text_input("Project Name", value="NOTAM_A00")
        l7018_sheet = st.text_input("L7018 SHEET", value="L7018-01")
        
        st.markdown('<div class="panel-header" style="margin-top:20px;">AREA PARAMETERS</div>', unsafe_allow_html=True)
        sub1, sub2 = st.columns(2)
        with sub1:
            ns_nm = st.number_input("N-S (NM)", value=5.0, step=0.5)
        with sub2:
            we_nm = st.number_input("W-E (NM)", value=3.0, step=0.5)
            
        btn_generate = st.button("🌐 Generate Flight Area")

    coords = parse_l7018(l7018_sheet)
    
    df_result = pd.DataFrame([
        {"Point": "Center", "Lat_DMS": dd_to_dms(coords["CENTER"][0], True), "Lon_DMS": dd_to_dms(coords["CENTER"][1], False), "Latitude": coords["CENTER"][0], "Longitude": coords["CENTER"][1]},
        {"Point": "SW", "Lat_DMS": dd_to_dms(coords["SW"][0], True), "Lon_DMS": dd_to_dms(coords["SW"][1], False), "Latitude": coords["SW"][0], "Longitude": coords["SW"][1]},
        {"Point": "NW", "Lat_DMS": dd_to_dms(coords["NW"][0], True), "Lon_DMS": dd_to_dms(coords["NW"][1], False), "Latitude": coords["NW"][0], "Longitude": coords["NW"][1]},
        {"Point": "NE", "Lat_DMS": dd_to_dms(coords["NE"][0], True), "Lon_DMS": dd_to_dms(coords["NE"][1], False), "Latitude": coords["NE"][0], "Longitude": coords["NE"][1]},
        {"Point": "SE", "Lat_DMS": dd_to_dms(coords["SE"][0], True), "Lon_DMS": dd_to_dms(coords["SE"][1], False), "Latitude": coords["SE"][0], "Longitude": coords["SE"][1]},
    ])

    # --- Map (Right) ---
    with col_map:
        m = folium.Map(
            location=[coords["CENTER"][0], coords["CENTER"][1]], 
            zoom_start=11, 
            tiles="CartoDB dark_matter"
        )
        
        boundary = [coords["SW"], coords["NW"], coords["NE"], coords["SE"], coords["SW"]]
        folium.Polygon(
            locations=boundary,
            color="#60A5FA",
            weight=2,
            fill=True,
            fill_color="#3B82F6",
            fill_opacity=0.2,
            popup=f"Project: {project_name}"
        ).add_to(m)
        
        folium.CircleMarker(
            location=coords["CENTER"],
            radius=5,
            color="#EF4444",
            fill=True,
            fill_color="#EF4444",
            popup="Center Point"
        ).add_to(m)
        
        st_folium(m, width="100%", height=520)

    # --- Table & Download Package ---
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
