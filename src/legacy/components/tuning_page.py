"""Tuning page - Gait parameters and balance tuning with rich visual aids."""
import streamlit as st
import requests
import math

from components.robot_viz import create_robot_svg, create_side_svg, create_front_svg

try:
    from components.calibration_viz import create_gait_hildebrand_diagram
except ImportError:
    create_gait_hildebrand_diagram = None


def save_tuning(api_url: str, key: str, value) -> bool:
    """Save a tuning parameter to the backend."""
    try:
        response = requests.post(
            f"{api_url}/api/tuning/{key}",
            json={"value": value},
            timeout=2
        )
        return response.ok
    except Exception:
        return False


# ---------------------------------------------------------------------------
# SVG helper generators
# ---------------------------------------------------------------------------

def _create_knee_bend_poses_svg(width: int = 400, height: int = 160) -> str:
    """Side-view SVG showing three robot poses at different knee bend angles."""

    def _leg_path(knee_bend: float, ox: float, oy: float, scale: float = 1.0) -> tuple:
        """Return (hip, knee, foot) coords for a simplified 2-DOF leg."""
        thigh_len = 55 * scale
        shin_len = 55 * scale
        hip_angle = math.radians(70)          # hip forward from vertical
        knee_extra = math.radians(knee_bend)  # extra knee bend inward
        knee_angle = hip_angle + knee_extra   # knee relative to thigh

        hip_x = ox
        hip_y = oy
        knee_x = hip_x + thigh_len * math.sin(hip_angle)
        knee_y = hip_y + thigh_len * math.cos(hip_angle)
        foot_x = knee_x + shin_len * math.sin(knee_angle)
        foot_y = knee_y + shin_len * math.cos(knee_angle)
        return (hip_x, hip_y), (knee_x, knee_y), (foot_x, foot_y)

    def _pose(knee_bend: float, cx: float, label: str, color: str, scale: float = 1.0) -> str:
        body_w, body_h = 70 * scale, 25 * scale
        bx, by = cx - body_w / 2, 30
        (hx, hy), (kx, ky), (fx, fy) = _leg_path(knee_bend, cx, by + body_h, scale)
        # Draw back leg slightly offset for depth
        off = 8 * scale
        (_, _), (kx2, ky2), (fx2, fy2) = _leg_path(knee_bend, cx + off, by + body_h, scale)

        parts = []
        # Body
        parts.append(
            f'<rect x="{bx}" y="{by}" width="{body_w}" height="{body_h}" '
            f'fill="#334155" stroke="{color}" stroke-width="2" rx="4"/>'
        )
        # Head marker
        parts.append(
            f'<polygon points="{bx+body_w},{by+body_h/2} {bx+body_w+12},{by+body_h/2-6} '
            f'{bx+body_w+12},{by+body_h/2+6}" fill="#3b82f6"/>'
        )
        # Back leg (darker)
        parts.append(
            f'<line x1="{cx+off}" y1="{by+body_h}" x2="{kx2}" y2="{ky2}" '
            f'stroke="#475569" stroke-width="3" stroke-linecap="round"/>'
        )
        parts.append(
            f'<line x1="{kx2}" y1="{ky2}" x2="{fx2}" y2="{fy2}" '
            f'stroke="#475569" stroke-width="3" stroke-linecap="round"/>'
        )
        # Front leg (brighter)
        parts.append(
            f'<line x1="{cx}" y1="{by+body_h}" x2="{kx}" y2="{ky}" '
            f'stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        )
        parts.append(
            f'<line x1="{kx}" y1="{ky}" x2="{fx}" y2="{fy}" '
            f'stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        )
        # Joints
        parts.append(f'<circle cx="{hx}" cy="{hy}" r="3" fill="{color}"/>')
        parts.append(f'<circle cx="{kx}" cy="{ky}" r="3" fill="{color}"/>')
        parts.append(f'<circle cx="{fx}" cy="{fy}" r="3" fill="white"/>')
        # Label
        parts.append(
            f'<text x="{cx}" y="{height-10}" text-anchor="middle" '
            f'fill="#94a3b8" font-family="monospace" font-size="11">{label}</text>'
        )
        return "\n".join(parts)

    low = _pose(50, 70, "Low (50°)", "#ef4444", scale=0.85)
    med = _pose(40, 200, "Medium (40°)", "#f59e0b", scale=0.85)
    high = _pose(20, 330, "High (20°)", "#22c55e", scale=0.85)

    return f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="{width}" height="{height}" fill="#0f172a" rx="8"/>
        <line x1="10" y1="{height-35}" x2="{width-10}" y2="{height-35}" stroke="#334155" stroke-width="2"/>
        {low}
        {med}
        {high}
    </svg>
    '''


def _create_spirit_level_svg(pitch: float, roll: float, width: int = 320, height: int = 90) -> str:
    """Spirit-level style bar that moves with pitch/roll."""
    pitch = max(-20, min(20, pitch))
    roll = max(-20, min(20, roll))
    cx, cy = width // 2, height // 2
    bar_w, bar_h = width * 0.85, 24
    bx, by = (width - bar_w) / 2, cy - bar_h / 2

    # Bubble position based on roll (primary axis for spirit level)
    max_off = bar_w / 2 - 14
    bubble_x = cx + (roll / 20) * max_off

    is_level = abs(pitch) < 2 and abs(roll) < 2
    bubble_color = "#22c55e" if is_level else "#f59e0b" if max(abs(pitch), abs(roll)) < 8 else "#ef4444"

    return f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="{width}" height="{height}" fill="#0f172a" rx="8"/>
        <!-- Bar background -->
        <rect x="{bx}" y="{by}" width="{bar_w}" height="{bar_h}" fill="#1e293b" stroke="#334155" stroke-width="2" rx="{bar_h/2}"/>
        <!-- Ticks -->
        <line x1="{cx}" y1="{by-4}" x2="{cx}" y2="{by+bar_h+4}" stroke="#64748b" stroke-width="1"/>
        <line x1="{cx - bar_w/4}" y1="{by+4}" x2="{cx - bar_w/4}" y2="{by+bar_h-4}" stroke="#475569" stroke-width="1"/>
        <line x1="{cx + bar_w/4}" y1="{by+4}" x2="{cx + bar_w/4}" y2="{by+bar_h-4}" stroke="#475569" stroke-width="1"/>
        <!-- Bubble -->
        <circle cx="{bubble_x}" cy="{cy}" r="10" fill="{bubble_color}" stroke="white" stroke-width="2"/>
        <!-- Labels -->
        <text x="{width/2}" y="{height-8}" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="11">
            P: {pitch:+.1f}°  R: {roll:+.1f}°
        </text>
        <text x="{width/2}" y="18" text-anchor="middle" fill="#64748b" font-family="monospace" font-size="10">
            Spirit Level (Roll)
        </text>
    </svg>
    '''


def _create_balance_correction_svg(pitch: float, width: int = 260, height: int = 140) -> str:
    """Side-view robot with arrows showing corrective forces."""
    pitch = max(-30, min(30, pitch))
    cx, cy = width // 2, height // 2
    body_w, body_h = 90, 28
    bx, by = cx - body_w / 2, cy - body_h / 2

    color = "#22c55e" if abs(pitch) < 5 else "#f59e0b" if abs(pitch) < 15 else "#ef4444"
    correction_dir = -1 if pitch > 0 else 1  # pitch nose up -> push nose down

    # Arrow near front of body
    arrow_x = bx + body_w - 10
    arrow_y = by + body_h / 2
    arrow_len = 30
    ax_end = arrow_x + correction_dir * arrow_len
    ay_end = arrow_y

    def _arrow_head(x, y, direction) -> str:
        d = direction
        return (
            f'<polygon points="{x},{y} {x - d*8},{y - 5} {x - d*8},{y + 5}" '
            f'fill="#3b82f6"/>'
        )

    return f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="{width}" height="{height}" fill="#0f172a" rx="8"/>
        <!-- Ground -->
        <line x1="10" y1="{cy + 35}" x2="{width-10}" y2="{cy + 35}" stroke="#334155" stroke-width="2"/>
        <!-- Legs -->
        <line x1="{bx+15}" y1="{by+body_h}" x2="{bx+15}" y2="{cy+35}" stroke="#475569" stroke-width="3" stroke-linecap="round"/>
        <line x1="{bx+body_w-15}" y1="{by+body_h}" x2="{bx+body_w-15}" y2="{cy+35}" stroke="#475569" stroke-width="3" stroke-linecap="round"/>
        <!-- Body -->
        <g transform="rotate({-pitch}, {cx}, {cy})">
            <rect x="{bx}" y="{by}" width="{body_w}" height="{body_h}" fill="#334155" stroke="{color}" stroke-width="2" rx="4"/>
            <polygon points="{bx+body_w},{by+body_h/2} {bx+body_w+10},{by+body_h/2-5} {bx+body_w+10},{by+body_h/2+5}" fill="#3b82f6"/>
        </g>
        <!-- Correction arrow -->
        <line x1="{arrow_x}" y1="{arrow_y}" x2="{ax_end}" y2="{ay_end}" stroke="#3b82f6" stroke-width="2" stroke-dasharray="4,2"/>
        {_arrow_head(ax_end, ay_end, correction_dir)}
        <text x="{ax_end + correction_dir*6}" y="{ay_end - 8}" text-anchor="{'start' if correction_dir > 0 else 'end'}" fill="#3b82f6" font-family="monospace" font-size="10">Correction</text>
        <!-- Label -->
        <text x="{width/2}" y="15" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="11">Tilt Correction Force</text>
    </svg>
    '''


def _create_gait_hildebrand_fallback(gait_type: str, width: int = 320, height: int = 160) -> str:
    """Simple fallback SVG gait diagram when calibration_viz is unavailable."""
    cx, cy = width // 2, height // 2

    descriptions = {
        "trot": (
            "Trot: diagonal pairs move together",
            ["LF+RR", "RF+LR"],
            ["#22c55e", "#334155", "#22c55e", "#334155"]
        ),
        "walk": (
            "Walk: 3 legs on ground at all times",
            ["LF", "RF", "RR", "LR"],
            ["#22c55e", "#334155", "#334155", "#22c55e"]
        ),
        "crawl": (
            "Crawl: shift weight, lift one leg",
            ["LF", "RF", "RR", "LR"],
            ["#f59e0b", "#334155", "#334155", "#334155"]
        ),
    }
    label, leg_order, colors = descriptions.get(gait_type.lower(), descriptions["trot"])

    leg_w = 28
    gap = (width - 40 - len(leg_order) * leg_w) / (len(leg_order) - 1)
    bars = []
    for i, (leg, color) in enumerate(zip(leg_order, colors)):
        x = 20 + i * (leg_w + gap)
        # Ground contact bar
        bars.append(
            f'<rect x="{x}" y="{cy-10}" width="{leg_w}" height="20" '
            f'rx="4" fill="{color}" stroke="white" stroke-width="1"/>'
        )
        bars.append(
            f'<text x="{x + leg_w/2}" y="{cy+40}" text-anchor="middle" '
            f'fill="#94a3b8" font-family="monospace" font-size="10">{leg}</text>'
        )

    return f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="{width}" height="{height}" fill="#0f172a" rx="8"/>
        <text x="{width/2}" y="20" text-anchor="middle" fill="#e2e8f0" font-family="monospace" font-size="12" font-weight="bold">{label}</text>
        {"\n".join(bars)}
        <text x="{width/2}" y="{height-10}" text-anchor="middle" fill="#64748b" font-family="monospace" font-size="10">Green = swinging leg(s)</text>
    </svg>
    '''


# ---------------------------------------------------------------------------
# Main page renderer
# ---------------------------------------------------------------------------

def render_tuning_page(api_url):
    st.title("🦵 Robot Tuning")

    # Fetch state
    tuning = {}
    pitch, roll = 0.0, 0.0
    connected = False

    try:
        tuning_response = requests.get(f"{api_url}/api/tuning", timeout=2)
        if tuning_response.ok:
            tuning = tuning_response.json()
            connected = True
    except Exception:
        st.error("Cannot connect to backend")

    try:
        ang_response = requests.get(f"{api_url}/api/balance/angles", timeout=1)
        if ang_response.ok:
            ang = ang_response.json()
            pitch = float(ang.get("pitch", 0))
            roll = float(ang.get("roll", 0))
    except Exception:
        pass

    # Connection pill
    if connected:
        st.success("🟢 Connected to robot backend")
    else:
        st.error("🔴 Disconnected - changes will not be applied")

    t1, t2, t3, t4 = st.tabs(["🦵 Stand", "📐 IMU Cal", "⚖️ Balance", "🚶 Gait"])

    # =====================================================================
    # STAND TAB
    # =====================================================================
    with t1:
        st.subheader("Stand Position")
        st.info(
            "Knee Bend determines how low the robot crouches. "
            "For walking, **30–40°** usually works best. "
            "Too low and legs can't lift; too high and the robot becomes tippy."
        )

        left, right = st.columns([1, 1])

        with right:
            st.markdown("#### Visual Guide")
            st.markdown(
                _create_knee_bend_poses_svg(),
                unsafe_allow_html=True
            )
            st.caption(
                "Lower = more crouched, stable but slower  |  "
                "Higher = taller, faster but less stable"
            )

        with left:
            st.markdown("#### Controls")
            kb = st.slider(
                "Knee Bend (degrees)",
                min_value=0,
                max_value=60,
                value=int(tuning.get("knee_bend", 40)),
                step=5,
                help=(
                    "0–20: Tall stance – max speed, less stable\n"
                    "20–40: Normal stance – balanced\n"
                    "40–60: Low stance – max stability, slower"
                )
            )

            # Zone badges
            if kb <= 20:
                st.success("🏃 Tall stance – max speed, less stable")
            elif kb <= 40:
                st.info("✅ Normal stance – balanced")
            else:
                st.warning("🐢 Low stance – max stability, slower")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🧪 Test Stand", use_container_width=True, disabled=not connected,
                             help="Temporarily applies the pose without saving to tuning.json"):
                    try:
                        resp = requests.post(
                            f"{api_url}/api/gait/stand_height",
                            json={"knee_bend": kb},
                            timeout=2
                        )
                        if resp.ok:
                            preview_resp = requests.post(
                                f"{api_url}/api/gait/preview_stand", timeout=2
                            )
                            if preview_resp.ok:
                                st.success("Preview applied temporarily!")
                            else:
                                st.error("Preview failed")
                        else:
                            st.error("Stand height update failed")
                    except Exception as e:
                        st.error(f"Error: {e}")

            with c2:
                if st.button("💾 Save", use_container_width=True, type="primary", disabled=not connected,
                             help="Persist this value to tuning.json"):
                    if save_tuning(api_url, "knee_bend", kb):
                        st.success("Saved!")
                    else:
                        st.error("Save failed")

    # =====================================================================
    # IMU CALIBRATION TAB
    # =====================================================================
    with t2:
        st.subheader("📐 IMU Calibration")
        st.info(
            "Place the robot on **perfectly flat ground**. "
            "All 4 feet must touch the surface evenly. "
            "Wait until the indicator reads LEVEL before calibrating."
        )

        left, right = st.columns([2, 1])
        with left:
            st.markdown(create_robot_svg(pitch, roll, 280, 280), unsafe_allow_html=True)
        with right:
            st.markdown(create_side_svg(pitch), unsafe_allow_html=True)
            st.markdown(create_front_svg(roll), unsafe_allow_html=True)
            st.markdown("<br/>", unsafe_allow_html=True)
            st.markdown(
                _create_spirit_level_svg(pitch, roll),
                unsafe_allow_html=True
            )

        is_level = abs(pitch) < 2 and abs(roll) < 2
        if is_level:
            st.success(f"✅ LEVEL — Pitch: {pitch:.1f}°, Roll: {roll:.1f}°")
        else:
            st.warning(f"⚠️ NOT LEVEL — Pitch: {pitch:.1f}°, Roll: {roll:.1f}°")

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

    # =====================================================================
    # BALANCE TAB
    # =====================================================================
    with t3:
        st.subheader("⚖️ Balance Settings")
        st.info(
            "Balance uses the IMU to detect tilt and automatically adjusts leg angles "
            "to keep the robot level. If the robot shakes or vibrates, **reduce Kp**."
        )

        left, right = st.columns([1, 1])

        with right:
            st.markdown("#### Correction Visual")
            st.markdown(
                _create_balance_correction_svg(pitch),
                unsafe_allow_html=True
            )
            st.caption(
                "The blue arrow shows the direction the robot pushes to counteract tilt."
            )

            # Live tilt indicator
            st.markdown("#### Live Tilt")
            st.markdown(
                create_robot_svg(pitch, roll, 200, 200),
                unsafe_allow_html=True
            )

        with left:
            st.markdown("#### Controls")
            kp = st.slider(
                "Kp (Proportional Gain)",
                min_value=0.1,
                max_value=1.5,
                value=float(tuning.get("balance_kp", 0.5)),
                step=0.1,
                help="How aggressively the robot reacts to tilt."
            )

            if kp <= 0.3:
                st.info("🐢 Gentle – smooth but slow correction")
            elif kp <= 0.7:
                st.success("✅ Normal – balanced response")
            else:
                st.warning("🚀 Aggressive – fast correction but may oscillate")

            if kp > 1.0:
                st.error("⚠️ Warning: values above 1.0 often cause shaking. Reduce if the robot vibrates.")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Save", type="primary", key="sv3", use_container_width=True, disabled=not connected):
                    if save_tuning(api_url, "balance_kp", kp):
                        try:
                            requests.post(f"{api_url}/api/balance/kp", json={"kp": kp}, timeout=2)
                        except Exception:
                            pass
                        st.success("Saved!")
                    else:
                        st.error("Save failed")

            with c2:
                if st.button("⚡ Apply Live", key="apply_kp", use_container_width=True, disabled=not connected,
                             help="Send to backend immediately without persisting"):
                    try:
                        response = requests.post(f"{api_url}/api/balance/kp", json={"kp": kp}, timeout=2)
                        if response.ok:
                            st.info(f"Kp temporarily set to {kp}")
                        else:
                            st.error("Failed to apply")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # =====================================================================
    # GAIT TAB
    # =====================================================================
    with t4:
        st.subheader("🚶 Gait Parameters")

        # Gait type selector
        gait_type = st.selectbox(
            "Gait Type",
            options=["Trot", "Walk", "Crawl"],
            index=0,
            help="Choose the leg coordination pattern."
        )

        # Gait diagram
        st.markdown("#### Leg Coordination Pattern")
        if create_gait_hildebrand_diagram is not None:
            try:
                st.markdown(
                    create_gait_hildebrand_diagram(gait_type.lower(), width=360),
                    unsafe_allow_html=True
                )
            except Exception:
                st.markdown(
                    _create_gait_hildebrand_fallback(gait_type.lower(), width=360),
                    unsafe_allow_html=True
                )
        else:
            st.markdown(
                _create_gait_hildebrand_fallback(gait_type.lower(), width=360),
                unsafe_allow_html=True
            )

        gait_descriptions = {
            "Trot": (
                "Diagonal legs move together. Fast but requires balance. "
                "Best for flat ground and confident tuning."
            ),
            "Walk": (
                "3 legs on the ground at all times. Slower but very stable. "
                "Good for rough terrain or when learning."
            ),
            "Crawl": (
                "Shift body weight before lifting each leg. Slowest but safest. "
                "Use when balance is poor or space is tight."
            ),
        }
        st.caption(gait_descriptions[gait_type])

        st.divider()

        left, right = st.columns([1, 1])

        with left:
            st.markdown("#### Timing & Motion")
            cyc = st.slider(
                "Cycle Time (seconds)",
                min_value=0.4,
                max_value=1.5,
                value=float(tuning.get("cycle_time", 0.8)),
                step=0.1,
                help="How long one complete step cycle takes."
            )

            # Speed estimate (very rough heuristic)
            speed_cm_s = round(8.0 / cyc, 1)
            st.info(f"🚀 Estimated walking speed: **~{speed_cm_s} cm/s**")

            if cyc <= 0.5:
                st.warning("⚡ Fast / Frenetic – requires excellent balance")
            elif cyc <= 0.9:
                st.success("✅ Normal – good for everyday use")
            else:
                st.info("🐢 Slow / Smooth – very stable, sluggish")

            st.caption(
                "Faster cycle = robot walks quicker but needs better balance. "
                "Slower = more stable but sluggish."
            )

            st.markdown("---")

            step_deg = st.slider(
                "Step Height (degrees)",
                min_value=10,
                max_value=40,
                value=int(tuning.get("step_height", 25)),
                step=5,
                help="How high the foot lifts during the swing phase."
            )

            # Rough mm conversion (~1.5 mm per degree for this robot scale)
            step_mm = round(step_deg * 1.5)
            st.info(f"📏 Approximate lift: **~{step_mm} mm**")

            if step_deg <= 15:
                st.warning("👟 Low shuffle – efficient, but might trip on bumps")
            elif step_deg <= 30:
                st.success("✅ Normal clearance")
            else:
                st.info("🏔️ High step – clears obstacles but slow and energy-hungry")

            st.caption(
                "Too low = feet drag. Too high = wasted energy and slower gait."
            )

        with right:
            st.markdown("#### Presets")
            st.caption("One-click configurations with proven values.")

            presets = {
                "Slow & Safe": {
                    "cycle_time": 1.2,
                    "step_height": 20,
                    "desc": "Cycle: 1.2 s | Step: 20° (~30 mm)\nBest for: Learning, rough ground, tight spaces",
                },
                "Normal": {
                    "cycle_time": 0.8,
                    "step_height": 25,
                    "desc": "Cycle: 0.8 s | Step: 25° (~38 mm)\nBest for: Everyday walking, flat ground",
                },
                "Fast": {
                    "cycle_time": 0.5,
                    "step_height": 30,
                    "desc": "Cycle: 0.5 s | Step: 30° (~45 mm)\nBest for: Open space, experienced tuning",
                },
            }

            for name, cfg in presets.items():
                with st.container(border=True):
                    st.markdown(f"**{name}**")
                    st.caption(cfg["desc"])
                    if st.button(f"Apply {name}", key=f"preset_{name}", use_container_width=True, disabled=not connected):
                        try:
                            requests.post(
                                f"{api_url}/api/gait/params",
                                json={
                                    "cycle_time": cfg["cycle_time"],
                                    "step_height": cfg["step_height"],
                                },
                                timeout=2,
                            )
                            # Also persist
                            save_tuning(api_url, "cycle_time", cfg["cycle_time"])
                            save_tuning(api_url, "step_height", cfg["step_height"])
                            st.success(f"{name} preset applied!")
                            st.rerun()
                        except Exception:
                            st.error("Failed to apply preset")

            st.markdown("---")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("🧪 Test Gait", use_container_width=True, disabled=not connected,
                             help="Apply parameters live (backend may start gait immediately)"):
                    try:
                        resp = requests.post(
                            f"{api_url}/api/gait/params",
                            json={"cycle_time": cyc, "step_height": step_deg},
                            timeout=2
                        )
                        if resp.ok:
                            st.info("Gait parameters applied live!")
                        else:
                            st.warning("Apply returned error")
                    except Exception as e:
                        st.error(f"Error: {e}")

            with c2:
                if st.button("💾 Save", type="primary", key="sv4", use_container_width=True, disabled=not connected):
                    ok1 = save_tuning(api_url, "cycle_time", cyc)
                    ok2 = save_tuning(api_url, "step_height", step_deg)
                    if ok1 and ok2:
                        st.success("Saved!")
                    else:
                        st.error("Save failed")

        st.divider()

        with st.container(border=True):
            st.markdown("#### 💡 Tuning Tips")
            tips = [
                "If robot falls forward: **increase knee bend** or **reduce step height**",
                "If robot drags feet: **increase step height**",
                "If robot wobbles side-to-side: **reduce cycle time** or **enable balance**",
                "**Always calibrate IMU** before tuning gait",
                "Start with **Slow & Safe**, then work up to **Normal**",
            ]
            for tip in tips:
                st.markdown(f"- {tip}")
