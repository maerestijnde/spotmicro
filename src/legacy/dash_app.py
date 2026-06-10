#!/usr/bin/env python3
"""
MicroSpot Dash UI - Real-time robot control dashboard
Replacement for Streamlit UI with better real-time performance
"""
import os
import sys
import socket
import requests
from dash import Dash, html, dcc, callback, Input, Output, State, ctx
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

# Add src directory to path for component imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the working 3D robot visualization from Streamlit components
from components.robot_3d import create_3d_robot

# ============== CONFIGURATION ==============

def get_backend_url():
    """Get backend API URL from environment or auto-detect"""
    if "MICROSPOT_BACKEND" in os.environ:
        return os.environ["MICROSPOT_BACKEND"]
    try:
        hostname = socket.gethostname()
        return f"http://{hostname}:8000"
    except:
        return "http://localhost:8000"

API_URL = get_backend_url()

# ============== APP SETUP ==============

app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
    title="MicroSpot"
)

# ============== LAYOUT ==============

# Sidebar navigation
sidebar = dbc.Nav(
    [
        dbc.NavLink("Control", href="/", active="exact", id="nav-control"),
        dbc.NavLink("Servos", href="/servos", active="exact", id="nav-servos"),
        dbc.NavLink("Tuning", href="/tuning", active="exact", id="nav-tuning"),
        dbc.NavLink("IMU", href="/imu", active="exact", id="nav-imu"),
        dbc.NavLink("Settings", href="/settings", active="exact", id="nav-settings"),
    ],
    vertical=True,
    pills=True,
    className="bg-dark p-3",
)

# Main layout
app.layout = dbc.Container([
    dcc.Location(id='url', refresh=False),
    dcc.Interval(id='interval-fast', interval=200, n_intervals=0),  # 5Hz for real-time
    dcc.Interval(id='interval-slow', interval=2000, n_intervals=0),  # 0.5Hz for status
    dcc.Store(id='store-status', data={}),

    dbc.Row([
        # Sidebar
        dbc.Col([
            html.H4("MicroSpot", className="text-center mb-3"),
            html.Div(id="connection-status", className="mb-3"),
            html.Hr(),
            sidebar,
        ], width=2, className="bg-dark vh-100 p-3"),

        # Main content
        dbc.Col([
            html.Div(id="page-content", className="p-4")
        ], width=10),
    ], className="g-0"),
], fluid=True, className="p-0")

# ============== PAGE LAYOUTS ==============

def create_control_page():
    """Control page layout"""
    return dbc.Container([
        html.H2("Robot Control"),
        dbc.Row([
            # Left column - Status and 3D view
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Status"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Span("Gait: ", className="text-muted"),
                                html.Span(id="gait-status", className="fw-bold"),
                            ], width=6),
                            dbc.Col([
                                html.Span("Balance: ", className="text-muted"),
                                html.Span(id="balance-status", className="fw-bold"),
                            ], width=6),
                        ]),
                    ])
                ], className="mb-3"),
                dbc.Card([
                    dbc.CardHeader([
                        "3D View",
                        html.Small(" (drag to rotate, scroll to zoom)", className="text-muted ms-2"),
                    ]),
                    dbc.CardBody([
                        dcc.Graph(
                            id="robot-3d",
                            style={"height": "450px"},
                            # Initial figure - shows robot in default position immediately
                            figure=create_3d_robot({}, 0, 0, 0, 450),
                            config={
                                'scrollZoom': True,
                                'displayModeBar': True,
                                'modeBarButtonsToRemove': ['select2d', 'lasso2d'],
                                'displaylogo': False,
                                'responsive': True,  # Important for proper rendering
                            }
                        )
                    ], style={"minHeight": "450px"})
                ]),
            ], width=8),

            # Right column - Controls
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Walking"),
                    dbc.CardBody([
                        dbc.ButtonGroup([
                            dbc.Button("Start", id="btn-walk-start", color="success", className="me-1"),
                            dbc.Button("Stop", id="btn-walk-stop", color="danger", className="me-1"),
                            dbc.Button("Step", id="btn-walk-step", color="primary"),
                        ], className="mb-3 w-100"),
                        html.Div(id="walk-feedback"),
                    ])
                ], className="mb-3"),
                dbc.Card([
                    dbc.CardHeader("Poses"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col(dbc.Button("Stand", id="btn-pose-stand", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("Sit", id="btn-pose-sit", color="secondary", className="w-100"), width=6),
                        ], className="mb-2"),
                        dbc.Row([
                            dbc.Col(dbc.Button("Rest", id="btn-pose-rest", color="secondary", className="w-100"), width=6),
                            dbc.Col(dbc.Button("Neutral", id="btn-pose-neutral", color="secondary", className="w-100"), width=6),
                        ]),
                        html.Div(id="pose-feedback", className="mt-2"),
                    ])
                ], className="mb-3"),
                dbc.Card([
                    dbc.CardHeader("Balance"),
                    dbc.CardBody([
                        dbc.Switch(id="switch-balance", label="Enable Balance", value=False),
                        html.Div(id="balance-feedback"),
                    ])
                ]),
            ], width=4),
        ]),
    ])

