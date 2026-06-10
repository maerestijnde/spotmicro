"""Robot SVG visualizations for IMU and tuning pages."""
import math


def create_robot_svg(pitch: float, roll: float, width: int = 300, height: int = 300) -> str:
    """
    Create an SVG visualization of the robot from a top-down view
    showing pitch and roll orientation.

    Args:
        pitch: Pitch angle in degrees (positive = nose up)
        roll: Roll angle in degrees (positive = right side down)
        width: SVG width in pixels
        height: SVG height in pixels

    Returns:
        HTML string with embedded SVG
    """
    cx, cy = width // 2, height // 2

    # Clamp angles for visualization
    pitch = max(-45, min(45, pitch))
    roll = max(-45, min(45, roll))

    # Calculate indicator position (center dot moves based on tilt)
    # Scale: 45 degrees = edge of safe zone
    max_offset = min(width, height) // 4
    dx = roll / 45 * max_offset
    dy = pitch / 45 * max_offset

    # Determine status color (thresholds increased to reduce noise sensitivity)
    max_tilt = max(abs(pitch), abs(roll))
    if max_tilt < 10:
        status_color = "#22c55e"  # Green - level
        status_text = "LEVEL"
    elif max_tilt < 25:
        status_color = "#f59e0b"  # Orange - tilted
        status_text = "TILTED"
    else:
        status_color = "#ef4444"  # Red - excessive
        status_text = "DANGER"

    # Robot body dimensions (scaled to fit)
    body_w = width * 0.4
    body_h = height * 0.5

    svg = f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="bodyGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#334155"/>
                <stop offset="100%" style="stop-color:#1e293b"/>
            </linearGradient>
        </defs>

        <!-- Background -->
        <rect width="{width}" height="{height}" fill="#0f172a" rx="8"/>

        <!-- Grid lines -->
        <line x1="{cx}" y1="20" x2="{cx}" y2="{height-20}" stroke="#334155" stroke-width="1" stroke-dasharray="5,5"/>
        <line x1="20" y1="{cy}" x2="{width-20}" y2="{cy}" stroke="#334155" stroke-width="1" stroke-dasharray="5,5"/>

        <!-- Safe zone circle -->
        <circle cx="{cx}" cy="{cy}" r="{max_offset}" fill="none" stroke="#22c55e" stroke-width="2" opacity="0.3"/>
        <circle cx="{cx}" cy="{cy}" r="{max_offset * 3}" fill="none" stroke="#ef4444" stroke-width="1" opacity="0.2"/>

        <!-- Robot body (rotated based on roll) -->
        <g transform="rotate({roll}, {cx}, {cy})">
            <!-- Body rectangle -->
            <rect x="{cx - body_w/2}" y="{cy - body_h/2}" width="{body_w}" height="{body_h}"
                  fill="url(#bodyGrad)" stroke="#64748b" stroke-width="2" rx="8"/>

            <!-- Head indicator (front) -->
            <polygon points="{cx},{cy - body_h/2 - 15} {cx-12},{cy - body_h/2 + 5} {cx+12},{cy - body_h/2 + 5}"
                     fill="#3b82f6" stroke="#60a5fa" stroke-width="1"/>

            <!-- Legs (circles at corners) -->
            <circle cx="{cx - body_w/2 - 10}" cy="{cy - body_h/2 + 15}" r="8" fill="#475569" stroke="#64748b"/>
            <circle cx="{cx + body_w/2 + 10}" cy="{cy - body_h/2 + 15}" r="8" fill="#475569" stroke="#64748b"/>
            <circle cx="{cx - body_w/2 - 10}" cy="{cy + body_h/2 - 15}" r="8" fill="#475569" stroke="#64748b"/>
            <circle cx="{cx + body_w/2 + 10}" cy="{cy + body_h/2 - 15}" r="8" fill="#475569" stroke="#64748b"/>
        </g>

        <!-- Tilt indicator dot -->
        <circle cx="{cx + dx}" cy="{cy + dy}" r="12" fill="{status_color}" stroke="white" stroke-width="2">
            <animate attributeName="opacity" values="1;0.6;1" dur="1s" repeatCount="indefinite"/>
        </circle>

        <!-- Center crosshair -->
        <circle cx="{cx}" cy="{cy}" r="4" fill="none" stroke="#64748b" stroke-width="2"/>

        <!-- Status text -->
        <text x="{cx}" y="{height - 15}" text-anchor="middle" fill="{status_color}" font-family="monospace" font-size="14" font-weight="bold">
            {status_text}
        </text>

        <!-- Angle labels -->
        <text x="{width - 15}" y="{cy + 5}" text-anchor="end" fill="#94a3b8" font-family="monospace" font-size="11">
            R: {roll:+.1f}
        </text>
        <text x="{cx}" y="25" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="11">
            P: {pitch:+.1f}
        </text>
    </svg>
    '''
    return svg


def create_side_svg(pitch: float, width: int = 180, height: int = 100) -> str:
    """
    Create a side-view SVG showing pitch angle.

    Args:
        pitch: Pitch angle in degrees (positive = nose up)
        width: SVG width in pixels
        height: SVG height in pixels

    Returns:
        HTML string with embedded SVG
    """
    cx, cy = width // 2, height // 2
    pitch = max(-45, min(45, pitch))

    # Status color (thresholds increased to reduce noise sensitivity)
    if abs(pitch) < 10:
        color = "#22c55e"
    elif abs(pitch) < 25:
        color = "#f59e0b"
    else:
        color = "#ef4444"

    # Robot body as a rectangle that tilts
    body_w = width * 0.6
    body_h = height * 0.25

    svg = f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <!-- Background -->
        <rect width="{width}" height="{height}" fill="#0f172a" rx="6"/>

        <!-- Ground line -->
        <line x1="10" y1="{cy + 25}" x2="{width-10}" y2="{cy + 25}" stroke="#334155" stroke-width="2"/>

        <!-- Robot body (rotated for pitch) -->
        <g transform="rotate({-pitch}, {cx}, {cy})">
            <rect x="{cx - body_w/2}" y="{cy - body_h/2}" width="{body_w}" height="{body_h}"
                  fill="#334155" stroke="{color}" stroke-width="2" rx="4"/>

            <!-- Head indicator -->
            <circle cx="{cx + body_w/2 - 10}" cy="{cy}" r="6" fill="#3b82f6"/>
        </g>

        <!-- Label -->
        <text x="{width//2}" y="15" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="11">
            PITCH: {pitch:+.1f}
        </text>

        <!-- Angle arc -->
        <path d="M {cx},{cy} L {cx + 40},{cy} A 40,40 0 0,{1 if pitch < 0 else 0} {cx + 40 * math.cos(math.radians(-pitch))},{cy + 40 * math.sin(math.radians(-pitch))}"
              fill="none" stroke="{color}" stroke-width="2" opacity="0.5"/>
    </svg>
    '''
    return svg


