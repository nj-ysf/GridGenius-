#!/usr/bin/env python3
"""
pages/supervision.py — Supervision temps réel GridGenius
  Fragment 2s pour les métriques live
  Historique depuis InfluxDB via api.py
"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

PLOT_BG = "#111827"
ACCENT  = "#00d4aa"
ACCENT2 = "#3b82f6"
WARNING = "#f59e0b"
DANGER  = "#ef4444"


def _gauge(val, max_val, title, unit, color, min_val=0):
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=val,
        title={"text":title,"font":{"family":"Space Mono","size":11,"color":"#94a3b8"}},
        number={"suffix":f" {unit}","font":{"family":"Space Mono","size":18,"color":"#e2e8f0"}},
        gauge={
            "axis":  {"range":[min_val,max_val],"tickfont":{"size":9},"tickcolor":"#2a3a5c"},
            "bar":   {"color":color}, "bgcolor":"#1a2236", "bordercolor":"#2a3a5c",
            "steps": [{"range":[min_val,max_val*0.35],"color":"#0f1929"},
                      {"range":[max_val*0.35,max_val*0.7],"color":"#131f35"},
                      {"range":[max_val*0.7,max_val],"color":"#162040"}]
        }
    ))
    fig.update_layout(height=190, margin=dict(l=10,r=10,t=40,b=10),
                      paper_bgcolor=PLOT_BG, font_color="#94a3b8")
    return fig


def _mode_badge(mode: str) -> str:
    icons = {"solar":"☀️","battery":"🔋","grid":"🔌","hybrid":"⚡"}
    css   = {"solar":"badge-solar","battery":"badge-battery",
             "grid":"badge-grid","hybrid":"badge-hybrid"}
    if mode not in css:
        return "<span class='badge badge-safe'>🛡️ SAFE MODE</span>"
    return f"<span class='badge {css[mode]}'>{icons[mode]} {mode.upper()}</span>"


def render(api_get):
    st.markdown("""
    <div style='font-family:Space Mono;font-size:20px;font-weight:700;
                color:#e2e8f0;margin-bottom:2px'>SUPERVISION TEMPS RÉEL</div>
    <div style='font-family:Space Mono;font-size:9px;color:#64748b;
                letter-spacing:3px;margin-bottom:20px'>
        MICRO-RÉSEAU INTELLIGENT — EHTP CASABLANCA
    </div>""", unsafe_allow_html=True)

    # ── Fragment rafraîchi toutes les 2s ───────────────────────
    @st.fragment(run_every="2s")
    def live():
        s = api_get("/status")
        if not s:
            st.error("⚠️ API indisponible — vérifier FastAPI port 8000")
            return

        # Bannière SAFE MODE
        if s.get("safe_mode"):
            st.markdown("""
            <div style='background:#2d1f4e;border:2px solid #a78bfa;border-radius:10px;
                        padding:12px;text-align:center;margin-bottom:16px'>
                <span style='font-family:Space Mono;font-size:12px;color:#a78bfa;
                             letter-spacing:2px'>
                    🛡️ SAFE MODE — Solar ON · Grid ON · Battery OFF
                </span>
            </div>""", unsafe_allow_html=True)

        # Bannière apprentissage
        if s.get("data_status") == "LEARNING":
            st.markdown(f"""
            <div class='learning-banner' style='margin-bottom:16px'>
                <span style='font-family:Space Mono;font-size:11px;color:#f59e0b'>
                    📚 APPRENTISSAGE — {s.get('confidence_pct',0)}% confiance
                </span><br>
                <span style='font-size:11px;color:#64748b'>
                    Prédiction disponible après 48h de collecte
                </span>
            </div>""", unsafe_allow_html=True)

        # Métriques
        pv   = s.get("pv_power",  0)
        load = s.get("load_power",0)
        soc  = s.get("bat_soc",  50)
        mode = s.get("active_mode","unknown")
        soc_c= "#34d399" if soc>50 else "#f59e0b" if soc>20 else "#ef4444"

        c1,c2,c3,c4 = st.columns(4)
        with c1:
            st.markdown(f"""<div class='card'>
                <div class='label'>☀️ Production PV</div>
                <div class='value'>{pv:.1f}</div>
                <div style='color:#64748b;font-size:12px'>kW</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class='card'>
                <div class='label'>🏫 Consommation</div>
                <div class='value'>{load:.1f}</div>
                <div style='color:#64748b;font-size:12px'>kW</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown(f"""<div class='card'>
                <div class='label'>🔋 Batterie SOC</div>
                <div class='value' style='color:{soc_c}'>{soc:.0f}</div>
                <div style='color:#64748b;font-size:12px'>%</div>
                <div class='soc-bar' style='margin-top:8px'>
                    <div class='soc-fill' style='width:{soc}%;background:{soc_c}'></div>
                </div>
            </div>""", unsafe_allow_html=True)
        with c4:
            st.markdown(f"""<div class='card'>
                <div class='label'>🤖 Décision IA</div>
                <div style='margin:8px 0'>{_mode_badge(mode)}</div>
                <div style='font-size:10px;color:#64748b;font-family:Space Mono'>
                    {s.get('ai_reason','-')[:38]}
                </div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Batterie + Énergie + Alertes
        cb, ce, ca = st.columns(3)
        with cb:
            st.markdown("<div class='label'>État Batterie</div>", unsafe_allow_html=True)
            b1,b2 = st.columns(2)
            with b1:
                st.metric("Tension", f"{s.get('bat_voltage',51.2):.1f} V")
                st.metric("Temp.",   f"{s.get('bat_temp',25):.1f} °C")
            with b2:
                st.metric("Mode",    s.get("charge_mode","-").upper())
                st.metric("Action",  s.get("bat_action","idle").upper())

        with ce:
            st.markdown("<div class='label'>Énergie Aujourd'hui</div>", unsafe_allow_html=True)
            st.metric("Production PV", f"{s.get('e_pv_today',0):.1f} kWh")
            st.metric("Consommation",  f"{s.get('e_load_today',0):.1f} kWh")
            st.metric("Autonomie",     f"{s.get('autonomy_today',0):.1f}%")

        with ca:
            st.markdown("<div class='label'>Alertes</div>", unsafe_allow_html=True)
            n = s.get("n_alerts",0)
            if n == 0:
                st.markdown("<div class='alert-i'>✅ Aucune anomalie</div>",
                            unsafe_allow_html=True)
            else:
                css = "alert-c" if s.get("has_critical") else "alert-w"
                icon= "🚨" if s.get("has_critical") else "⚠️"
                st.markdown(f"<div class='{css}'>{icon} {n} alerte(s)</div>",
                            unsafe_allow_html=True)
                if st.button("Voir alertes", key="btn_alerts"):
                    alerts = api_get("/data/alerts",{"hours":1}).get("alerts",[])
                    for a in alerts[:5]:
                        c = "alert-c" if a['severity']=="critical" else "alert-w"
                        st.markdown(
                            f"<div class='{c}'><strong>{a['type']}</strong>"
                            f" — {a['message']}</div>",
                            unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Jauges
        g1,g2,g3 = st.columns(3)
        with g1: st.plotly_chart(_gauge(pv,  10,"PUISSANCE PV","kW",ACCENT),
                                  use_container_width=True)
        with g2: st.plotly_chart(_gauge(soc,100,"SOC BATTERIE","%", ACCENT2),
                                  use_container_width=True)
        with g3: st.plotly_chart(_gauge(load,40,"CONSOMMATION","kW",WARNING),
                                  use_container_width=True)

        # Événements actifs
        if s.get("active_events",0) > 0:
            st.markdown("<br><div class='label'>Événements Actifs</div>",
                        unsafe_allow_html=True)
            evts = api_get("/events/current").get("active_events",[])
            cols = st.columns(min(len(evts),3))
            for i,ev in enumerate(evts[:3]):
                imp = ev.get("importance_pct",50)
                c   = "#34d399" if imp>=80 else "#fbbf24" if imp>=50 else "#94a3b8"
                with cols[i]:
                    st.markdown(f"""<div class='card'>
                        <div style='font-size:10px;font-family:Space Mono;color:{c}'>
                            {ev.get('label','')}</div>
                        <div style='font-size:13px;font-weight:700;margin:4px 0'>
                            {ev.get('name','')}</div>
                        <div style='font-size:11px;color:#64748b'>
                            🕐 {ev.get('start','')}→{ev.get('end','')}
                            &nbsp;⚡ {ev.get('expected_kw',0)}kW
                            &nbsp;📊 {imp}%
                        </div>
                    </div>""", unsafe_allow_html=True)

        st.markdown(
            f"<div style='text-align:right;font-family:Space Mono;"
            f"font-size:9px;color:#374151;margin-top:8px'>"
            f"MAJ : {datetime.now().strftime('%H:%M:%S')}</div>",
            unsafe_allow_html=True)

    live()

    # ── Historique ─────────────────────────────────────────────
    st.divider()
    st.markdown("<div class='label' style='margin-bottom:10px'>"
                "Historique</div>", unsafe_allow_html=True)

    hours = st.select_slider("Fenêtre", [1,3,6,12,24,48], value=6,
                              label_visibility="collapsed")
    hist  = api_get("/data/history", {"hours": hours})
    mppt  = hist.get("mppt",[])

    if not mppt:
        st.info("Historique vide — données en cours de collecte.")
        return

    df = pd.DataFrame(mppt)
    if 'time' not in df.columns:
        st.info("Format de données inattendu.")
        return

    df['time'] = pd.to_datetime(df['time'])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df['time'], y=df['pv_power'], name="PV (kW)",
        line=dict(color=ACCENT,width=1.5),
        fill='tozeroy', fillcolor='rgba(0,212,170,0.06)'))
    fig.add_trace(go.Scatter(x=df['time'], y=df['load_power'], name="Conso (kW)",
        line=dict(color=ACCENT2,width=1.5,dash='dash')))
    fig.add_trace(go.Scatter(x=df['time'], y=df['bat_soc'], name="SOC (%)",
        yaxis="y2", line=dict(color=WARNING,width=1.5)))
    fig.update_layout(
        height=320, plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
        font_color="#94a3b8",
        xaxis=dict(gridcolor="#1e2a3a", zeroline=False),
        yaxis=dict(gridcolor="#1e2a3a", zeroline=False, title="kW"),
        yaxis2=dict(overlaying="y", side="right", gridcolor="#1e2a3a",
                    range=[0,100], title="SOC %"),
        margin=dict(l=40,r=40,t=20,b=30),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)),
        hovermode="x unified"
    )
    st.plotly_chart(fig, use_container_width=True)
