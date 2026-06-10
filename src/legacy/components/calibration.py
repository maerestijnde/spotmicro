import streamlit as st
import requests
import time
import traceback

def render_calibration(api_url):
    st.title("Calibration")

    try:
        resp = requests.get(f"{api_url}/api/calibration", timeout=2)
        calib_data = resp.json()
        servos = calib_data.get("servos", {})
    except Exception as e:
        st.error(f"Cannot connect to backend: {e}")
        st.code(traceback.format_exc())
        return

    if not servos:
        st.error("No servos in calibration data")
        st.json(calib_data)
        return

    # Servo selector
    try:
        options = [f"Ch{ch}: {s['label']}" for ch, s in servos.items() if int(ch) < 12]
        if not options:
            st.error("No valid servo options")
            return
        selected = st.selectbox("Select Servo", options)
        channel = int(selected.split(":")[0].replace("Ch", ""))
        servo = servos[str(channel)]
    except Exception as e:
        st.error(f"Error parsing servo options: {e}")
        st.code(traceback.format_exc())
        return

    st.caption(f"{servo['leg']} {servo['joint']} | Saved: {servo['neutral_angle']} | {'calibrated' if servo['calibrated'] else 'not calibrated'}")

    # Session state key for this channel's angle
    angle_key = f"calib_angle_{channel}"

    # Initialize with saved neutral if not set
    if angle_key not in st.session_state:
        st.session_state[angle_key] = servo.get("neutral_angle", 90)

    # Current angle from session state
    current_angle = st.session_state[angle_key]

    # Slider
    try:
        angle = st.slider("Angle", 0, 180, int(current_angle), key=f"sl{channel}")
    except Exception as e:
        st.error(f"Slider error: {e}")
        st.code(f"current_angle={current_angle}, type={type(current_angle)}")
        angle = 90

    # Update session state and send if slider changed
    if angle != current_angle:
        st.session_state[angle_key] = angle
        try:
            requests.post(f"{api_url}/api/servo/{channel}", json={"angle": angle, "raw": True}, timeout=0.5)
        except Exception as e:
            st.error(f"Failed to send servo command: {e}")

    st.write(f"**{st.session_state[angle_key]}°** (offset: {st.session_state[angle_key]-90:+d} van midden)")

    # Fine tune buttons
    c1, c2, c3, c4 = st.columns(4)

    def send_angle(new_angle):
        try:
            st.session_state[angle_key] = new_angle
            requests.post(f"{api_url}/api/servo/{channel}", json={"angle": new_angle, "raw": True}, timeout=0.5)
            return True
        except Exception as e:
            st.error(f"Send failed: {e}")
            return False

    with c1:
        if st.button("-5", key=f"m5_{channel}"):
            if send_angle(max(0, st.session_state[angle_key] - 5)):
                st.rerun()
    with c2:
        if st.button("-1", key=f"m1_{channel}"):
            if send_angle(max(0, st.session_state[angle_key] - 1)):
                st.rerun()
    with c3:
        if st.button("+1", key=f"p1_{channel}"):
            if send_angle(min(180, st.session_state[angle_key] + 1)):
                st.rerun()
    with c4:
        if st.button("+5", key=f"p5_{channel}"):
            if send_angle(min(180, st.session_state[angle_key] + 5)):
                st.rerun()

    st.divider()

    # Free move calibration mode
    st.subheader("Free Move Calibratie")
    st.caption("1. Druk 'Vrijgeven' om servo los te maken")
    st.caption("2. Beweeg de poot met de hand naar neutrale positie")
    st.caption("3. Gebruik slider om servo te 'pakken' - beweeg tot hij net vastpakt")
    st.caption("4. Druk 'SAVE' om deze waarde op te slaan")

    free_col1, free_col2 = st.columns(2)

    with free_col1:
        if st.button("🔓 Vrijgeven", key=f"free_{channel}", use_container_width=True):
            try:
                resp = requests.post(f"{api_url}/api/servo/{channel}/disable", timeout=2)
                if resp.status_code == 200:
                    st.success("Servo vrij! Beweeg met de hand.")
                else:
                    st.error(f"Failed: {resp.status_code}")
            except Exception as e:
                st.error(f"Error: {e}")

    with free_col2:
        if st.button("🔒 Naar 90°", key=f"lock_{channel}", use_container_width=True):
            if send_angle(90):
                st.success("Servo op 90°")
                st.rerun()

    st.divider()

    # Save and goto
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Goto saved ({servo['neutral_angle']})", key=f"goto_{channel}"):
            try:
                st.session_state[angle_key] = servo['neutral_angle']
                requests.post(f"{api_url}/api/servo/{channel}", json={"angle": servo['neutral_angle'], "raw": True}, timeout=0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Goto failed: {e}")

    with col2:
        if st.button("SAVE", type="primary", key=f"save_{channel}"):
            try:
                save_angle = st.session_state[angle_key]
                servo["neutral_angle"] = save_angle
                servo["offset"] = save_angle - 90  # 90 = midden van 180° range
                servo["calibrated"] = True

                requests.post(f"{api_url}/api/calibration/servo/{channel}", json=servo, timeout=2)
                requests.post(f"{api_url}/api/calibration/save", timeout=2)

                st.success(f"Saved {save_angle}!")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
                st.code(traceback.format_exc())

    st.divider()

    # === ALL SERVOS SLIDERS ===
    st.subheader("Alle Servo's (Raw)")

    # Per leg layout
    legs = [
        ("FL", "Front Left", [0, 1, 2]),
        ("FR", "Front Right", [3, 4, 5]),
        ("RL", "Rear Left", [6, 7, 8]),
        ("RR", "Rear Right", [9, 10, 11]),
    ]

    joints = ["Hip", "Knee", "Ankle"]

    for leg_id, leg_name, channels in legs:
        st.markdown(f"**{leg_name}**")
        cols = st.columns(3)

        for idx, ch in enumerate(channels):
            ch_str = str(ch)
            if ch_str not in servos:
                continue

            s = servos[ch_str]
            joint = joints[idx]

            # Session state for this servo
            key = f"all_servo_{ch}"
            if key not in st.session_state:
                st.session_state[key] = s.get("neutral_angle", 90)

            with cols[idx]:
                st.caption(f"{joint} (ch{ch})")

                # Slider
                new_val = st.slider(
                    f"ch{ch}",
                    0, 180,
                    int(st.session_state[key]),
                    key=f"slider_all_{ch}",
                    label_visibility="collapsed"
                )

                # Send if changed
                if new_val != st.session_state[key]:
                    st.session_state[key] = new_val
                    try:
                        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": new_val, "raw": True}, timeout=0.3)
                    except:
                        pass

                # Show value and offset (90 = midden/neutral)
                offset = new_val - 90
                st.caption(f"{new_val}° (offset {offset:+d})")

        st.markdown("---")

    # Quick actions
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Midden (90°)", key="all_90"):
            for ch in range(12):
                try:
                    requests.post(f"{api_url}/api/servo/{ch}", json={"angle": 90, "raw": True}, timeout=0.3)
                    st.session_state[f"all_servo_{ch}"] = 90
                except:
                    pass
            st.rerun()

    with col2:
        if st.button("All to neutrals", key="all_neutrals"):
            try:
                requests.post(f"{api_url}/api/goto_neutrals", timeout=5)
                # Update session state to match saved neutrals
                for ch_str, s in servos.items():
                    ch = int(ch_str)
                    if ch < 12:
                        st.session_state[f"all_servo_{ch}"] = s.get("neutral_angle", 90)
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

    with col3:
        if st.button("Save ALL", type="primary", key="save_all"):
            try:
                for ch in range(12):
                    ch_str = str(ch)
                    if ch_str in servos:
                        new_angle = st.session_state.get(f"all_servo_{ch}", servos[ch_str].get("neutral_angle", 90))
                        servos[ch_str]["neutral_angle"] = new_angle
                        servos[ch_str]["offset"] = new_angle - 90  # 90 = midden van 180° range
                        servos[ch_str]["calibrated"] = True
                        requests.post(f"{api_url}/api/calibration/servo/{ch}", json=servos[ch_str], timeout=1)

                requests.post(f"{api_url}/api/calibration/save", timeout=2)
                st.success("All saved!")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
