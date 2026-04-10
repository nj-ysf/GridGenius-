#!/usr/bin/env python3
"""pages/parametres.py — Paramètres admin GridGenius"""

import streamlit as st
import plotly.graph_objects as go
import os

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
API   = os.getenv("API_BASE_URL", "http://localhost:8000")


def render(api_get, api_put):
    st.markdown("""
    <div class='gg-page-title'>Paramètres</div>
    <div class='gg-page-sub'>Configuration système — Admin GridGenius</div>
    """, unsafe_allow_html=True)

    cfg = api_get("/admin/config")
    if not cfg:
        st.markdown("<div class='gg-alert-c' style='padding:14px'>API indisponible.</div>",
                    unsafe_allow_html=True)
        return

    tab_s, tab_b, tab_sys, tab_sim = st.tabs([
        "SCORING IA", "BATTERIE", "SYSTÈME", "SIMULATION"
    ])

    # ── Scoring ────────────────────────────────────────────────
    with tab_s:
        st.markdown("""
        <div class='gg-formula' style='margin-bottom:16px'>
            Score = α·PV_norm + β·SOC_proj − γ·grid_dep − δ·conflict
            &nbsp;&nbsp;|&nbsp;&nbsp; variables ∈ [0, 1]
        </div>""", unsafe_allow_html=True)

        sc = cfg.get("scoring", {})
        c1, c2 = st.columns(2)
        with c1:
            alpha = st.slider("α — Poids PV",         0.0, 1.0, float(sc.get("alpha",  0.40)), 0.05)
            beta  = st.slider("β — Poids SOC",        0.0, 1.0, float(sc.get("beta",   0.35)), 0.05)
            cost  = st.number_input("Coût réseau (MAD/kWh)", 0.5, 5.0,
                                     float(sc.get("cost_grid_kwh", 1.20)), 0.05)
        with c2:
            gamma = st.slider("γ — Pénalité réseau",  0.0, 1.0, float(sc.get("gamma",  0.50)), 0.05)
            delta = st.slider("δ — Pénalité conflit", 0.0, 1.0, float(sc.get("delta",  0.30)), 0.05)
            soc_pc = st.slider("SOC cible pré-charge (%)", 50, 95,
                                int(float(sc.get("soc_precharge", 0.80)) * 100))

        cov = st.slider("Couverture minimale (%)", 30, 90,
                         int(float(sc.get("coverage_min_pct", 60.0))))

        st.markdown(f"""
        <div style='font-family:JetBrains Mono,monospace;font-size:11px;
                    color:{AMBER};background:rgba(232,160,32,0.05);
                    border:1px solid rgba(232,160,32,0.15);
                    border-radius:4px;padding:10px 14px;margin:12px 0;letter-spacing:1px'>
            Score = {alpha}·PV + {beta}·SOC − {gamma}·Grid − {delta}·Conflit
        </div>""", unsafe_allow_html=True)

        # Radar chart
        fig = go.Figure(go.Scatterpolar(
            r=[alpha, beta, gamma, delta, alpha],
            theta=["α PV", "β SOC", "γ Grid", "δ Conflit", "α PV"],
            fill='toself',
            fillcolor='rgba(232,160,32,0.08)',
            line=dict(color=AMBER, width=1.5)
        ))
        fig.update_layout(
            polar=dict(
                bgcolor=SURF,
                radialaxis=dict(
                    visible=True, range=[0, 1],
                    gridcolor=BORD,
                    tickfont=dict(size=8, family="JetBrains Mono", color=MUTED)
                ),
                angularaxis=dict(
                    gridcolor=BORD,
                    tickfont=dict(size=10, family="JetBrains Mono", color=TEXT2)
                )
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            font_color=TEXT2,
            height=240,
            margin=dict(l=40, r=40, t=20, b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

        if st.button("SAUVEGARDER LE SCORING", use_container_width=True):
            res = api_put("/admin/scoring", {
                "alpha": alpha, "beta": beta, "gamma": gamma, "delta": delta,
                "coverage_min_pct": float(cov),
                "soc_precharge": soc_pc / 100,
                "cost_grid_kwh": cost
            })
            if res.get("status") == "updated":
                st.markdown("<div class='gg-alert-ok'>✓ Scoring mis à jour</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='gg-alert-c'>{str(res)}</div>",
                            unsafe_allow_html=True)

    # ── Batterie ───────────────────────────────────────────────
    with tab_b:
        bc = cfg.get("battery", {})
        c1, c2 = st.columns(2)
        with c1:
            cap     = st.number_input("Capacité (kWh)", 10.0, 200.0,
                                       float(bc.get("capacity_kwh", 50.0)))
            soc_min = st.slider("SOC minimum (%)", 5, 30,
                                 int(float(bc.get("soc_min", 0.10)) * 100))
            soc_max = st.slider("SOC maximum (%)", 70, 100,
                                 int(float(bc.get("soc_max", 0.95)) * 100))
        with c2:
            eta_c  = st.slider("Rendement charge (%)", 85, 99,
                                int(float(bc.get("eta_charge", 0.95)) * 100))
            eta_d  = st.slider("Rendement décharge (%)", 85, 99,
                                int(float(bc.get("eta_discharge", 0.95)) * 100))
            pmax_c = st.number_input("P max charge (kW)", 1.0, 30.0,
                                      float(bc.get("p_max_charge_kw", 10.0)))
            losses = st.number_input("Pertes fixes (kW)", 0.01, 1.0,
                                      float(bc.get("p_losses_kw", 0.05)), 0.01)

        # SOC range visualization
        st.markdown("<div class='gg-label' style='margin-top:12px;margin-bottom:6px'>"
                    "Plage SOC opérationnelle</div>", unsafe_allow_html=True)
        st.markdown(f"""
        <div style='background:{BORD};border-radius:2px;height:16px;position:relative;
                    margin-bottom:4px;overflow:visible'>
            <div style='position:absolute;left:{soc_min}%;width:{soc_max-soc_min}%;
                        height:100%;background:linear-gradient(90deg,{COBALT},{AMBER});
                        border-radius:2px;opacity:0.7'></div>
        </div>
        <div style='display:flex;justify-content:space-between;
                    font-family:JetBrains Mono,monospace;font-size:9px;color:{MUTED}'>
            <span>0%</span>
            <span style='color:{COBALT}'>{soc_min}%</span>
            <span style='color:{AMBER}'>{soc_max}%</span>
            <span>100%</span>
        </div>""", unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        if st.button("SAUVEGARDER BATTERIE", use_container_width=True):
            res = api_put("/admin/battery", {
                "capacity_kwh": cap, "soc_min": soc_min / 100,
                "soc_max": soc_max / 100, "eta_charge": eta_c / 100,
                "eta_discharge": eta_d / 100, "p_max_charge_kw": pmax_c,
                "p_losses_kw": losses
            })
            if res.get("status") == "updated":
                st.markdown("<div class='gg-alert-ok'>✓ Batterie mise à jour</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='gg-alert-c'>{str(res)}</div>",
                            unsafe_allow_html=True)

    # ── Système ────────────────────────────────────────────────
    with tab_sys:
        ds = cfg.get("data_status", {})

        st.markdown("<div class='gg-label' style='margin-bottom:10px'>◌  InfluxDB</div>",
                    unsafe_allow_html=True)

        c1, c2, c3 = st.columns(3)
        with c1: st.metric("Statut",    ds.get("status", "?"))
        with c2: st.metric("Données",   f"{ds.get('hours_of_data', 0):.1f}h")
        with c3: st.metric("Confiance", f"{ds.get('confidence_pct', 0)}%")

        if ds.get("message"):
            st.markdown(f"<div class='gg-info'>{ds.get('message','')}</div>",
                        unsafe_allow_html=True)

        st.markdown("<hr style='opacity:0.2'>", unsafe_allow_html=True)
        st.markdown("<div class='gg-label' style='margin-bottom:10px'>◌  Rétention</div>",
                    unsafe_allow_html=True)

        retention = st.slider("Jours de rétention", 7, 365, 30)
        if st.button("METTRE À JOUR LA RÉTENTION"):
            res = api_put("/admin/system", {"retention_days": retention})
            if res.get("status") == "updated":
                st.markdown(f"<div class='gg-alert-ok'>✓ Rétention → {retention} jours</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='gg-alert-c'>{str(res)}</div>",
                            unsafe_allow_html=True)

        st.markdown("<hr style='opacity:0.2'>", unsafe_allow_html=True)
        st.markdown("<div class='gg-label' style='margin-bottom:10px'>△  Seuils Anomalies</div>",
                    unsafe_allow_html=True)

        a1, a2 = st.columns(2)
        with a1:
            soc_crit  = st.number_input("SOC critique (%)",   5, 30, 15)
            temp_crit = st.number_input("Temp. critique (°C)", 40, 70, 55)
        with a2:
            soc_low   = st.number_input("SOC faible (%)",     10, 40, 25)
            temp_high = st.number_input("Temp. élevée (°C)",  35, 60, 45)

        if st.button("SAUVEGARDER SEUILS"):
            res = api_put("/admin/system", {"thresholds": {
                "bat_soc_critical":  soc_crit,
                "bat_soc_low":       soc_low,
                "bat_temp_critical": temp_crit,
                "bat_temp_high":     temp_high
            }})
            if res.get("status") == "updated":
                st.markdown("<div class='gg-alert-ok'>✓ Seuils mis à jour</div>",
                            unsafe_allow_html=True)
            else:
                st.markdown(f"<div class='gg-alert-c'>{str(res)}</div>",
                            unsafe_allow_html=True)

    # ── Simulation ─────────────────────────────────────────────
    with tab_sim:
        st.markdown("""
        <div class='gg-info' style='margin-bottom:16px'>
            Lance la simulation heuristique sur N jours depuis les prédictions courantes.
        </div>""", unsafe_allow_html=True)

        sim_days = st.slider("Horizon (jours)", 1, 14, 7)

        if st.button("LANCER LA SIMULATION", use_container_width=True):
            import requests
            with st.spinner("Simulation en cours..."):
                try:
                    r = requests.post(f"{API}/predict",
                                      params={"days": sim_days}, timeout=30)
                    sim = r.json()
                except Exception as e:
                    st.markdown(f"<div class='gg-alert-c'>{str(e)}</div>",
                                unsafe_allow_html=True); return

            if sim.get("status") == "LEARNING":
                st.markdown(f"<div class='gg-learning'>"
                            f"<div style='font-family:JetBrains Mono,monospace;font-size:10px;"
                            f"color:#e8a020;letter-spacing:2px'>DONNÉES INSUFFISANTES</div>"
                            f"<div style='font-size:12px;color:#4a6080;margin-top:6px'>"
                            f"{sim.get('message','')}</div></div>", unsafe_allow_html=True)
                return

            daily = sim.get("daily_summary", {})
            if daily:
                import pandas as pd
                df = pd.DataFrame(list(daily.values()))
                avg_auto = df['autonomy_pct'].mean()
                auto_c = SUCC if avg_auto > 70 else AMBER if avg_auto > 40 else DANG

                st.markdown(f"""
                <div style='background:rgba(34,168,107,0.08);border:1px solid rgba(34,168,107,0.2);
                            border-radius:4px;padding:12px 16px;margin-bottom:16px;
                            font-family:JetBrains Mono,monospace;font-size:11px;
                            color:{auto_c};letter-spacing:1px'>
                    ✓ SIMULATION OK &nbsp;|&nbsp; Autonomie moyenne : {avg_auto:.1f}%
                </div>""", unsafe_allow_html=True)

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=df['date'], y=df['pv_kwh'],
                    name="PV kWh", marker_color=AMBER, opacity=0.85,
                    marker=dict(line=dict(width=0))
                ))
                fig.add_trace(go.Bar(
                    x=df['date'], y=df['consumption_kwh'],
                    name="Conso kWh", marker_color=COBALT, opacity=0.85,
                    marker=dict(line=dict(width=0))
                ))
                fig.update_layout(
                    barmode="group", height=280,
                    plot_bgcolor=SURF, paper_bgcolor="rgba(0,0,0,0)",
                    font_color=TEXT2, font_family="JetBrains Mono",
                    xaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
                    yaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
                    margin=dict(l=40, r=20, t=16, b=30),
                    legend=dict(
                        bgcolor="rgba(0,0,0,0)",
                        font=dict(size=9, family="JetBrains Mono"),
                        orientation="h", y=1.08
                    ),
                    bargap=0.25, bargroupgap=0.08
                )
                st.plotly_chart(fig, use_container_width=True)