"""Settings page - PS4 controller info and custom poses."""
import streamlit as st
import requests
import subprocess


def get_controller_status():
    """Check if PS4 controller is connected."""
    try:
        result = subprocess.run(
            ["ls", "/dev/input/js0"],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except:
        return False


def get_controller_process():
    """Check if ps4_controller.py is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "ps4_controller.py"],
            capture_output=True,
            timeout=2
        )
        return result.returncode == 0
    except:
        return False


def get_paired_controller_mac():
    """Get MAC of paired PlayStation controller."""
    try:
        result = subprocess.run(
            ["bluetoothctl", "devices", "Paired"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n'):
            if 'Wireless Controller' in line or 'DualSense' in line:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
    except:
        pass
    return None


def reconnect_controller():
    """Try to reconnect the controller."""
    mac = get_paired_controller_mac()
    if mac:
        try:
            subprocess.run(
                ["bluetoothctl", "connect", mac],
                capture_output=True, timeout=10
            )
            return True
        except:
            pass
    return False


def render_settings_page(api_url):
    st.title("Settings")

    tab_controller, tab_poses, tab_system = st.tabs(["Controller", "Custom Poses", "System"])

    # === CONTROLLER TAB ===
    with tab_controller:
        st.subheader("PlayStation Controller")
        st.caption("Works with PS4 (DualShock 4) and PS5 (DualSense)")

        # Status
        col1, col2 = st.columns(2)

        with col1:
            controller_connected = get_controller_status()
            if controller_connected:
                st.success("Controller: Connected")
            else:
                st.warning("Controller: Not connected")

        with col2:
            process_running = get_controller_process()
            if process_running:
                st.success("Listener: Running")
            else:
                st.error("Listener: Not running")

        if not controller_connected:
            mac = get_paired_controller_mac()
            if mac:
                st.warning(f"Controller paired ({mac}) but not connected")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Reconnect", type="primary", use_container_width=True):
                        with st.spinner("Connecting..."):
                            reconnect_controller()
                            import time
                            time.sleep(2)
                            st.rerun()
                with col2:
                    if st.button("Refresh", use_container_width=True):
                        st.rerun()
                st.caption("Tip: Press PS button to wake up controller")
            else:
                st.info("""
                **Connect controller:**
                1. Hold CREATE/SHARE + PS button until light flashes rapidly
                2. Run `./pair_ps4.sh` to pair (one time)
                3. Restart `./start.sh`
                """)

        st.divider()

        # Controller mapping
        st.subheader("Controller Mapping")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Movement")
            st.markdown("""
            | Input | Action |
            |-------|--------|
            | **Left Stick Up/Down** | Walk forward/backward |
            | **Left Stick Left/Right** | Lateral step |
            | **L2 / R2** | Turn left/right |
            | **X** | Single step forward |
            | **L3 Click** | Single step backward |
            | **Circle** | Stop |
            """)

            st.markdown("### Poses")
            st.markdown("""
            | Input | Action |
            |-------|--------|
            | **D-pad Up** | Stand |
            | **D-pad Down** | Sit |
            | **D-pad Left** | Rest |
            | **D-pad Right** | Neutral |
            """)

        with col2:
            st.markdown("### Body Control")
            st.markdown("""
            | Input | Action |
            |-------|--------|
            | **Right Stick** | Pitch / Roll |
            | **L2 / R2** | Yaw (+ turn while walking) |
            | **L1** | Body LOWER (crouch) |
            | **R1** | Body HIGHER (stand up) |
            | **R3 Click** | Reset orientation |
            """)

            st.markdown("### Other")
            st.markdown("""
            | Input | Action |
            |-------|--------|
            | **Triangle** | Toggle balance |
            | **Square** | Go to neutrals |
            | **Share** | Calibrate IMU |
            | **Options** | EMERGENCY STOP |
            | **PS Button** | Show status |
            """)

        st.divider()

        # Controller diagram
        st.subheader("Controller Layout")
        st.code("""
                [L1=LOWER]                        [R1=HIGHER]
                [L2=TURN]                         [R2=TURN]

              +---------------------------------------------+
              |                                             |
              |      [^]              [/\\]    [T]          |
              |    [<] [>]    [SH] [OP]    [S]  [O]        |
              |      [v]              [><]    [X]          |
              |                                             |
              |         (L)                  (R)            |
              |                                             |
              +---------------------------------------------+

    L = Left Stick: Up/Down=Walk, Left/Right=Lateral
    R = Right Stick: Body pitch/roll
    D-pad = Poses
    L1 = Body LOWER    R1 = Body HIGHER
    L2/R2 = Turn (while walking) + Yaw (body)
    SH = Share (IMU cal)   OP = Options (STOP)
        """, language=None)

        st.divider()

        # Xbox controller
        st.subheader("Xbox 360 Controller (USB)")
        st.caption("Start with: `python3 xbox_controller.py`")
        st.code("""
    Xbox 360 Button Mapping:

    A = Step forward     B = Stop
    X = Go to neutrals   Y = Toggle balance
    LB = Body LOWER      RB = Body HIGHER
    LT = Turn left       RT = Turn right
    Back = IMU calibrate Start = EMERGENCY STOP

    Left Stick  = Walk/Lateral
    Right Stick = Pitch/Roll
    D-pad       = Poses (same as PS)
        """, language=None)

    # === CUSTOM POSES TAB ===
    with tab_poses:
        st.subheader("Custom Pose Manager")

        st.markdown("""
        **Create your own poses!**
        - Set all servos as you want
        - Save as "my_stand", "lying", "sitting", etc.
        - Load later with 1 click
        """)

        # Fetch custom poses
        try:
            resp = requests.get(f"{api_url}/api/custom_poses", timeout=2)
            custom_poses = resp.json().get("poses", {})
        except Exception as e:
            st.error(f"Cannot connect to backend: {e}")
            return

        # Fetch current angles
        try:
            resp = requests.get(f"{api_url}/api/current_pose", timeout=2)
            current_angles = resp.json().get("angles", {})
        except:
            current_angles = {}

        st.divider()

        # Section 1: Load existing custom poses
        if custom_poses:
            st.subheader("Saved Custom Poses")

            cols = st.columns(min(4, len(custom_poses)))
            for idx, (pose_name, pose_data) in enumerate(custom_poses.items()):
                with cols[idx % 4]:
                    st.write(f"**{pose_name}**")
                    st.caption(pose_data.get("description", "") if isinstance(pose_data, dict) else "")

                    col_load, col_del = st.columns(2)
                    with col_load:
                        if st.button("Load", key=f"load_{pose_name}", use_container_width=True):
                            try:
                                resp = requests.post(f"{api_url}/api/custom_poses/{pose_name}/execute", timeout=5)
                                if resp.json().get("status") == "ok":
                                    st.success(f"Loaded {pose_name}!")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

                    with col_del:
                        if st.button("Del", key=f"del_{pose_name}", use_container_width=True):
                            try:
                                resp = requests.delete(f"{api_url}/api/custom_poses/{pose_name}", timeout=5)
                                if resp.json().get("status") == "ok":
                                    st.success(f"Deleted {pose_name}")
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")

            st.divider()

        # Section 2: Save current position
        st.subheader("Save Current Position")

        # Show current angles
        with st.expander("Current Servo Angles", expanded=False):
            for leg_id in ["FL", "FR", "RL", "RR"]:
                if leg_id in current_angles:
                    angles = current_angles[leg_id]
                    st.caption(f"{leg_id}: hip={angles.get('hip', 90)}, knee={angles.get('knee', 90)}, ankle={angles.get('ankle', 90)}")

        col_name, col_desc = st.columns(2)

        with col_name:
            new_pose_name = st.text_input("Pose Name", placeholder="e.g.: my_stand, lying, sitting")

        with col_desc:
            new_pose_desc = st.text_input("Description", placeholder="e.g.: Low stance for walking")

        if st.button("Save Current Position", type="primary", use_container_width=True, disabled=not new_pose_name):
            if new_pose_name:
                try:
                    data = {
                        "description": new_pose_desc or "Custom pose",
                        "angles": current_angles
                    }
                    resp = requests.post(f"{api_url}/api/custom_poses/{new_pose_name}", json=data, timeout=5)
                    result = resp.json()

                    if result.get("status") == "ok":
                        st.success(f"Saved '{new_pose_name}'!")
                        st.rerun()
                    else:
                        st.error(f"Error: {result.get('message', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # === SYSTEM TAB ===
    with tab_system:
        st.subheader("System Info")

        try:
            status = requests.get(f"{api_url}/api/status", timeout=2).json()

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Hardware", "Active" if status.get("hardware") else "Simulation")
                st.metric("Kinematics", "Available" if status.get("kinematics") else "Disabled")
            with col2:
                calib = status.get("calibration", {})
                calibrated = sum(1 for s in calib.get("servos", {}).values()
                                if s.get("calibrated", False))
                st.metric("Calibrated Servos", f"{calibrated}/12")
        except:
            st.error("Cannot fetch system status")

        st.divider()

        # Backend URL
        st.write(f"**Backend:** {api_url}")

        st.divider()

        # Quick actions
        st.subheader("Quick Actions")
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Test API", use_container_width=True):
                try:
                    resp = requests.get(f"{api_url}/api/status", timeout=2)
                    if resp.status_code == 200:
                        st.success("API working!")
                    else:
                        st.error(f"API error: {resp.status_code}")
                except Exception as e:
                    st.error(f"Connection failed: {e}")

        with col2:
            if st.button("Reset Servos to 90", use_container_width=True):
                try:
                    requests.post(f"{api_url}/api/reset", timeout=5)
                    st.success("Reset complete")
                except Exception as e:
                    st.error(f"Error: {e}")

        with col3:
            if st.button("Emergency Stop", type="primary", use_container_width=True):
                try:
                    requests.post(f"{api_url}/api/gait/stop", timeout=2)
                    requests.post(f"{api_url}/api/pose/neutral", timeout=2)
                    st.success("Stopped!")
                except Exception as e:
                    st.error(f"Error: {e}")
