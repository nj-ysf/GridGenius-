#!/usr/bin/env python3
"""pages/planification.py — Planification événements GridGenius"""

import streamlit as st
import os
from datetime import date, timedelta

API   = os.getenv("API_BASE_URL", "http://localhost:8000")
AMBER = "#e8a020"
COBALT= "#2060d8"
SUCC  = "#22a86b"
DANG  = "#c93030"
MUTED = "#4a6080"


def render(api_get, api_post, api_delete):
    st.markdown("""
    <div class='gg-page-title'>Planification</div>
    <div class='gg-page-sub'>Score = α·PV + β·SOC − γ·Grid − δ·Conflit</div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["RECOMMANDER UN CRÉNEAU", "ÉVÉNEMENTS PLANIFIÉS"])

    # ── Tab 1 ──────────────────────────────────────────────────
    with tab1:
        profiles   = api_get("/events/profiles").get("profiles", {})
        type_labels = {k: v['label'] for k, v in profiles.items()}

        c1, c2, c3 = st.columns(3)
        with c1:
            ev_type = st.selectbox("Type d'événement", list(type_labels.keys()),
                                    format_func=lambda x: type_labels.get(x, x))
        with c2:
            duration_h = st.number_input("Durée (h)", 0.5, 8.0, 2.0, 0.5)
        with c3:
            top_n = st.slider("Créneaux proposés", 1, 5, 3)

        custom_kw, custom_imp = None, None
        if ev_type == "autre":
            cc1, cc2 = st.columns(2)
            with cc1: custom_kw  = st.number_input("Consommation (kW)", 0.5, 50.0, 5.0)
            with cc2: custom_imp = st.slider("Importance (%)", 0, 100, 50)

        c4, c5 = st.columns(2)
        with c4: date_from = st.date_input("Du", date.today())
        with c5: date_to   = st.date_input("Au", date.today() + timedelta(days=7))

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        if st.button("ANALYSER LES CRÉNEAUX", use_container_width=True):
            payload = {
                "event_type": ev_type, "duration_h": duration_h,
                "date_from": str(date_from), "date_to": str(date_to),
                "top_n": top_n
            }
            if custom_kw:  payload["custom_kw"]        = custom_kw
            if custom_imp: payload["custom_importance"] = custom_imp

            with st.spinner("Analyse heuristique en cours..."):
                result = api_post("/recommend", payload)

            if result.get("error"):
                st.markdown(f"<div class='gg-alert-c'>{result['error']}</div>",
                            unsafe_allow_html=True); return

            if result.get("status") == "LEARNING":
                st.markdown(f"""
                <div class='gg-learning'>
                    <div style='font-family:JetBrains Mono,monospace;font-size:10px;
                                color:#e8a020;letter-spacing:2px'>DONNÉES INSUFFISANTES</div>
                    <div style='font-size:12px;color:#4a6080;margin-top:6px'>
                        {result.get('message','Collecte en cours...')}
                    </div>
                </div>""", unsafe_allow_html=True); return

            slots    = result.get("top_slots", [])
            cfg      = result.get("scoring_config", {})
            warnings = result.get("warnings", [])

            # Scoring recap
            st.markdown(f"""
            <div class='gg-formula'>
                α={cfg.get('alpha',0.4):.2f}·PV &nbsp;+&nbsp;
                β={cfg.get('beta',0.35):.2f}·SOC &nbsp;−&nbsp;
                γ={cfg.get('gamma',0.5):.2f}·Grid &nbsp;−&nbsp;
                δ={cfg.get('delta',0.3):.2f}·Conflit
                &nbsp;&nbsp;|&nbsp;&nbsp;
                {result.get('n_candidates',0)} candidats évalués
            </div>""", unsafe_allow_html=True)

            for w in warnings:
                st.markdown(f"<div class='gg-alert-w'>{w}</div>", unsafe_allow_html=True)

            if not slots:
                st.markdown("<div class='gg-alert-c'>Aucun créneau disponible.</div>",
                            unsafe_allow_html=True); return

            st.markdown(f"<div class='gg-label' style='margin:16px 0 10px'>"
                        f"◈  {len(slots)} CRÉNEAUX RECOMMANDÉS</div>",
                        unsafe_allow_html=True)

            medals = ["01", "02", "03", "04", "05"]
            for i, slot in enumerate(slots):
                feas   = slot.get('feasible', False)
                feas_c = SUCC if feas else AMBER
                feas_t = "Faisable" if feas else "Partiel — réseau ONEE"
                slot_class = "gg-slot gg-slot-best" if i == 0 else "gg-slot"

                conf_str = ""
                if slot.get('conflicts_with'):
                    names = [c['event_name'] for c in slot['conflicts_with'][:2]]
                    conf_str = (f"<div style='font-family:JetBrains Mono,monospace;"
                                f"font-size:9px;color:{AMBER};margin-top:8px;letter-spacing:1px'>"
                                f"△ CONFLIT : {', '.join(names)}</div>")

                st.markdown(f"""
                <div class='{slot_class}'>
                    <div style='display:flex;justify-content:space-between;align-items:center'>
                        <span style='font-family:JetBrains Mono,monospace;font-size:9px;
                                     color:{MUTED};letter-spacing:2px'>#{medals[i]}</span>
                        <span style='font-family:JetBrains Mono,monospace;font-size:13px;
                                     color:#d8e4f0;font-weight:500'>
                            {slot['date']} &nbsp;·&nbsp; {slot['start']} → {slot['end']}
                        </span>
                        <div style='text-align:right'>
                            <span style='font-family:JetBrains Mono,monospace;font-size:18px;
                                         color:{AMBER};font-weight:700'>{slot['score']:.4f}</span>
                            <div style='font-family:JetBrains Mono,monospace;font-size:9px;
                                        color:{feas_c};letter-spacing:1px;margin-top:2px'>
                                {feas_t.upper()}
                            </div>
                        </div>
                    </div>
                    <div style='display:flex;gap:20px;margin-top:12px;
                                font-family:JetBrains Mono,monospace;font-size:10px'>
                        <span style='color:{MUTED}'>PV <strong style='color:{AMBER}'>{slot['pv_norm']:.2f}</strong></span>
                        <span style='color:{MUTED}'>SOC <strong style='color:{COBALT}'>{slot['soc_proj']:.2f}</strong></span>
                        <span style='color:{MUTED}'>Grid <strong style='color:{DANG}'>{slot['grid_dep']:.2f}</strong></span>
                        <span style='color:{MUTED}'>Couv. <strong style='color:{AMBER}'>{slot['coverage_pct']:.1f}%</strong></span>
                    </div>
                    {conf_str}
                </div>""", unsafe_allow_html=True)

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            best = slots[0]
            cn, cb2 = st.columns([2, 1])
            with cn:
                ev_name = st.text_input("Nom de l'événement",
                                         value=result.get("event_label", ""))
            with cb2:
                st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
                if st.button("✓ PLANIFIER LE MEILLEUR CRÉNEAU"):
                    add_payload = {
                        "name": ev_name, "type": ev_type,
                        "date": best['date'], "start": best['start'], "end": best['end'],
                        "importance_pct": custom_imp or profiles.get(ev_type, {}).get('importance_pct', 75)
                    }
                    if custom_kw: add_payload["expected_kw"] = custom_kw
                    res = api_post("/events/add", add_payload)
                    if res.get("status") == "added":
                        st.markdown(f"<div class='gg-alert-ok'>✓ Événement planifié : {ev_name}</div>",
                                    unsafe_allow_html=True)
                        pc = res.get("precharge", {})
                        if pc.get("needed"):
                            st.markdown(f"""
                            <div class='gg-info'>
                                ◉ Pré-charge — Démarrage : {pc.get('start_precharge_at')} &nbsp;|&nbsp;
                                SOC cible : {pc.get('soc_target_pct')}% &nbsp;|&nbsp;
                                Réseau : {pc.get('e_grid_kwh',0):.1f} kWh
                            </div>""", unsafe_allow_html=True)
                        if res.get("resolution"):
                            st.markdown(f"<div class='gg-alert-w'>{res['resolution'].get('fallback_message','')}</div>",
                                        unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div class='gg-alert-c'>{str(res)}</div>",
                                    unsafe_allow_html=True)

    # ── Tab 2 ──────────────────────────────────────────────────
    with tab2:
        st.markdown("<div class='gg-label' style='margin-bottom:14px'>▣  Événements Planifiés</div>",
                    unsafe_allow_html=True)

        events_data = api_get("/events")
        events = events_data.get("events", [])

        if not events:
            st.markdown("<div class='gg-info'>Aucun événement planifié.</div>",
                        unsafe_allow_html=True)
            return

        status_colors = {
            "planned":               SUCC,
            "planned_with_conflict": AMBER,
            "active":                COBALT,
            "completed":             MUTED
        }

        for ev in sorted(events, key=lambda e: f"{e['date']} {e['start']}"):
            status = ev.get("status", "")
            s_color = status_colors.get(status, MUTED)
            imp = ev.get("importance_pct", 50)

            with st.expander(
                f"▸  {ev['date']}  {ev['start']}–{ev['end']}  ·  "
                f"{ev['name']}  ({ev.get('expected_kw',0)}kW · {imp}%)"
            ):
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown(f"<div class='gg-label'>Type</div>"
                                f"<div style='font-size:13px;color:#d8e4f0;margin-bottom:8px'>"
                                f"{ev.get('label','')}</div>", unsafe_allow_html=True)
                    st.markdown(
                        f"<div class='gg-label'>Statut</div>"
                        f"<div style='font-family:JetBrains Mono,monospace;font-size:11px;"
                        f"color:{s_color};letter-spacing:1px'>{status.upper()}</div>",
                        unsafe_allow_html=True)
                with c2:
                    st.markdown(f"<div class='gg-label'>Importance</div>"
                                f"<div style='font-family:JetBrains Mono,monospace;font-size:18px;"
                                f"color:#d8e4f0'>{imp}%</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='gg-label' style='margin-top:8px'>Durée</div>"
                                f"<div style='font-family:JetBrains Mono,monospace;font-size:16px;"
                                f"color:#d8e4f0'>{ev.get('duration_h',0):.1f} h</div>",
                                unsafe_allow_html=True)
                with c3:
                    if st.button("Supprimer", key=f"del_{ev['id']}"):
                        r = api_delete(f"/events/{ev['id']}")
                        if r.get("status") == "deleted":
                            st.success("Supprimé")
                            st.rerun()
                    st.markdown(
                        f"<div style='margin-top:8px'><a href='{API}/report/{ev['id']}' "
                        f"style='font-family:JetBrains Mono,monospace;font-size:10px;"
                        f"color:{MUTED};letter-spacing:1px;text-decoration:none'>"
                        f"↓ RAPPORT PDF</a></div>",
                        unsafe_allow_html=True)