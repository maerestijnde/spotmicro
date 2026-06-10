"""Servo page - Individual servo control, bulk control, and guided calibration wizard."""
import streamlit as st
import requests
import pandas as pd
import time

try:
    from components.calibration_viz import (
        create_robot_topdown_view,
        create_leg_diagram,
        create_offset_explanation_diagram,
        create_calibration_workflow_diagram,
        create_support_polygon_diagram,
    )
except ImportError:
    create_robot_topdown_view = None
    create_leg_diagram = None
    create_offset_explanation_diagram = None
    create_calibration_workflow_diagram = None
    create_support_polygon_diagram = None

LEG_CHANNELS = {
    "FL": [0, 1, 2],
    "FR": [3, 4, 5],
    "RL": [6, 7, 8],
    "RR": [9, 10, 11],
}
JOINT_NAMES = ["hip", "knee", "ankle"]
LEG_COLORS = {"FL": "#ff4444", "FR": "#44ff44", "RL": "#4444ff", "RR": "#ffaa44"}


def _send_servo(api_url, ch, angle, raw=True):
    try:
        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": angle, "raw": raw}, timeout=0.5)
        return True
    except Exception:
        return False


def _save_servo_calib(api_url, ch, servo_data):
    try:
        requests.post(f"{api_url}/api/calibration/servo/{ch}", json=servo_data, timeout=2)
        return True
    except Exception:
        return False