def create_front_svg(roll: float, width: int = 180, height: int = 100) -> str:
    """
    Create a front-view SVG showing roll angle.

    Args:
        roll: Roll angle in degrees (positive = right side down)
        width: SVG width in pixels
        height: SVG height in pixels

    Returns:
        HTML string with embedded SVG
    """
    cx, cy = width // 2, height // 2
    roll = max(-45, min(45, roll))

    # Status color (thresholds increased to reduce noise sensitivity)
    if abs(roll) < 10:
        color = "#22c55e"
    elif abs(roll) < 25:
        color = "#f59e0b"
    else:
        color = "#ef4444"

    # Robot body dimensions
    body_w = width * 0.5
    body_h = height * 0.3

    svg = f'''
    <svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
        <!-- Background -->
        <rect width="{width}" height="{height}" fill="#0f172a" rx="6"/>

        <!-- Ground line -->
        <line x1="10" y1="{cy + 25}" x2="{width-10}" y2="{cy + 25}" stroke="#334155" stroke-width="2"/>

        <!-- Robot body (rotated for roll) -->
        <g transform="rotate({roll}, {cx}, {cy})">
            <rect x="{cx - body_w/2}" y="{cy - body_h/2}" width="{body_w}" height="{body_h}"
                  fill="#334155" stroke="{color}" stroke-width="2" rx="4"/>

            <!-- Left/Right indicators -->
            <circle cx="{cx - body_w/2 + 8}" cy="{cy}" r="5" fill="#f59e0b"/>
            <circle cx="{cx + body_w/2 - 8}" cy="{cy}" r="5" fill="#3b82f6"/>
        </g>

        <!-- Label -->
        <text x="{width//2}" y="15" text-anchor="middle" fill="#94a3b8" font-family="monospace" font-size="11">
            ROLL: {roll:+.1f}
        </text>

        <!-- Angle arc -->
        <path d="M {cx},{cy} L {cx},{cy - 35} A 35,35 0 0,{1 if roll > 0 else 0} {cx + 35 * math.sin(math.radians(roll))},{cy - 35 * math.cos(math.radians(roll))}"
              fill="none" stroke="{color}" stroke-width="2" opacity="0.5"/>
    </svg>
    '''
    return svg
