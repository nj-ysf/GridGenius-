#!/usr/bin/env python3
"""
app.py — GridGenius Dashboard Entry Point
  Streamlit multipage | Port 8501
  Parle UNIQUEMENT à api.py (port 8000)
  Lance : streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

import streamlit as st
import requests
import os
from datetime import datetime

API = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

st.set_page_config(
    page_title="GridGenius",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS global ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500;700&family=Outfit:wght@300;400;500;600&display=swap');

:root {
    --bg:         #06090f;
    --surface:    #0b1120;
    --card:       #0f1829;
    --card-2:     #131e30;
    --border:     #1c2d44;
    --border-2:   #243548;
    --amber:      #e8a020;
    --amber-dim:  #9b6a14;
    --amber-glow: rgba(232,160,32,0.12);
    --copper:     #c4632a;
    --cobalt:     #2060d8;
    --cobalt-dim: #1a3d8a;
    --cobalt-glow:rgba(32,96,216,0.12);
    --success:    #22a86b;
    --danger:     #c93030;
    --muted:      #4a6080;
    --muted-2:    #3a4e66;
    --text:       #d8e4f0;
    --text-2:     #8ba0bc;
    --text-dim:   #4a6080;
}

/* ── Reset & Base ── */
html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif;
    background: var(--bg) !important;
    color: var(--text) !important;
}
.stApp, .main { background: var(--bg) !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: var(--surface); }
::-webkit-scrollbar-thumb { background: var(--border-2); border-radius: 2px; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: var(--surface) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"]::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, var(--amber), var(--copper), var(--cobalt));
}

/* ── Metric cards ── */
[data-testid="metric-container"] {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 4px !important;
    padding: 14px 16px !important;
}
[data-testid="stMetricLabel"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 9px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: var(--muted) !important;
}
[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', monospace !important;
    color: var(--text) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: transparent !important;
    color: var(--amber) !important;
    font-weight: 600 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    border: 1px solid var(--amber) !important;
    border-radius: 2px !important;
    padding: 8px 20px !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: var(--amber-glow) !important;
    box-shadow: 0 0 16px rgba(232,160,32,0.2) !important;
}

/* ── Primary action button ── */
.stButton > button[kind="primary"] {
    background: var(--amber) !important;
    color: #000 !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 10px !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    color: var(--muted) !important;
    padding: 10px 20px !important;
    border-bottom: 2px solid transparent !important;
}
.stTabs [aria-selected="true"] {
    color: var(--amber) !important;
    border-bottom-color: var(--amber) !important;
    background: transparent !important;
}

/* ── Form elements ── */
.stSelectbox > div, .stNumberInput > div {
    background: var(--card) !important;
    border-color: var(--border) !important;
    border-radius: 4px !important;
    font-family: 'Outfit', sans-serif !important;
}
.stSlider [data-testid="stSlider"] { color: var(--amber) !important; }
.stSlider [role="slider"] { background: var(--amber) !important; }

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 16px 0 !important; }

/* ── Custom components ── */

/* Card */
.gg-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 20px;
    margin: 4px 0;
    position: relative;
    overflow: hidden;
}
.gg-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 3px; height: 100%;
    background: var(--amber);
    opacity: 0;
    transition: opacity 0.2s;
}
.gg-card:hover::before { opacity: 1; }

/* Accent card */
.gg-card-accent {
    border-color: var(--amber);
    background: linear-gradient(135deg, var(--card), var(--amber-glow));
}

/* Label */
.gg-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 6px;
}

/* Value */
.gg-value {
    font-family: 'JetBrains Mono', monospace;
    font-size: 32px;
    font-weight: 700;
    color: var(--amber);
    line-height: 1;
}
.gg-value-unit {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--muted);
    margin-top: 4px;
}

/* Badges */
.gg-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 2px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    text-transform: uppercase;
}
.badge-solar    { background: rgba(34,168,107,0.12); color: #22a86b; border: 1px solid #22a86b40; }
.badge-battery  { background: var(--cobalt-glow);    color: #4d8ef5; border: 1px solid #2060d840; }
.badge-grid     { background: rgba(201,48,48,0.12);  color: #e05454; border: 1px solid #c9303040; }
.badge-hybrid   { background: var(--amber-glow);     color: var(--amber); border: 1px solid #e8a02040; }
.badge-safe     { background: rgba(196,99,42,0.12);  color: var(--copper); border: 1px solid #c4632a40; }

/* SOC bar */
.gg-bar-track {
    background: var(--border);
    border-radius: 2px;
    height: 6px;
    overflow: hidden;
    margin-top: 10px;
}
.gg-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.6s ease;
}

/* Alerts */
.gg-alert-c {
    background: rgba(201,48,48,0.08);
    border-left: 2px solid var(--danger);
    padding: 8px 12px;
    border-radius: 2px;
    margin: 3px 0;
    font-size: 12px;
    font-family: 'Outfit', sans-serif;
}
.gg-alert-w {
    background: rgba(232,160,32,0.08);
    border-left: 2px solid var(--amber);
    padding: 8px 12px;
    border-radius: 2px;
    margin: 3px 0;
    font-size: 12px;
}
.gg-alert-i {
    background: rgba(32,96,216,0.08);
    border-left: 2px solid var(--cobalt);
    padding: 8px 12px;
    border-radius: 2px;
    margin: 3px 0;
    font-size: 12px;
}
.gg-alert-ok {
    background: rgba(34,168,107,0.08);
    border-left: 2px solid var(--success);
    padding: 8px 12px;
    border-radius: 2px;
    font-size: 12px;
}

/* Learning banner */
.gg-learning {
    background: rgba(232,160,32,0.05);
    border: 1px solid var(--amber-dim);
    border-radius: 4px;
    padding: 16px 20px;
    text-align: center;
}

/* Score formula box */
.gg-formula {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--amber);
    background: var(--amber-glow);
    border: 1px solid #e8a02030;
    border-radius: 4px;
    padding: 12px 16px;
    margin: 12px 0;
    letter-spacing: 1px;
}

/* Info box */
.gg-info {
    background: var(--cobalt-glow);
    border: 1px solid #2060d830;
    border-radius: 4px;
    padding: 10px 14px;
    font-size: 12px;
    color: var(--text-2);
    font-family: 'Outfit', sans-serif;
    margin: 8px 0;
}

/* Page header */
.gg-page-title {
    font-family: 'Syne', sans-serif;
    font-size: 26px;
    font-weight: 800;
    color: var(--text);
    letter-spacing: -0.5px;
    line-height: 1;
    margin-bottom: 2px;
}
.gg-page-sub {
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    color: var(--muted);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 24px;
}

/* Slot card */
.gg-slot {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 16px 20px;
    margin: 8px 0;
    transition: border-color 0.2s;
}
.gg-slot-best { border-color: var(--amber); }

/* Geometric decoration – pure CSS zellige-inspired corner mark */
.gg-corner {
    position: absolute;
    top: 12px; right: 12px;
    width: 18px; height: 18px;
    opacity: 0.15;
    background:
        linear-gradient(45deg, var(--amber) 25%, transparent 25%) -4px 0,
        linear-gradient(-45deg, var(--amber) 25%, transparent 25%) -4px 0,
        linear-gradient(45deg, transparent 75%, var(--amber) 75%),
        linear-gradient(-45deg, transparent 75%, var(--amber) 75%);
    background-size: 8px 8px;
    background-color: transparent;
}

/* Sidebar nav */
.gg-nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    border-radius: 2px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 1px;
    cursor: pointer;
    border: 1px solid transparent;
    transition: all 0.15s;
    margin: 3px 0;
    color: var(--muted);
    text-decoration: none;
}
.gg-nav-item:hover {
    background: var(--card);
    border-color: var(--border);
    color: var(--text);
}
.gg-nav-item-active {
    background: var(--amber-glow);
    border-color: #e8a02030 !important;
    color: var(--amber) !important;
}

/* Status dot */
.gg-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
}
.gg-dot-ok { background: var(--success); box-shadow: 0 0 6px var(--success); }
.gg-dot-err { background: var(--danger); box-shadow: 0 0 6px var(--danger); }
.gg-dot-warn { background: var(--amber); box-shadow: 0 0 6px var(--amber); }

/* Dataframe */
[data-testid="stDataFrame"] { border: 1px solid var(--border) !important; border-radius: 4px !important; }

/* Top accent line on main content */
.stMainBlockContainer::before {
    content: '';
    display: block;
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--amber) 30%, var(--copper) 60%, transparent);
    margin-bottom: 24px;
    opacity: 0.4;
}

/* Pattern overlay for sidebar */
[data-testid="stSidebar"]::after {
    content: '';
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 160px;
    background-image: repeating-linear-gradient(
        45deg,
        transparent,
        transparent 10px,
        rgba(232,160,32,0.02) 10px,
        rgba(232,160,32,0.02) 11px
    );
    pointer-events: none;
}
</style>
""", unsafe_allow_html=True)