def render_servo_page(api_url):
    st.title("🔧 Servos & Calibration")

    # Fetch status
    try:
        resp = requests.get(f"{api_url}/api/status", timeout=2)
        status = resp.json()
        angles = status.get("angles", {})
        calib = status.get("calibration", {}).get("servos", {})
        connected = True
    except Exception as e:
        st.error(f"Cannot connect to backend: {e}")
        angles = {}
        calib = {}
        connected = False
        return

    # Determine default tab
    default_tab = st.session_state.pop("servo_default_tab", 0)
    tab_labels = ["📊 Overview", "🎛️ Individual", "🎯 Calibration", "🔌 Bulk Control"]

    # Use a trick to set default tab index
    tab_overview, tab_individual, tab_calibration, tab_bulk = st.tabs(tab_labels)

    # === OVERVIEW TAB ===
    with tab_overview:
        st.subheader("Robot Overview")

        # Calibration progress
        total_cal = sum(1 for ch in range(12) if calib.get(str(ch), {}).get("calibrated", False))
        progress = total_cal / 12.0

        col_prog, col_viz = st.columns([1, 2])
        with col_prog:
            st.metric("Calibration Progress", f"{total_cal}/12")
            st.progress(progress, text=f"{'✅ Fully calibrated' if progress >= 1 else '⚠️ Incomplete'}")
            if progress < 1:
                st.info("Go to the **Calibration** tab to finish calibration.")

            # Quick actions
            if st.button("Reset All to 90°", use_container_width=True, type="primary"):
                try:
                    resp = requests.post(f"{api_url}/api/reset", timeout=5)
                    if resp.json().get("status") == "ok":
                        st.success("Reset done")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

            if st.button("Go to Neutrals", use_container_width=True):
                try:
                    resp = requests.post(f"{api_url}/api/goto_neutrals", timeout=5)
                    if resp.json().get("status") == "ok":
                        st.success("At neutral positions")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        with col_viz:
            if create_robot_topdown_view:
                # Determine leg colors based on calibration status
                leg_status = {}
                for leg, channels in LEG_CHANNELS.items():
                    cal_count = sum(1 for ch in channels if calib.get(str(ch), {}).get("calibrated", False))
                    if cal_count == 3:
                        leg_status[leg] = "#22c55e"  # Green
                    elif cal_count > 0:
                        leg_status[leg] = "#f59e0b"  # Orange
                    else:
                        leg_status[leg] = "#ef4444"  # Red
                st.markdown(
                    create_robot_topdown_view(leg_colors=leg_status, width=360),
                    unsafe_allow_html=True,
                )
                st.caption("🟢 All joints calibrated  🟡 Partial  🔴 None")
            else:
                st.info("Top-down visualization unavailable")

        st.divider()

        # Servo table
        servo_data = []
        for ch in range(12):
            ch_str = str(ch)
            servo_info = calib.get(ch_str, {})
            current_angle = angles.get(ch, angles.get(str(ch), 90))
            leg = servo_info.get("leg", "-")
            color = LEG_COLORS.get(leg, "#cccccc")
            servo_data.append({
                "Ch": ch,
                "Label": servo_info.get("label", f"Servo {ch}"),
                "Leg": leg,
                "Joint": servo_info.get("joint", "-"),
                "Current": f"{current_angle}",
                "Neutral": f"{servo_info.get('neutral_angle', 90)}",
                "Offset": f"{servo_info.get('offset', 0):+d}",
                "Cal": "✅" if servo_info.get("calibrated", False) else "❌",
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
        leg = servo_info.get("leg", "-")
        joint = servo_info.get("joint", "-")

        col_info, col_viz = st.columns([2, 1])
        with col_info:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Leg", leg)
            with col2:
                st.metric("Joint", joint)
            with col3:
                st.metric("Neutral", f"{servo_info.get('neutral_angle', 90)}")
            with col4:
                current = angles.get(channel, angles.get(str(channel), 90))
                st.metric("Current", f"{current}")

            st.divider()

            # Angle control
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

            # Quick angles
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

        with col_viz:
            # Leg diagram if we have this servo's leg info
            if create_leg_diagram and leg in LEG_CHANNELS:
                leg_chs = LEG_CHANNELS[leg]
                ja = {}
                for jname, ch in zip(JOINT_NAMES, leg_chs):
                    ja[jname] = angles.get(ch, angles.get(str(ch), 90))
                st.markdown(create_leg_diagram(ja, leg, width=280), unsafe_allow_html=True)
                st.caption(f"{leg} leg current pose")
            else:
                st.info("Leg diagram unavailable")

            # Offset explanation mini
            offset = servo_info.get("offset", 0)
            st.metric("Offset", f"{offset:+d}°")
            st.caption("offset = neutral_angle - 90")

    # === CALIBRATION TAB ===
    with tab_calibration:
        # Fetch fresh calibration data
        try:
            calib_resp = requests.get(f"{api_url}/api/calibration", timeout=2)
            calib_data = calib_resp.json()
            servos = calib_data.get("servos", {})
        except Exception as e:
            st.error(f"Cannot get calibration: {e}")
            return

        # Session state for wizard
        if "cal_step" not in st.session_state:
            st.session_state.cal_step = 0
        if "cal_selected_leg" not in st.session_state:
            st.session_state.cal_selected_leg = "FL"
        if "cal_leg_index" not in st.session_state:
            st.session_state.cal_leg_index = 0

        step = st.session_state.cal_step

        # Step indicator
        if create_calibration_workflow_diagram:
            st.markdown(create_calibration_workflow_diagram(step, width=640), unsafe_allow_html=True)
        else:
            st.write(f"Step {step + 1} of 5")

        st.divider()

        # ---- STEP 0: PREPARE ----
        if step == 0:
            st.header("Step 1: Prepare")
            st.info("Before starting, make sure the robot is positioned safely for calibration.")

            col_text, col_exp = st.columns([2, 1])
            with col_text:
                st.markdown("""
                ### 📋 Preparation Checklist
                1. **Place robot on a box or block** so the legs hang freely without touching the ground.
                2. **Ensure all servo horns are attached** but not forced against their stops.
                3. **Power on** the robot and connect to this interface.
                4. Have a **small screwdriver or hex key** ready for adjusting horns if needed.
                
                ### ❓ What is calibration?
                Each servo has a software center (90°), but due to manufacturing tolerances and how you mounted the horn, the physical "neutral" position may differ. Calibration measures this difference (the **offset**) so the robot knows how to command each servo to reach the desired pose.
                """)

            with col_exp:
                if create_offset_explanation_diagram:
                    st.markdown(create_offset_explanation_diagram(width=400), unsafe_allow_html=True)
                else:
                    st.code("offset = neutral_angle - 90")
                    st.caption("If servo is at 82° when leg is straight, offset = -8")

            if st.button("➡️ Next: Center All Servos", type="primary", use_container_width=True):
                st.session_state.cal_step = 1
                st.rerun()

        # ---- STEP 1: CENTER ALL ----
        elif step == 1:
            st.header("Step 2: Center All Servos")
            st.info("Set every servo to its raw/software center (90°). The legs probably won't look perfect yet — that's expected!")

            col_left, col_right = st.columns([1, 1])
            with col_left:
                st.markdown("""
                ### What happens now?
                - All 12 servos move to **90° raw**.
                - This is the electronic center of each servo.
                - The leg will likely NOT be perfectly straight — that's why we measure offsets next.
                
                ### ⚠️ Safety
                Make sure legs can move freely. If a servo is straining, **release it** and reposition the horn before continuing.
                """)

                if st.button("🔘 Set ALL Servos to 90° (Raw)", type="primary", use_container_width=True):
                    for ch in range(12):
                        _send_servo(api_url, ch, 90, raw=True)
                    st.success("All servos set to 90° raw!")
                    time.sleep(0.3)
                    st.rerun()

                if st.button("🔓 Release All (disable PWM)", use_container_width=True):
                    for ch in range(12):
                        try:
                            requests.post(f"{api_url}/api/servo/{ch}/disable", timeout=0.5)
                        except:
                            pass
                    st.success("All servos released. Adjust horns by hand.")

            with col_right:
                # Show 3D robot at all-90
                try:
                    from components.robot_3d import create_3d_robot
                    all_90 = {i: 90 for i in range(12)}
                    fig = create_3d_robot(all_90, height=350)
                    st.plotly_chart(fig, use_container_width=True, key="cal_3d_center")
                except Exception:
                    st.info("3D preview unavailable")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("⬅️ Back", use_container_width=True):
                    st.session_state.cal_step = 0
                    st.rerun()
            with c2:
                if st.button("➡️ Next: Calibrate Legs", type="primary", use_container_width=True):
                    st.session_state.cal_step = 2
                    st.rerun()

        # ---- STEP 2: CALIBRATE LEGS ----
        elif step == 2:
            st.header("Step 3: Calibrate Each Leg")
            st.info("Select a leg, then adjust each joint until it matches the target physical position. Save each joint individually.")

            # Leg selector
            legs = ["FL", "FR", "RL", "RR"]
            leg_index = st.session_state.cal_leg_index

            cols = st.columns(4)
            for i, leg in enumerate(legs):
                with cols[i]:
                    color = LEG_COLORS[leg]
                    is_selected = i == leg_index
                    btn_type = "primary" if is_selected else "secondary"
                    if st.button(leg, key=f"cal_leg_btn_{leg}", use_container_width=True, type=btn_type):
                        st.session_state.cal_leg_index = i
                        st.session_state.cal_selected_leg = leg
                        st.rerun()

            selected_leg = legs[leg_index]
            channels = LEG_CHANNELS[selected_leg]

            # Top-down highlight
            if create_robot_topdown_view:
                st.markdown(
                    create_robot_topdown_view(selected_leg=selected_leg, width=300),
                    unsafe_allow_html=True,
                )

            st.divider()

            # Joint target descriptions
            target_desc = {
                "hip": f"**{selected_leg} Hip**: Leg should point straight down from the body (no forward or backward tilt).",
                "knee": f"**{selected_leg} Knee**: Upper leg should hang vertically downward from the hip.",
                "ankle": f"**{selected_leg} Ankle**: Lower leg should continue straight from the knee. Foot flat / pointing down.",
            }

            # Per-joint calibration
            for idx, (ch, jname) in enumerate(zip(channels, JOINT_NAMES)):
                ch_str = str(ch)
                servo = servos.get(ch_str, {})
                current_saved = servo.get("neutral_angle", 90)

                # Card container using columns
                st.markdown(f"#### {jname.title()} (Channel {ch})")
                col_ctrl, col_viz = st.columns([2, 1])

                with col_ctrl:
                    st.caption(target_desc[jname])

                    # Session state for this joint's calibration angle
                    cal_key = f"cal_wiz_{ch}"
                    if cal_key not in st.session_state:
                        st.session_state[cal_key] = current_saved

                    cal_angle = st.slider(
                        f"Raw angle for {selected_leg} {jname}",
                        0, 180,
                        int(st.session_state[cal_key]),
                        key=f"cal_slider_{ch}",
                        label_visibility="collapsed",
                    )

                    # Live send on slider change
                    if cal_angle != st.session_state[cal_key]:
                        st.session_state[cal_key] = cal_angle
                        _send_servo(api_url, ch, cal_angle, raw=True)

                    # Offset display
                    offset = cal_angle - 90
                    st.write(f"**{cal_angle}°** (offset: **{offset:+d}°** from center)")

                    # Fine tune buttons
                    fc1, fc2, fc3, fc4 = st.columns(4)
                    with fc1:
                        if st.button("-5", key=f"cfm5_{ch}"):
                            st.session_state[cal_key] = max(0, cal_angle - 5)
                            _send_servo(api_url, ch, st.session_state[cal_key], raw=True)
                            st.rerun()
                    with fc2:
                        if st.button("-1", key=f"cfm1_{ch}"):
                            st.session_state[cal_key] = max(0, cal_angle - 1)
                            _send_servo(api_url, ch, st.session_state[cal_key], raw=True)
                            st.rerun()
                    with fc3:
                        if st.button("+1", key=f"cfp1_{ch}"):
                            st.session_state[cal_key] = min(180, cal_angle + 1)
                            _send_servo(api_url, ch, st.session_state[cal_key], raw=True)
                            st.rerun()
                    with fc4:
                        if st.button("+5", key=f"cfp5_{ch}"):
                            st.session_state[cal_key] = min(180, cal_angle + 5)
                            _send_servo(api_url, ch, st.session_state[cal_key], raw=True)
                            st.rerun()

                    # Save button for this joint
                    if st.button(f"💾 Save {jname.title()}", key=f"cfsave_{ch}", type="primary"):
                        servo["neutral_angle"] = cal_angle
                        servo["offset"] = cal_angle - 90
                        servo["calibrated"] = True
                        _save_servo_calib(api_url, ch, servo)
                        st.success(f"Saved {selected_leg} {jname} = {cal_angle}° (offset {offset:+d}°)")
                        time.sleep(0.3)
                        st.rerun()

                    # Quick release/goto
                    qcol1, qcol2 = st.columns(2)
                    with qcol1:
                        if st.button(f"🔓 Release", key=f"cfrel_{ch}", use_container_width=True):
                            try:
                                requests.post(f"{api_url}/api/servo/{ch}/disable", timeout=1)
                                st.info("Servo released. Move by hand.")
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with qcol2:
                        if st.button(f"Goto saved ({current_saved})", key=f"cfgoto_{ch}", use_container_width=True):
                            st.session_state[cal_key] = current_saved
                            _send_servo(api_url, ch, current_saved, raw=True)
                            st.rerun()

                with col_viz:
                    if create_leg_diagram:
                        ja = {jn: st.session_state.get(f"cal_wiz_{c}", servos.get(str(c), {}).get("neutral_angle", 90)) for jn, c in zip(JOINT_NAMES, channels)}
                        st.markdown(create_leg_diagram(ja, selected_leg, width=260), unsafe_allow_html=True)
                    else:
                        st.write(f"Hip: {st.session_state.get(f'cal_wiz_{channels[0]}', 90)}°")
                        st.write(f"Knee: {st.session_state.get(f'cal_wiz_{channels[1]}', 90)}°")
                        st.write(f"Ankle: {st.session_state.get(f'cal_wiz_{channels[2]}', 90)}°")

                st.markdown("---")

            # Leg navigation
            nav_prev, nav_save_all, nav_next = st.columns(3)
            with nav_prev:
                if leg_index > 0:
                    if st.button("⬅️ Previous Leg", use_container_width=True):
                        st.session_state.cal_leg_index = leg_index - 1
                        st.rerun()
            with nav_save_all:
                if st.button(f"💾 Save ALL {selected_leg} Joints", type="primary", use_container_width=True):
                    for ch in channels:
                        ch_str = str(ch)
                        s = servos.get(ch_str, {})
                        cal_angle = st.session_state.get(f"cal_wiz_{ch}", s.get("neutral_angle", 90))
                        s["neutral_angle"] = cal_angle
                        s["offset"] = cal_angle - 90
                        s["calibrated"] = True
                        _save_servo_calib(api_url, ch, s)
                    st.success(f"All {selected_leg} joints saved!")
                    time.sleep(0.3)
                    st.rerun()
            with nav_next:
                if leg_index < 3:
                    if st.button("Next Leg ➡️", use_container_width=True):
                        st.session_state.cal_leg_index = leg_index + 1
                        st.rerun()
                else:
                    if st.button("➡️ Finish & Verify", type="primary", use_container_width=True):
                        st.session_state.cal_step = 3
                        st.rerun()

            # Also allow jumping back
            if st.button("⬅️ Back to Center All", use_container_width=True):
                st.session_state.cal_step = 1
                st.rerun()

        # ---- STEP 3: VERIFY ----
        elif step == 3:
            st.header("Step 4: Verify Calibration")
            st.info("Check that all legs are in a good neutral pose with the saved calibration values.")

            col_viz, col_data = st.columns([2, 1])
            with col_viz:
                try:
                    from components.robot_3d import create_3d_robot
                    # Use saved neutral angles for preview
                    preview_angles = {}
                    for ch in range(12):
                        preview_angles[ch] = servos.get(str(ch), {}).get("neutral_angle", 90)
                    fig = create_3d_robot(preview_angles, height=400)
                    st.plotly_chart(fig, use_container_width=True, key="cal_3d_verify")
                except Exception as e:
                    st.error(f"3D preview error: {e}")

                if st.button("🦵 Go to Neutral Pose", type="primary", use_container_width=True):
                    try:
                        resp = requests.post(f"{api_url}/api/goto_neutrals", timeout=5)
                        if resp.json().get("status") == "ok":
                            st.success("Robot moved to neutral pose!")
                        else:
                            st.error("Failed")
                    except Exception as e:
                        st.error(f"Error: {e}")

            with col_data:
                st.subheader("Offset Summary")
                for leg, channels in LEG_CHANNELS.items():
                    st.markdown(f"**{leg}**")
                    for ch, jname in zip(channels, JOINT_NAMES):
                        s = servos.get(str(ch), {})
                        na = s.get("neutral_angle", 90)
                        off = s.get("offset", 0)
                        cal = s.get("calibrated", False)
                        icon = "✅" if cal else "❌"
                        st.markdown(f"- {jname}: {na}° (offset {off:+d}°) {icon}")

                # Support polygon (conceptual)
                if create_support_polygon_diagram:
                    st.markdown("#### Stability Preview")
                    # Approximate foot positions at neutral
                    foot_pos = {
                        "FL": (0.093, 0.039, True),
                        "FR": (0.093, -0.039, True),
                        "RL": (-0.093, 0.039, True),
                        "RR": (-0.093, -0.039, True),
                    }
                    st.markdown(create_support_polygon_diagram(foot_pos, width=260), unsafe_allow_html=True)

            if st.button("⬅️ Back to Calibration", use_container_width=True):
                st.session_state.cal_step = 2
                st.rerun()
            if st.button("➡️ Next: Save to File", type="primary", use_container_width=True):
                st.session_state.cal_step = 4
                st.rerun()

        # ---- STEP 4: SAVE ----
        elif step == 4:
            st.header("Step 5: Save Calibration")
            st.info("Persist all calibration values to the robot's configuration file.")

            # Summary table
            summary_data = []
            for ch in range(12):
                s = servos.get(str(ch), {})
                summary_data.append({
                    "Channel": ch,
                    "Label": s.get("label", "-"),
                    "Neutral": s.get("neutral_angle", 90),
                    "Offset": f"{s.get('offset', 0):+d}",
                    "Calibrated": "✅" if s.get("calibrated", False) else "❌",
                })
            df_sum = pd.DataFrame(summary_data)
            st.dataframe(df_sum, use_container_width=True, hide_index=True)

            total = sum(1 for ch in range(12) if servos.get(str(ch), {}).get("calibrated", False))
            st.metric("Total Calibrated", f"{total}/12")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("💾 Save All to File", type="primary", use_container_width=True):
                    try:
                        requests.post(f"{api_url}/api/calibration/save", timeout=3)
                        st.success("Calibration saved to file! ✅")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Save failed: {e}")

            with col2:
                if st.button("🔄 Start Over", use_container_width=True):
                    st.session_state.cal_step = 0
                    st.session_state.cal_leg_index = 0
                    st.rerun()

            st.divider()
            st.subheader("Advanced")
            with st.expander("Reset calibration to defaults"):
                st.warning("This will erase all calibration data!")
                if st.button("Reset Calibration", use_container_width=True):
                    try:
                        requests.post(f"{api_url}/api/calibration/reset", timeout=3)
                        st.success("Calibration reset to defaults.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Reset failed: {e}")

            if st.button("⬅️ Back to Verify", use_container_width=True):
                st.session_state.cal_step = 3
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
                    leg = calib.get(str(i), {}).get("leg", "")
                    color = LEG_COLORS.get(leg, "#cccccc")
                    if st.checkbox(f"{label}", key=f"bulk_ch_{i}"):
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
                    st.success(f"Sent {bulk_angle}° to {success_count}/{len(selected_servos)} servos")
                    st.rerun()
                else:
                    st.warning("Select at least one servo")

        with col_bulk2:
            st.write("**Leg quick control:**")
            leg_bulk_angle = st.slider("Leg Angle", 0, 180, 90, key="leg_bulk_angle")

            for leg, channels in LEG_CHANNELS.items():
                color = LEG_COLORS[leg]
                if st.button(f"{leg} → {leg_bulk_angle}°", use_container_width=True):
                    for ch in channels:
                        requests.post(f"{api_url}/api/servo/{ch}", json={"angle": leg_bulk_angle, "raw": False}, timeout=1)
                    st.success(f"{leg} set to {leg_bulk_angle}°")
                    st.rerun()

            st.divider()
            if st.button("All Legs to Neutral", use_container_width=True, type="primary"):
                try:
                    resp = requests.post(f"{api_url}/api/goto_neutrals", timeout=5)
                    if resp.json().get("status") == "ok":
                        st.success("All legs at neutral")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

            if st.button("All Legs to 90° Raw", use_container_width=True):
                for ch in range(12):
                    requests.post(f"{api_url}/api/servo/{ch}", json={"angle": 90, "raw": True}, timeout=1)
                st.success("All servos at 90° raw")
                st.rerun()
