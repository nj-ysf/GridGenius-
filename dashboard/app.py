#!/usr/bin/env python3
"""
app.py — GridGenius Dashboard Entry Point
  Streamlit multipage | Port 8501
  Parle UNIQUEMENT à api.py (port 8000)
  Lance : streamlit run app.py --server.port 8501 --server.address 0.0.0.0
"""

import streamlit as st
import requests
from datetime import datetime
import plotly.graph_objects as go

API = "http://localhost:8000"

st.set_page_config(
    page_title = "GridGenius",
    page_icon  = "⚡",
    layout     = "wide",
    initial_sidebar_state = "expanded"
)

# ── CSS global ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;600;700&display=swap');
:root {
    --bg:#0a0e1a; --surface:#111827; --card:#1a2236;
    --border:#2a3a5c; --accent:#00d4aa; --accent2:#3b82f6;
    --warn:#f59e0b; --danger:#ef4444; --text:#e2e8f0; --muted:#64748b;
}
html,body,[class*="css"]{ font-family:'DM Sans',sans-serif;
    background:var(--bg)!important; color:var(--text)!important; }
.stApp,.main{ background:var(--bg)!important; }
[data-testid="stSidebar"]{ background:var(--surface)!important;
    border-right:1px solid var(--border); }
[data-testid="metric-container"]{ background:var(--card)!important;
    border:1px solid var(--border)!important; border-radius:10px!important;
    padding:16px!important; }
.stButton>button{ background:var(--accent)!important; color:#000!important;
    font-weight:700!important; font-family:'Space Mono',monospace!important;
    border:none!important; border-radius:8px!important; }
.stTabs [data-baseweb="tab-list"]{ background:var(--surface)!important;
    border-bottom:1px solid var(--border)!important; }
.stTabs [data-baseweb="tab"]{ font-family:'Space Mono',monospace!important;
    font-size:11px!important; letter-spacing:2px!important;
    text-transform:uppercase!important; color:var(--muted)!important; }
.stTabs [aria-selected="true"]{ color:var(--accent)!important;
    border-bottom:2px solid var(--accent)!important; }
.stSelectbox>div,.stNumberInput>div{ background:var(--card)!important;
    border-color:var(--border)!important; }
.card{ background:var(--card); border:1px solid var(--border);
    border-radius:12px; padding:20px; margin:4px 0; }
.card-accent{ border-color:var(--accent); }
.label{ font-family:'Space Mono',monospace; font-size:10px;
    letter-spacing:2px; text-transform:uppercase; color:var(--muted); }
.value{ font-family:'Space Mono',monospace; font-size:28px;
    font-weight:700; color:var(--accent); line-height:1.1; }
.badge{ display:inline-block; padding:3px 12px; border-radius:20px;
    font-size:11px; font-family:'Space Mono',monospace; font-weight:700;
    letter-spacing:1px; text-transform:uppercase; }
.badge-solar   { background:#064e3b; color:#34d399; border:1px solid #34d399; }
.badge-battery { background:#1e3a5f; color:#60a5fa; border:1px solid #60a5fa; }
.badge-grid    { background:#4a1d1d; color:#f87171; border:1px solid #f87171; }
.badge-hybrid  { background:#3d2e00; color:#fbbf24; border:1px solid #fbbf24; }
.badge-safe    { background:#2d1f4e; color:#a78bfa; border:1px solid #a78bfa; }
.soc-bar{ background:#1e2a3a; border-radius:6px; height:10px; overflow:hidden; }
.soc-fill{ height:100%; border-radius:6px; transition:width 0.5s; }
.alert-c{ background:#4a1d1d; border-left:3px solid #ef4444;
    padding:8px 12px; border-radius:4px; margin:3px 0; font-size:12px; }
.alert-w{ background:#3d2e00; border-left:3px solid #f59e0b;
    padding:8px 12px; border-radius:4px; margin:3px 0; font-size:12px; }
.alert-i{ background:#1e3a5f; border-left:3px solid #3b82f6;
    padding:8px 12px; border-radius:4px; margin:3px 0; font-size:12px; }
.learning-banner{ background:#1a1a2e; border:1px solid #f59e0b;
    border-radius:10px; padding:16px; text-align:center; }
::-webkit-scrollbar{ width:5px; }
::-webkit-scrollbar-thumb{ background:var(--border); border-radius:3px; }
</style>
""", unsafe_allow_html=True)

# ── Helpers API ────────────────────────────────────────────────
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

# Exposer pour les pages
st.session_state['API']        = API
st.session_state['api_get']    = api_get
st.session_state['api_post']   = api_post
st.session_state['api_put']    = api_put
st.session_state['api_delete'] = api_delete

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:20px 0 10px'>
        <div style='font-family:Space Mono;font-size:22px;
                    color:#00d4aa;font-weight:700;letter-spacing:2px'>
            ⚡ GRID<span style='color:#3b82f6'>GENIUS</span>
        </div>
        <div style='font-family:Space Mono;font-size:9px;
                    color:#64748b;letter-spacing:4px;margin-top:4px'>
            EHTP — GIEW 2026
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Statut API + InfluxDB
    health = api_get("/health", timeout=2)
    api_ok = bool(health)
    db_ok  = health.get("influxdb") == "connected"
    ds     = health.get("data_status", {})

    def dot(ok, label):
        c = "#00d4aa" if ok else "#ef4444"
        return (f"<div style='display:flex;align-items:center;gap:8px;padding:4px 0'>"
                f"<div style='width:7px;height:7px;border-radius:50%;"
                f"background:{c};box-shadow:0 0 5px {c}'></div>"
                f"<span style='font-family:Space Mono;font-size:10px;"
                f"color:{c};letter-spacing:1px'>{label}</span></div>")

    st.markdown(dot(api_ok, "API FASTAPI"), unsafe_allow_html=True)
    st.markdown(dot(db_ok,  "INFLUXDB"),    unsafe_allow_html=True)

    if ds:
        status = ds.get("status","?")
        conf   = ds.get("confidence_pct", 0)
        colors = {"LEARNING":"#f59e0b","PARTIAL":"#3b82f6","OPERATIONAL":"#00d4aa"}
        c = colors.get(status, "#94a3b8")
        st.markdown(f"""
        <div style='background:#111827;border:1px solid {c};border-radius:8px;
                    padding:10px;margin:8px 0'>
            <div style='font-family:Space Mono;font-size:9px;
                        color:{c};letter-spacing:2px'>{status}</div>
            <div style='font-size:11px;color:#94a3b8;margin-top:4px'>
                {ds.get('hours_of_data',0):.1f}h données
                | confiance {conf}%
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.divider()

    page = st.radio("", [
        "📊  Supervision",
        "📈  Prédictions",
        "📅  Planification",
        "⚙️  Paramètres"
    ], label_visibility="collapsed")

    st.divider()
    st.markdown(f"""
    <div style='font-family:Space Mono;font-size:9px;color:#374151;
                text-align:center;letter-spacing:1px'>
        {datetime.now().strftime('%H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

# ── Routing vers les pages ─────────────────────────────────────
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
