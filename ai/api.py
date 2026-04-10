#!/usr/bin/env python3
"""
api.py — FastAPI GridGenius (GIEW 2026 — ENSET Mohammedia)
  Stateless : lit depuis InfluxDB, pas de state en mémoire.
  Port 8000 | uvicorn api:app --host 0.0.0.0 --port 8000

  Endpoints :
    POST /decide          → décision IA temps réel (Node-RED 10s)
    GET  /predict         → prédictions 14j (Node-RED 30min)
    POST /recommend       → recommandation créneaux (Streamlit)
    GET  /status          → état courant (Streamlit 2s)
    GET  /report/{id}     → rapport PDF (Streamlit)
    PUT  /admin/*         → config admin (Streamlit)
    GET  /health          → santé API + InfluxDB
"""

import logging, asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from influx_client import db
from predict       import engine as pred_engine, DELTA_T_H
from battery_model import battery
from smart_engine  import engine as smart_engine, PREDEFINED
from anomaly       import run_anomaly_detection, save_thresholds

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [api] %(levelname)s: %(message)s')


# ── Pydantic Models ────────────────────────────────────────────
class MPPTData(BaseModel):
    pv_power:float=0.0; pv_voltage:float=0.0; pv_current:float=0.0
    bat_soc:float=50.0; bat_voltage:float=51.2; bat_current:float=0.0
    bat_temp:float=25.0; load_power:float=0.0

class DecideRequest(BaseModel):
    mppt: MPPTData

class EventRequest(BaseModel):
    name:str; type:str; date:str; start:str; end:str
    expected_kw:Optional[float]=None; importance_pct:Optional[int]=None

class RecommendRequest(BaseModel):
    event_type:str; duration_h:float; date_from:str; date_to:str
    custom_kw:Optional[float]=None; custom_importance:Optional[int]=None
    top_n:int=3; current_soc:Optional[float]=None

class AdminScoringRequest(BaseModel):
    alpha:Optional[float]=None; beta:Optional[float]=None
    gamma:Optional[float]=None; delta:Optional[float]=None
    coverage_min_pct:Optional[float]=None
    soc_precharge:Optional[float]=None
    cost_grid_kwh:Optional[float]=None

class AdminBatteryRequest(BaseModel):
    capacity_kwh:Optional[float]=None; soc_min:Optional[float]=None
    soc_max:Optional[float]=None; eta_charge:Optional[float]=None
    eta_discharge:Optional[float]=None; p_max_charge_kw:Optional[float]=None
    p_max_discharge_kw:Optional[float]=None; p_losses_kw:Optional[float]=None

class AdminSystemRequest(BaseModel):
    retention_days:Optional[int]=None
    thresholds:Optional[dict]=None


# ── App ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.setup()
    log.info("🚀 GridGenius API — port 8000")
    asyncio.create_task(_retrain_loop())
    yield

