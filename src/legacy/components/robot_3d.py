"""
Interactive 3D Robot Visualization for SpotMicro

A reusable Plotly 3D visualization component that renders the SpotMicro
quadruped robot with accurate dimensions and proper forward kinematics.

Author: MicroSpot Project
"""

import plotly.graph_objects as go
import numpy as np
from math import radians, cos, sin, degrees


# Robot dimensions in meters (accurate SpotMicro dimensions)
BODY_LENGTH = 0.186      # front-to-back hip distance
BODY_WIDTH = 0.078       # side-to-side hip distance
HIP_LENGTH = 0.055       # shoulder/hip segment
UPPER_LEG_LENGTH = 0.1075  # upper leg (femur)
LOWER_LEG_LENGTH = 0.130   # lower leg (tibia)

# Leg configuration
LEG_CONFIG = {
    "FL": {"channels": [0, 1, 2], "color": "#ff4444", "side": "left", "end": "front"},
    "FR": {"channels": [3, 4, 5], "color": "#44ff44", "side": "right", "end": "front"},
    "RL": {"channels": [6, 7, 8], "color": "#4444ff", "side": "left", "end": "rear"},
    "RR": {"channels": [9, 10, 11], "color": "#ffaa44", "side": "right", "end": "rear"},
}


def get_servo_angle(servo_angles: dict, channel: int) -> float:
    """Get servo angle handling both int and string keys from JSON."""
    return servo_angles.get(channel, servo_angles.get(str(channel), 90))


def rotation_matrix_x(angle_rad: float) -> np.ndarray:
    """Rotation matrix around X axis."""
    c, s = cos(angle_rad), sin(angle_rad)
    return np.array([
        [1, 0, 0],
        [0, c, -s],
        [0, s, c]
    ])


def rotation_matrix_y(angle_rad: float) -> np.ndarray:
    """Rotation matrix around Y axis."""
    c, s = cos(angle_rad), sin(angle_rad)
    return np.array([
        [c, 0, s],
        [0, 1, 0],
        [-s, 0, c]
    ])


def rotation_matrix_z(angle_rad: float) -> np.ndarray:
    """Rotation matrix around Z axis."""
    c, s = cos(angle_rad), sin(angle_rad)
    return np.array([
        [c, -s, 0],
        [s, c, 0],
        [0, 0, 1]
    ])


def apply_body_rotation(points: np.ndarray, pitch: float, roll: float, yaw: float,
                        center: np.ndarray) -> np.ndarray:
    """
    Apply body rotation (pitch, roll, yaw) to a set of points around a center.

    Args:
        points: Nx3 array of points
        pitch: rotation around Z axis (degrees)
        roll: rotation around X axis (degrees)
        yaw: rotation around Y axis (degrees)
        center: rotation center point

    Returns:
        Rotated points
    """
    if pitch == 0 and roll == 0 and yaw == 0:
        return points

    # Convert to radians
    pitch_rad = radians(pitch)
    roll_rad = radians(roll)
    yaw_rad = radians(yaw)

    # Create combined rotation matrix (order: yaw -> pitch -> roll)
    R = rotation_matrix_x(roll_rad) @ rotation_matrix_z(pitch_rad) @ rotation_matrix_y(yaw_rad)

    # Apply rotation around center
    rotated = np.zeros_like(points)
    for i, p in enumerate(points):
        rotated[i] = R @ (p - center) + center

    return rotated


