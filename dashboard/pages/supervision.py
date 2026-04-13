#!/usr/bin/env python3
"""pages/supervision.py — Supervision temps réel GridGenius"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

BG    = "#06090f"
SURF  = "#0b1120"
CARD  = "#0f1829"
BORD  = "#1c2d44"
AMBER = "#e8a020"
COBALT= "#2060d8"
SUCC  = "#22a86b"
DANG  = "#c93030"
MUTED = "#4a6080"
TEXT2 = "#8ba0bc"


def _gauge(val, max_val, title, unit, color, min_val=0):
    pct = min(100, max(0, (val - min_val) / (max_val - min_val) * 100))
    return f"""
    <div class='gg-card' style='text-align:center; padding: 30px 20px; min-height: 180px; display:flex; flex-direction:column; justify-content:center'>
        <div class='gg-label' style='margin-bottom: 16px'>{title}</div>
        <div class='gg-value' style='color:{color}; font-size:42px; margin-bottom: 24px'>{val:.1f} <span style='font-size:16px; color:{MUTED}'>{unit}</span></div>
        <div class='gg-bar-track' style='height:6px; background:#0b1120; border:1px solid {BORD}'>
            <div class='gg-bar-fill' style='width:{pct}%; background:{color}; box-shadow:0 0 10px {color}40'></div>
        </div>
    </div>
    """


def _mode_badge(mode: str) -> str:
    icons = {"solar": "◈", "battery": "◉", "grid": "◎", "hybrid": "⬡"}
    css_map = {
        "solar": "badge-solar", "battery": "badge-battery",
        "grid": "badge-grid", "hybrid": "badge-hybrid"
    }
    if mode not in css_map:
        return "<span class='gg-badge badge-safe'>⊛ SAFE MODE</span>"
    return f"<span class='gg-badge {css_map[mode]}'>{icons[mode]} {mode.upper()}</span>"


def render(api_get):
    st.markdown("""
    <div class='gg-page-title'>Supervision</div>
    <div class='gg-page-sub'>Temps réel · Micro-réseau EHTP Casablanca</div>
    """, unsafe_allow_html=True)

    @st.fragment(run_every="2s")
    def live():
        s = api_get("/status")
        if not s:
            st.markdown("""
            <div class='gg-alert-c' style='padding:14px 18px;font-size:13px'>
                ⚠ API indisponible — vérifier FastAPI port 8000
            </div>""", unsafe_allow_html=True)
            return

        # Safe mode
        if s.get("safe_mode"):
            st.markdown("""
            <div style='background:rgba(196,99,42,0.08);border:1px solid #c4632a40;
                        border-radius:4px;padding:12px 18px;margin-bottom:16px;
                        font-family:JetBrains Mono,monospace;font-size:10px;
                        color:#c4632a;letter-spacing:2px;text-align:center'>
                ⊛ SAFE MODE — SOLAR ON · GRID ON · BATTERY ISOLATED
            </div>""", unsafe_allow_html=True)

        # Learning banner
        if s.get("data_status") == "LEARNING":
            conf = s.get('confidence_pct', 0)
            st.markdown(f"""
            <div class='gg-learning' style='margin-bottom:16px'>
                <div style='font-family:JetBrains Mono,monospace;font-size:10px;
                            color:#e8a020;letter-spacing:2px;margin-bottom:6px'>
                    PHASE D'APPRENTISSAGE · {conf}% CONFIANCE
                </div>
                <div style='font-family:Outfit,sans-serif;font-size:12px;color:#4a6080'>
                    Prédictions actives après 48h de collecte
                </div>
            </div>""", unsafe_allow_html=True)

        pv   = s.get("pv_power",   0)
        load = s.get("load_power", 0)
        soc  = s.get("bat_soc",    50)
        mode = s.get("active_mode", "unknown")
        soc_color = SUCC if soc > 50 else AMBER if soc > 20 else DANG

        # ── KPI row ────────────────────────────────────────────
        c1, c2, c3, c4 = st.columns(4)

        def kpi_card(col, icon, label, value, unit, color=AMBER, extra=""):
            col.markdown(f"""
            <div class='gg-card' style='min-height:100px'>
                <div class='gg-label'>{icon}  {label}</div>
                <div class='gg-value' style='color:{color};margin-top:6px'>{value}</div>
                <div class='gg-value-unit'>{unit}</div>
                {extra}
            </div>""", unsafe_allow_html=True)

        kpi_card(c1, "◈", "Production PV",  f"{pv:.1f}",   "kW")
        kpi_card(c2, "▣", "Consommation",   f"{load:.1f}", "kW", COBALT)
        c3.markdown(f"""
        <div class='gg-card' style='min-height:100px'>
            <div class='gg-label'>◉  SOC Batterie</div>
            <div class='gg-value' style='color:{soc_color};margin-top:6px'>{soc:.0f}</div>
            <div class='gg-value-unit'>%</div>
            <div class='gg-bar-track'>
                <div class='gg-bar-fill' style='width:{soc}%;background:{soc_color}'></div>
            </div>
        </div>""", unsafe_allow_html=True)

        c4.markdown(f"""
        <div class='gg-card' style='min-height:100px'>
            <div class='gg-label'>⬡  Décision IA</div>
            <div style='margin:10px 0 8px'>{_mode_badge(mode)}</div>
            <div style='font-family:JetBrains Mono,monospace;font-size:9px;
                        color:{MUTED};line-height:1.5;letter-spacing:0.5px'>
                {s.get('ai_reason', '—')[:44]}
            </div>
        </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── Secondary row ──────────────────────────────────────
        cb, ce, ca = st.columns([1, 1, 1])

        with cb:
            st.markdown(f"""
            <div class='gg-card'>
                <div class='gg-label' style='margin-bottom:12px'>◉  État Batterie</div>
                <div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>
                    <div>
                        <div class='gg-label'>Tension</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:16px;
                                    color:#d8e4f0'>{s.get('bat_voltage',51.2):.1f}<span style='font-size:10px;color:{MUTED}'> V</span></div>
                    </div>
                    <div>
                        <div class='gg-label'>Température</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:16px;
                                    color:#d8e4f0'>{s.get('bat_temp',25):.1f}<span style='font-size:10px;color:{MUTED}'> °C</span></div>
                    </div>
                    <div>
                        <div class='gg-label'>Mode</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:12px;
                                    color:{AMBER}'>{s.get('charge_mode','-').upper()}</div>
                    </div>
                    <div>
                        <div class='gg-label'>Action</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:12px;
                                    color:{AMBER}'>{s.get('bat_action','idle').upper()}</div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

        with ce:
            auto = s.get('autonomy_today', 0)
            auto_c = SUCC if auto > 70 else AMBER if auto > 40 else DANG
            st.markdown(f"""
            <div class='gg-card'>
                <div class='gg-label' style='margin-bottom:12px'>◌  Énergie Aujourd'hui</div>
                <div style='display:grid;grid-template-columns:1fr 1fr;gap:10px'>
                    <div>
                        <div class='gg-label'>Production PV</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:16px;
                                    color:#d8e4f0'>{s.get('e_pv_today',0):.1f}<span style='font-size:10px;color:{MUTED}'> kWh</span></div>
                    </div>
                    <div>
                        <div class='gg-label'>Consommation</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:16px;
                                    color:#d8e4f0'>{s.get('e_load_today',0):.1f}<span style='font-size:10px;color:{MUTED}'> kWh</span></div>
                    </div>
                    <div style='grid-column:1/-1'>
                        <div class='gg-label'>Autonomie</div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:22px;
                                    color:{auto_c}'>{auto:.1f}<span style='font-size:11px;color:{MUTED}'> %</span></div>
                        <div class='gg-bar-track'>
                            <div class='gg-bar-fill' style='width:{min(auto,100)}%;background:{auto_c}'></div>
                        </div>
                    </div>
                </div>
            </div>""", unsafe_allow_html=True)

        with ca:
            n = s.get("n_alerts", 0)
            st.markdown(f"<div class='gg-card'>", unsafe_allow_html=True)
            st.markdown(f"<div class='gg-label' style='margin-bottom:12px'>◈  Alertes</div>", unsafe_allow_html=True)
            if n == 0:
                st.markdown("<div class='gg-alert-ok'>✓ Aucune anomalie détectée</div>", unsafe_allow_html=True)
            else:
                css = "gg-alert-c" if s.get("has_critical") else "gg-alert-w"
                icon = "✖" if s.get("has_critical") else "△"
                st.markdown(f"<div class='{css}'>{icon} {n} alerte(s) active(s)</div>",
                            unsafe_allow_html=True)
                if st.button("Consulter les alertes", key="btn_alerts"):
                    alerts = api_get("/data/alerts", {"hours": 1}).get("alerts", [])
                    for a in alerts[:5]:
                        css_a = "gg-alert-c" if a['severity'] == "critical" else "gg-alert-w"
                        st.markdown(f"<div class='{css_a}'><strong>{a['type']}</strong> — {a['message']}</div>",
                                    unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # ── Gauges ─────────────────────────────────────────────
        g1, g2, g3 = st.columns(3)
        with g1: st.markdown(_gauge(pv,  10,  "PUISSANCE PV",  "kW", AMBER),  unsafe_allow_html=True)
        with g2: st.markdown(_gauge(soc, 100, "SOC BATTERIE",  "%",  COBALT), unsafe_allow_html=True)
        with g3: st.markdown(_gauge(load, 40, "CONSOMMATION",  "kW", SUCC),   unsafe_allow_html=True)

        # ── Active events ──────────────────────────────────────
        if s.get("active_events", 0) > 0:
            st.markdown("""
            <div class='gg-label' style='margin:8px 0 10px'>
                ▣  Événements Actifs
            </div>""", unsafe_allow_html=True)
            evts = api_get("/events/current").get("active_events", [])
            cols = st.columns(min(len(evts), 3))
            for i, ev in enumerate(evts[:3]):
                imp = ev.get("importance_pct", 50)
                c = SUCC if imp >= 80 else AMBER if imp >= 50 else MUTED
                with cols[i]:
                    st.markdown(f"""
                    <div class='gg-card'>
                        <div style='font-family:JetBrains Mono,monospace;font-size:9px;
                                    color:{c};letter-spacing:2px;margin-bottom:6px'>
                            {ev.get('label','').upper()}
                        </div>
                        <div style='font-family:Syne,sans-serif;font-size:15px;
                                    font-weight:700;color:#d8e4f0;margin-bottom:8px'>
                            {ev.get('name','')}
                        </div>
                        <div style='font-family:JetBrains Mono,monospace;font-size:10px;
                                    color:{MUTED};display:flex;gap:12px'>
                            <span>{ev.get('start','')}→{ev.get('end','')}</span>
                            <span>{ev.get('expected_kw',0)}kW</span>
                            <span>{imp}%</span>
                        </div>
                    </div>""", unsafe_allow_html=True)

        # Timestamp
        st.markdown(
            f"<div style='text-align:right;font-family:JetBrains Mono,monospace;"
            f"font-size:8px;color:#1c2d44;margin-top:4px;letter-spacing:2px'>"
            f"SYNC {datetime.now().strftime('%H:%M:%S')}</div>",
            unsafe_allow_html=True
        )

    live()

    # ── Historical chart ────────────────────────────────────────
    st.markdown("<div style='margin:24px 0 0'><hr style='opacity:0.3'></div>",
                unsafe_allow_html=True)
    st.markdown("<div class='gg-label' style='margin-bottom:10px'>◌  Historique</div>",
                unsafe_allow_html=True)

    hours = st.select_slider(
        "Fenêtre temporelle",
        options=[1, 3, 6, 12, 24, 48],
        value=6,
        label_visibility="collapsed"
    )
    hist = api_get("/data/history", {"hours": hours})
    mppt = hist.get("mppt", [])

    if not mppt:
        st.markdown("<div class='gg-info'>Historique vide — données en cours de collecte.</div>",
                    unsafe_allow_html=True)
        return

    df = pd.DataFrame(mppt)
    if 'time' not in df.columns:
        return

    df['time'] = pd.to_datetime(df['time'])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['time'], y=df['pv_power'], name="PV (kW)",
        line=dict(color=AMBER, width=1.5),
        fill='tozeroy', fillcolor='rgba(232,160,32,0.05)'
    ))
    fig.add_trace(go.Scatter(
        x=df['time'], y=df['load_power'], name="Conso (kW)",
        line=dict(color=COBALT, width=1.5, dash='dot')
    ))
    fig.add_trace(go.Scatter(
        x=df['time'], y=df['bat_soc'], name="SOC (%)",
        yaxis="y2",
        line=dict(color=SUCC, width=1.5, dash='dash')
    ))
    fig.update_layout(
        height=300,
        plot_bgcolor=SURF,
        paper_bgcolor="rgba(0,0,0,0)",
        font_color=TEXT2,
        font_family="JetBrains Mono",
        xaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
        yaxis=dict(gridcolor=BORD, zeroline=False, title="kW",
                   titlefont=dict(size=9), tickfont=dict(size=9)),
        yaxis2=dict(
            overlaying="y", side="right",
            gridcolor=BORD, range=[0, 100],
            title="SOC %", titlefont=dict(size=9), tickfont=dict(size=9)
        ),
        margin=dict(l=40, r=40, t=16, b=30),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=9, family="JetBrains Mono"),
            orientation="h", y=1.08
        ),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)