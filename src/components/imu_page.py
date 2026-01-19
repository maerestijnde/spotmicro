"""IMU page - IMU monitor and balance visualization with real-time updates."""
import streamlit as st
import requests
import time
from components.robot_viz import create_robot_svg, create_side_svg, create_front_svg


def create_ascii_viz(pitch: float, roll: float) -> str:
    """Create ASCII visualization of robot orientation."""
    p = max(-30, min(30, pitch))
    r = max(-30, min(30, roll))

    grid = [[' ' for _ in range(21)] for _ in range(11)]

    # Center cross
    for i in range(21):
        grid[5][i] = '-'
    for i in range(11):
        grid[i][10] = '|'
    grid[5][10] = '+'

    # Robot position (center = 10,5)
    rx = 10 + int(r / 3)
    ry = 5 + int(p / 6)
    rx = max(1, min(19, rx))
    ry = max(1, min(9, ry))

    grid[ry][rx] = 'O'

    lines = [''.join(row) for row in grid]

    # Create the visualization with labels
    viz = """
     ROLL
  -30   0   +30
    <   |   >
"""
    viz += '\n'.join(lines)
    viz += """
    ^   0   v
  -30      +30
     PITCH
"""
    return viz


def render_imu_page(api_url: str):
    st.title("IMU Monitor")

    # Initialize session state for live mode (default ON)
    if "imu_live" not in st.session_state:
        st.session_state.imu_live = True

    # Check IMU availability once at page load
    try:
        status = requests.get(f"{api_url}/api/balance/status", timeout=2).json()
        available = status.get("available", False)
        enabled = status.get("enabled", False)

        if not available:
            st.error("IMU not available - check I2C connection")
            st.code("sudo i2cdetect -y 1  # Should show 0x68")
            return
    except Exception as e:
        st.error(f"Cannot connect to backend: {e}")
        return

    # Controls row (outside fragment for stable UI)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Calibrate", use_container_width=True):
            try:
                requests.post(f"{api_url}/api/balance/calibrate", timeout=5)
                st.success("Calibrated!")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    with col2:
        label = "Balance OFF" if enabled else "Balance ON"
        if st.button(label, use_container_width=True, type="primary" if not enabled else "secondary"):
            try:
                requests.post(f"{api_url}/api/balance/enable", json={"enable": not enabled}, timeout=2)
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    with col3:
        if st.button("Refresh", use_container_width=True):
            st.rerun()

    with col4:
        live = st.toggle("Live", value=st.session_state.imu_live)
        if live != st.session_state.imu_live:
            st.session_state.imu_live = live
            st.rerun()

    st.divider()

    # Real-time data display - always poll when live is enabled
    @st.fragment(run_every=0.5 if st.session_state.imu_live else None)
    def imu_data_fragment():
        """Fragment that updates IMU data in real-time."""
        # Get current angles
        try:
            angles = requests.get(f"{api_url}/api/balance/angles", timeout=1).json()
            pitch = angles.get("pitch", 0)
            roll = angles.get("roll", 0)
        except Exception:
            pitch, roll = 0, 0

        # Get current balance status
        try:
            bal_status = requests.get(f"{api_url}/api/balance/status", timeout=1).json()
            bal_enabled = bal_status.get("enabled", False)
        except Exception:
            bal_enabled = False

        # Status banner (thresholds increased to reduce noise sensitivity)
        tilt = max(abs(pitch), abs(roll))
        if tilt < 10:
            st.success(f"LEVEL | Pitch: {pitch:.1f} | Roll: {roll:.1f} | Balance: {'ON' if bal_enabled else 'OFF'}")
        elif tilt < 25:
            st.warning(f"TILTED | Pitch: {pitch:.1f} | Roll: {roll:.1f} | Balance: {'ON' if bal_enabled else 'OFF'}")
        else:
            st.error(f"EXCESSIVE TILT | Pitch: {pitch:.1f} | Roll: {roll:.1f} | Balance: {'ON' if bal_enabled else 'OFF'}")

        # Main visualization
        col_viz, col_side = st.columns([2, 1])

        with col_viz:
            st.markdown(create_robot_svg(pitch, roll, 320, 320), unsafe_allow_html=True)

        with col_side:
            st.markdown(create_side_svg(pitch, 200, 120), unsafe_allow_html=True)
            st.markdown(create_front_svg(roll, 200, 120), unsafe_allow_html=True)

            # Metrics with delta
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                st.metric("Pitch", f"{pitch:+.1f}")
            with col_m2:
                st.metric("Roll", f"{roll:+.1f}")

        # ASCII visualization
        with st.expander("ASCII View", expanded=False):
            viz = create_ascii_viz(pitch, roll)
            st.code(viz, language=None)

    # Run the fragment
    imu_data_fragment()

    st.divider()

    # Balance gain control (outside fragment - doesn't need real-time updates)
    st.subheader("Balance Gain")
    st.markdown("Adjust how aggressively the robot compensates for tilt")

    # Get current tuning
    try:
        response = requests.get(f"{api_url}/api/tuning", timeout=2)
        if response.ok:
            tuning = response.json()
            current_kp = tuning.get("balance_kp", 0.5)
        else:
            current_kp = 0.5
    except Exception:
        current_kp = 0.5

    new_kp = st.slider(
        "Balance Kp (Proportional Gain)",
        min_value=0.1,
        max_value=2.0,
        value=float(current_kp),
        step=0.1,
        help="Higher values = more aggressive correction. Start low (0.3-0.5) and increase gradually."
    )

    col_save, col_apply = st.columns(2)

    with col_save:
        if st.button("Save Gain", use_container_width=True, type="primary"):
            try:
                requests.post(f"{api_url}/api/tuning/balance_kp", json={"value": new_kp}, timeout=2)
                requests.post(f"{api_url}/api/balance/kp", json={"kp": new_kp}, timeout=2)
                st.success(f"Balance Kp saved: {new_kp}")
            except Exception as e:
                st.error(f"Error: {e}")

    with col_apply:
        if st.button("Apply (no save)", use_container_width=True):
            try:
                requests.post(f"{api_url}/api/balance/kp", json={"kp": new_kp}, timeout=2)
                st.info(f"Kp temporarily set to {new_kp}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Thresholds info
    st.divider()
    with st.expander("Tilt Thresholds"):
        st.markdown("""
        - **Level**: < 10 degrees tilt
        - **Tilted**: 10-25 degrees tilt
        - **Excessive**: > 25 degrees tilt

        Robot will show warning colors based on these thresholds.
        """)
