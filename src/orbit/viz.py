"""SVG-based visualizations for quadruped robot calibration.

All functions return raw SVG strings that can be embedded in Streamlit with
``st.markdown(svg, unsafe_allow_html=True)``.
"""

import math

# Consistent leg colors
LEG_COLORS = {
    "FL": "#ff4444",
    "FR": "#44ff44",
    "RL": "#4444ff",
    "RR": "#ffaa44",
}

# Joint colors for leg diagrams
JOINT_COLORS = {
    "hip": "#ff6b6b",
    "knee": "#4ecdc4",
    "ankle": "#45b7d1",
}

# Theme colors
BG_COLOR = "#0a0a0f"
TEXT_COLOR = "#cccccc"
TEXT_SECONDARY = "#94a3b8"
ACCENT_COLOR = "#3b82f6"
COMPLETED_COLOR = "#22c55e"
PENDING_COLOR = "#475569"
HIGHLIGHT_COLOR = "#f59e0b"


def _svg_start(width: int, height: int) -> str:
    """Return the opening SVG tag with dark background."""
    return (
        f'<svg width="100%" height="100%" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="background:{BG_COLOR};border-radius:8px;">\n'
        f'  <rect width="{width}" height="{height}" fill="{BG_COLOR}" rx="8"/>\n'
    )


def create_robot_topdown_view(selected_leg=None, leg_colors=None, width=400):
    """Create a top-down SVG view of the SpotMicro robot body.

    Args:
        selected_leg: Leg ID to highlight ("FL", "FR", "RL", "RR") or None.
        leg_colors: Dict mapping leg IDs to custom colors. Falls back to defaults.
        width: SVG width in pixels.

    Returns:
        Raw SVG string.
    """
    height = int(width * 0.85)
    cx, cy = width // 2, height // 2 - 10

    colors = {**LEG_COLORS, **(leg_colors or {})}
    body_w = width * 0.35
    body_h = height * 0.55

    # Leg positions relative to body corners
    leg_offset_x = body_w / 2 + 8
    leg_offset_y = body_h / 2 + 8

    legs = {
        "FL": (cx - leg_offset_x, cy - leg_offset_y, -1, -1),
        "FR": (cx + leg_offset_x, cy - leg_offset_y, 1, -1),
        "RL": (cx - leg_offset_x, cy + leg_offset_y, -1, 1),
        "RR": (cx + leg_offset_x, cy + leg_offset_y, 1, 1),
    }

    svg = _svg_start(width, height)

    # Title
    svg += (
        f'  <text x="{width // 2}" y="22" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="14" font-weight="bold">'
        f'Robot Bovenaanzicht / Top View</text>\n'
    )

    # Forward arrow at top
    arrow_y = cy - body_h / 2 - 25
    svg += (
        f'  <polygon points="{cx},{arrow_y - 12} {cx - 10},{arrow_y + 6} {cx + 10},{arrow_y + 6}" '
        f'fill="{ACCENT_COLOR}" stroke="{ACCENT_COLOR}" stroke-width="1"/>\n'
        f'  <text x="{cx}" y="{arrow_y - 18}" text-anchor="middle" fill="{ACCENT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="10" font-weight="bold">VOOR / FRONT</text>\n'
    )

    # Robot body
    svg += (
        f'  <rect x="{cx - body_w / 2}" y="{cy - body_h / 2}" width="{body_w}" height="{body_h}" '
        f'fill="#1a1a2e" stroke="#475569" stroke-width="2" rx="6"/>\n'
    )

    # Body center dot
    svg += f'  <circle cx="{cx}" cy="{cy}" r="3" fill="{TEXT_SECONDARY}"/>\n'

    # Draw each leg as an L-shape
    for leg_id, (lx, ly, dx, dy) in legs.items():
        color = colors.get(leg_id, "#cccccc")
        is_selected = selected_leg == leg_id
        stroke_w = 4 if is_selected else 2.5
        opacity = 1.0 if (selected_leg is None or is_selected) else 0.4

        # L-shape: first segment outward, then forward/backward
        seg1_len = 22
        seg2_len = 28
        x1 = lx + dx * 8
        y1 = ly + dy * 8
        x2 = x1 + dx * seg1_len
        y2 = y1 + dy * 5
        x3 = x2 + (dx * 8 if dy > 0 else dx * 8)
        y3 = y2 + dy * seg2_len

        svg += (
            f'  <polyline points="{x1},{y1} {x2},{y2} {x3},{y3}" '
            f'fill="none" stroke="{color}" stroke-width="{stroke_w}" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="{opacity}"/>\n'
        )

        # Joint dot
        svg += (
            f'  <circle cx="{x1}" cy="{y1}" r="5" fill="{color}" '
            f'stroke="{BG_COLOR}" stroke-width="1" opacity="{opacity}"/>\n'
        )

        # Label
        label_x = x3 + dx * 14
        label_y = y3 + 4
        svg += (
            f'  <text x="{label_x}" y="{label_y}" text-anchor="middle" '
            f'fill="{color}" font-family="monospace" font-size="12" font-weight="bold" '
            f'opacity="{opacity}">{leg_id}</text>\n'
        )

    # Legend / labels at bottom
    legend_y = height - 18
    labels = [
        ("FL = Front Left / Voor Links", colors["FL"]),
        ("FR = Front Right / Voor Rechts", colors["FR"]),
        ("RL = Rear Left / Achter Links", colors["RL"]),
        ("RR = Rear Right / Achter Rechts", colors["RR"]),
    ]
    col_width = width / 4
    for i, (text, color) in enumerate(labels):
        x = col_width * i + col_width / 2
        svg += (
            f'  <text x="{x}" y="{legend_y}" text-anchor="middle" fill="{color}" '
            f'font-family="system-ui, sans-serif" font-size="9">{text}</text>\n'
        )

    svg += "</svg>"
    return svg