app = FastAPI(
    title="GridGenius API",
    description="Micro-Réseau Intelligent — EHTP GIEW 2026",
    version="3.0.0",
    lifespan=lifespan
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# ── Santé ──────────────────────────────────────────────────────
@app.get("/health", tags=["Santé"])
async def health():
    influx_ok  = db.ping()
    data_status= db.get_data_status()
    return {
        "api":          "online",
        "influxdb":     "connected" if influx_ok else "disconnected",
        "data_status":  data_status,
        "events":       len(smart_engine.events),
        "timestamp":    datetime.now().isoformat()
    }


# ── 1. DÉCISION TEMPS RÉEL ─────────────────────────────────────
@app.post("/decide", tags=["Temps réel"])
async def api_decide(req: DecideRequest):
    """
    Décision IA temps réel — appelé par Node-RED toutes les 10s.
    Lit prédictions depuis InfluxDB.
    Écrit décision + état batterie dans InfluxDB.
    """
    try:
        mppt = req.mppt.model_dump()

        # Mise à jour modèle batterie
        battery.update_from_mppt(mppt)

        # Écrire données MPPT dans InfluxDB
        db.write_mppt(mppt)

        # Lire dernière prédiction PV depuis InfluxDB
        pv_preds = db.get_last_predictions("pv", hours_ahead=2)
        pv_next  = float(pv_preds[0].get('predicted_kw', mppt['pv_power'])) \
                   if pv_preds else None

        # Événements à venir
        upcoming = smart_engine.get_upcoming_events(2)

        # Décision IA
        dec = smart_engine.decide(
            p_pv            = float(mppt['pv_power']),
            p_load          = float(mppt['load_power']),
            soc             = battery.soc,
            pv_predicted    = pv_next,
            upcoming_events = [e.to_dict() for e in upcoming],
            hour            = datetime.now().hour
        )

        # Détection anomalies
        events_now = smart_engine.get_current_events()
        anom = run_anomaly_detection({
            **mppt,
            "expected_load": events_now.get("total_expected_kw", 0)
        }, write_to_influx=True)

        if anom['alerts']:
            dec['alerts'] = anom['alerts']

        # Écrire décision + état batterie dans InfluxDB
        db.write_decision(dec)
        db.write_battery_state({
            "soc":           battery.soc_pct,
            "voltage":       battery.voltage,
            "mode":          battery.mode,
            "cycles_equiv":  battery.cycles_equiv,
            "available_kwh": battery.available_kwh
        })

        return dec

    except Exception as e:
        log.error(f"/decide : {e}")
        # Retourner SAFE_MODE si erreur
        return smart_engine.safe_mode_decision()


# ── 2. PRÉDICTIONS ────────────────────────────────────────────
@app.get("/predict", tags=["Prédictions"])
async def api_predict(days: int = Query(14, ge=1, le=30)):
    """
    Prédictions PV + consommation sur N jours.
    Appelé par Node-RED toutes les 30min.
    Écrit résultats dans InfluxDB.
    Retourne statut LEARNING si données insuffisantes.
    """
    try:
        events = [e.to_dict() for e in smart_engine.events
                  if e.status in ("planned","planned_with_conflict")]
        return pred_engine.predict(db, days=days, events=events)
    except Exception as e:
        log.error(f"/predict : {e}")
        raise HTTPException(500, str(e))


# ── 3. RECOMMANDATION CRÉNEAUX ─────────────────────────────────
@app.post("/recommend", tags=["Planification"])
async def api_recommend(req: RecommendRequest):
    """
    Top-N créneaux optimaux pour un événement.
    Score = α·PV + β·SOC - γ·grid - δ·conflit
    """
    try:
        return smart_engine.recommend_slots(
            db            = db,
            event_type    = req.event_type,
            duration_h    = req.duration_h,
            date_from     = req.date_from,
            date_to       = req.date_to,
            custom_kw     = req.custom_kw,
            custom_importance = req.custom_importance,
            top_n         = req.top_n,
            current_soc   = req.current_soc or battery.soc
        )
    except Exception as e:
        log.error(f"/recommend : {e}")
        raise HTTPException(500, str(e))


# ── 4. ÉTAT COURANT ────────────────────────────────────────────
@app.get("/status", tags=["Dashboard"])
async def api_status():
    """
    État synthétique — appelé par Streamlit toutes les 2s.
    Lit depuis InfluxDB uniquement.
    """
    last_mppt = db.get_last_mppt() or {}
    last_dec  = db.get_last_decision() or {}
    events    = smart_engine.get_current_events()
    data_st   = db.get_data_status()
    energy    = db.get_energy_today()
    alerts    = db.get_alerts(hours=1)

    return {
        # MPPT temps réel
        "pv_power":       float(last_mppt.get("pv_power",   0)),
        "bat_soc":        float(last_mppt.get("bat_soc",    50)),
        "bat_temp":       float(last_mppt.get("bat_temp",   25)),
        "load_power":     float(last_mppt.get("load_power",  0)),
        "bat_voltage":    float(last_mppt.get("bat_voltage",51.2)),
        "charge_mode":    str(last_mppt.get("charge_mode", "unknown")),
        # Décision IA
        "active_mode":    str(last_dec.get("decision",  "unknown")),
        "bat_action":     str(last_dec.get("action",    "idle")),
        "ai_reason":      str(last_dec.get("reason",    "-")),
        "safe_mode":      last_dec.get("mode","normal") == "SAFE_MODE",
        # Événements
        "active_events":  events.get("event_count", 0),
        "total_event_kw": events.get("total_expected_kw", 0),
        # Énergie du jour
        "e_pv_today":     energy["e_pv_kwh"],
        "e_load_today":   energy["e_load_kwh"],
        "autonomy_today": db.get_autonomy_today(),
        # Système
        "data_status":    data_st["status"],
        "confidence_pct": data_st["confidence_pct"],
        "n_alerts":       len(alerts),
        "has_critical":   any(a.get("severity")=="critical" for a in alerts),
        "timestamp":      datetime.now().isoformat()
    }


# ── ÉVÉNEMENTS ─────────────────────────────────────────────────
@app.get("/events", tags=["Planification"])
async def api_events():
    return {"events":[e.to_dict() for e in smart_engine.events],
            "count":len(smart_engine.events)}

@app.get("/events/current", tags=["Planification"])
async def api_events_current():
    return smart_engine.get_current_events()

@app.get("/events/upcoming", tags=["Planification"])
async def api_events_upcoming(hours: int = Query(24, ge=1, le=168)):
    return {"events":[e.to_dict() for e in smart_engine.get_upcoming_events(hours)]}

@app.post("/events/add", tags=["Planification"])
async def api_events_add(event: EventRequest):
    try:
        return smart_engine.add_event(event.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))

