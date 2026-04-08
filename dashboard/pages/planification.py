#!/usr/bin/env python3
"""pages/planification.py — Planification événements GridGenius"""

import streamlit as st
from datetime import date, timedelta

API = "http://localhost:8000"


def render(api_get, api_post, api_delete):
    st.markdown("""
    <div style='font-family:Space Mono;font-size:20px;font-weight:700;
                color:#e2e8f0;margin-bottom:2px'>PLANIFICATION ÉVÉNEMENTS</div>
    <div style='font-family:Space Mono;font-size:9px;color:#64748b;
                letter-spacing:3px;margin-bottom:20px'>
        Score = α·PV + β·SOC - γ·Grid - δ·Conflit
    </div>""", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["RECOMMANDER UN CRÉNEAU", "ÉVÉNEMENTS PLANIFIÉS"])

    # ── Tab 1 : Recommandation ─────────────────────────────────
    with tab1:
        st.markdown("<div class='label' style='margin-bottom:12px'>"
                    "Paramètres</div>", unsafe_allow_html=True)

        profiles = api_get("/events/profiles").get("profiles", {})
        type_labels = {k: v['label'] for k, v in profiles.items()}

        c1, c2, c3 = st.columns(3)
        with c1:
            ev_type = st.selectbox("Type", list(type_labels.keys()),
                                    format_func=lambda x: type_labels.get(x, x))
        with c2:
            duration_h = st.number_input("Durée (h)", 0.5, 8.0, 2.0, 0.5)
        with c3:
            top_n = st.slider("Créneaux à proposer", 1, 5, 3)

        custom_kw, custom_imp = None, None
        if ev_type == "autre":
            cc1, cc2 = st.columns(2)
            with cc1:
                custom_kw  = st.number_input("Consommation (kW)", 0.5, 50.0, 5.0)
            with cc2:
                custom_imp = st.slider("Importance (%)", 0, 100, 50)

        c4, c5 = st.columns(2)
        with c4:
            date_from = st.date_input("Du", date.today())
        with c5:
            date_to   = st.date_input("Au", date.today()+timedelta(days=7))

        if st.button("RECHERCHER LES MEILLEURS CRÉNEAUX", use_container_width=True):
            payload = {"event_type":ev_type, "duration_h":duration_h,
                       "date_from":str(date_from), "date_to":str(date_to),
                       "top_n":top_n}
            if custom_kw:  payload["custom_kw"]         = custom_kw
            if custom_imp: payload["custom_importance"]  = custom_imp

            with st.spinner("Analyse en cours..."):
                result = api_post("/recommend", payload)

            if result.get("error"):
                st.error(result["error"])
                return

            # Statut LEARNING
            if result.get("status") == "LEARNING":
                st.warning(f"📚 {result.get('message','Données insuffisantes')}")
                return

            slots    = result.get("top_slots", [])
            cfg      = result.get("scoring_config", {})
            warnings = result.get("warnings", [])

            # Info scoring
            st.markdown(f"""
            <div style='font-family:Space Mono;font-size:10px;color:#64748b;
                        background:#111827;border:1px solid #1e2a3a;
                        border-radius:8px;padding:10px;margin:12px 0'>
                α={cfg.get('alpha',0.4):.2f}·PV +
                β={cfg.get('beta',0.35):.2f}·SOC -
                γ={cfg.get('gamma',0.5):.2f}·Grid -
                δ={cfg.get('delta',0.3):.2f}·Conflit &nbsp;|&nbsp;
                {result.get('n_candidates',0)} candidats évalués
            </div>""", unsafe_allow_html=True)

            for w in warnings:
                st.warning(w)

            if not slots:
                st.error("Aucun créneau trouvé.")
                return

            st.markdown("<div class='label' style='margin-bottom:10px'>"
                        f"Top {len(slots)} Créneaux</div>", unsafe_allow_html=True)

            medals = ["🥇","🥈","🥉","4️⃣","5️⃣"]
            for i, slot in enumerate(slots):
                feas   = slot.get('feasible', False)
                feas_c = "#34d399" if feas else "#f59e0b"
                feas_t = "✅ Faisable" if feas else "⚠️ Partiel (réseau ONEE)"
                border = "border-color:#00d4aa;" if i==0 else ""
                conf_str = ""
                if slot.get('conflicts_with'):
                    names = [c['event_name'] for c in slot['conflicts_with'][:2]]
                    conf_str = f"<div style='font-size:10px;color:#f59e0b;margin-top:4px'>⚠️ Conflit avec : {', '.join(names)}</div>"

                st.markdown(f"""
                <div class='card' style='{border}'>
                    <div style='display:flex;justify-content:space-between;
                                align-items:center;margin-bottom:8px'>
                        <span style='font-size:16px'>{medals[i]}</span>
                        <span style='font-family:Space Mono;font-size:13px;
                                     color:#e2e8f0;font-weight:700'>
                            {slot['date']} — {slot['start']} → {slot['end']}
                        </span>
                        <span>
                            <span style='font-family:Space Mono;font-size:16px;
                                         color:#00d4aa'>{slot['score']:.4f}</span>
                            &nbsp;
                            <span style='font-size:11px;color:{feas_c}'>{feas_t}</span>
                        </span>
                    </div>
                    <div style='display:flex;gap:16px;font-size:11px;color:#64748b;
                                flex-wrap:wrap'>
                        <span>☀️ PV: <strong style='color:#00d4aa'>{slot['pv_norm']:.2f}</strong></span>
                        <span>🔋 SOC: <strong style='color:#3b82f6'>{slot['soc_proj']:.2f}</strong></span>
                        <span>🔌 Grid: <strong style='color:#ef4444'>{slot['grid_dep']:.2f}</strong></span>
                        <span>📊 Couv.: <strong style='color:#fbbf24'>{slot['coverage_pct']:.1f}%</strong></span>
                    </div>
                    {conf_str}
                </div>""", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            best = slots[0]
            cn, cb2 = st.columns([2,1])
            with cn:
                ev_name = st.text_input("Nom de l'événement",
                                         value=result.get("event_label",""))
            with cb2:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("✅ PLANIFIER LE MEILLEUR CRÉNEAU"):
                    add_payload = {
                        "name":           ev_name,
                        "type":           ev_type,
                        "date":           best['date'],
                        "start":          best['start'],
                        "end":            best['end'],
                        "importance_pct": custom_imp or profiles.get(ev_type,{}).get('importance_pct',75)
                    }
                    if custom_kw: add_payload["expected_kw"] = custom_kw
                    res = api_post("/events/add", add_payload)
                    if res.get("status") == "added":
                        st.success(f"✅ Événement planifié : {ev_name}")
                        pc = res.get("precharge",{})
                        if pc.get("needed"):
                            st.info(f"🔋 Pré-charge : démarrer à {pc.get('start_precharge_at')} "
                                    f"| SOC cible : {pc.get('soc_target_pct')}% "
                                    f"| Réseau : {pc.get('e_grid_kwh',0):.1f} kWh")
                        if res.get("resolution"):
                            st.warning(res["resolution"].get("fallback_message",""))
                    else:
                        st.error(str(res))

    # ── Tab 2 : Événements planifiés ───────────────────────────
    with tab2:
        st.markdown("<div class='label' style='margin-bottom:12px'>"
                    "Événements Planifiés</div>", unsafe_allow_html=True)

        events_data = api_get("/events")
        events = events_data.get("events", [])

        if not events:
            st.info("Aucun événement planifié.")
            return

        for ev in sorted(events, key=lambda e: f"{e['date']} {e['start']}"):
            status = ev.get("status","")
            s_color = {"planned":"#34d399","planned_with_conflict":"#f59e0b",
                       "active":"#3b82f6","completed":"#64748b"}.get(status,"#94a3b8")
            imp = ev.get("importance_pct",50)

            with st.expander(
                f"📅 {ev['date']} {ev['start']}-{ev['end']} — "
                f"{ev['name']} ({ev.get('expected_kw',0)}kW | {imp}%)"
            ):
                c1,c2,c3 = st.columns(3)
                with c1:
                    st.markdown(f"**Type :** {ev.get('label','')}")
                    st.markdown(
                        f"**Statut :** <span style='color:{s_color}'>{status}</span>",
                        unsafe_allow_html=True)
                with c2:
                    st.markdown(f"**Importance :** {imp}%")
                    st.markdown(f"**Durée :** {ev.get('duration_h',0):.1f}h")
                with c3:
                    if st.button("🗑️ Supprimer", key=f"del_{ev['id']}"):
                        r = api_delete(f"/events/{ev['id']}")
                        if r.get("status") == "deleted":
                            st.success("Supprimé")
                            st.rerun()
                    st.markdown(
                        f"[📄 Rapport PDF]({API}/report/{ev['id']})",
                        unsafe_allow_html=True)
