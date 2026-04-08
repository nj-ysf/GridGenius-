#!/usr/bin/env python3
"""
smart_engine.py — Moteur IA GridGenius (optimizer + scheduler fusionnés)
  - Décision temps réel (appelé par /decide toutes les 10s)
  - Recommandation créneaux (appelé par /recommend)
  - Score = α·PV_norm + β·SOC_proj - γ·grid_dep - δ·conflict
  - Priorité stricte par importance %
  - Gestion conflits + pré-charge
  - Lit prédictions depuis InfluxDB
"""

import json, logging
import numpy as np
from datetime import datetime, timedelta, date
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from predict       import DELTA_T_H, P_PV_INSTALLED, PV_PROFILE
from battery_model import battery

log = logging.getLogger(__name__)

CONFIG_DIR   = Path(__file__).parent.parent / "config"
CONFIG_DIR.mkdir(exist_ok=True)
EVENTS_FILE  = CONFIG_DIR / "events.json"
SCORING_FILE = CONFIG_DIR / "scoring_config.json"

PREDEFINED = {
    "examen_final":     {"label":"Examen final",       "kw":22.0,"importance_pct":95,
                         "preferred_hours":list(range(8,13))},
    "portes_ouvertes":  {"label":"Portes ouvertes",    "kw":35.0,"importance_pct":85,
                         "preferred_hours":list(range(9,17))},
    "conference":       {"label":"Conférence",         "kw":15.0,"importance_pct":75,
                         "preferred_hours":list(range(9,18))},
    "labo_electronique":{"label":"Labo électronique",  "kw": 9.0,"importance_pct":65,
                         "preferred_hours":list(range(8,18))},
    "amphi":            {"label":"Amphi 150 places",   "kw": 8.0,"importance_pct":55,
                         "preferred_hours":list(range(8,18))},
    "salle_tp_info":    {"label":"Salle TP Info",      "kw": 6.5,"importance_pct":45,
                         "preferred_hours":list(range(8,18))},
    "salle_standard":   {"label":"Salle standard",     "kw": 2.5,"importance_pct":35,
                         "preferred_hours":list(range(8,18))},
    "autre":            {"label":"Autre (personnalisé)","kw": 0.0,"importance_pct":50,
                         "preferred_hours":list(range(6,22))},
}


# ── Config scoring ─────────────────────────────────────────────
@dataclass
class ScoringConfig:
    alpha: float = 0.40
    beta:  float = 0.35
    gamma: float = 0.50
    delta: float = 0.30
    coverage_min_pct:  float = 60.0
    soc_precharge:     float = 0.80
    cost_grid_kwh:     float = 1.20
    lambda_cycles:     float = 0.50
    p_grid_max:        float = 50.0

    @classmethod
    def load(cls):
        if SCORING_FILE.exists():
            try:
                return cls(**{k:v for k,v in json.loads(
                    SCORING_FILE.read_text()).items() if hasattr(cls,k)})
            except Exception: pass
        return cls()

    def save(self):
        SCORING_FILE.write_text(json.dumps(self.__dict__, indent=2))

    def to_dict(self): return self.__dict__