def create_leg_diagram(joint_angles, leg_id, width=300):
    """Create a side-view SVG diagram of a single leg.

    Args:
        joint_angles: Dict with keys "hip", "knee", "ankle" in degrees.
        leg_id: Leg identifier ("FL", "FR", "RL", "RR").
        width: SVG width in pixels.

    Returns:
        Raw SVG string.
    """
    height = int(width * 1.1)
    cx = width // 2
    ground_y = height - 40

    hip_angle = joint_angles.get("hip", 90)
    knee_angle = joint_angles.get("knee", 90)
    ankle_angle = joint_angles.get("ankle", 90)

    leg_color = LEG_COLORS.get(leg_id, "#cccccc")

    # Segment lengths (visual only)
    coxa_len = width * 0.12
    femur_len = width * 0.30
    tibia_len = width * 0.28

    # Start from hip position
    hip_x = cx
    hip_y = ground_y - femur_len - tibia_len + 20

    # Calculate joint positions
    # Hip rotates the whole leg; for side view, coxa is a short horizontal segment
    knee_x = hip_x + coxa_len
    knee_y = hip_y

    # Femur rotates around knee
    femur_rad = math.radians(180 - knee_angle)
    ankle_x = knee_x + femur_len * math.sin(femur_rad)
    ankle_y = knee_y + femur_len * math.cos(femur_rad)

    # Tibia rotates around ankle
    tibia_rad = math.radians(180 - knee_angle + (90 - ankle_angle))
    foot_x = ankle_x + tibia_len * math.sin(tibia_rad)
    foot_y = ankle_y + tibia_len * math.cos(tibia_rad)

    svg = _svg_start(width, height)

    # Title
    svg += (
        f'  <text x="{width // 2}" y="22" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="14" font-weight="bold">'
        f'Been {leg_id} — Zijaanzicht / Side View</text>\n'
    )

    # Ground line
    svg += (
        f'  <line x1="20" y1="{ground_y}" x2="{width - 20}" y2="{ground_y}" '
        f'stroke="{TEXT_SECONDARY}" stroke-width="2" stroke-dasharray="6,4"/>\n'
        f'  <text x="{width - 18}" y="{ground_y + 12}" text-anchor="end" fill="{TEXT_SECONDARY}" '
        f'font-family="system-ui, sans-serif" font-size="9">grond / ground</text>\n'
    )

    # Neutral position reference (dashed gray)
    n_knee_x = hip_x + coxa_len
    n_knee_y = hip_y
    n_ankle_x = n_knee_x
    n_ankle_y = n_knee_y + femur_len
    n_foot_x = n_ankle_x
    n_foot_y = n_ankle_y + tibia_len

    svg += (
        f'  <polyline points="{hip_x},{hip_y} {n_knee_x},{n_knee_y} {n_ankle_x},{n_ankle_y} {n_foot_x},{n_foot_y}" '
        f'fill="none" stroke="#475569" stroke-width="2" stroke-dasharray="4,4" opacity="0.5"/>\n'
    )
    svg += (
        f'  <text x="{hip_x - 8}" y="{hip_y - 8}" text-anchor="end" fill="#475569" '
        f'font-family="system-ui, sans-serif" font-size="8">neutraal 90°</text>\n'
    )

    # Actual leg segments
    # Coxa
    svg += (
        f'  <line x1="{hip_x}" y1="{hip_y}" x2="{knee_x}" y2="{knee_y}" '
        f'stroke="{JOINT_COLORS["hip"]}" stroke-width="5" stroke-linecap="round"/>\n'
    )
    # Femur
    svg += (
        f'  <line x1="{knee_x}" y1="{knee_y}" x2="{ankle_x}" y2="{ankle_y}" '
        f'stroke="{JOINT_COLORS["knee"]}" stroke-width="5" stroke-linecap="round"/>\n'
    )
    # Tibia
    svg += (
        f'  <line x1="{ankle_x}" y1="{ankle_y}" x2="{foot_x}" y2="{foot_y}" '
        f'stroke="{JOINT_COLORS["ankle"]}" stroke-width="5" stroke-linecap="round"/>\n'
    )

    # Joints
    for jx, jy, jcolor, jname, jangle in [
        (hip_x, hip_y, JOINT_COLORS["hip"], "Hip (coxa)", hip_angle),
        (knee_x, knee_y, JOINT_COLORS["knee"], "Knee (femur)", knee_angle),
        (ankle_x, ankle_y, JOINT_COLORS["ankle"], "Ankle (tibia)", ankle_angle),
    ]:
        svg += (
            f'  <circle cx="{jx}" cy="{jy}" r="6" fill="{jcolor}" stroke="{BG_COLOR}" stroke-width="2"/>\n'
        )
        # Label
        label_x = jx - 10 if jx > width // 2 else jx + 10
        label_anchor = "end" if jx > width // 2 else "start"
        svg += (
            f'  <text x="{label_x}" y="{jy - 10}" text-anchor="{label_anchor}" fill="{jcolor}" '
            f'font-family="system-ui, sans-serif" font-size="9" font-weight="bold">'
            f'{jname}: {jangle}°</text>\n'
        )

    # Foot
    svg += (
        f'  <circle cx="{foot_x}" cy="{foot_y}" r="4" fill="{leg_color}" '
        f'stroke="{BG_COLOR}" stroke-width="1"/>\n'
    )

    # Angle arcs (small arcs near joints)
    def _arc(cx, cy, radius, start_deg, end_deg, color):
        start = math.radians(start_deg)
        end = math.radians(end_deg)
        x1 = cx + radius * math.cos(start)
        y1 = cy + radius * math.sin(start)
        x2 = cx + radius * math.cos(end)
        y2 = cy + radius * math.sin(end)
        large = 1 if abs(end_deg - start_deg) > 180 else 0
        sweep = 1 if end_deg > start_deg else 0
        return (
            f'  <path d="M {x1},{y1} A {radius},{radius} 0 {large},{sweep} {x2},{y2}" '
            f'fill="none" stroke="{color}" stroke-width="1.5" opacity="0.7"/>\n'
        )

    # Knee angle arc
    svg += _arc(knee_x, knee_y, 18, 90, 90 + (90 - knee_angle), JOINT_COLORS["knee"])
    # Ankle angle arc
    svg += _arc(ankle_x, ankle_y, 18, 90 + (90 - knee_angle), 90 + (90 - knee_angle) + (90 - ankle_angle), JOINT_COLORS["ankle"])

    svg += "</svg>"
    return svg


