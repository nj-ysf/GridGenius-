#!/usr/bin/env python3
"""pages/parametres.py — Paramètres admin GridGenius"""

import streamlit as st
import plotly.graph_objects as go


PLOT_BG = "#111827"
ACCENT  = "#00d4aa"
ACCENT2 = "#3b82f6"
WARNING = "#f59e0b"
DANGER  = "#ef4444"


def render(api_get, api_put):
    st.markdown("""
    <div style='font-family:Space Mono;font-size:20px;font-weight:700;
                color:#e2e8f0;margin-bottom:2px'>PARAMÈTRES SYSTÈME</div>
    <div style='font-family:Space Mono;font-size:9px;color:#64748b;
                letter-spacing:3px;margin-bottom:20px'>
        CONFIGURATION ADMIN — GridGenius
    </div>""", unsafe_allow_html=True)

    cfg = api_get("/admin/config")
    if not cfg:
        st.error("API indisponible.")
        return

    tab_s, tab_b, tab_sys, tab_sim = st.tabs([
        "SCORING IA", "BATTERIE", "SYSTÈME", "SIMULATION"
    ])

    # ── Scoring ────────────────────────────────────────────────
    with tab_s:
        st.markdown("""
        <div style='font-family:Space Mono;font-size:10px;color:#64748b;
                    background:#111827;border:1px solid #1e2a3a;
                    border-radius:8px;padding:12px;margin-bottom:16px'>
            Score = α·PV_norm + β·SOC_proj - γ·grid_dep - δ·conflict<br>
            Variables normalisées ∈ [0,1] — poids libres
        </div>""", unsafe_allow_html=True)

        sc = cfg.get("scoring", {})
        c1, c2 = st.columns(2)
        with c1:
            alpha = st.slider("α — Poids PV",         0.0, 1.0, float(sc.get("alpha",0.40)), 0.05)
            beta  = st.slider("β — Poids SOC",        0.0, 1.0, float(sc.get("beta", 0.35)), 0.05)
            cost  = st.number_input("Coût réseau (MAD/kWh)", 0.5, 5.0,
                                     float(sc.get("cost_grid_kwh",1.20)), 0.05)
        with c2:
            gamma = st.slider("γ — Pénalité réseau",  0.0, 1.0, float(sc.get("gamma",0.50)), 0.05)
            delta = st.slider("δ — Pénalité conflit", 0.0, 1.0, float(sc.get("delta",0.30)), 0.05)
            soc_pc= st.slider("SOC cible pré-charge (%)", 50, 95,
                               int(float(sc.get("soc_precharge",0.80))*100))

        cov = st.slider("Couverture minimale (%)", 30, 90,
                         int(float(sc.get("coverage_min_pct",60.0))))

        # Aperçu score
        st.markdown(f"""
        <div style='font-family:Space Mono;font-size:12px;color:#00d4aa;
                    background:#0a1a14;border:1px solid #064e3b;
                    border-radius:8px;padding:12px;margin:12px 0'>
            Score = {alpha}·PV + {beta}·SOC - {gamma}·Grid - {delta}·Conflit
        </div>""", unsafe_allow_html=True)

        # Radar chart des poids
        fig = go.Figure(go.Scatterpolar(
            r=[alpha, beta, gamma, delta, alpha],
            theta=["α PV","β SOC","γ Grid","δ Conflit","α PV"],
            fill='toself', fillcolor='rgba(0,212,170,0.15)',
            line=dict(color=ACCENT, width=2)
        ))
        fig.update_layout(
            polar=dict(bgcolor=PLOT_BG,
                       radialaxis=dict(visible=True, range=[0,1],
                                       gridcolor="#1e2a3a",tickfont=dict(size=9)),
                       angularaxis=dict(gridcolor="#1e2a3a",tickfont=dict(size=11))),
            paper_bgcolor=PLOT_BG, font_color="#94a3b8",
            height=250, margin=dict(l=40,r=40,t=20,b=20)
        )
        st.plotly_chart(fig, use_container_width=True)

        if st.button("💾 SAUVEGARDER LE SCORING", use_container_width=True):
            res = api_put("/admin/scoring", {
                "alpha":alpha, "beta":beta, "gamma":gamma, "delta":delta,
                "coverage_min_pct":float(cov),
                "soc_precharge":soc_pc/100,
                "cost_grid_kwh":cost
            })
            st.success("Scoring mis à jour ✅") \
                if res.get("status")=="updated" else st.error(str(res))

    # ── Batterie ───────────────────────────────────────────────
    with tab_b:
        bc = cfg.get("battery", {})
        c1, c2 = st.columns(2)
        with c1:
            cap     = st.number_input("Capacité (kWh)", 10.0, 200.0,
                                       float(bc.get("capacity_kwh",50.0)))
            soc_min = st.slider("SOC minimum (%)", 5, 30,
                                 int(float(bc.get("soc_min",0.10))*100))
            soc_max = st.slider("SOC maximum (%)", 70, 100,
                                 int(float(bc.get("soc_max",0.95))*100))
        with c2:
            eta_c  = st.slider("Rendement charge (%)", 85, 99,
                                int(float(bc.get("eta_charge",0.95))*100))
            eta_d  = st.slider("Rendement décharge (%)", 85, 99,
                                int(float(bc.get("eta_discharge",0.95))*100))
            pmax_c = st.number_input("P max charge (kW)", 1.0, 30.0,
                                      float(bc.get("p_max_charge_kw",10.0)))
            losses = st.number_input("Pertes fixes (kW)", 0.01, 1.0,
                                      float(bc.get("p_losses_kw",0.05)), 0.01)

        if st.button("💾 SAUVEGARDER BATTERIE", use_container_width=True):
            res = api_put("/admin/battery", {
                "capacity_kwh":cap, "soc_min":soc_min/100,
                "soc_max":soc_max/100, "eta_charge":eta_c/100,
                "eta_discharge":eta_d/100, "p_max_charge_kw":pmax_c,
                "p_losses_kw":losses
            })
            st.success("Batterie mise à jour ✅") \
                if res.get("status")=="updated" else st.error(str(res))

    # ── Système ────────────────────────────────────────────────
    with tab_sys:
        st.markdown("<div class='label' style='margin-bottom:12px'>"
                    "InfluxDB</div>", unsafe_allow_html=True)

        ds = cfg.get("data_status",{})
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("Statut", ds.get("status","?"))
        with c2: st.metric("Données", f"{ds.get('hours_of_data',0):.1f}h")
        with c3: st.metric("Confiance", f"{ds.get('confidence_pct',0)}%")

        st.markdown("<div style='font-size:12px;color:#64748b;margin:8px 0'>"
                    f"{ds.get('message','')}</div>", unsafe_allow_html=True)

        st.divider()
        st.markdown("<div class='label' style='margin-bottom:12px'>"
                    "Rétention des données</div>", unsafe_allow_html=True)
        retention = st.slider("Jours de rétention", 7, 365, 30)
        if st.button("💾 METTRE À JOUR LA RÉTENTION"):
            res = api_put("/admin/system", {"retention_days": retention})
            st.success(f"Rétention → {retention}j ✅") \
                if res.get("status")=="updated" else st.error(str(res))

        st.divider()
        st.markdown("<div class='label' style='margin-bottom:12px'>"
                    "Seuils Anomalies</div>", unsafe_allow_html=True)
        a1, a2 = st.columns(2)
        with a1:
            soc_crit = st.number_input("SOC critique (%)", 5, 30, 15)
            temp_crit= st.number_input("Temp. critique (°C)", 40, 70, 55)
        with a2:
            soc_low  = st.number_input("SOC faible (%)", 10, 40, 25)
            temp_high= st.number_input("Temp. élevée (°C)", 35, 60, 45)

        if st.button("💾 SAUVEGARDER SEUILS ANOMALIES"):
            res = api_put("/admin/system", {"thresholds": {
                "bat_soc_critical":  soc_crit,
                "bat_soc_low":       soc_low,
                "bat_temp_critical": temp_crit,
                "bat_temp_high":     temp_high
            }})
            st.success("Seuils mis à jour ✅") \
                if res.get("status")=="updated" else st.error(str(res))

    # ── Simulation ─────────────────────────────────────────────
    with tab_sim:
        st.markdown("<div class='label' style='margin-bottom:12px'>"
                    "Simulation Horizon</div>", unsafe_allow_html=True)
        st.info("Lance la simulation heuristique sur N jours depuis les prédictions.")

        sim_days = st.slider("Jours", 1, 14, 7)
        if st.button("▶️ LANCER SIMULATION", use_container_width=True):
            import requests
            with st.spinner("Simulation en cours..."):
                try:
                    r = requests.post(f"http://localhost:8000/predict",
                                      params={"days":sim_days}, timeout=30)
                    sim = r.json()
                except Exception as e:
                    st.error(str(e)); return

            if sim.get("status") == "LEARNING":
                st.warning(sim.get("message","Données insuffisantes"))
                return

            daily = sim.get("daily_summary",{})
            if daily:
                import pandas as pd
                
                df = pd.DataFrame(list(daily.values()))
                st.success(f"Simulation OK | Autonomie moy.: "
                           f"{df['autonomy_pct'].mean():.1f}%")

                fig = go.Figure()
                fig.add_trace(go.Bar(x=df['date'],y=df['pv_kwh'],
                                     name="PV kWh",marker_color=ACCENT,opacity=0.85))
                fig.add_trace(go.Bar(x=df['date'],y=df['consumption_kwh'],
                                     name="Conso kWh",marker_color=ACCENT2,opacity=0.85))
                fig.update_layout(barmode="group",height=280,
                    plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,
                    font_color="#94a3b8",
                    xaxis=dict(gridcolor="#1e2a3a",zeroline=False),
                    yaxis=dict(gridcolor="#1e2a3a",zeroline=False),
                    margin=dict(l=40,r=20,t=20,b=30),
                    legend=dict(bgcolor="rgba(0,0,0,0)"))
                st.plotly_chart(fig, use_container_width=True)
