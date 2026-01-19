import streamlit as st
import requests
import sys
import os
import socket
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="MicroSpot",
    page_icon="🐕",
    layout="wide",
    initial_sidebar_state="expanded"
)

def get_backend_url():
    if "MICROSPOT_BACKEND" in os.environ:
        return os.environ["MICROSPOT_BACKEND"]
    try:
        hostname = socket.gethostname()
        return f"http://{hostname}:8000"
    except:
        return "http://localhost:8000"

API_URL = get_backend_url()

# Clean CSS
st.markdown("""
<style>
    .main {padding: 0.5rem;}
    .stButton>button {width: 100%; border-radius: 8px; height: 3em;}
    .block-container {padding-top: 1rem;}
    section[data-testid="stSidebar"] {width: 200px !important;}
    .stMetric {background: #1a1a2e; padding: 0.5rem; border-radius: 8px;}
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("MicroSpot")

# Connection status
try:
    resp = requests.get(f"{API_URL}/api/status", timeout=1)
    st.sidebar.success("Connected")

    # Live IMU pitch/roll in sidebar
    try:
        imu_resp = requests.get(f"{API_URL}/api/balance/angles", timeout=0.5)
        if imu_resp.status_code == 200:
            imu_data = imu_resp.json()
            pitch = imu_data.get("pitch", 0)
            roll = imu_data.get("roll", 0)

            col1, col2 = st.sidebar.columns(2)

            # Color based on tilt
            max_tilt = max(abs(pitch), abs(roll))
            if max_tilt < 10:
                color = "🟢"
            elif max_tilt < 20:
                color = "🟡"
            else:
                color = "🔴"

            col1.metric("Pitch", f"{pitch:.1f}°")
            col2.metric("Roll", f"{roll:.1f}°")
            st.sidebar.caption(f"{color} Tilt: {max_tilt:.1f}°")
    except:
        pass

except:
    st.sidebar.error("Disconnected")

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    ["Control", "Servos", "Tuning", "IMU", "Settings"],
    label_visibility="collapsed"
)

# Route pages
if page == "Control":
    from components.control_page import render_control_page
    render_control_page(API_URL)
elif page == "Servos":
    from components.servo_page import render_servo_page
    render_servo_page(API_URL)
elif page == "Tuning":
    from components.tuning_page import render_tuning_page
    render_tuning_page(API_URL)
elif page == "IMU":
    from components.imu_page import render_imu_page
    render_imu_page(API_URL)
elif page == "Settings":
    from components.settings_page import render_settings_page
    render_settings_page(API_URL)
