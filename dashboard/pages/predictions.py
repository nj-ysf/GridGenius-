#!/usr/bin/env python3
"""pages/predictions.py — Prédictions PV + Consommation GridGenius"""

import streamlit as st
import plotly.graph_objects as go
import pandas as pd

BG    = "#06090f"
SURF  = "#0b1120"
CARD  = "#0f1829"
BORD  = "#1c2d44"
AMBER = "#e8a020"
COBALT= "#2060d8"
SUCC  = "#22a86b"
WARN  = "#e8a020"
MUTED = "#4a6080"
TEXT2 = "#8ba0bc"


def render(api_get):
    st.markdown("""
    <div class='gg-page-title'>Prédictions IA</div>
    <div class='gg-page-sub'>XGBoost + Open-Meteo · Horizon 14 jours</div>
    """, unsafe_allow_html=True)

    c1, _ = st.columns([1, 3])
    with c1:
        days = st.slider("Horizon (jours)", 1, 14, 7)

    with st.spinner("Chargement des prédictions..."):
        preds = api_get("/predict", {"days": days}, timeout=20)

    if not preds:
        st.markdown("<div class='gg-alert-c' style='padding:14px'>API indisponible.</div>",
                    unsafe_allow_html=True)
        return

    # ── LEARNING mode ─────────────────────────────────────────
    if preds.get("status") == "LEARNING":
        hours = preds.get("hours_of_data", 0)
        pct   = min(100, hours / 48 * 100)
        st.markdown(f"""
        <div class='gg-learning' style='margin-bottom:24px'>
            <div style='font-family:JetBrains Mono,monospace;font-size:12px;
                        color:#e8a020;letter-spacing:2px;margin-bottom:8px'>
                PHASE D'APPRENTISSAGE
            </div>
            <div style='font-family:Outfit,sans-serif;font-size:13px;
                        color:#4a6080;margin-bottom:14px'>
                {preds.get('message', '')}
            </div>
            <div style='background:#1c2d44;border-radius:2px;height:4px;
                        max-width:320px;margin:0 auto;overflow:hidden'>
                <div style='height:100%;border-radius:2px;background:#e8a020;
                            width:{pct:.0f}%;transition:width 1s ease'></div>
            </div>
            <div style='font-family:JetBrains Mono,monospace;font-size:9px;
                        color:#4a6080;margin-top:8px;letter-spacing:1px'>
                {hours:.1f} h / 48 h collectées
            </div>
        </div>""", unsafe_allow_html=True)

        pv_pts = preds.get("pv", [])[:96]
        if pv_pts:
            ts = [p.get('timestamp', '')[11:16] for p in pv_pts]
            pv = [p.get('pv_corrected_kw', p.get('predicted_kw', 0)) for p in pv_pts]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ts, y=pv, name="PV Open-Meteo (kW)",
                line=dict(color=AMBER, width=1.5),
                fill='tozeroy', fillcolor='rgba(232,160,32,0.06)'
            ))
            fig.update_layout(
                height=260, plot_bgcolor=SURF, paper_bgcolor="rgba(0,0,0,0)",
                font_color=TEXT2, font_family="JetBrains Mono",
                xaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
                yaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
                margin=dict(l=40, r=20, t=16, b=30)
            )
            st.plotly_chart(fig, use_container_width=True)
        return

    # ── Status chip ───────────────────────────────────────────
    conf   = preds.get("confidence_pct", 100)
    status = preds.get("status", "OPERATIONAL")
    s_color = {"OPERATIONAL": SUCC, "PARTIAL": COBALT, "LEARNING": AMBER}.get(status, MUTED)

    st.markdown(f"""
    <div style='background:rgba(11,17,32,0.8);border:1px solid {s_color}30;
                border-radius:4px;padding:8px 14px;margin-bottom:20px;
                display:inline-flex;align-items:center;gap:10px'>
        <span class='gg-dot' style='background:{s_color};box-shadow:0 0 6px {s_color}'></span>
        <span style='font-family:JetBrains Mono,monospace;font-size:10px;
                     color:{s_color};letter-spacing:2px'>{status}</span>
        <span style='font-family:JetBrains Mono,monospace;font-size:10px;
                     color:{MUTED}'>·  {conf}% confiance</span>
    </div>
    """, unsafe_allow_html=True)

    daily  = preds.get("daily_summary", {})
    pv_pts = preds.get("pv", [])[:96]
    co_pts = preds.get("consumption", [])[:96]

    # ── KPIs ──────────────────────────────────────────────────
    if daily:
        df_d = pd.DataFrame(list(daily.values()))
        k1, k2, k3, k4 = st.columns(4)
        with k1: st.metric("Total PV",    f"{df_d['pv_kwh'].sum():.0f} kWh")
        with k2: st.metric("Total Conso", f"{df_d['consumption_kwh'].sum():.0f} kWh")
        with k3: st.metric("Autonomie",   f"{df_d['autonomy_pct'].mean():.1f}%")
        with k4:
            n = int(df_d['is_autonomous'].sum()) if 'is_autonomous' in df_d.columns else 0
            st.metric("Jours autonomes", f"{n}/{len(df_d)}")

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # Daily bar chart
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df_d['date'], y=df_d['pv_kwh'],
            name="PV (kWh)", marker_color=AMBER, opacity=0.85,
            marker=dict(line=dict(width=0))
        ))
        fig.add_trace(go.Bar(
            x=df_d['date'], y=df_d['consumption_kwh'],
            name="Conso (kWh)", marker_color=COBALT, opacity=0.85,
            marker=dict(line=dict(width=0))
        ))
        fig.add_trace(go.Scatter(
            x=df_d['date'], y=df_d['autonomy_pct'],
            name="Autonomie (%)", yaxis="y2",
            line=dict(color=SUCC, width=1.5, dash='dot'),
            mode="lines+markers",
            marker=dict(size=4, color=SUCC, symbol="diamond")
        ))
        fig.update_layout(
            barmode="group", height=320,
            plot_bgcolor=SURF, paper_bgcolor="rgba(0,0,0,0)",
            font_color=TEXT2, font_family="JetBrains Mono",
            xaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
            yaxis=dict(gridcolor=BORD, zeroline=False, tickfont=dict(size=9)),
            yaxis2=dict(
                overlaying="y", side="right", range=[0, 120],
                gridcolor=BORD, tickfont=dict(size=9)
            ),
            margin=dict(l=40, r=40, t=16, b=30),
            legend=dict(
                bgcolor="rgba(0,0,0,0)",
                font=dict(size=9, family="JetBrains Mono"),
                orientation="h", y=1.08
            ),
            hovermode="x unified",
            bargap=0.25, bargroupgap=0.08
        )
        st.plotly_chart(fig, use_container_width=True)

        # Table
        df_s = df_d[['date', 'pv_kwh', 'consumption_kwh', 'autonomy_pct',
                      'peak_pv_kw', 'peak_conso_kw']].copy()
        df_s.columns = ['Date', 'PV kWh', 'Conso kWh', 'Autonomie %',
                         'Pic PV kW', 'Pic Conso kW']
        # Avoid pandas Styler.background_gradient because it requires matplotlib.
        st.dataframe(
            df_s.style.format({c: '{:.1f}' for c in df_s.columns[1:]}),
            use_container_width=True,
            hide_index=True
        )

    # ── 24h intraday curves ───────────────────────────────────
    if pv_pts and co_pts:
        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
        st.markdown("<div class='gg-label' style='margin-bottom:10px'>◌  Courbes intra-jour (24h)</div>",
                    unsafe_allow_html=True)

        ts    = [p.get('timestamp', '')[11:16] for p in pv_pts]
        pv_v  = [p.get('pv_corrected_kw', p.get('predicted_kw', 0)) for p in pv_pts]
        co_v  = [p.get('predicted_kw', 0) for p in co_pts]
        co_lo = [p.get('ci_lower', max(0, p.get('predicted_kw', 0) - 2)) for p in co_pts]
        co_hi = [p.get('ci_upper', p.get('predicted_kw', 0) + 2) for p in co_pts]

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=ts + ts[::-1], y=co_hi + co_lo[::-1],
            fill='toself', fillcolor='rgba(32,96,216,0.06)',
            line=dict(color='rgba(0,0,0,0)'), name="IC Conso 95%",
            showlegend=True
        ))
        fig2.add_trace(go.Scatter(
            x=ts, y=pv_v, name="PV (kW)",
            line=dict(color=AMBER, width=2),
            fill='tozeroy', fillcolor='rgba(232,160,32,0.06)'
        ))
        fig2.add_trace(go.Scatter(
            x=ts, y=co_v, name="Conso (kW)",
            line=dict(color=COBALT, width=1.5, dash='dash')
        ))
        fig2.update_layout(
            height=300,
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
            hovermode="x unified"
        )
        st.plotly_chart(fig2, use_container_width=True)