def create_offset_explanation_diagram(width=500):
    """Create an educational SVG explaining servo offsets.

    Args:
        width: SVG width in pixels.

    Returns:
        Raw SVG string.
    """
    height = int(width * 0.65)
    cx = width // 2
    cy = height // 2 - 10

    servo_r = 55
    horn_r = 38

    svg = _svg_start(width, height)

    # Title
    svg += (
        f'  <text x="{width // 2}" y="26" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="15" font-weight="bold">'
        f'Servo Offset Uitleg / Explanation</text>\n'
    )

    # Servo body
    svg += (
        f'  <circle cx="{cx}" cy="{cy}" r="{servo_r}" fill="#1a1a2e" '
        f'stroke="#475569" stroke-width="2"/>\n'
        f'  <circle cx="{cx}" cy="{cy}" r="{servo_r - 6}" fill="none" '
        f'stroke="#334155" stroke-width="1" stroke-dasharray="3,3"/>\n'
    )

    # Software center line (vertical = 90°)
    svg += (
        f'  <line x1="{cx}" y1="{cy - servo_r + 4}" x2="{cx}" y2="{cy + servo_r - 4}" '
        f'stroke="{ACCENT_COLOR}" stroke-width="2" stroke-dasharray="6,3" opacity="0.6"/>\n'
    )
    svg += (
        f'  <text x="{cx + 6}" y="{cy - servo_r + 18}" fill="{ACCENT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="10" font-weight="bold">'
        f'Software Center (90°)</text>\n'
    )

    # Physical neutral position (rotated by -8° for the example)
    offset_deg = -8
    offset_rad = math.radians(offset_deg)
    nx = cx + horn_r * math.sin(offset_rad)
    ny = cy - horn_r * math.cos(offset_rad)

    # Horn arm at physical neutral
    svg += (
        f'  <line x1="{cx}" y1="{cy}" x2="{nx}" y2="{ny}" '
        f'stroke="{HIGHLIGHT_COLOR}" stroke-width="4" stroke-linecap="round"/>\n'
        f'  <circle cx="{nx}" cy="{ny}" r="5" fill="{HIGHLIGHT_COLOR}"/>\n'
    )

    # Arc showing offset
    svg += (
        f'  <path d="M {cx},{cy - 28} A 28,28 0 0,0 {cx + 28 * math.sin(offset_rad)},{cy - 28 * math.cos(offset_rad)}" '
        f'fill="none" stroke="{HIGHLIGHT_COLOR}" stroke-width="2"/>\n'
    )

    # Offset arrow and label
    mid_angle = math.radians(offset_deg / 2)
    ax = cx + 45 * math.sin(mid_angle)
    ay = cy - 45 * math.cos(mid_angle)
    svg += (
        f'  <text x="{ax + 12}" y="{ay}" text-anchor="start" fill="{HIGHLIGHT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="11" font-weight="bold">'
        f'Offset = {offset_deg}°</text>\n'
    )

    # Physical neutral label
    svg += (
        f'  <text x="{nx + 10}" y="{ny + 4}" text-anchor="start" fill="{HIGHLIGHT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="10">Fysiek neutraal / Physical neutral</text>\n'
    )

    # Formula box
    box_y = height - 55
    svg += (
        f'  <rect x="{cx - 140}" y="{box_y}" width="280" height="40" '
        f'fill="#1a1a2e" stroke="#475569" stroke-width="1" rx="6"/>\n'
        f'  <text x="{cx}" y="{box_y + 16}" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="monospace" font-size="12">'
        f'offset = neutral_angle − 90</text>\n'
        f'  <text x="{cx}" y="{box_y + 32}" text-anchor="middle" fill="{TEXT_SECONDARY}" '
        f'font-family="system-ui, sans-serif" font-size="10">'
        f'Voorbeeld / Example: servo staat op 82° wanneer been recht → offset = −8</text>\n'
    )

    # Bottom note
    svg += (
        f'  <text x="{width // 2}" y="{height - 8}" text-anchor="middle" fill="{TEXT_SECONDARY}" '
        f'font-family="system-ui, sans-serif" font-size="9">'
        f'90° = software center | Fysiek neutraal kan afwijken door servo-horn montage</text>\n'
    )

    svg += "</svg>"
    return svg