def create_tuning_page():
    """Tuning page layout"""
    return dbc.Container([
        html.H2("Tuning"),
        dbc.Tabs([
            dbc.Tab(label="Stand", children=[
                dbc.Card([
                    dbc.CardBody([
                        html.Label("Knee Bend (degrees)"),
                        dcc.Slider(id="slider-knee-bend", min=0, max=60, step=5, value=40,
                                   marks={i: str(i) for i in range(0, 61, 10)}),
                        dbc.Row([
                            dbc.Col(dbc.Button("Preview", id="btn-stand-preview", color="secondary"), width=6),
                            dbc.Col(dbc.Button("Save", id="btn-stand-save", color="primary"), width=6),
                        ], className="mt-3"),
                        html.Div(id="stand-feedback", className="mt-2"),
                    ])
                ], className="mt-3"),
            ]),
            dbc.Tab(label="Balance", children=[
                dbc.Card([
                    dbc.CardBody([
                        html.Label("Kp (Proportional Gain)"),
                        dcc.Slider(id="slider-kp", min=0.1, max=1.5, step=0.1, value=0.5,
                                   marks={i/10: str(i/10) for i in range(1, 16, 2)}),
                        dbc.Button("Save Kp", id="btn-save-kp", color="primary", className="mt-3"),
                        html.Div(id="kp-feedback", className="mt-2"),
                    ])
                ], className="mt-3"),
            ]),
            dbc.Tab(label="Gait", children=[
                dbc.Card([
                    dbc.CardBody([
                        html.Label("Cycle Time (seconds)"),
                        dcc.Slider(id="slider-cycle-time", min=0.4, max=1.5, step=0.1, value=1.0,
                                   marks={i/10: str(i/10) for i in range(4, 16, 2)}),
                        html.Label("Step Height (degrees)", className="mt-3"),
                        dcc.Slider(id="slider-step-height", min=10, max=40, step=5, value=36,
                                   marks={i: str(i) for i in range(10, 41, 10)}),
                        dbc.Row([
                            dbc.Col(dbc.Button("Apply", id="btn-gait-apply", color="secondary"), width=6),
                            dbc.Col(dbc.Button("Save", id="btn-gait-save", color="primary"), width=6),
                        ], className="mt-3"),
                        html.Div(id="gait-feedback", className="mt-2"),
                        html.Hr(),
                        html.H6("Presets"),
                        dbc.ButtonGroup([
                            dbc.Button("Slow", id="btn-preset-slow", color="info", size="sm"),
                            dbc.Button("Normal", id="btn-preset-normal", color="info", size="sm"),
                            dbc.Button("Fast", id="btn-preset-fast", color="info", size="sm"),
                        ]),
                    ])
                ], className="mt-3"),
            ]),
        ]),
    ])

