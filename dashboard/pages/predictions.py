#!/usr/bin/env python3
"""pages/predictions.py — Prédictions PV + Consommation GridGenius"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

PLOT_BG = "#111827"
ACCENT  = "#00d4aa"
ACCENT2 = "#3b82f6"
WARNING = "#f59e0b"


def render(api_get):
    st.markdown("""
    <div style='font-family:Space Mono;font-size:20px;font-weight:700;
                color:#e2e8f0;margin-bottom:2px'>PRÉDICTIONS IA</div>
    <div style='font-family:Space Mono;font-size:9px;color:#64748b;
                letter-spacing:3px;margin-bottom:20px'>
        XGBoost + Open-Meteo | Horizon 14 jours
    </div>""", unsafe_allow_html=True)

    c1, _ = st.columns([1,3])
    with c1:
        days = st.slider("Horizon (jours)", 1, 14, 7)

    with st.spinner("Chargement..."):
        preds = api_get("/predict", {"days": days}, timeout=20)

    if not preds:
        st.error("API indisponible.")
        return

    # LEARNING
    if preds.get("status") == "LEARNING":
        hours = preds.get("hours_of_data", 0)
        st.markdown(f"""
        <div class='learning-banner'>
            <div style='font-family:Space Mono;font-size:14px;color:#f59e0b;margin-bottom:8px'>
                PHASE D APPRENTISSAGE</div>
            <div style='font-size:13px;color:#94a3b8'>{preds.get('message','')}</div>
            <div style='margin-top:12px'>
                <div style='background:#1e2a3a;border-radius:6px;height:8px;
                            overflow:hidden;max-width:400px;margin:0 auto'>
                    <div style='height:100%;border-radius:6px;background:#f59e0b;
                                width:{min(100,hours/48*100):.0f}%'></div>
                </div>
                <div style='font-size:11px;color:#64748b;margin-top:6px'>
                    {hours:.1f}h / 48h collectees
                </div>
            </div>
        </div>""", unsafe_allow_html=True)
        pv_pts = preds.get("pv", [])[:96]
        if pv_pts:
            ts  = [p.get('timestamp','')[11:16] for p in pv_pts]
            pv  = [p.get('pv_corrected_kw', p.get('predicted_kw',0)) for p in pv_pts]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ts, y=pv, name="PV Open-Meteo (kW)",
                line=dict(color=ACCENT,width=2),
                fill='tozeroy', fillcolor='rgba(0,212,170,0.07)'))
            fig.update_layout(height=280, plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
                font_color="#94a3b8",
                xaxis=dict(gridcolor="#1e2a3a",zeroline=False),
                yaxis=dict(gridcolor="#1e2a3a",zeroline=False),
                margin=dict(l=40,r=20,t=20,b=30))
            st.plotly_chart(fig, use_container_width=True)
        return

    # PARTIAL / OPERATIONAL
    conf   = preds.get("confidence_pct", 100)
    status = preds.get("status","OPERATIONAL")
    c_col  = "#00d4aa" if status=="OPERATIONAL" else "#3b82f6"
    st.markdown(f"""
    <div style='background:#111827;border:1px solid {c_col};border-radius:8px;
                padding:10px;margin-bottom:16px;font-family:Space Mono;
                font-size:10px;color:{c_col}'>
        {status} — Confiance : {conf}%
    </div>""", unsafe_allow_html=True)

    daily   = preds.get("daily_summary",{})
    pv_pts  = preds.get("pv",[])[:96]
    co_pts  = preds.get("consumption",[])[:96]

    if daily:
        df_d = pd.DataFrame(list(daily.values()))
        k1,k2,k3,k4 = st.columns(4)
        with k1: st.metric("Total PV",    f"{df_d['pv_kwh'].sum():.0f} kWh")
        with k2: st.metric("Total Conso", f"{df_d['consumption_kwh'].sum():.0f} kWh")
        with k3: st.metric("Autonomie",   f"{df_d['autonomy_pct'].mean():.1f}%")
        with k4:
            n = int(df_d['is_autonomous'].sum()) if 'is_autonomous' in df_d.columns else 0
            st.metric("Jours autonomes", f"{n}/{len(df_d)}")

        st.markdown("<br>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=df_d['date'], y=df_d['pv_kwh'],
                             name="PV (kWh)", marker_color=ACCENT, opacity=0.85))
        fig.add_trace(go.Bar(x=df_d['date'], y=df_d['consumption_kwh'],
                             name="Conso (kWh)", marker_color=ACCENT2, opacity=0.85))
        fig.add_trace(go.Scatter(x=df_d['date'], y=df_d['autonomy_pct'],
                                  name="Autonomie (%)", yaxis="y2",
                                  line=dict(color=WARNING,width=2,dash='dot'),
                                  mode="lines+markers", marker=dict(size=5)))
        fig.update_layout(barmode="group", height=340,
            plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color="#94a3b8",
            xaxis=dict(gridcolor="#1e2a3a",zeroline=False),
            yaxis=dict(gridcolor="#1e2a3a",zeroline=False),
            yaxis2=dict(overlaying="y",side="right",range=[0,120],
                        gridcolor="#1e2a3a"),
            margin=dict(l=40,r=40,t=20,b=30),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)

        df_s = df_d[['date','pv_kwh','consumption_kwh','autonomy_pct',
                      'peak_pv_kw','peak_conso_kw']].copy()
        df_s.columns = ['Date','PV kWh','Conso kWh','Autonomie %',
                         'Pic PV kW','Pic Conso kW']
        st.dataframe(df_s.style.format({c:'{:.1f}' for c in df_s.columns[1:]})
                     .background_gradient(subset=['Autonomie %'],cmap='RdYlGn'),
                     use_container_width=True, hide_index=True)

    if pv_pts and co_pts:
        st.markdown("<br>", unsafe_allow_html=True)
        ts    = [p.get('timestamp','')[11:16] for p in pv_pts]
        pv_v  = [p.get('pv_corrected_kw', p.get('predicted_kw',0)) for p in pv_pts]
        co_v  = [p.get('predicted_kw',0) for p in co_pts]
        co_lo = [p.get('ci_lower', max(0,p.get('predicted_kw',0)-2)) for p in co_pts]
        co_hi = [p.get('ci_upper', p.get('predicted_kw',0)+2) for p in co_pts]

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=ts+ts[::-1], y=co_hi+co_lo[::-1],
            fill='toself', fillcolor='rgba(59,130,246,0.07)',
            line=dict(color='rgba(0,0,0,0)'), name="IC Conso 95%"))
        fig2.add_trace(go.Scatter(x=ts, y=pv_v, name="PV (kW)",
            line=dict(color=ACCENT,width=2),
            fill='tozeroy', fillcolor='rgba(0,212,170,0.07)'))
        fig2.add_trace(go.Scatter(x=ts, y=co_v, name="Conso (kW)",
            line=dict(color=ACCENT2,width=2,dash='dash')))
        fig2.update_layout(height=320, plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG,
            font_color="#94a3b8",
            xaxis=dict(gridcolor="#1e2a3a",zeroline=False),
            yaxis=dict(gridcolor="#1e2a3a",zeroline=False),
            margin=dict(l=40,r=20,t=20,b=30),
            legend=dict(bgcolor="rgba(0,0,0,0)"),
            hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)
