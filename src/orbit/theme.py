"""
Orbit UI Theme - Color palette, leg colors, and Quasar CSS overrides.

Dark navy palette inspired by GitHub's dark theme with accent blues/cyans.
All NiceGUI/Quasar pages should call `apply_theme()` on load.
"""

# ============================================================================
# COLOR PALETTE
# ============================================================================

BG_PRIMARY = "#0d1117"
BG_SECONDARY = "#161b22"
BG_SIDEBAR = "#010409"
BORDER_COLOR = "#21262d"

ACCENT_BLUE = "#1f6feb"
ACCENT_CYAN = "#39d2f5"

TEXT_PRIMARY = "#e6edf3"
TEXT_MUTED = "#7d8590"

STATUS_GREEN = "#3fb950"
STATUS_YELLOW = "#d29922"
STATUS_RED = "#f85149"
STATUS_PURPLE = "#a371f7"

# Per-leg accent colors (consistent across all visualizations)
LEG_COLORS = {
    "FL": "#ff4444",
    "FR": "#44ff44",
    "RL": "#4444ff",
    "RR": "#ffaa44",
}

# ============================================================================
# CSS - Quasar overrides, fonts, animations
# ============================================================================

ORBIT_CSS = """
<style>
/* ---- Google Fonts: Inter ---- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ---- CSS Variables ---- */
:root {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-sidebar: #010409;
    --border-color: #21262d;
    --accent-blue: #1f6feb;
    --accent-cyan: #39d2f5;
    --text-primary: #e6edf3;
    --text-muted: #7d8590;
    --status-green: #3fb950;
    --status-yellow: #d29922;
    --status-red: #f85149;
    --status-purple: #a371f7;
}

/* ---- Global ---- */
body, .q-page, .nicegui-content {
    background-color: var(--bg-primary) !important;
    font-family: 'Inter', sans-serif !important;
    color: var(--text-primary) !important;
}

/* ---- Quasar Card ---- */
.q-card {
    background-color: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: 12px !important;
    color: var(--text-primary) !important;
}

/* ---- Quasar Drawer / Sidebar ---- */
.q-drawer {
    background-color: var(--bg-sidebar) !important;
}

/* ---- Quasar Toolbar / Header ---- */
.q-toolbar {
    background-color: var(--bg-sidebar) !important;
}

/* ---- Quasar Header ---- */
.q-header {
    background-color: var(--bg-sidebar) !important;
    border-bottom: 1px solid var(--border-color) !important;
}

/* ---- Quasar Footer ---- */
.q-footer {
    background-color: var(--bg-sidebar) !important;
    border-top: 1px solid var(--border-color) !important;
}

/* ---- Quasar Tabs ---- */
.q-tabs {
    background-color: transparent !important;
}

/* ---- Flat button hover ---- */
.q-btn--flat.text-white:hover {
    background: rgba(31, 111, 235, 0.15) !important;
}

/* ---- Glow slider (cyan thumb glow) ---- */
.glow-slider .q-slider__thumb {
    box-shadow: 0 0 8px var(--accent-cyan) !important;
}

/* ---- Status badge ---- */
.status-badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border-radius: 20px;
    font-weight: 600;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    gap: 6px;
}

.status-badge::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: currentColor;
}

/* ---- Leg card left-border accents ---- */
.leg-card-fl { border-left: 4px solid #ff4444 !important; }
.leg-card-fr { border-left: 4px solid #44ff44 !important; }
.leg-card-rl { border-left: 4px solid #4444ff !important; }
.leg-card-rr { border-left: 4px solid #ffaa44 !important; }

/* ---- Emergency button pulse animation ---- */
.emergency-btn {
    animation: pulse-red 2s infinite;
}

@keyframes pulse-red {
    0%, 100% { box-shadow: 0 0 5px rgba(248, 81, 73, 0.5); }
    50% { box-shadow: 0 0 20px rgba(248, 81, 73, 0.8); }
}

/* ---- Scrollbar styling ---- */
::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

::-webkit-scrollbar-track {
    background: var(--bg-primary);
}

::-webkit-scrollbar-thumb {
    background: var(--border-color);
    border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
    background: var(--text-muted);
}

/* ---- Quasar separator ---- */
.q-separator {
    background-color: var(--border-color) !important;
}

/* ---- Mini-sidebar nav link styling ---- */
.orbit-nav-link {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 8px;
    color: var(--text-muted) !important;
    text-decoration: none !important;
    transition: all 0.2s ease;
    font-size: 0.9rem;
}

.orbit-nav-link:hover {
    background: rgba(31, 111, 235, 0.1);
    color: var(--text-primary) !important;
}

.orbit-nav-link.active {
    background: rgba(31, 111, 235, 0.15);
    color: var(--accent-blue) !important;
}

/* ---- Activity feed ---- */
.activity-feed {
    max-height: 300px;
    overflow-y: auto;
}

.activity-item {
    padding: 6px 10px;
    border-left: 2px solid var(--border-color);
    margin-bottom: 2px;
    font-size: 0.8rem;
    color: var(--text-muted);
    transition: border-color 0.2s ease;
}

.activity-item:hover {
    border-left-color: var(--accent-cyan);
    color: var(--text-primary);
}
</style>
"""


def apply_theme():
    """Apply the Orbit theme to the current NiceGUI page.

    Call this at the top of every @ui.page function:
        from orbit.theme import apply_theme
        apply_theme()
    """
    from nicegui import ui
    ui.dark_mode(True)
    ui.add_head_html(ORBIT_CSS)