# ── Helpers API ─────────────────────────────────────────────────
def api_get(endpoint: str, params: dict = None, timeout: int = 4):
    try:
        r = requests.get(f"{API}{endpoint}", params=params, timeout=timeout)
        return r.json() if r.status_code == 200 else {}
    except Exception:
        return {}

def api_post(endpoint: str, data: dict = None, timeout: int = 10):
    try:
        r = requests.post(f"{API}{endpoint}", json=data or {}, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_put(endpoint: str, data: dict, timeout: int = 5):
    try:
        r = requests.put(f"{API}{endpoint}", json=data, timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def api_delete(endpoint: str, timeout: int = 5):
    try:
        r = requests.delete(f"{API}{endpoint}", timeout=timeout)
        return r.json()
    except Exception as e:
        return {"error": str(e)}

st.session_state['API']        = API
st.session_state['api_get']    = api_get
st.session_state['api_post']   = api_post
st.session_state['api_put']    = api_put
st.session_state['api_delete'] = api_delete

# ── Sidebar ─────────────────────────────────────────────────────
with st.sidebar:
    # Logo
    st.markdown("""
    <div style='padding: 24px 4px 20px'>
        <div style='font-family: Syne, sans-serif; font-size: 24px; font-weight: 800;
                    color: #d8e4f0; letter-spacing: -0.5px; line-height: 1'>
            Grid<span style='color: #e8a020'>Genius</span>
        </div>
        <div style='font-family: JetBrains Mono, monospace; font-size: 8px;
                    color: #4a6080; letter-spacing: 4px; margin-top: 5px'>
            EHTP · CASABLANCA · GIEW 2026
        </div>
    </div>
    """, unsafe_allow_html=True)

    # API health
    health = api_get("/health", timeout=2)
    api_ok = bool(health)
    db_ok  = health.get("influxdb") == "connected"
    ds     = health.get("data_status", {})

    def status_row(ok, label):
        dot_class = "gg-dot-ok" if ok else "gg-dot-err"
        color = "#22a86b" if ok else "#c93030"
        return f"""<div style='display:flex;align-items:center;gap:8px;padding:3px 0'>
            <span class='gg-dot {dot_class}'></span>
            <span style='font-family:JetBrains Mono,monospace;font-size:9px;
                         letter-spacing:1.5px;color:{color}'>{label}</span>
        </div>"""

    st.markdown(
        f"<div style='background:#0b1120;border:1px solid #1c2d44;border-radius:4px;padding:10px 14px;margin-bottom:14px'>"
        + status_row(api_ok, "API  FASTAPI")
        + status_row(db_ok,  "INFLUXDB")
        + "</div>",
        unsafe_allow_html=True
    )

    # Data status chip
    if ds:
        status  = ds.get("status", "?")
        conf    = ds.get("confidence_pct", 0)
        hours   = ds.get("hours_of_data", 0)
        s_color = {"LEARNING": "#e8a020", "PARTIAL": "#2060d8", "OPERATIONAL": "#22a86b"}.get(status, "#4a6080")
        st.markdown(f"""
        <div style='background:rgba(11,17,32,0.9);border:1px solid {s_color}30;
                    border-radius:4px;padding:10px 14px;margin-bottom:16px'>
            <div style='font-family:JetBrains Mono,monospace;font-size:9px;
                        letter-spacing:2.5px;color:{s_color};margin-bottom:4px'>{status}</div>
            <div style='font-family:Outfit,sans-serif;font-size:11px;color:#4a6080;
                        display:flex;gap:10px'>
                <span>{hours:.1f}h collectées</span>
                <span style='color:#1c2d44'>|</span>
                <span>{conf}% confiance</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

    # Navigation
    page = st.radio("", [
        "📊  Supervision",
        "📈  Prédictions",
        "📅  Planification",
        "⚙️  Paramètres"
    ], label_visibility="collapsed")

    # Bottom timestamp
    st.markdown(f"""
    <div style='position:absolute;bottom:20px;left:0;right:0;
                font-family:JetBrains Mono,monospace;font-size:8px;
                color:#253040;text-align:center;letter-spacing:2px;
                pointer-events:none;z-index:0'>
        {datetime.now().strftime('%Y·%m·%d — %H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

# ── Routing ─────────────────────────────────────────────────────
if "Supervision" in page:
    from pages.supervision import render
    render(api_get)

elif "Prédictions" in page:
    from pages.predictions import render
    render(api_get)

elif "Planification" in page:
    from pages.planification import render
    render(api_get, api_post, api_delete)

elif "Paramètres" in page:
    from pages.parametres import render
    render(api_get, api_put)