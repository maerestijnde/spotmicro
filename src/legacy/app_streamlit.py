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

    /* Sidebar nav styling */
    [data-testid="stRadio"] > div {flex-direction: column; gap: 0.3rem;}
    [data-testid="stRadio"] label {
        padding: 0.5rem;
        border-radius: 6px;
        transition: background 0.2s ease;
        cursor: pointer;
    }
    [data-testid="stRadio"] label:hover {background: #222;}
    [data-testid="stRadio"] label:has(input:checked) {
        background: #1a1a2e;
        border-left: 3px solid #4CAF50;
    }

    /* Page-specific CSS */
    .calibration-card {
        border: 1px solid #333;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
        background: #111;
    }
    .step-active {border-left: 3px solid #4CAF50;}
    .step-inactive {border-left: 3px solid #333;}
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("MicroSpot")

connected = False

# Connection status
try:
    resp = requests.get(f"{API_URL}/api/status", timeout=1)
    st.sidebar.success("Connected")
    connected = True

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

    # Quick status indicators
    try:
        gait_resp = requests.get(f"{API_URL}/api/gait/status", timeout=0.5)
        if gait_resp.status_code == 200:
            gait_data = gait_resp.json()
            if gait_data.get("running", False):
                st.sidebar.markdown("🚶 **Walking**")
            else:
                st.sidebar.markdown("🛑 **Stopped**")
    except:
        pass

    try:
        balance_resp = requests.get(f"{API_URL}/api/balance/status", timeout=0.5)
        if balance_resp.status_code == 200:
            balance_data = balance_resp.json()
            if balance_data.get("enabled", False):
                st.sidebar.markdown("⚖️ **Balance ON**")
            else:
                st.sidebar.markdown("⚖️ **Balance OFF**")
    except:
        pass

    try:
        cal_resp = requests.get(f"{API_URL}/api/calibration", timeout=0.5)
        if cal_resp.status_code == 200:
            cal_data = cal_resp.json()
            calibrated_count = 0
            if isinstance(cal_data, list):
                calibrated_count = sum(1 for s in cal_data if s.get("calibrated", False))
            elif isinstance(cal_data, dict):
                servos = cal_data.get("servos", cal_data)
                if isinstance(servos, list):
                    calibrated_count = sum(1 for s in servos if s.get("calibrated", False))
                elif isinstance(servos, dict):
                    calibrated_count = sum(
                        1 for s in servos.values()
                        if isinstance(s, dict) and s.get("calibrated", False)
                    )
            status_icon = "✅" if calibrated_count >= 12 else "⚠️"
            st.sidebar.markdown(f"**Calibration:** {calibrated_count}/12 {status_icon}")
    except:
        pass

except:
    st.sidebar.error("Disconnected")

st.sidebar.divider()

page = st.sidebar.radio(
    "Navigation",
    ["Control", "Servos", "Calibration", "Tuning", "IMU", "Settings"],
    label_visibility="collapsed"
)

# Help expander
with st.sidebar.expander("❓ Help"):
    st.markdown("""
    1. Calibrate servos before walking
    2. Set stand height in Tuning
    3. Enable balance for stability
    4. Start with Slow gait preset
    """)

# Route pages
if page == "Control":
    from components.control_page import render_control_page
    render_control_page(API_URL)
elif page == "Servos":
    from components.servo_page import render_servo_page
    render_servo_page(API_URL)
elif page == "Calibration":
    from components.servo_page import render_servo_page
    st.info("👇 Click the **🎯 Calibration** tab below to start the wizard.")
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
