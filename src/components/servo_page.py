"""Servo page - Individual servo control, bulk control, and calibration."""
import streamlit as st
import requests
import pandas as pd
import time


def render_servo_page(api_url):
    st.title("Servos")

    # Fetch status
    try:
        resp = requests.get(f"{api_url}/api/status", timeout=2)
        status = resp.json()
        angles = status.get("angles", {})
        calib = status.get("calibration", {}).get("servos", {})
    except Exception as e:
        st.error(f"Cannot connect to backend: {e}")
        return

    # Tabs for different servo functions
    tab_overview, tab_individual, tab_calibration, tab_bulk = st.tabs([
        "Overview", "Individual", "Calibration", "Bulk Control"
    ])

    # === OVERVIEW TAB ===
    with tab_overview:
        # Quick actions
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Reset All to 90", use_container_width=True, type="primary"):
                try:
                    resp = requests.post(f"{api_url}/api/reset", timeout=5)
                    if resp.json().get("status") == "ok":
                        st.success("Reset done")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        with col2:
            if st.button("Go to Neutrals", use_container_width=True):
                try:
                    resp = requests.post(f"{api_url}/api/goto_neutrals", timeout=5)
                    if resp.json().get("status") == "ok":
                        st.success("At neutral positions")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        with col3:
            if st.button("Refresh", use_container_width=True):
                st.rerun()

        st.divider()

        # Servo table
        servo_data = []
        for ch in range(12):
            ch_str = str(ch)
            servo_info = calib.get(ch_str, {})
            current_angle = angles.get(ch, angles.get(str(ch), 90))
            servo_data.append({
                "Ch": ch,
                "Label": servo_info.get("label", f"Servo {ch}"),
                "Leg": servo_info.get("leg", "-"),
                "Joint": servo_info.get("joint", "-"),
                "Current": f"{current_angle}",
                "Neutral": f"{servo_info.get('neutral_angle', 90)}",
                "Offset": f"{servo_info.get('offset', 0):+d}",
                "Cal": "OK" if servo_info.get("calibrated", False) else "?"
            })

        df = pd.DataFrame(servo_data)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # === INDIVIDUAL TAB ===
    with tab_individual:
        servo_options = {f"Ch{ch}: {calib.get(str(ch), {}).get('label', f'Servo {ch}')}": ch
                         for ch in range(12)}

        selected = st.selectbox("Select Servo", list(servo_options.keys()))
        channel = servo_options[selected]
        servo_info = calib.get(str(channel), {})

        # Info display
        col_info1, col_info2, col_info3, col_info4 = st.columns(4)
        with col_info1:
            st.metric("Leg", servo_info.get("leg", "-"))
        with col_info2:
            st.metric("Joint", servo_info.get("joint", "-"))
        with col_info3:
            st.metric("Neutral", f"{servo_info.get('neutral_angle', 90)}")
        with col_info4:
            current = angles.get(channel, angles.get(str(channel), 90))
            st.metric("Current", f"{current}")

        st.divider()

        # Angle control
        col_slider, col_buttons = st.columns([2, 1])

        with col_slider:
            angle_key = f"servo_angle_{channel}"
            if angle_key not in st.session_state:
                st.session_state[angle_key] = int(angles.get(channel, angles.get(str(channel), 90)))

            angle = st.slider(
                f"Angle for Ch{channel}",
                0, 180,
                st.session_state[angle_key],
                key=f"slider_ch_{channel}"
            )
            st.markdown(f"### Set angle: **{angle}**")

        with col_buttons:
            st.write("**Quick Angles:**")
            qcol1, qcol2 = st.columns(2)
            with qcol1:
                if st.button("0", key=f"q0_{channel}", use_container_width=True):
                    angle = 0
                if st.button("45", key=f"q45_{channel}", use_container_width=True):
                    angle = 45
                if st.button("90", key=f"q90_{channel}", use_container_width=True):
                    angle = 90
            with qcol2:
                if st.button("120", key=f"q120_{channel}", use_container_width=True):
                    angle = 120
                if st.button("150", key=f"q150_{channel}", use_container_width=True):
                    angle = 150
                if st.button("180", key=f"q180_{channel}", use_container_width=True):
                    angle = 180

            neutral = servo_info.get("neutral_angle", 90)
            if st.button(f"Neutral ({neutral})", key=f"qn_{channel}", use_container_width=True):
                angle = neutral

        st.divider()

        # Action buttons
        col_send, col_send_raw, col_neutral = st.columns(3)

        with col_send:
            if st.button("Send (calibrated)", use_container_width=True, type="primary"):
                try:
                    resp = requests.post(
                        f"{api_url}/api/servo/{channel}",
                        json={"angle": angle, "raw": False},
                        timeout=2
                    )
                    if resp.json().get("status") == "ok":
                        st.success(f"Ch{channel} -> {angle} (cal)")
                        st.session_state[angle_key] = angle
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        with col_send_raw:
            if st.button("Send RAW", use_container_width=True):
                try:
                    resp = requests.post(
                        f"{api_url}/api/servo/{channel}",
                        json={"angle": angle, "raw": True},
                        timeout=2
                    )
                    if resp.json().get("status") == "ok":
                        st.success(f"Ch{channel} -> {angle} (raw)")
                        st.session_state[angle_key] = angle
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        with col_neutral:
            if st.button("Go to Neutral", use_container_width=True):
                try:
                    resp = requests.post(
                        f"{api_url}/api/servo/{channel}",
                        json={"angle": 90, "raw": False},
                        timeout=2
                    )
                    if resp.json().get("status") == "ok":
                        st.success(f"Ch{channel} at neutral")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    # === CALIBRATION TAB ===
    with tab_calibration:
        # Fetch calibration data
        try:
            calib_resp = requests.get(f"{api_url}/api/calibration", timeout=2)
            calib_data = calib_resp.json()
            servos = calib_data.get("servos", {})
        except Exception as e:
            st.error(f"Cannot get calibration: {e}")
            return

        # Servo selector
        options = [f"Ch{ch}: {s['label']}" for ch, s in servos.items() if int(ch) < 12]
        selected_cal = st.selectbox("Select Servo to Calibrate", options, key="cal_select")
        cal_channel = int(selected_cal.split(":")[0].replace("Ch", ""))
        servo = servos[str(cal_channel)]

        st.caption(f"{servo['leg']} {servo['joint']} | Saved: {servo['neutral_angle']} | {'calibrated' if servo['calibrated'] else 'not calibrated'}")

        # Session state for angle
        angle_key = f"calib_angle_{cal_channel}"
        if angle_key not in st.session_state:
            st.session_state[angle_key] = servo.get("neutral_angle", 90)

        current_angle = st.session_state[angle_key]

        # Slider
        cal_angle = st.slider("Angle", 0, 180, int(current_angle), key=f"cal_sl{cal_channel}")

        # Update and send if changed
        if cal_angle != current_angle:
            st.session_state[angle_key] = cal_angle
            try:
                requests.post(f"{api_url}/api/servo/{cal_channel}", json={"angle": cal_angle, "raw": True}, timeout=0.5)
            except:
                pass

        st.write(f"**{st.session_state[angle_key]}** (offset: {st.session_state[angle_key]-90:+d} from center)")

        # Fine tune buttons
        c1, c2, c3, c4 = st.columns(4)

        def send_cal_angle(new_angle):
            st.session_state[angle_key] = new_angle
            try:
                requests.post(f"{api_url}/api/servo/{cal_channel}", json={"angle": new_angle, "raw": True}, timeout=0.5)
                return True
            except:
                return False

        with c1:
            if st.button("-5", key=f"cm5_{cal_channel}"):
                if send_cal_angle(max(0, st.session_state[angle_key] - 5)):
                    st.rerun()
        with c2:
            if st.button("-1", key=f"cm1_{cal_channel}"):
                if send_cal_angle(max(0, st.session_state[angle_key] - 1)):
                    st.rerun()
        with c3:
            if st.button("+1", key=f"cp1_{cal_channel}"):
                if send_cal_angle(min(180, st.session_state[angle_key] + 1)):
                    st.rerun()
        with c4:
            if st.button("+5", key=f"cp5_{cal_channel}"):
                if send_cal_angle(min(180, st.session_state[angle_key] + 5)):
                    st.rerun()

        st.divider()

        # Free move calibration
        st.subheader("Free Move Calibration")
        st.caption("1. Press 'Release' to free the servo")
        st.caption("2. Move the joint by hand to neutral position")
        st.caption("3. Use slider to 'capture' - move until it just engages")
        st.caption("4. Press 'SAVE' to store this value")

        free_col1, free_col2 = st.columns(2)

        with free_col1:
            if st.button("Release Servo", key=f"free_{cal_channel}", use_container_width=True):
                try:
                    resp = requests.post(f"{api_url}/api/servo/{cal_channel}/disable", timeout=2)
                    if resp.status_code == 200:
                        st.success("Servo released! Move by hand.")
                except Exception as e:
                    st.error(f"Error: {e}")

        with free_col2:
            if st.button("Go to 90", key=f"lock_{cal_channel}", use_container_width=True):
                if send_cal_angle(90):
                    st.success("Servo at 90")
                    st.rerun()

        st.divider()

        # Save buttons
        col_goto, col_save = st.columns(2)
        with col_goto:
            if st.button(f"Goto saved ({servo['neutral_angle']})", key=f"goto_{cal_channel}"):
                st.session_state[angle_key] = servo['neutral_angle']
                requests.post(f"{api_url}/api/servo/{cal_channel}", json={"angle": servo['neutral_angle'], "raw": True}, timeout=0.5)
                st.rerun()

        with col_save:
            if st.button("SAVE", type="primary", key=f"save_{cal_channel}"):
                save_angle = st.session_state[angle_key]
                servo["neutral_angle"] = save_angle
                servo["offset"] = save_angle - 90
                servo["calibrated"] = True

                requests.post(f"{api_url}/api/calibration/servo/{cal_channel}", json=servo, timeout=2)
                requests.post(f"{api_url}/api/calibration/save", timeout=2)
                st.success(f"Saved {save_angle}!")
                time.sleep(0.5)
                st.rerun()

    # === BULK CONTROL TAB ===
    with tab_bulk:
        col_bulk1, col_bulk2 = st.columns(2)

        with col_bulk1:
            st.write("**Send same angle to multiple servos:**")
            bulk_angle = st.slider("Bulk Angle", 0, 180, 90, key="bulk_angle")

            selected_servos = []
            scol1, scol2, scol3, scol4 = st.columns(4)
            for i in range(12):
                col = [scol1, scol2, scol3, scol4][i % 4]
                with col:
                    label = calib.get(str(i), {}).get("label", f"Ch{i}")[:15]
                    if st.checkbox(label, key=f"bulk_ch_{i}"):
                        selected_servos.append(i)

            if st.button("Send to Selected", use_container_width=True):
                if selected_servos:
                    success_count = 0
                    for ch in selected_servos:
                        try:
                            resp = requests.post(
                                f"{api_url}/api/servo/{ch}",
                                json={"angle": bulk_angle, "raw": False},
                                timeout=1
                            )
                            if resp.json().get("status") == "ok":
                                success_count += 1
                        except:
                            pass
                    st.success(f"Sent {bulk_angle} to {success_count}/{len(selected_servos)} servos")
                    st.rerun()
                else:
                    st.warning("Select at least one servo")

        with col_bulk2:
            st.write("**Leg quick control:**")
            leg_bulk_angle = st.slider("Leg Angle", 0, 180, 90, key="leg_bulk_angle")

            legs = {
                "FL": [0, 1, 2],
                "FR": [3, 4, 5],
                "RL": [6, 7, 8],
                "RR": [9, 10, 11]
            }

            lcol1, lcol2 = st.columns(2)
            with lcol1:
                if st.button("FL", use_container_width=True):
                    for ch in legs["FL"]:
                        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": leg_bulk_angle, "raw": False}, timeout=1)
                    st.success("FL set")
                    st.rerun()

                if st.button("RL", use_container_width=True):
                    for ch in legs["RL"]:
                        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": leg_bulk_angle, "raw": False}, timeout=1)
                    st.success("RL set")
                    st.rerun()

            with lcol2:
                if st.button("FR", use_container_width=True):
                    for ch in legs["FR"]:
                        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": leg_bulk_angle, "raw": False}, timeout=1)
                    st.success("FR set")
                    st.rerun()

                if st.button("RR", use_container_width=True):
                    for ch in legs["RR"]:
                        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": leg_bulk_angle, "raw": False}, timeout=1)
                    st.success("RR set")
                    st.rerun()

            if st.button("All Legs", use_container_width=True, type="primary"):
                for ch in range(12):
                    requests.post(f"{api_url}/api/servo/{ch}", json={"angle": leg_bulk_angle, "raw": False}, timeout=1)
                st.success(f"All servos -> {leg_bulk_angle}")
                st.rerun()