def calculate_leg_points(hip_origin: np.ndarray, hip_angle: float, knee_angle: float,
                         ankle_angle: float, is_left_side: bool) -> dict:
    """
    Calculate leg joint positions using forward kinematics.

    Coordinate system:
    - +X = forward (front of robot)
    - +Y = up (height)
    - +Z = left, -Z = right

    Args:
        hip_origin: Starting point where leg attaches to body
        hip_angle: Hip servo angle (90 = neutral)
        knee_angle: Knee servo angle (90 = straight down)
        ankle_angle: Ankle servo angle (90 = straight)
        is_left_side: True for left legs (FL, RL), False for right (FR, RR)

    Returns:
        Dict with joint positions: hip_end, knee_end, foot_end
    """
    # Direction multiplier: left legs extend in +Z, right in -Z
    z_dir = 1.0 if is_left_side else -1.0

    # Hip extends sideways from body
    hip_end = hip_origin + np.array([0, 0, z_dir * HIP_LENGTH])

    # Convert servo angles to radians
    # Hip angle affects forward/backward tilt of the leg (rotation around Z axis in leg frame)
    hip_rad = radians(hip_angle - 90)  # 90 = neutral (straight down)

    # Knee angle bends upper leg (0 = straight down from hip, positive = bends backward)
    # At neutral (90), leg points straight down
    knee_rad = radians(knee_angle - 90)

    # Ankle angle relative to upper leg
    # At neutral (90), lower leg continues from upper leg direction
    ankle_rad = radians(ankle_angle - 90)

    # Upper leg: starts at hip_end, rotates based on hip and knee
    # Hip rotation affects X position (forward/back lean)
    # Knee rotation affects the bend

    # Upper leg endpoint (knee position)
    # The knee angle determines how much the upper leg bends from vertical
    # The hip angle adds a forward/backward tilt
    knee_x = hip_end[0] + UPPER_LEG_LENGTH * sin(hip_rad + knee_rad)
    knee_y = hip_end[1] - UPPER_LEG_LENGTH * cos(hip_rad + knee_rad)
    knee_z = hip_end[2]  # No sideways movement in knee
    knee_end = np.array([knee_x, knee_y, knee_z])

    # Lower leg: continues from knee, affected by ankle angle
    # Total angle from vertical is hip + knee + ankle
    total_angle = hip_rad + knee_rad + ankle_rad
    foot_x = knee_end[0] + LOWER_LEG_LENGTH * sin(total_angle)
    foot_y = knee_end[1] - LOWER_LEG_LENGTH * cos(total_angle)
    foot_z = knee_end[2]
    foot_end = np.array([foot_x, foot_y, foot_z])

    return {
        "hip_origin": hip_origin,
        "hip_end": hip_end,
        "knee_end": knee_end,
        "foot_end": foot_end
    }


def create_body_mesh(body_y: float, body_pitch: float, body_roll: float,
                     body_yaw: float) -> tuple:
    """
    Create body box vertices and faces.

    Returns:
        Tuple of (vertices, i_indices, j_indices, k_indices) for Mesh3d
    """
    hx = BODY_LENGTH / 2
    hy = 0.025  # Body thickness (50mm total height)
    hz = BODY_WIDTH / 2

    # Body vertices (8 corners of a box)
    vertices = np.array([
        [hx, body_y + hy, hz],    # 0: front-top-left
        [hx, body_y + hy, -hz],   # 1: front-top-right
        [-hx, body_y + hy, -hz],  # 2: back-top-right
        [-hx, body_y + hy, hz],   # 3: back-top-left
        [hx, body_y - hy, hz],    # 4: front-bottom-left
        [hx, body_y - hy, -hz],   # 5: front-bottom-right
        [-hx, body_y - hy, -hz],  # 6: back-bottom-right
        [-hx, body_y - hy, hz],   # 7: back-bottom-left
    ])

    # Apply body rotation
    center = np.array([0, body_y, 0])
    vertices = apply_body_rotation(vertices, body_pitch, body_roll, body_yaw, center)

    # Triangle indices for all 6 faces (2 triangles per face)
    i = [0, 0, 4, 4, 0, 0, 2, 2, 0, 0, 7, 7]
    j = [1, 2, 5, 6, 1, 4, 3, 7, 3, 4, 3, 6]
    k = [2, 3, 6, 7, 5, 5, 7, 6, 4, 7, 2, 2]

    return vertices, i, j, k


def create_head_indicator(body_y: float, body_pitch: float, body_roll: float,
                          body_yaw: float) -> tuple:
    """
    Create a cone/arrow at the front of the robot to indicate heading.

    Returns:
        Tuple of (tip_point, base_points) for drawing
    """
    hx = BODY_LENGTH / 2
    cone_length = 0.03  # 30mm cone
    cone_radius = 0.015  # 15mm radius

    # Cone tip at front of robot
    tip = np.array([hx + cone_length, body_y, 0])

    # Base of cone (circle approximation)
    n_points = 8
    base_points = []
    for i in range(n_points):
        angle = 2 * np.pi * i / n_points
        point = np.array([
            hx,
            body_y + cone_radius * cos(angle),
            cone_radius * sin(angle)
        ])
        base_points.append(point)
    base_points = np.array(base_points)

    # Apply body rotation
    center = np.array([0, body_y, 0])
    tip = apply_body_rotation(np.array([tip]), body_pitch, body_roll, body_yaw, center)[0]
    base_points = apply_body_rotation(base_points, body_pitch, body_roll, body_yaw, center)

    return tip, base_points