def create_calibration_workflow_diagram(current_step, width=600):
    """Create a visual step indicator for the calibration workflow.

    Args:
        current_step: Integer 1-5 indicating the active step.
        width: SVG width in pixels.

    Returns:
        Raw SVG string.
    """
    height = 140
    steps = [
        ("1", "Prepare", "Zet robot op doos\n(Pla robot on box)"),
        ("2", "Center All", "Alle servos op 90°\n(Set all to 90°)"),
        ("3", "Calibrate Legs", "Stel ledematen af\n(Adjust to neutral)"),
        ("4", "Verify", "Controleer alle benen\n(Check all legs)"),
        ("5", "Save", "Bewaar calibratie\n(Save calibration)"),
    ]

    n = len(steps)
    margin = 50
    usable = width - 2 * margin
    step_spacing = usable / (n - 1)
    cy = 45
    circle_r = 18

    svg = _svg_start(width, height)

    # Title
    svg += (
        f'  <text x="{width // 2}" y="22" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="14" font-weight="bold">'
        f'Calibratie Workflow / Calibration Steps</text>\n'
    )

    # Connecting line background
    svg += (
        f'  <line x1="{margin}" y1="{cy}" x2="{width - margin}" y2="{cy}" '
        f'stroke="#334155" stroke-width="3" stroke-linecap="round"/>\n'
    )

    # Completed line
    if current_step > 1:
        completed_x = margin + step_spacing * (current_step - 1.5)
        svg += (
            f'  <line x1="{margin}" y1="{cy}" x2="{completed_x}" y2="{cy}" '
            f'stroke="{COMPLETED_COLOR}" stroke-width="3" stroke-linecap="round"/>\n'
        )

    for i, (num, title, desc) in enumerate(steps):
        x = margin + i * step_spacing
        step_num = i + 1

        if step_num < current_step:
            fill = COMPLETED_COLOR
            stroke = COMPLETED_COLOR
            text_fill = BG_COLOR
        elif step_num == current_step:
            fill = HIGHLIGHT_COLOR
            stroke = HIGHLIGHT_COLOR
            text_fill = BG_COLOR
        else:
            fill = BG_COLOR
            stroke = PENDING_COLOR
            text_fill = TEXT_SECONDARY

        # Circle
        svg += (
            f'  <circle cx="{x}" cy="{cy}" r="{circle_r}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2.5"/>\n'
        )

        # Number
        svg += (
            f'  <text x="{x}" y="{cy + 5}" text-anchor="middle" fill="{text_fill}" '
            f'font-family="monospace" font-size="14" font-weight="bold">{num}</text>\n'
        )

        # Title
        svg += (
            f'  <text x="{x}" y="{cy + circle_r + 16}" text-anchor="middle" fill="{TEXT_COLOR}" '
            f'font-family="system-ui, sans-serif" font-size="10" font-weight="bold">{title}</text>\n'
        )

        # Description (two lines)
        desc_lines = desc.split("\n")
        for di, dline in enumerate(desc_lines):
            svg += (
                f'  <text x="{x}" y="{cy + circle_r + 30 + di * 12}" text-anchor="middle" '
                f'fill="{TEXT_SECONDARY}" font-family="system-ui, sans-serif" font-size="8">'
                f'{dline}</text>\n'
            )

    svg += "</svg>"
    return svg


