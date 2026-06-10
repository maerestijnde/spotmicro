"""Control page - Main control interface combining walking, poses, and safety."""
import streamlit as st
import requests
import numpy as np
from math import radians


def get_stability_state(pitch: float, roll: float) -> tuple:
    """Determine stability state based on pitch and roll angles."""
    max_tilt = max(abs(pitch), abs(roll))
    if max_tilt < 10:
        return "stable", "Robot is stable"
    elif max_tilt < 25:
        return "warning", "Moderate tilt"
    elif max_tilt < 35:
        return "critical", "High tilt!"
    else:
        return "emergency", "EXTREME TILT!"


def render_control_page(api_url: str):
    st.title("Control")

    # Initialize session state for auto-refresh
    if "control_live" not in st.session_state:
        st.session_state.control_live = False

    # Initial data fetch for controls that need it
    try:
        gait = requests.get(f"{api_url}/api/gait/status", timeout=1).json()
        bal = requests.get(f"{api_url}/api/balance/status", timeout=1).json()
        status = requests.get(f"{api_url}/api/status", timeout=1).json()
        connected = True
    except Exception:
        st.error("Cannot connect to backend")
        return

    running = gait.get("running", False)
    bal_on = bal.get("enabled", False)
    imu_available = bal.get("available", False)
    body = status.get("body", {})

    # Real-time status bar and visualization
    @st.fragment(run_every=0.5 if st.session_state.control_live else None)
    def status_fragment():
        """Real-time status updates."""
        try:
            ang = requests.get(f"{api_url}/api/balance/angles", timeout=1).json()
            gait_status = requests.get(f"{api_url}/api/gait/status", timeout=1).json()
            bal_status = requests.get(f"{api_url}/api/balance/status", timeout=1).json()
            current_status = requests.get(f"{api_url}/api/status", timeout=1).json()
        except Exception:
            ang = {"pitch": 0, "roll": 0}
            gait_status = {"running": False}
            bal_status = {"enabled": False}
            current_status = {"angles": {}}

        pitch = ang.get("pitch", 0)
        roll = ang.get("roll", 0)
        is_running = gait_status.get("running", False)
        is_bal_on = bal_status.get("enabled", False)

        # Safety status bar
        state, state_desc = get_stability_state(pitch, roll)
        state_colors = {
            "stable": ("#22c55e", "STABLE"),
            "warning": ("#f59e0b", "WARNING"),
            "critical": ("#ef4444", "CRITICAL"),
            "emergency": ("#dc2626", "EMERGENCY")
        }
        color, label = state_colors.get(state, ("#666", "UNKNOWN"))

        st.markdown(f"""
        <div style="background-color:{color};color:white;padding:8px 16px;border-radius:8px;
                    display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;">
            <span style="font-weight:bold;">{label}</span>
            <span>Pitch: {pitch:.1f} | Roll: {roll:.1f}</span>
            <span>{'Walking' if is_running else 'Stopped'} | Balance: {'ON' if is_bal_on else 'OFF'}</span>
        </div>
        """, unsafe_allow_html=True)

        # 3D Robot visualization
        try:
            from components.robot_3d import create_3d_robot
            servo_angles = current_status.get("angles", {})
            fig = create_3d_robot(servo_angles, pitch, roll, height=400)
            st.plotly_chart(fig, use_container_width=True, key="robot_3d_live")
        except Exception as e:
            st.error(f"3D visualization error: {e}")

    # Main layout
    col_viz, col_ctrl = st.columns([2, 1])

    with col_viz:
        status_fragment()

    with col_ctrl:
        # Auto-refresh toggle at top of controls
        st.session_state.control_live = st.toggle("Live Updates", value=st.session_state.control_live)

        st.divider()

        # Walking controls
        st.subheader("Walking")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Walk", use_container_width=True, disabled=running):
                requests.post(f"{api_url}/api/gait/start", json={"direction": "forward"})
                st.rerun()
        with c2:
            if st.button("STOP", use_container_width=True, type="primary"):
                requests.post(f"{api_url}/api/gait/stop")
                st.rerun()
        with c3:
            if st.button("Step", use_container_width=True):
                requests.post(f"{api_url}/api/gait/step")
                st.rerun()

        # Balance toggle
        bal_col1, bal_col2 = st.columns(2)
        with bal_col1:
            if st.button("Balance ON" if not bal_on else "Balance OFF",
                        use_container_width=True, disabled=not imu_available):
                requests.post(f"{api_url}/api/balance/enable", json={"enable": not bal_on})
                st.rerun()
        with bal_col2:
            if st.button("Cal IMU", use_container_width=True, disabled=not imu_available):
                requests.post(f"{api_url}/api/balance/calibrate")
                st.rerun()

        st.divider()

        # Preset poses
        st.subheader("Poses")
        pose_cols = st.columns(4)
        poses = ["neutral", "stand", "sit", "rest"]
        for idx, pose in enumerate(poses):
            with pose_cols[idx]:
                if st.button(pose.title(), use_container_width=True):
                    requests.post(f"{api_url}/api/pose/{pose}")
                    st.rerun()

    st.divider()

    # Body control section
    st.subheader("Body Control")
    col_height, col_angles = st.columns(2)

    with col_height:
        st.write("**Height**")
        height = st.slider("Height (mm)", 20, 160, int(body.get('y', 0.14) * 1000), 5,
                          key="height_slider", label_visibility="collapsed")

        hcols = st.columns(4)
        quick_heights = [20, 60, 100, 140]
        for i, h in enumerate(quick_heights):
            with hcols[i]:
                if st.button(f"{h}", key=f"h{h}"):
                    height = h
                    try:
                        data = {"y": height / 1000.0, "phi": 0, "theta": 0, "psi": 0}
                        requests.post(f"{api_url}/api/body", json=data, timeout=2)
                        st.rerun()
                    except Exception:
                        pass

    with col_angles:
        st.write("**Orientation**")
        phi = st.slider("Roll", -30.0, 30.0, float(np.degrees(body.get('phi', 0))), 1.0,
                       key="phi_slider")
        theta = st.slider("Pitch", -30.0, 30.0, float(np.degrees(body.get('theta', 0))), 1.0,
                         key="theta_slider")

    # Apply body state
    col_apply, col_reset = st.columns(2)
    with col_apply:
        if st.button("Apply Body", type="primary", use_container_width=True):
            data = {
                "y": height / 1000.0,
                "phi": radians(phi),
                "theta": radians(theta),
                "psi": 0
            }
            requests.post(f"{api_url}/api/body", json=data, timeout=2)
            st.rerun()

    with col_reset:
        if st.button("Reset Body", use_container_width=True):
            data = {"y": 0.14, "phi": 0, "theta": 0, "psi": 0}
            requests.post(f"{api_url}/api/body", json=data, timeout=2)
            st.rerun()

    st.divider()

    # Emergency section
    st.subheader("Emergency")
    e1, e2, e3 = st.columns(3)

    with e1:
        if st.button("EMERGENCY STOP", type="primary", use_container_width=True):
            requests.post(f"{api_url}/api/gait/stop", timeout=2)
            for channel in range(12):
                try:
                    requests.post(f"{api_url}/api/servo/{channel}/disable", timeout=0.5)
                except Exception:
                    pass
            st.warning("All servos disabled!")

    with e2:
        if st.button("Rest Pose", use_container_width=True):
            requests.post(f"{api_url}/api/gait/stop", timeout=2)
            requests.post(f"{api_url}/api/pose/rest", timeout=2)

    with e3:
        if st.button("Neutral Pose", use_container_width=True):
            requests.post(f"{api_url}/api/gait/stop", timeout=2)
            requests.post(f"{api_url}/api/pose/neutral", timeout=2)