def create_ground_grid(size: float = 0.3, divisions: int = 10) -> list:
    """
    Create ground plane with grid lines.

    Args:
        size: Half-size of the ground plane in meters
        divisions: Number of grid divisions

    Returns:
        List of traces for the ground plane and grid
    """
    traces = []

    # Ground plane mesh
    traces.append(go.Mesh3d(
        x=[-size, size, size, -size],
        y=[0, 0, 0, 0],
        z=[-size, -size, size, size],
        i=[0, 0],
        j=[1, 2],
        k=[2, 3],
        color='#1a1a2e',
        opacity=0.4,
        showlegend=False,
        hoverinfo='skip'
    ))

    # Grid lines
    step = 2 * size / divisions
    grid_color = '#333344'

    # Lines parallel to X axis
    for i in range(divisions + 1):
        z = -size + i * step
        traces.append(go.Scatter3d(
            x=[-size, size],
            y=[0, 0],
            z=[z, z],
            mode='lines',
            line=dict(color=grid_color, width=1),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Lines parallel to Z axis
    for i in range(divisions + 1):
        x = -size + i * step
        traces.append(go.Scatter3d(
            x=[x, x],
            y=[0, 0],
            z=[-size, size],
            mode='lines',
            line=dict(color=grid_color, width=1),
            showlegend=False,
            hoverinfo='skip'
        ))

    return traces


def create_3d_robot(
    servo_angles: dict,
    body_pitch: float = 0,
    body_roll: float = 0,
    body_yaw: float = 0,
    height: int = 500,
    body_height: float = None
) -> go.Figure:
    """
    Create an interactive 3D visualization of the SpotMicro robot.

    Args:
        servo_angles: Dict mapping channel numbers to angles (0-11)
                     Can use int or string keys: {0: 90} or {"0": 90}
        body_pitch: Body pitch angle in degrees (rotation around Z)
        body_roll: Body roll angle in degrees (rotation around X)
        body_yaw: Body yaw angle in degrees (rotation around Y)
        height: Figure height in pixels
        body_height: Optional body height override in meters (default: auto-calculate)

    Returns:
        Plotly Figure object
    """
    fig = go.Figure()

    # Calculate body height based on leg positions, or use default
    # Default standing height with legs at 45 degree knee bend
    if body_height is None:
        # Estimate from average leg extension
        # At neutral (90 deg), legs point straight down
        default_knee = 90
        default_ankle = 90
        knee_rad = radians(default_knee - 90)
        ankle_rad = radians(default_ankle - 90)
        body_height = (UPPER_LEG_LENGTH * cos(knee_rad) +
                      LOWER_LEG_LENGTH * cos(knee_rad + ankle_rad))

    body_y = body_height  # Y is up

    # Convert to mm for display (Plotly works better with larger numbers)
    scale = 1000  # meters to mm

    # Hip attachment points on body
    hx = BODY_LENGTH / 2
    hz = BODY_WIDTH / 2

    hip_origins = {
        "FL": np.array([hx, body_y, hz]),
        "FR": np.array([hx, body_y, -hz]),
        "RL": np.array([-hx, body_y, hz]),
        "RR": np.array([-hx, body_y, -hz]),
    }

    # Apply body rotation to hip origins
    center = np.array([0, body_y, 0])
    for leg_id in hip_origins:
        hip_origins[leg_id] = apply_body_rotation(
            np.array([hip_origins[leg_id]]),
            body_pitch, body_roll, body_yaw, center
        )[0]

    # Draw body
    body_vertices, bi, bj, bk = create_body_mesh(body_y, body_pitch, body_roll, body_yaw)
    fig.add_trace(go.Mesh3d(
        x=body_vertices[:, 0] * scale,
        y=body_vertices[:, 1] * scale,
        z=body_vertices[:, 2] * scale,
        i=bi,
        j=bj,
        k=bk,
        color='#1a3a5c',
        opacity=0.9,
        name='Body',
        showlegend=True,
        flatshading=True
    ))

    # Body outline for better visibility
    outline_indices = [0, 1, 2, 3, 0, 4, 5, 6, 7, 4]
    outline_connections = [(0, 4), (1, 5), (2, 6), (3, 7)]

    # Top and bottom outlines
    for start_idx in [0, 4]:
        indices = [start_idx, start_idx + 1, start_idx + 2, start_idx + 3, start_idx]
        if start_idx == 4:
            indices = [4, 5, 6, 7, 4]
        fig.add_trace(go.Scatter3d(
            x=[body_vertices[i, 0] * scale for i in indices],
            y=[body_vertices[i, 1] * scale for i in indices],
            z=[body_vertices[i, 2] * scale for i in indices],
            mode='lines',
            line=dict(color='#4a8ac7', width=3),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Vertical edges
    for top, bottom in outline_connections:
        fig.add_trace(go.Scatter3d(
            x=[body_vertices[top, 0] * scale, body_vertices[bottom, 0] * scale],
            y=[body_vertices[top, 1] * scale, body_vertices[bottom, 1] * scale],
            z=[body_vertices[top, 2] * scale, body_vertices[bottom, 2] * scale],
            mode='lines',
            line=dict(color='#4a8ac7', width=3),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Draw head indicator (cone at front)
    tip, base_points = create_head_indicator(body_y, body_pitch, body_roll, body_yaw)

    # Draw cone as lines from base to tip
    for i in range(len(base_points)):
        fig.add_trace(go.Scatter3d(
            x=[base_points[i, 0] * scale, tip[0] * scale],
            y=[base_points[i, 1] * scale, tip[1] * scale],
            z=[base_points[i, 2] * scale, tip[2] * scale],
            mode='lines',
            line=dict(color='#ffcc00', width=2),
            showlegend=False,
            hoverinfo='skip'
        ))

    # Cone base circle
    base_x = [p[0] * scale for p in base_points] + [base_points[0, 0] * scale]
    base_y = [p[1] * scale for p in base_points] + [base_points[0, 1] * scale]
    base_z = [p[2] * scale for p in base_points] + [base_points[0, 2] * scale]
    fig.add_trace(go.Scatter3d(
        x=base_x,
        y=base_y,
        z=base_z,
        mode='lines',
        line=dict(color='#ffcc00', width=2),
        showlegend=False,
        hoverinfo='skip'
    ))

    # Draw legs
    foot_positions = []

    for leg_id, config in LEG_CONFIG.items():
        channels = config["channels"]
        color = config["color"]
        is_left = config["side"] == "left"

        # Get servo angles
        hip_angle = get_servo_angle(servo_angles, channels[0])
        knee_angle = get_servo_angle(servo_angles, channels[1])
        ankle_angle = get_servo_angle(servo_angles, channels[2])

        # Calculate leg joint positions
        leg_points = calculate_leg_points(
            hip_origins[leg_id],
            hip_angle,
            knee_angle,
            ankle_angle,
            is_left
        )

        # Apply body rotation to leg points (except hip_origin which is already rotated)
        for key in ["hip_end", "knee_end", "foot_end"]:
            leg_points[key] = apply_body_rotation(
                np.array([leg_points[key]]),
                body_pitch, body_roll, body_yaw, center
            )[0]

        foot_positions.append(leg_points["foot_end"])

        # Draw hip segment (body to hip_end)
        fig.add_trace(go.Scatter3d(
            x=[leg_points["hip_origin"][0] * scale, leg_points["hip_end"][0] * scale],
            y=[leg_points["hip_origin"][1] * scale, leg_points["hip_end"][1] * scale],
            z=[leg_points["hip_origin"][2] * scale, leg_points["hip_end"][2] * scale],
            mode='lines+markers',
            line=dict(color=color, width=8),
            marker=dict(size=[6, 8], color=color),
            name=f'{leg_id} Hip',
            showlegend=False,
            hovertemplate=f'{leg_id} Hip<br>Angle: {hip_angle:.1f}<extra></extra>'
        ))

        # Draw upper leg (hip_end to knee_end)
        fig.add_trace(go.Scatter3d(
            x=[leg_points["hip_end"][0] * scale, leg_points["knee_end"][0] * scale],
            y=[leg_points["hip_end"][1] * scale, leg_points["knee_end"][1] * scale],
            z=[leg_points["hip_end"][2] * scale, leg_points["knee_end"][2] * scale],
            mode='lines+markers',
            line=dict(color=color, width=6),
            marker=dict(size=[8, 6], color=color),
            name=f'{leg_id} Upper',
            showlegend=False,
            hovertemplate=f'{leg_id} Knee<br>Angle: {knee_angle:.1f}<extra></extra>'
        ))

        # Draw lower leg (knee_end to foot_end)
        fig.add_trace(go.Scatter3d(
            x=[leg_points["knee_end"][0] * scale, leg_points["foot_end"][0] * scale],
            y=[leg_points["knee_end"][1] * scale, leg_points["foot_end"][1] * scale],
            z=[leg_points["knee_end"][2] * scale, leg_points["foot_end"][2] * scale],
            mode='lines+markers',
            line=dict(color=color, width=5),
            marker=dict(size=[6, 10], color=color, symbol='diamond'),
            name=leg_id,
            showlegend=True,
            hovertemplate=f'{leg_id} Foot<br>Ankle: {ankle_angle:.1f}<extra></extra>'
        ))

    # Add ground plane with grid
    ground_traces = create_ground_grid(size=0.25, divisions=8)
    for trace in ground_traces:
        # Scale the ground traces
        if hasattr(trace, 'x') and trace.x is not None:
            trace.x = [x * scale if x is not None else None for x in trace.x]
            trace.z = [z * scale if z is not None else None for z in trace.z]
        fig.add_trace(trace)

    # Add foot contact indicators (circles on ground where feet would touch)
    for i, (leg_id, foot_pos) in enumerate(zip(LEG_CONFIG.keys(), foot_positions)):
        color = LEG_CONFIG[leg_id]["color"]
        # Project foot to ground
        fig.add_trace(go.Scatter3d(
            x=[foot_pos[0] * scale],
            y=[1],  # Slightly above ground
            z=[foot_pos[2] * scale],
            mode='markers',
            marker=dict(size=8, color=color, symbol='circle', opacity=0.5),
            showlegend=False,
            hovertemplate=f'{leg_id} Ground Contact<extra></extra>'
        ))

    # Calculate appropriate axis ranges
    axis_range = 300  # mm

    # Layout with dark theme
    fig.update_layout(
        scene=dict(
            xaxis=dict(
                title='X (forward)',
                range=[-axis_range, axis_range],
                backgroundcolor='#0a0a0f',
                gridcolor='#222233',
                showbackground=True,
                zerolinecolor='#444455'
            ),
            yaxis=dict(
                title='Y (up)',
                range=[-50, 350],  # Ground at 0, robot body around 100-200mm
                backgroundcolor='#0a0a0f',
                gridcolor='#222233',
                showbackground=True,
                zerolinecolor='#444455'
            ),
            zaxis=dict(
                title='Z (left/right)',
                range=[-axis_range, axis_range],
                backgroundcolor='#0a0a0f',
                gridcolor='#222233',
                showbackground=True,
                zerolinecolor='#444455'
            ),
            aspectmode='data',  # Scale axes proportionally to data (not 'cube' which distorts)
            camera=dict(
                eye=dict(x=1.5, y=0.8, z=1.0),  # Front-right-above view, closer
                center=dict(x=0, y=0.1, z=0),  # Look slightly up at the robot
                up=dict(x=0, y=1, z=0)
            ),
            bgcolor='#0a0a0f'
        ),
        height=height,
        margin=dict(l=0, r=0, t=30, b=0),
        paper_bgcolor='#0a0a0f',
        plot_bgcolor='#0a0a0f',
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor='rgba(20, 20, 30, 0.8)',
            font=dict(color='#cccccc', size=10)
        ),
        title=dict(
            text='SpotMicro 3D View',
            font=dict(color='#888888', size=14),
            x=0.5,
            xanchor='center'
        )
    )

    return fig


def create_3d_robot_simple(
    servo_angles: dict,
    height: int = 400
) -> go.Figure:
    """
    Simplified version for quick visualization without body orientation.

    Args:
        servo_angles: Dict mapping channel numbers to angles
        height: Figure height in pixels

    Returns:
        Plotly Figure object
    """
    return create_3d_robot(servo_angles, height=height)


# Example usage and testing
if __name__ == "__main__":
    # Test with neutral position (all servos at 90 degrees)
    test_angles = {i: 90 for i in range(12)}

    # Create figure
    fig = create_3d_robot(test_angles, body_pitch=0, body_roll=0, body_yaw=0)

    # Show in browser
    fig.show()

    print("3D Robot visualization test complete.")
    print("Dimensions used:")
    print(f"  Body length: {BODY_LENGTH * 1000:.1f}mm")
    print(f"  Body width: {BODY_WIDTH * 1000:.1f}mm")
    print(f"  Hip length: {HIP_LENGTH * 1000:.1f}mm")
    print(f"  Upper leg: {UPPER_LEG_LENGTH * 1000:.1f}mm")
    print(f"  Lower leg: {LOWER_LEG_LENGTH * 1000:.1f}mm")