def create_gait_hildebrand_diagram(gait_type="trot", width=500):
    """Create a Hildebrand gait diagram.

    Args:
        gait_type: One of "trot", "walk", "pace", "crawl".
        width: SVG width in pixels.

    Returns:
        Raw SVG string.
    """
    height = 220
    margin_left = 50
    margin_right = 20
    margin_top = 40
    margin_bottom = 35

    chart_w = width - margin_left - margin_right
    chart_h = height - margin_top - margin_bottom

    leg_order = ["FL", "FR", "RL", "RR"]
    row_h = chart_h / len(leg_order)

    # Duty factor and phase offsets per gait type
    gait_config = {
        "trot": {
            "duty": 0.50,
            "phases": {"FL": 0.0, "RR": 0.0, "FR": 0.5, "RL": 0.5},
        },
        "walk": {
            "duty": 0.75,
            "phases": {"FL": 0.0, "FR": 0.25, "RL": 0.50, "RR": 0.75},
        },
        "pace": {
            "duty": 0.50,
            "phases": {"FL": 0.0, "RL": 0.0, "FR": 0.5, "RR": 0.5},
        },
        "crawl": {
            "duty": 0.75,
            "phases": {"FL": 0.0, "FR": 0.50, "RL": 0.25, "RR": 0.75},
        },
    }

    config = gait_config.get(gait_type, gait_config["trot"])
    duty = config["duty"]
    phases = config["phases"]

    svg = _svg_start(width, height)

    # Title
    svg += (
        f'  <text x="{width // 2}" y="22" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="14" font-weight="bold">'
        f'Gang Diagram / Gait Diagram — {gait_type.capitalize()}</text>\n'
    )

    # Grid and labels
    svg += (
        f'  <text x="{margin_left - 8}" y="{margin_top - 8}" text-anchor="end" '
        f'fill="{TEXT_SECONDARY}" font-family="system-ui, sans-serif" font-size="9">'
        f'been / leg →</text>\n'
    )

    for i, leg in enumerate(leg_order):
        y = margin_top + i * row_h
        color = LEG_COLORS[leg]

        # Leg label
        svg += (
            f'  <text x="{margin_left - 8}" y="{y + row_h / 2 + 4}" text-anchor="end" '
            f'fill="{color}" font-family="monospace" font-size="11" font-weight="bold">{leg}</text>\n'
        )

        # Row background
        svg += (
            f'  <rect x="{margin_left}" y="{y + 2}" width="{chart_w}" height="{row_h - 4}" '
            f'fill="#111118" stroke="none" rx="2"/>\n'
        )

        # Draw stance (ground contact) bars
        phase = phases.get(leg, 0.0)
        bar_h = row_h * 0.5
        bar_y = y + (row_h - bar_h) / 2

        start = phase * chart_w
        end = start + duty * chart_w
        if end > chart_w + 0.5:
            # Wrap around
            svg += (
                f'  <rect x="{margin_left + start}" y="{bar_y}" '
                f'width="{chart_w - start}" height="{bar_h}" fill="{color}" rx="3"/>\n'
                f'  <rect x="{margin_left}" y="{bar_y}" '
                f'width="{end - chart_w}" height="{bar_h}" fill="{color}" rx="3"/>\n'
            )
        else:
            svg += (
                f'  <rect x="{margin_left + start}" y="{bar_y}" '
                f'width="{duty * chart_w}" height="{bar_h}" fill="{color}" rx="3" opacity="0.9"/>\n'
            )

    # X-axis ticks and labels (0%, 25%, 50%, 75%, 100%)
    for pct in [0, 25, 50, 75, 100]:
        x = margin_left + (pct / 100) * chart_w
        svg += (
            f'  <line x1="{x}" y1="{margin_top}" x2="{x}" y2="{margin_top + chart_h}" '
            f'stroke="#334155" stroke-width="1" opacity="0.4"/>\n'
            f'  <text x="{x}" y="{margin_top + chart_h + 14}" text-anchor="middle" '
            f'fill="{TEXT_SECONDARY}" font-family="monospace" font-size="9">{pct}%</text>\n'
        )

    # Axis label
    svg += (
        f'  <text x="{margin_left + chart_w / 2}" y="{height - 6}" text-anchor="middle" '
        f'fill="{TEXT_SECONDARY}" font-family="system-ui, sans-serif" font-size="9">'
        f'gangcyclus / gait cycle</text>\n'
    )

    # Legend
    legend_y = margin_top + chart_h + 26
    svg += (
        f'  <rect x="{margin_left}" y="{legend_y - 6}" width="12" height="6" '
        f'fill="{TEXT_COLOR}" rx="2"/>\n'
        f'  <text x="{margin_left + 18}" y="{legend_y}" fill="{TEXT_SECONDARY}" '
        f'font-family="system-ui, sans-serif" font-size="8">grondcontact / stance</text>\n'
        f'  <rect x="{margin_left + 130}" y="{legend_y - 6}" width="12" height="6" '
        f'fill="#111118" stroke="#475569" stroke-width="1" rx="2"/>\n'
        f'  <text x="{margin_left + 148}" y="{legend_y}" fill="{TEXT_SECONDARY}" '
        f'font-family="system-ui, sans-serif" font-size="8">zwaai / swing</text>\n'
    )

    svg += "</svg>"
    return svg