@app.delete("/events/{event_id}", tags=["Planification"])
async def api_events_delete(event_id: str):
    if not smart_engine.delete_event(event_id):
        raise HTTPException(404, f"Événement {event_id} non trouvé")
    return {"status":"deleted","id":event_id}

@app.get("/events/profiles", tags=["Planification"])
async def api_events_profiles():
    return {"profiles": PREDEFINED}


# ── DONNÉES DASHBOARD ──────────────────────────────────────────
@app.get("/data/history", tags=["Dashboard"])
async def api_history(hours: int = Query(24, ge=1, le=336)):
    """Historique MPPT + décisions pour graphiques Streamlit"""
    return {
        "mppt":      db.get_mppt_history(hours),
        "decisions": db.get_decision_history(hours),
        "battery":   db.get_battery_history(hours)
    }

@app.get("/data/daily", tags=["Dashboard"])
async def api_daily(days: int = Query(14, ge=1, le=30)):
    return {"stats": db.get_daily_stats(days)}

@app.get("/data/alerts", tags=["Dashboard"])
async def api_alerts(hours: int = Query(24, ge=1, le=168)):
    return {"alerts": db.get_alerts(hours)}


# ── ADMIN ───────────────────────────────────────────────────────
@app.get("/admin/config", tags=["Admin"])
async def api_admin_config():
    return {
        "scoring":    smart_engine.cfg.to_dict(),
        "battery":    battery.cfg.to_dict(),
        "data_status":db.get_data_status()
    }

@app.put("/admin/scoring", tags=["Admin"])
async def api_admin_scoring(req: AdminScoringRequest):
    smart_engine.update_config(
        {k:v for k,v in req.model_dump().items() if v is not None})
    return {"status":"updated","scoring":smart_engine.cfg.to_dict()}

@app.put("/admin/battery", tags=["Admin"])
async def api_admin_battery(req: AdminBatteryRequest):
    for k, v in req.model_dump().items():
        if v is not None and hasattr(battery.cfg, k):
            setattr(battery.cfg, k, v)
    return {"status":"updated","battery":battery.cfg.to_dict()}

@app.put("/admin/system", tags=["Admin"])
async def api_admin_system(req: AdminSystemRequest):
    result = {}
    if req.retention_days:
        db.update_retention(req.retention_days)
        result["retention_days"] = req.retention_days
    if req.thresholds:
        save_thresholds(req.thresholds)
        result["thresholds"] = "updated"
    return {"status":"updated","changes":result}


# ── RAPPORT PDF ────────────────────────────────────────────────
@app.get("/report/{event_id}", tags=["Rapports"])
async def api_report(event_id: str, background_tasks: BackgroundTasks):
    event = next((e for e in smart_engine.events if e.id==event_id), None)
    if not event: raise HTTPException(404, f"Événement {event_id} non trouvé")

    # Récupérer données depuis InfluxDB
    decisions = db.get_decision_history(hours=48)
    data      = _build_report(event, decisions)
    path      = await _gen_pdf(data)
    background_tasks.add_task(lambda p: Path(p).unlink(missing_ok=True), path)
    return FileResponse(path, filename=f"rapport_{event_id}.pdf",
                        media_type="application/pdf")

@app.get("/report/{event_id}/json", tags=["Rapports"])
async def api_report_json(event_id: str):
    event = next((e for e in smart_engine.events if e.id==event_id), None)
    if not event: raise HTTPException(404, f"Événement {event_id} non trouvé")
    return _build_report(event, db.get_decision_history(hours=48))


