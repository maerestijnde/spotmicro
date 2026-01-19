"""Tuning page - Gait parameters and balance tuning."""
import streamlit as st
import requests
from components.robot_viz import create_robot_svg, create_side_svg, create_front_svg


def save_tuning(api_url: str, key: str, value) -> bool:
    """Save a tuning parameter to the backend."""
    try:
        response = requests.post(
            f"{api_url}/api/tuning/{key}",
            json={"value": value},
            timeout=2
        )
        return response.ok
    except:
        return False


def render_tuning_page(api_url):
    st.title("Tuning")

    # Initialize state variables
    tuning = {}
    pitch, roll = 0, 0
    connected = False

    # Fetch tuning data from /api/tuning (persistent tuning.json)
    try:
        tuning_response = requests.get(f"{api_url}/api/tuning", timeout=2)
        if tuning_response.ok:
            tuning = tuning_response.json()
            connected = True
    except:
        st.error("Cannot connect to backend")

    try:
        ang_response = requests.get(f"{api_url}/api/balance/angles", timeout=1)
        if ang_response.ok:
            ang = ang_response.json()
            pitch = ang.get("pitch", 0)
            roll = ang.get("roll", 0)
    except:
        pass

    # Connection status
    if connected:
        st.success("Connected")
    else:
        st.error("Disconnected")

    # Create tabs
    t1, t2, t3, t4 = st.tabs(["Stand", "IMU Cal", "Balance", "Gait"])

    # === STAND TAB ===
    with t1:
        st.subheader("Stand Position")
        st.markdown("Adjust how low the robot bends its knees when standing")

        kb = st.slider(
            "Knee Bend (degrees)",
            min_value=0,
            max_value=60,
            value=int(tuning.get("knee_bend", 40)),
            step=5,
            help="Higher values = lower stance"
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Preview", use_container_width=True, disabled=not connected):
                try:
                    response = requests.post(
                        f"{api_url}/api/gait/stand_height",
                        json={"knee_bend": kb},
                        timeout=2
                    )
                    if response.ok:
                        preview_response = requests.post(
                            f"{api_url}/api/gait/preview_stand",
                            timeout=2
                        )
                        if preview_response.ok:
                            st.success("Preview applied!")
                        else:
                            st.error("Preview failed")
                except Exception as e:
                    st.error(f"Error: {e}")

        with c2:
            if st.button("Save", use_container_width=True, type="primary", disabled=not connected):
                if save_tuning(api_url, "knee_bend", kb):
                    st.success("Saved!")
                else:
                    st.error("Save failed")

    # === IMU CALIBRATION TAB ===
    with t2:
        st.subheader("IMU Calibration")
        st.markdown("Place robot on a **flat surface**, check if the indicator is centered")

        # Robot visualization
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(create_robot_svg(pitch, roll, 280, 280), unsafe_allow_html=True)
        with col2:
            st.markdown(create_side_svg(pitch), unsafe_allow_html=True)
            st.markdown(create_front_svg(roll), unsafe_allow_html=True)

        # Level status
        is_level = abs(pitch) < 2 and abs(roll) < 2
        if is_level:
            st.success("LEVEL - Ready for calibration")
        else:
            st.warning(f"NOT LEVEL - Pitch: {pitch:.1f}, Roll: {roll:.1f}")

        if st.button("CALIBRATE IMU", type="primary", use_container_width=True, disabled=not connected):
            try:
                response = requests.post(f"{api_url}/api/balance/calibrate", timeout=5)
                if response.ok:
                    st.success("Zero point set to current position!")
                    st.rerun()
                else:
                    st.error("Calibration failed")
            except Exception as e:
                st.error(f"Error: {e}")

    # === BALANCE TAB ===
    with t3:
        st.subheader("Balance Settings")
        st.markdown("Adjust how aggressively the robot compensates for tilt")

        kp = st.slider(
            "Kp (Proportional Gain)",
            min_value=0.1,
            max_value=1.5,
            value=float(tuning.get("balance_kp", 0.5)),
            step=0.1,
            help="Higher = more aggressive correction"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save", type="primary", key="sv3", use_container_width=True, disabled=not connected):
                if save_tuning(api_url, "balance_kp", kp):
                    try:
                        requests.post(f"{api_url}/api/balance/kp", json={"kp": kp}, timeout=2)
                    except:
                        pass
                    st.success("Saved!")
                else:
                    st.error("Save failed")

        with col2:
            if st.button("Apply Live", key="apply_kp", use_container_width=True, disabled=not connected):
                try:
                    response = requests.post(f"{api_url}/api/balance/kp", json={"kp": kp}, timeout=2)
                    if response.ok:
                        st.info(f"Kp temporarily set to {kp}")
                    else:
                        st.error("Failed to apply")
                except Exception as e:
                    st.error(f"Error: {e}")

    # === GAIT TAB ===
    with t4:
        st.subheader("Gait Parameters")
        st.markdown("Adjust walking cycle timing and step height")

        cyc = st.slider(
            "Cycle Time (seconds)",
            min_value=0.4,
            max_value=1.5,
            value=float(tuning.get("cycle_time", 0.8)),
            step=0.1,
            help="Duration of one complete gait cycle"
        )

        hgt = st.slider(
            "Step Height (degrees)",
            min_value=10,
            max_value=40,
            value=int(tuning.get("step_height", 25)),
            step=5,
            help="How high legs lift during walking"
        )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Save", type="primary", key="sv4", use_container_width=True, disabled=not connected):
                success1 = save_tuning(api_url, "cycle_time", cyc)
                success2 = save_tuning(api_url, "step_height", hgt)
                if success1 and success2:
                    st.success("Saved!")
                else:
                    st.error("Save failed")

        with col2:
            if st.button("Apply to Gait", key="apply_gait", use_container_width=True, disabled=not connected):
                try:
                    response = requests.post(
                        f"{api_url}/api/gait/params",
                        json={"cycle_time": cyc, "step_height": hgt},
                        timeout=2
                    )
                    if response.ok:
                        st.info("Gait parameters applied!")
                    else:
                        st.warning("Apply returned error")
                except Exception as e:
                    st.error(f"Error: {e}")

        st.divider()

        # Presets
        st.subheader("Presets")
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Slow & Safe", use_container_width=True):
                try:
                    requests.post(f"{api_url}/api/gait/params", json={
                        "cycle_time": 1.2, "step_height": 20
                    }, timeout=2)
                    st.success("Applied slow preset")
                    st.rerun()
                except:
                    pass
        with c2:
            if st.button("Normal", use_container_width=True):
                try:
                    requests.post(f"{api_url}/api/gait/params", json={
                        "cycle_time": 0.8, "step_height": 25
                    }, timeout=2)
                    st.success("Applied normal preset")
                    st.rerun()
                except:
                    pass
        with c3:
            if st.button("Fast", use_container_width=True):
                try:
                    requests.post(f"{api_url}/api/gait/params", json={
                        "cycle_time": 0.5, "step_height": 30
                    }, timeout=2)
                    st.success("Applied fast preset")
                    st.rerun()
                except:
                    pass