def create_imu_page():
    """IMU page layout"""
    return dbc.Container([
        html.H2("IMU / Balance"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Orientation (Real-time)"),
                    dbc.CardBody([
                        dcc.Graph(id="imu-graph", style={"height": "350px"}, config={'displayModeBar': False}),
                    ])
                ]),
            ], width=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Current Angles"),
                    dbc.CardBody([
                        html.Div([
                            html.Span("Pitch: ", className="text-muted"),
                            html.Span(id="pitch-value", className="h3 text-info"),
                        ], className="mb-3"),
                        html.Div([
                            html.Span("Roll: ", className="text-muted"),
                            html.Span(id="roll-value", className="h3 text-warning"),
                        ]),
                        html.Hr(),
                        html.Div([
                            html.Span("Status: ", className="text-muted"),
                            html.Span(id="balance-enabled-status", className="text-success"),
                        ]),
                    ])
                ], className="mb-3"),
                dbc.Card([
                    dbc.CardHeader("Calibration"),
                    dbc.CardBody([
                        html.P("Place robot on flat surface before calibrating", className="text-muted small"),
                        dbc.Button("Calibrate IMU Zero", id="btn-calibrate-imu", color="primary", className="w-100"),
                        html.Div(id="imu-calibrate-feedback", className="mt-2"),
                    ])
                ]),
            ], width=4),
        ]),
    ])

def create_servo_card(leg):
    """Create a servo control card for a leg"""
    return dbc.Card([
        dbc.CardHeader(f"{leg} Leg", className="fw-bold"),
        dbc.CardBody([
            # Hip
            dbc.Row([
                dbc.Col(html.Label("Hip", className="mb-0"), width=3),
                dbc.Col(html.Span(id=f"servo-{leg}-hip-val", className="text-info"), width=2),
                dbc.Col(
                    dcc.Slider(
                        id=f"servo-{leg}-hip",
                        min=0, max=180, step=1, value=90,
                        marks={0: '0', 45: '45', 90: '90', 135: '135', 180: '180'},
                        tooltip={"placement": "bottom", "always_visible": False},
                        className="mt-1"
                    ),
                    width=7
                ),
            ], className="mb-2 align-items-center"),
            # Knee
            dbc.Row([
                dbc.Col(html.Label("Knee", className="mb-0"), width=3),
                dbc.Col(html.Span(id=f"servo-{leg}-knee-val", className="text-warning"), width=2),
                dbc.Col(
                    dcc.Slider(
                        id=f"servo-{leg}-knee",
                        min=0, max=180, step=1, value=90,
                        marks={0: '0', 45: '45', 90: '90', 135: '135', 180: '180'},
                        tooltip={"placement": "bottom", "always_visible": False},
                        className="mt-1"
                    ),
                    width=7
                ),
            ], className="mb-2 align-items-center"),
            # Ankle
            dbc.Row([
                dbc.Col(html.Label("Ankle", className="mb-0"), width=3),
                dbc.Col(html.Span(id=f"servo-{leg}-ankle-val", className="text-success"), width=2),
                dbc.Col(
                    dcc.Slider(
                        id=f"servo-{leg}-ankle",
                        min=0, max=180, step=1, value=90,
                        marks={0: '0', 45: '45', 90: '90', 135: '135', 180: '180'},
                        tooltip={"placement": "bottom", "always_visible": False},
                        className="mt-1"
                    ),
                    width=7
                ),
            ], className="align-items-center"),
        ])
    ], className="mb-3")

def create_servos_page():
    """Servos page layout"""
    return dbc.Container([
        html.H2("Servo Control"),
        dbc.Row([
            dbc.Col([create_servo_card("FL")], width=6),
            dbc.Col([create_servo_card("FR")], width=6),
        ]),
        dbc.Row([
            dbc.Col([create_servo_card("RL")], width=6),
            dbc.Col([create_servo_card("RR")], width=6),
        ]),
        dbc.Row([
            dbc.Col([
                dbc.ButtonGroup([
                    dbc.Button("Reset All to 90°", id="btn-servo-reset", color="warning"),
                    dbc.Button("Go to Neutrals", id="btn-servo-neutrals", color="primary"),
                ]),
            ]),
        ]),
        html.Div(id="servo-feedback", className="mt-2"),
    ])