# ── Modèle événement ───────────────────────────────────────────
@dataclass
class Event:
    id:             str
    name:           str
    type:           str
    date:           str
    start:          str
    end:            str
    expected_kw:    float
    importance_pct: int
    duration_h:     float
    label:          str   = ""
    status:         str   = "planned"
    created_at:     str   = ""
    score:          float = 0.0

    @classmethod
    def from_dict(cls, d):
        return cls(**{k:v for k,v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self): return self.__dict__

    @property
    def energy_needed_kwh(self): return self.expected_kw * self.duration_h

    def overlaps(self, other: "Event") -> bool:
        return self.date == other.date and \
               not (self.end <= other.start or self.start >= other.end)


# ── Résultat scoring créneau ───────────────────────────────────
@dataclass
class SlotScore:
    date:          str
    start:         str
    end:           str
    score:         float
    pv_norm:       float
    soc_proj:      float
    grid_dep:      float
    conflict:      float
    coverage_pct:  float
    autonomy_pct:  float
    feasible:      bool
    conflicts_with: list = field(default_factory=list)

    def to_dict(self): return self.__dict__


# ══════════════════════════════════════════════════════════════
# MOTEUR PRINCIPAL
# ══════════════════════════════════════════════════════════════

class SmartEngine:

    def __init__(self):
        self.cfg    = ScoringConfig.load()
        self.events = self._load_events()

    def _load_events(self):
        if EVENTS_FILE.exists():
            try:
                return [Event.from_dict(e)
                        for e in json.loads(EVENTS_FILE.read_text())]
            except Exception as e:
                log.warning(f"Chargement événements : {e}")
        return []

    def _save_events(self):
        EVENTS_FILE.write_text(
            json.dumps([e.to_dict() for e in self.events],
                       indent=2, ensure_ascii=False))

    # ── DÉCISION TEMPS RÉEL ────────────────────────────────────
    def decide(self, p_pv: float, p_load: float, soc: float,
               pv_predicted: float = None,
               upcoming_events: list = None,
               hour: int = None) -> dict:
        """
        Décision heuristique temps réel.
        Appelé par api.py/decide toutes les 10s.
        pv_predicted : prédiction PV prochaine heure (depuis InfluxDB)
        """
        cfg  = self.cfg
        bcfg = battery.cfg
        hour = hour if hour is not None else datetime.now().hour
        upcoming_events = upcoming_events or []

        p_net = p_pv - p_load - bcfg.p_losses_kw
        p_grid = p_charge = p_disc = 0.0
        decision = "solar"
        reason   = ""

        # 1. Pré-charge événement haute priorité
        high = sorted([e for e in upcoming_events if e.get('expected_kw',0) >= 15],
                      key=lambda e: e.get('importance_pct',50), reverse=True)
        if high and soc < cfg.soc_precharge:
            ev       = high[0]
            p_charge = min((cfg.soc_precharge-soc)*bcfg.capacity_kwh/DELTA_T_H,
                           bcfg.p_max_charge_kw)
            p_grid   = max(0, min(p_charge/bcfg.eta_charge-p_pv, cfg.p_grid_max))
            decision = "grid"
            reason   = f"precharge_{ev.get('expected_kw')}kw_imp{ev.get('importance_pct')}pct"
            return self._result(decision, p_grid, p_charge, p_disc, reason)

        # 2. Surplus PV → charge
        if p_net > 0 and soc < bcfg.soc_max:
            p_charge  = min(p_net*bcfg.eta_charge, bcfg.p_max_charge_kw)
            headroom  = (bcfg.soc_max-soc)*bcfg.capacity_kwh/DELTA_T_H
            p_charge  = max(0, min(p_charge, headroom))
            decision  = "solar"
            reason    = f"pv_surplus_{p_pv:.1f}kw"

        # 3. Déficit → décharge
        elif p_net < 0:
            if soc > bcfg.soc_min + 0.05:
                p_disc    = min(abs(p_net)/bcfg.eta_discharge, bcfg.p_max_discharge_kw)
                available = (soc-bcfg.soc_min)*bcfg.capacity_kwh/DELTA_T_H
                p_disc    = max(0, min(p_disc, available))
                p_missing = abs(p_net) - p_disc*bcfg.eta_discharge - bcfg.p_losses_kw
                if p_missing > 0.1:
                    p_grid   = min(p_missing, cfg.p_grid_max)
                    decision = "hybrid"
                    reason   = f"bat+grid_{abs(p_net):.1f}kw"
                else:
                    decision = "battery"
                    reason   = f"bat_discharge_soc{soc*100:.0f}pct"
            else:
                p_grid   = min(abs(p_net), cfg.p_grid_max)
                decision = "grid"
                reason   = f"low_soc_{soc*100:.0f}pct"
        else:
            decision = "battery" if soc > bcfg.soc_min+0.10 else "grid"
            reason   = "idle"

        return self._result(decision, p_grid, p_charge, p_disc, reason)

    def _result(self, decision, p_grid, p_charge, p_disc, reason) -> dict:
        return {
            "decision":    decision,
            "action":      "charge" if p_charge>0.01 else
                           "discharge" if p_disc>0.01 else "idle",
            "p_grid":      round(p_grid, 3),
            "p_charge":    round(p_charge, 3),
            "p_discharge": round(p_disc, 3),
            "reason":      reason,
            "mode":        "normal",
            "timestamp":   datetime.now().isoformat()
        }

    @staticmethod
    def safe_mode_decision() -> dict:
        """Mode sécurité : Solar ON + Grid ON + Battery OFF"""
        return {
            "decision":    "grid",
            "action":      "idle",
            "p_grid":      10.0,
            "p_charge":    0.0,
            "p_discharge": 0.0,
            "reason":      "SAFE_MODE_API_UNAVAILABLE",
            "mode":        "SAFE_MODE",
            "timestamp":   datetime.now().isoformat()
        }

    # ── SCORE FORMALISÉ ────────────────────────────────────────
    def score(self, pv_norm, soc_proj, grid_dep, conflict) -> float:
        """Score = α·PV_norm + β·SOC_proj - γ·grid_dep - δ·conflict"""
        c = self.cfg
        return c.alpha*pv_norm + c.beta*soc_proj \
             - c.gamma*grid_dep - c.delta*conflict

    # ── RECOMMANDATION CRÉNEAUX ────────────────────────────────
    def recommend_slots(self, db, event_type: str, duration_h: float,
                        date_from: str, date_to: str,
                        custom_kw: float = None,
                        custom_importance: int = None,
                        top_n: int = 3,
                        current_soc: float = 0.50) -> dict:
        """
        Recommande Top-N créneaux optimaux.
        Lit les prédictions depuis InfluxDB.
        """
        from predict import engine as pred_engine

        profile = PREDEFINED.get(event_type, PREDEFINED['autre']).copy()
        if custom_kw         is not None: profile['kw']             = custom_kw
        if custom_importance is not None: profile['importance_pct'] = custom_importance

        event_kw  = profile['kw']
        imp_pct   = profile['importance_pct']
        e_needed  = event_kw * duration_h

        # Vérifier prédictions disponibles dans InfluxDB
        if not db.has_recent_predictions():
            # Lancer la prédiction si pas disponible
            events_list = [e.to_dict() for e in self.events
                           if e.status in ("planned","planned_with_conflict")]
            pred_result = pred_engine.predict(db, days=(
                datetime.strptime(date_to,"%Y-%m-%d") -
                datetime.strptime(date_from,"%Y-%m-%d")).days+1,
                events=events_list)
            if pred_result.get('status') == 'LEARNING':
                return {"status":"LEARNING",
                        "message":pred_result['message'],
                        "top_slots":[], "warnings":["Données insuffisantes pour recommander."]}

        pv_preds   = db.get_last_predictions("pv", hours_ahead=336)
        conso_preds= db.get_last_predictions("consumption", hours_ahead=336)
        pv_map     = {p['time'][:16]: p for p in pv_preds}
        co_map     = {p['time'][:16]: p for p in conso_preds}

        dt_from = datetime.strptime(date_from, "%Y-%m-%d")
        dt_to   = datetime.strptime(date_to,   "%Y-%m-%d")

        candidates = []
        cur = dt_from.replace(hour=7, minute=0)
        while cur <= dt_to.replace(hour=20, minute=0):
            if cur.hour in profile.get('preferred_hours', list(range(6,22))):
                slot_end = cur + timedelta(hours=duration_h)
                pv_pts, co_pts = [], []
                t = cur
                while t < slot_end:
                    key = t.isoformat()[:16]
                    if key in pv_map:
                        pv_pts.append(pv_map[key])
                        co_pts.append(co_map.get(key, {"predicted_kw":5.0}))
                    t += timedelta(minutes=30)
                if pv_pts:
                    candidates.append({
                        "date":  cur.strftime("%Y-%m-%d"),
                        "start": cur.strftime("%H:%M"),
                        "end":   slot_end.strftime("%H:%M"),
                        "hour":  cur.hour,
                        "pv":    pv_pts,
                        "conso": co_pts
                    })
            cur += timedelta(minutes=30)

        scored = []
        for c in candidates:
            s = self._score_slot(c, event_kw, duration_h,
                                 e_needed, current_soc, imp_pct)
            if s: scored.append(s)
        scored.sort(key=lambda s: s.score, reverse=True)

        top, seen = [], set()
        for s in scored:
            k = f"{s.date}_{s.start}"
            if k not in seen:
                top.append(s); seen.add(k)
            if len(top) >= top_n: break

        warnings = []
        if not top:
            warnings.append("Aucun créneau faisable dans la fenêtre.")
        elif all(not s.feasible for s in top):
            warnings.append("Énergie insuffisante — réseau ONEE en complément.")

        return {
            "event_type":     event_type,
            "event_label":    profile['label'],
            "event_kw":       event_kw,
            "duration_h":     duration_h,
            "importance_pct": imp_pct,
            "e_needed_kwh":   round(e_needed, 2),
            "n_candidates":   len(candidates),
            "top_slots":      [s.to_dict() for s in top],
            "warnings":       warnings,
            "scoring_config": self.cfg.to_dict(),
            "generated_at":   datetime.now().isoformat()
        }

    def _score_slot(self, cand, event_kw, duration_h,
                    e_needed, current_soc, imp_pct) -> Optional[SlotScore]:
        try:
            pv_pts = cand['pv']; co_pts = cand['conso']
            if not pv_pts: return None

            def get_kw(p):
                return float(p.get('predicted_kw',
                             p.get('pv_corrected_kw',
                             p.get('_value', 0))))

            pv_mean  = float(np.mean([get_kw(p) for p in pv_pts]))
            pv_norm  = min(1.0, pv_mean / P_PV_INSTALLED)

            summary  = battery.project_summary(pv_pts, co_pts, current_soc)
            soc_proj = float(summary.get('soc_mean', current_soc*100)) / 100
            grid_dep = float(summary.get('grid_dependency', 1.0))
            coverage = float(summary.get('autonomy_pct', 0))
            autonomy = coverage

            e_avail  = float(summary.get('e_pv_kwh',0)) + \
                       (current_soc - battery.cfg.soc_min) * battery.cfg.capacity_kwh
            coverage_pct = min(100, e_avail/e_needed*100) if e_needed > 0 else 100
            feasible = coverage_pct >= self.cfg.coverage_min_pct

            conflict_val, conflicts = self._detect_conflicts(
                cand['date'], cand['start'], cand['end'], imp_pct)

            sc = self.score(pv_norm, soc_proj, grid_dep, conflict_val)
            if 9 <= cand['hour'] <= 14: sc += 0.05

            return SlotScore(
                date=cand['date'], start=cand['start'], end=cand['end'],
                score=round(sc,4), pv_norm=round(pv_norm,3),
                soc_proj=round(soc_proj,3), grid_dep=round(grid_dep,3),
                conflict=conflict_val, coverage_pct=round(coverage_pct,1),
                autonomy_pct=round(autonomy,1), feasible=feasible,
                conflicts_with=conflicts)
        except Exception as e:
            log.warning(f"Score créneau {cand['date']} {cand['start']}: {e}")
            return None

    def _detect_conflicts(self, date, start, end, imp_pct):
        conflicts = []
        for ev in self.events:
            if ev.date==date and ev.status in ("planned","planned_with_conflict"):
                if not (end<=ev.start or start>=ev.end):
                    conflicts.append({
                        "event_id":ev.id,"event_name":ev.name,
                        "importance_pct":ev.importance_pct,
                        "priority_gap":abs(imp_pct-ev.importance_pct)})
        if not conflicts: return 0.0, []
        conflict_val = min(1.0, len(conflicts)*(
            1-max(c['priority_gap'] for c in conflicts)/100))
        return round(conflict_val,3), conflicts

    # ── GESTION ÉVÉNEMENTS ─────────────────────────────────────
    def add_event(self, data: dict) -> dict:
        ev_type  = data.get('type','autre')
        profile  = PREDEFINED.get(ev_type, PREDEFINED['autre'])
        kw       = float(data.get('expected_kw', profile['kw']))
        imp      = int(data.get('importance_pct', profile['importance_pct']))
        start_dt = datetime.strptime(f"{data['date']} {data['start']}", "%Y-%m-%d %H:%M")
        end_dt   = datetime.strptime(f"{data['date']} {data['end']}",   "%Y-%m-%d %H:%M")
        dur_h    = (end_dt-start_dt).seconds / 3600

        event = Event(
            id=f"evt_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            name=data.get('name', profile['label']),
            type=ev_type, date=data['date'],
            start=data['start'], end=data['end'],
            expected_kw=kw, importance_pct=imp, duration_h=dur_h,
            label=profile['label'], status="planned",
            created_at=datetime.now().isoformat()
        )

        conflicts  = [ev for ev in self.events
                      if ev.status in ("planned","planned_with_conflict")
                      and event.overlaps(ev)]
        resolution = None
        if conflicts:
            resolution = self._resolve_conflict(event, conflicts)
            if resolution.get('alternatives'):
                event.status = "planned_with_conflict"

        precharge = self._compute_precharge(event)
        self.events.append(event)
        self._save_events()
        log.info(f"Événement ajouté : {event.name} {event.date} "
                 f"{event.start}-{event.end} {event.expected_kw}kW imp:{imp}%")
        return {"status":"added","event":event.to_dict(),
                "conflicts":[c.to_dict() for c in conflicts],
                "precharge":precharge,"resolution":resolution}

    def _resolve_conflict(self, event: Event, conflicting: list) -> dict:
        all_ev = [event]+conflicting
        all_ev.sort(key=lambda e: e.importance_pct, reverse=True)
        priority = all_ev[0]; secondary = all_ev[1:]
        return {
            "conflict_detected": True,
            "priority_event":    priority.to_dict(),
            "secondary_events":  [e.to_dict() for e in secondary],
            "alternatives":      [],
            "fallback_message": (
                f"Priorité à '{priority.name}' ({priority.importance_pct}%). "
                "Le reste sera couvert par le réseau ONEE."
            )
        }

    def _compute_precharge(self, event: Event) -> dict:
        soc_target = min(battery.cfg.soc_max,
                         battery.cfg.soc_min +
                         event.energy_needed_kwh/battery.cfg.capacity_kwh + 0.10)
        start_dt   = datetime.strptime(f"{event.date} {event.start}", "%Y-%m-%d %H:%M")
        pre_dt     = start_dt - timedelta(hours=2)
        pv_avail   = PV_PROFILE.get(pre_dt.hour, 2.0)
        pc         = battery.compute_precharge(soc_target, pv_avail, 2.0)
        pc['start_precharge_at'] = pre_dt.strftime("%H:%M")
        pc['event_start']        = event.start
        pc['soc_target_pct']     = round(soc_target*100, 1)
        return pc

    def get_current_events(self, dt: datetime = None) -> dict:
        dt    = dt or datetime.now()
        now   = dt.strftime("%H:%M")
        today = dt.strftime("%Y-%m-%d")
        active = sorted(
            [ev for ev in self.events
             if ev.date==today
             and ev.status in ("planned","planned_with_conflict","active")
             and ev.start<=now<=ev.end],
            key=lambda e: e.importance_pct, reverse=True)
        return {"active_events":[e.to_dict() for e in active],
                "total_expected_kw":round(sum(e.expected_kw for e in active),1),
                "event_count":len(active), "timestamp":dt.isoformat()}

    def get_upcoming_events(self, hours_ahead: int = 24) -> list:
        now = datetime.now()
        end = now + timedelta(hours=hours_ahead)
        res = []
        for ev in self.events:
            try:
                ev_dt = datetime.strptime(f"{ev.date} {ev.start}","%Y-%m-%d %H:%M")
                if now<=ev_dt<=end and ev.status in ("planned","planned_with_conflict"):
                    res.append(ev)
            except Exception: pass
        return sorted(res, key=lambda e: f"{e.date} {e.start}")

    def needs_precharge(self, hours_ahead: int = 2) -> dict:
        upcoming = self.get_upcoming_events(hours_ahead)
        high     = sorted([e for e in upcoming if e.expected_kw>=15],
                          key=lambda e: e.importance_pct, reverse=True)
        if high:
            ev = high[0]
            return {"needed":True,
                    "reason":f"'{ev.name}' à {ev.start} ({ev.expected_kw}kW)",
                    "max_kw":ev.expected_kw,"at_time":ev.start,
                    "importance":ev.importance_pct}
        return {"needed":False}

    def delete_event(self, event_id: str) -> bool:
        before = len(self.events)
        self.events = [e for e in self.events if e.id != event_id]
        self._save_events()
        return len(self.events) < before

    def update_config(self, config: dict):
        for k, v in config.items():
            if hasattr(self.cfg, k):
                setattr(self.cfg, k, float(v))
        self.cfg.save()


# Instance globale
engine = SmartEngine()