def create_support_polygon_diagram(foot_positions, width=300):
    """Create a top-down view showing body outline and support polygon.

    Args:
        foot_positions: Dict mapping leg IDs ("FL", "FR", "RL", "RR") to
            tuples (x, y, on_ground) where on_ground is a boolean.
            Coordinates should be in a local frame (e.g. -1 to 1).
        width: SVG width in pixels.

    Returns:
        Raw SVG string.
    """
    height = width
    cx, cy = width // 2, height // 2

    # Scale factor to map normalized positions to SVG pixels
    scale = width * 0.35

    # Default positions if not provided
    defaults = {
        "FL": (-1.0, -1.0, True),
        "FR": (1.0, -1.0, True),
        "RL": (-1.0, 1.0, True),
        "RR": (1.0, 1.0, True),
    }
    positions = {**defaults, **foot_positions}

    # Transform to SVG coordinates
    def _to_svg(leg_id):
        x_norm, y_norm, on_ground = positions.get(leg_id, (0, 0, False))
        return cx + x_norm * scale, cy + y_norm * scale, on_ground

    svg_coords = {lid: _to_svg(lid) for lid in ["FL", "FR", "RL", "RR"]}

    # Build support polygon from grounded feet
    grounded = [(lid, svg_coords[lid]) for lid in ["FL", "FR", "RL", "RR"] if svg_coords[lid][2]]

    # Determine stability: check if center (cx, cy) is inside polygon
    def _point_in_polygon(px, py, poly):
        """Ray-casting point-in-polygon test with boundary tolerance."""
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            # Check if point is on segment (within 1 px tolerance)
            if abs(xi - xj) < 0.5:
                if abs(px - xi) < 1.0 and min(yi, yj) <= py <= max(yi, yj):
                    return True
            else:
                m = (yj - yi) / (xj - xi)
                y_on_line = yi + m * (px - xi)
                if abs(py - y_on_line) < 1.0 and min(xi, xj) <= px <= max(xi, xj):
                    return True
            if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    poly_points = [(x, y) for _, (x, y, _) in grounded]
    is_stable = _point_in_polygon(cx, cy, poly_points) if len(poly_points) >= 3 else False
    is_marginal = len(grounded) == 3 or (len(grounded) >= 3 and not is_stable)

    if is_marginal:
        poly_color = "#f59e0b"  # orange/yellow
        status = "Marginaal / Marginal"
    elif is_stable:
        poly_color = "#22c55e"  # green
        status = "Stabiel / Stable"
    else:
        poly_color = "#ef4444"  # red
        status = "Instabiel / Unstable"

    svg = _svg_start(width, height)

    # Title
    svg += (
        f'  <text x="{width // 2}" y="22" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="14" font-weight="bold">'
        f'Steunvlak / Support Polygon</text>\n'
    )

    # Draw support polygon
    if len(poly_points) >= 3:
        pts_str = " ".join(f"{x},{y}" for x, y in poly_points)
        svg += (
            f'  <polygon points="{pts_str}" fill="{poly_color}" opacity="0.15" '
            f'stroke="{poly_color}" stroke-width="2" stroke-linejoin="round"/>\n'
        )
    elif len(poly_points) == 2:
        (x1, y1), (x2, y2) = poly_points
        svg += (
            f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{poly_color}" stroke-width="2" stroke-dasharray="4,4"/>\n'
        )

    # Body outline
    body_w = scale * 0.8
    body_h = scale * 1.0
    svg += (
        f'  <rect x="{cx - body_w / 2}" y="{cy - body_h / 2}" width="{body_w}" height="{body_h}" '
        f'fill="#1a1a2e" stroke="#475569" stroke-width="2" rx="4"/>\n'
    )

    # Center of body
    svg += (
        f'  <circle cx="{cx}" cy="{cy}" r="5" fill="{TEXT_COLOR}" '
        f'stroke="{BG_COLOR}" stroke-width="2"/>\n'
        f'  <text x="{cx}" y="{cy - 10}" text-anchor="middle" fill="{TEXT_COLOR}" '
        f'font-family="system-ui, sans-serif" font-size="8">Zwaartepunt / CoM</text>\n'
    )

    # Forward arrow
    arrow_y = cy - body_h / 2 - 15
    svg += (
        f'  <polygon points="{cx},{arrow_y - 8} {cx - 7},{arrow_y + 4} {cx + 7},{arrow_y + 4}" '
        f'fill="{ACCENT_COLOR}"/>\n'
    )

    # Feet
    for leg_id, (fx, fy, on_ground) in svg_coords.items():
        color = LEG_COLORS[leg_id]
        if on_ground:
            # Filled circle for on ground
            svg += (
                f'  <circle cx="{fx}" cy="{fy}" r="7" fill="{color}" '
                f'stroke="{BG_COLOR}" stroke-width="2"/>\n'
            )
            # Ground indicator
            svg += (
                f'  <line x1="{fx - 6}" y1="{fy + 10}" x2="{fx + 6}" y2="{fy + 10}" '
                f'stroke="{color}" stroke-width="2"/>\n'
            )
        else:
            # Hollow circle for in air
            svg += (
                f'  <circle cx="{fx}" cy="{fy}" r="7" fill="none" '
                f'stroke="{color}" stroke-width="2" stroke-dasharray="3,2"/>\n'
            )

        # Label
        label_offset = 14
        lx = fx + label_offset if fx >= cx else fx - label_offset
        anchor = "start" if fx >= cx else "end"
        svg += (
            f'  <text x="{lx}" y="{fy + 4}" text-anchor="{anchor}" fill="{color}" '
            f'font-family="monospace" font-size="10" font-weight="bold">{leg_id}</text>\n'
        )

    # Status label
    svg += (
        f'  <text x="{width // 2}" y="{height - 12}" text-anchor="middle" fill="{poly_color}" '
        f'font-family="system-ui, sans-serif" font-size="12" font-weight="bold">{status}</text>\n'
    )

    svg += "</svg>"
    return svg