def create_settings_page():
    """Settings page layout"""
    return dbc.Container([
        html.H2("Settings"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("System"),
                    dbc.CardBody([
                        html.P(f"Backend: {API_URL}"),
                        html.Div(id="system-status"),
                    ])
                ], className="mb-3"),
                dbc.Card([
                    dbc.CardHeader("Emergency"),
                    dbc.CardBody([
                        dbc.Button("EMERGENCY STOP", id="btn-emergency", color="danger", size="lg", className="w-100"),
                    ])
                ]),
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Calibration"),
                    dbc.CardBody([
                        dbc.Button("Export Calibration", id="btn-export-cal", color="secondary", className="w-100 mb-2"),
                        dbc.Button("Reset to Defaults", id="btn-reset-cal", color="warning", className="w-100"),
                    ])
                ]),
            ], width=6),
        ]),
    ])

# ============== CALLBACKS ==============

@callback(
    Output("page-content", "children"),
    Input("url", "pathname")
)
def display_page(pathname):
    """Route to correct page based on URL"""
    if pathname == "/servos":
        return create_servos_page()
    elif pathname == "/tuning":
        return create_tuning_page()
    elif pathname == "/imu":
        return create_imu_page()
    elif pathname == "/settings":
        return create_settings_page()
    else:
        return create_control_page()

@callback(
    Output("connection-status", "children"),
    Input("interval-slow", "n_intervals")
)
def update_connection_status(n):
    """Update connection status indicator"""
    try:
        resp = requests.get(f"{API_URL}/api/status", timeout=1)
        if resp.ok:
            return dbc.Alert("Connected", color="success", className="mb-0 py-1 text-center")
    except:
        pass
    return dbc.Alert("Disconnected", color="danger", className="mb-0 py-1 text-center")

@callback(
    [Output("gait-status", "children"), Output("balance-status", "children")],
    Input("interval-fast", "n_intervals")
)
def update_robot_status(n):
    """Update gait and balance status on control page"""
    gait_text = "Unknown"
    balance_text = "Unknown"

    try:
        resp = requests.get(f"{API_URL}/api/gait/status", timeout=0.5)
        if resp.ok:
            data = resp.json()
            if data.get("walking", False):
                gait_text = "Walking"
            else:
                gait_text = "Stopped"
    except:
        gait_text = "Error"

    try:
        resp = requests.get(f"{API_URL}/api/balance/status", timeout=0.5)
        if resp.ok:
            data = resp.json()
            balance_text = "ON" if data.get("enabled", False) else "OFF"
    except:
        balance_text = "Error"

    return gait_text, balance_text

# Walking controls
@callback(
    Output("walk-feedback", "children"),
    Input("btn-walk-start", "n_clicks"),
    Input("btn-walk-stop", "n_clicks"),
    Input("btn-walk-step", "n_clicks"),
    prevent_initial_call=True
)
def handle_walking(start, stop, step):
    """Handle walking button clicks"""
    triggered = ctx.triggered_id
    try:
        if triggered == "btn-walk-start":
            requests.post(f"{API_URL}/api/gait/start", timeout=2)
            return dbc.Alert("Walking started", color="success", duration=2000)
        elif triggered == "btn-walk-stop":
            requests.post(f"{API_URL}/api/gait/stop", timeout=2)
            return dbc.Alert("Walking stopped", color="info", duration=2000)
        elif triggered == "btn-walk-step":
            requests.post(f"{API_URL}/api/gait/step", timeout=2)
            return dbc.Alert("Step executed", color="info", duration=2000)
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger", duration=3000)
    return ""