def _build_report(event, decisions: list) -> dict:
    report = {"event":event.to_dict(),"generated_at":datetime.now().isoformat(),
              "energy":{},"economics":{},"coverage":{}}
    pts = [d for d in decisions
           if d.get('time','')[:10] == event.date
           and event.start <= d.get('time','')[11:16] <= event.end]
    if pts:
        e_pv  = sum(float(d.get('p_charge',0)) for d in pts) * DELTA_T_H
        e_grid= sum(float(d.get('p_grid',0))   for d in pts) * DELTA_T_H
        e_bat = sum(float(d.get('p_discharge',0)) for d in pts) * DELTA_T_H
        e_load= event.energy_needed_kwh
        e_loc = e_pv + e_bat
        cost  = e_grid * smart_engine.cfg.cost_grid_kwh
        report["energy"]    = {"e_load_kwh":round(e_load,2),"e_pv_kwh":round(e_pv,2),
                                "e_bat_kwh":round(e_bat,2),"e_grid_kwh":round(e_grid,2),
                                "coverage_pct":round(e_loc/e_load*100 if e_load>0 else 0,1)}
        report["economics"] = {"cost_grid_mad":round(cost,2),
                                "savings_mad":round(e_loc*smart_engine.cfg.cost_grid_kwh,2)}
        report["coverage"]  = {"solar_pct":round(e_pv/e_load*100 if e_load>0 else 0,1),
                                "battery_pct":round(e_bat/e_load*100 if e_load>0 else 0,1),
                                "grid_pct":round(e_grid/e_load*100 if e_load>0 else 0,1)}
    return report


async def _gen_pdf(data: dict) -> str:
    import tempfile
    path = Path(tempfile.gettempdir()) / f"rapport_{data['event']['id']}.pdf"
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                         Spacer, Table, TableStyle)
        from reportlab.lib import colors
        doc  = SimpleDocTemplate(str(path), pagesize=A4)
        styl = getSampleStyleSheet()
        ev   = data['event']
        body = [
            Paragraph(f"Rapport Post-Événement — {ev['name']}", styl['Title']),
            Paragraph(f"{ev['date']} | {ev['start']} → {ev['end']} | "
                      f"{ev['expected_kw']} kW | Importance: {ev['importance_pct']}%",
                      styl['Normal']),
            Spacer(1,12)
        ]
        if data.get('energy'):
            en,ec,cv = data['energy'],data.get('economics',{}),data.get('coverage',{})
            rows = [["Métrique","Valeur"],
                    ["Énergie consommée",   f"{en.get('e_load_kwh',0)} kWh"],
                    ["Production solaire",  f"{en.get('e_pv_kwh',0)} kWh"],
                    ["Décharge batterie",   f"{en.get('e_bat_kwh',0)} kWh"],
                    ["Import réseau ONEE",  f"{en.get('e_grid_kwh',0)} kWh"],
                    ["Couverture locale",   f"{en.get('coverage_pct',0)}%"],
                    ["Part solaire",        f"{cv.get('solar_pct',0)}%"],
                    ["Part batterie",       f"{cv.get('battery_pct',0)}%"],
                    ["Coût réseau",         f"{ec.get('cost_grid_mad',0)} MAD"],
                    ["Économies réalisées", f"{ec.get('savings_mad',0)} MAD"]]
            t = Table(rows, colWidths=[300,150])
            t.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#1A5276')),
                ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),
                 [colors.white,colors.HexColor('#EBF5FB')]),
                ('GRID',(0,0),(-1,-1),0.5,colors.grey),
                ('FONTSIZE',(0,0),(-1,-1),10),
                ('PADDING',(0,0),(-1,-1),8)]))
            body.extend([t,Spacer(1,20)])
        body.append(Paragraph(
            f"Rapport généré le {data['generated_at'][:19]} — GridGenius GIEW 2026",
            styl['Normal']))
        doc.build(body)
    except ImportError:
        path.write_text(f"Rapport: {data['event']['name']}\n{str(data.get('energy',{}))}")
    return str(path)


# ── Retrain journalier ─────────────────────────────────────────
async def _retrain_loop():
    """Retrain XGBoost depuis InfluxDB chaque nuit à 00:05"""
    while True:
        now      = datetime.now()
        midnight = (now+timedelta(days=1)).replace(
            hour=0, minute=5, second=0, microsecond=0)
        await asyncio.sleep((midnight-now).total_seconds())
        try:
            log.info("Retrain journalier depuis InfluxDB...")
            ok = pred_engine.retrain(db)
            log.info(f"Retrain {'réussi' if ok else 'reporté (données insuffisantes)'}")
        except Exception as e:
            log.error(f"Retrain : {e}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