# Pose controls
@callback(
    Output("pose-feedback", "children"),
    Input("btn-pose-stand", "n_clicks"),
    Input("btn-pose-sit", "n_clicks"),
    Input("btn-pose-rest", "n_clicks"),
    Input("btn-pose-neutral", "n_clicks"),
    prevent_initial_call=True
)
def handle_poses(stand, sit, rest, neutral):
    """Handle pose button clicks"""
    triggered = ctx.triggered_id
    pose_map = {
        "btn-pose-stand": "stand",
        "btn-pose-sit": "sit",
        "btn-pose-rest": "rest",
        "btn-pose-neutral": "neutral",
    }
    pose = pose_map.get(triggered)
    if pose:
        try:
            requests.post(f"{API_URL}/api/pose/{pose}", timeout=2)
            return dbc.Alert(f"Pose: {pose}", color="success", duration=2000)
        except Exception as e:
            return dbc.Alert(f"Error: {e}", color="danger", duration=3000)
    return ""

# Tuning - Save Kp
@callback(
    Output("kp-feedback", "children"),
    Input("btn-save-kp", "n_clicks"),
    State("slider-kp", "value"),
    prevent_initial_call=True
)
def save_kp(n_clicks, kp):
    """Save balance Kp"""
    try:
        requests.post(f"{API_URL}/api/tuning/balance_kp", json={"value": kp}, timeout=2)
        return dbc.Alert(f"Kp saved: {kp}", color="success", duration=2000)
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger", duration=3000)

# Tuning - Save Gait params
@callback(
    Output("gait-feedback", "children"),
    Input("btn-gait-save", "n_clicks"),
    Input("btn-gait-apply", "n_clicks"),
    Input("btn-preset-slow", "n_clicks"),
    Input("btn-preset-normal", "n_clicks"),
    Input("btn-preset-fast", "n_clicks"),
    State("slider-cycle-time", "value"),
    State("slider-step-height", "value"),
    prevent_initial_call=True
)
def handle_gait_tuning(save, apply, slow, normal, fast, cycle_time, step_height):
    """Handle gait tuning"""
    triggered = ctx.triggered_id
    try:
        if triggered == "btn-preset-slow":
            requests.post(f"{API_URL}/api/gait/params", json={"cycle_time": 1.2, "step_height": 20}, timeout=2)
            return dbc.Alert("Slow preset applied", color="info", duration=2000)
        elif triggered == "btn-preset-normal":
            requests.post(f"{API_URL}/api/gait/params", json={"cycle_time": 0.8, "step_height": 25}, timeout=2)
            return dbc.Alert("Normal preset applied", color="info", duration=2000)
        elif triggered == "btn-preset-fast":
            requests.post(f"{API_URL}/api/gait/params", json={"cycle_time": 0.5, "step_height": 30}, timeout=2)
            return dbc.Alert("Fast preset applied", color="info", duration=2000)
        elif triggered == "btn-gait-apply":
            requests.post(f"{API_URL}/api/gait/params", json={"cycle_time": cycle_time, "step_height": step_height}, timeout=2)
            return dbc.Alert("Gait params applied", color="info", duration=2000)
        elif triggered == "btn-gait-save":
            requests.post(f"{API_URL}/api/tuning/cycle_time", json={"value": cycle_time}, timeout=2)
            requests.post(f"{API_URL}/api/tuning/step_height", json={"value": step_height}, timeout=2)
            return dbc.Alert("Gait params saved", color="success", duration=2000)
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger", duration=3000)
    return ""

# IMU readings and graph
# Store for IMU history
imu_history = {"pitch": [], "roll": [], "time": []}
MAX_IMU_HISTORY = 100

@callback(
    [Output("pitch-value", "children"),
     Output("roll-value", "children"),
     Output("imu-graph", "figure"),
     Output("balance-enabled-status", "children")],
    Input("interval-fast", "n_intervals")
)
def update_imu_values(n):
    """Update IMU pitch/roll values and graph"""
    global imu_history

    pitch, roll = 0, 0
    balance_status = "Unknown"

    try:
        resp = requests.get(f"{API_URL}/api/balance/angles", timeout=0.5)
        if resp.ok:
            data = resp.json()
            pitch = data.get("pitch", 0)
            roll = data.get("roll", 0)
    except:
        pass

    try:
        resp = requests.get(f"{API_URL}/api/balance/status", timeout=0.5)
        if resp.ok:
            data = resp.json()
            balance_status = "Enabled" if data.get("enabled", False) else "Disabled"
    except:
        pass

    # Update history
    import time
    imu_history["pitch"].append(pitch)
    imu_history["roll"].append(roll)
    imu_history["time"].append(time.time())

    # Keep only last N samples
    if len(imu_history["pitch"]) > MAX_IMU_HISTORY:
        imu_history["pitch"] = imu_history["pitch"][-MAX_IMU_HISTORY:]
        imu_history["roll"] = imu_history["roll"][-MAX_IMU_HISTORY:]
        imu_history["time"] = imu_history["time"][-MAX_IMU_HISTORY:]

    # Create figure
    fig = go.Figure()

    # Normalize time to seconds from start
    if imu_history["time"]:
        t0 = imu_history["time"][0]
        times = [(t - t0) for t in imu_history["time"]]
    else:
        times = []

    fig.add_trace(go.Scatter(
        x=times, y=imu_history["pitch"],
        mode='lines',
        name='Pitch',
        line=dict(color='#17a2b8', width=2)
    ))
    fig.add_trace(go.Scatter(
        x=times, y=imu_history["roll"],
        mode='lines',
        name='Roll',
        line=dict(color='#ffc107', width=2)
    ))

    # Add zero line
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

    fig.update_layout(
        xaxis=dict(title="Time (s)", showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
        yaxis=dict(title="Angle (°)", range=[-45, 45], showgrid=True, gridcolor='rgba(128,128,128,0.2)'),
        margin=dict(l=50, r=20, t=20, b=40),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(color='white'),
    )

    return f"{pitch:.1f}°", f"{roll:.1f}°", fig, balance_status

# IMU calibration
@callback(
    Output("imu-calibrate-feedback", "children"),
    Input("btn-calibrate-imu", "n_clicks"),
    prevent_initial_call=True
)
def calibrate_imu(n_clicks):
    """Calibrate IMU zero point"""
    try:
        requests.post(f"{API_URL}/api/balance/calibrate", timeout=5)
        return dbc.Alert("IMU calibrated", color="success", duration=2000)
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger", duration=3000)

# Emergency stop
@callback(
    Output("system-status", "children"),
    Input("btn-emergency", "n_clicks"),
    prevent_initial_call=True
)
def emergency_stop(n_clicks):
    """Emergency stop - disable all servos"""
    try:
        requests.post(f"{API_URL}/api/gait/stop", timeout=1)
        requests.post(f"{API_URL}/api/reset", timeout=2)
        return dbc.Alert("EMERGENCY STOP ACTIVATED", color="danger")
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger")

# Servo reset
@callback(
    Output("servo-feedback", "children"),
    Input("btn-servo-reset", "n_clicks"),
    Input("btn-servo-neutrals", "n_clicks"),
    prevent_initial_call=True
)
def handle_servo_controls(reset, neutrals):
    """Handle servo control buttons"""
    triggered = ctx.triggered_id
    try:
        if triggered == "btn-servo-reset":
            requests.post(f"{API_URL}/api/reset", timeout=2)
            return dbc.Alert("All servos reset to 90°", color="info", duration=2000)
        elif triggered == "btn-servo-neutrals":
            requests.post(f"{API_URL}/api/goto_neutrals", timeout=2)
            return dbc.Alert("Moved to calibrated neutrals", color="success", duration=2000)
    except Exception as e:
        return dbc.Alert(f"Error: {e}", color="danger", duration=3000)
    return ""

# Individual servo slider controls
# Servo channel mapping
SERVO_CHANNELS = {
    "FL-hip": 0, "FL-knee": 1, "FL-ankle": 2,
    "FR-hip": 3, "FR-knee": 4, "FR-ankle": 5,
    "RL-hip": 6, "RL-knee": 7, "RL-ankle": 8,
    "RR-hip": 9, "RR-knee": 10, "RR-ankle": 11,
}

# Create callbacks for each leg - sends commands AND updates value displays
for leg in ["FL", "FR", "RL", "RR"]:
    def make_leg_callback(leg_name):
        @callback(
            Output(f"servo-{leg_name}-hip", "value", allow_duplicate=True),
            Output(f"servo-{leg_name}-knee", "value", allow_duplicate=True),
            Output(f"servo-{leg_name}-ankle", "value", allow_duplicate=True),
            Output(f"servo-{leg_name}-hip-val", "children"),
            Output(f"servo-{leg_name}-knee-val", "children"),
            Output(f"servo-{leg_name}-ankle-val", "children"),
            Input(f"servo-{leg_name}-hip", "value"),
            Input(f"servo-{leg_name}-knee", "value"),
            Input(f"servo-{leg_name}-ankle", "value"),
            prevent_initial_call=True
        )
        def update_leg_servos(hip, knee, ankle):
            """Send servo command when slider changes"""
            triggered = ctx.triggered_id
            if triggered:
                joint = triggered.split("-")[-1]
                channel = SERVO_CHANNELS.get(f"{leg_name}-{joint}")
                value = {"hip": hip, "knee": knee, "ankle": ankle}.get(joint, 90)

                if channel is not None:
                    try:
                        requests.post(f"{API_URL}/api/servo/{channel}", json={"angle": value}, timeout=1)
                    except:
                        pass
            return hip, knee, ankle, f"{hip}°", f"{knee}°", f"{ankle}°"
        return update_leg_servos

    make_leg_callback(leg)

# ============== 3D VISUALIZATION ==============
# Uses create_3d_robot imported from components/robot_3d.py
# This is the same visualization that works in Streamlit!

@callback(
    Output("robot-3d", "figure"),
    Input("interval-fast", "n_intervals")
)
def update_3d_view(n):
    """Update 3D robot visualization with real servo data from /api/status"""
    servo_angles = {}
    pitch, roll = 0, 0

    try:
        # Use /api/status which returns {"angles": {"0": 90, "1": 90, ...}}
        # This is the same endpoint the working Streamlit app uses!
        resp = requests.get(f"{API_URL}/api/status", timeout=0.5)
        if resp.ok:
            data = resp.json()
            if "angles" in data:
                # Keys are strings like "0", "1", etc.
                servo_angles = data["angles"]
    except Exception as e:
        print(f"Error getting servo angles: {e}")

    try:
        # Get IMU angles
        resp = requests.get(f"{API_URL}/api/balance/angles", timeout=0.5)
        if resp.ok:
            data = resp.json()
            pitch = data.get("pitch", 0)
            roll = data.get("roll", 0)
    except Exception as e:
        print(f"Error getting IMU angles: {e}")

    try:
        # Use the working create_3d_robot from robot_3d.py
        # This is the exact same function that works in Streamlit!
        fig = create_3d_robot(
            servo_angles=servo_angles,
            body_pitch=pitch,
            body_roll=roll,
            body_yaw=0,
            height=450
        )
        return fig
    except Exception as e:
        print(f"Error creating robot figure: {e}")
        import traceback
        traceback.print_exc()
        # Return a simple test figure on error
        fig = go.Figure()
        fig.add_trace(go.Scatter3d(
            x=[0, 100], y=[0, 100], z=[0, 0],
            mode='lines+markers',
            line=dict(color='red', width=5),
            marker=dict(size=10),
            name='Error - check terminal'
        ))
        fig.update_layout(
            scene=dict(
                xaxis=dict(range=[-200, 200], title='X'),
                yaxis=dict(range=[-50, 300], title='Y (up)'),
                zaxis=dict(range=[-200, 200], title='Z'),
            )
        )
        return fig

# ============== MAIN ==============

if __name__ == "__main__":
    print(f"Starting MicroSpot Dash UI on port 8050")
    print(f"Backend API: {API_URL}")
    app.run(host="0.0.0.0", port=8050, debug=True)
