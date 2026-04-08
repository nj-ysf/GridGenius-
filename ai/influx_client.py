#!/usr/bin/env python3
"""
influx_client.py — Client InfluxDB 1.x — GridGenius
  Source unique de données pour tous les modules.

  Measurements :
    mppt_data    : données brutes MPPT (10s)
    predictions  : prédictions PV + conso (30min)
    decisions    : décisions IA (10s)
    alerts       : anomalies (on-event)
    battery_state: état batterie (10s)

  Rétention : 30 jours par défaut, paramétrable admin.

  Niveaux d'apprentissage :
    LEARNING    : < 48h   → pas de prédiction XGBoost
    PARTIAL     : 48h-7j  → prédiction partielle
    OPERATIONAL : > 7j    → prédiction complète
"""

import logging
from datetime import datetime
from typing import Optional
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBClientError, InfluxDBServerError

log = logging.getLogger(__name__)

INFLUX_HOST          = "localhost"
INFLUX_PORT          = 8086
INFLUX_DB            = "microgrid"
INFLUX_RP            = "rp_default"
RETENTION_DAYS       = 30
MIN_HOURS_PARTIAL    = 48
MIN_HOURS_FULL       = 168
MPPT_INTERVAL_S      = 10       # Δt collecte = 10s


class InfluxClient:

    def __init__(self):
        self._client = None
        self._connect()

    def _connect(self):
        try:
            self._client = InfluxDBClient(
                host=INFLUX_HOST, port=INFLUX_PORT, database=INFLUX_DB
            )
            self._client.ping()
            log.info(f"InfluxDB connecté : {INFLUX_HOST}:{INFLUX_PORT}/{INFLUX_DB}")
        except Exception as e:
            log.error(f"InfluxDB connexion échouée : {e}")
            self._client = None

    def _ok(self) -> bool:
        if self._client is None:
            self._connect()
        return self._client is not None

    # ── Setup ──────────────────────────────────────────────────
    def setup(self, retention_days: int = RETENTION_DAYS) -> bool:
        if not self._ok(): return False
        try:
            dbs = [d['name'] for d in self._client.get_list_database()]
            if INFLUX_DB not in dbs:
                self._client.create_database(INFLUX_DB)
                log.info(f"Database '{INFLUX_DB}' créée")
            rps = [r['name'] for r in
                   self._client.get_list_retention_policies(INFLUX_DB)]
            if INFLUX_RP not in rps:
                self._client.create_retention_policy(
                    INFLUX_RP, f"{retention_days}d", 1, INFLUX_DB, default=True
                )
                log.info(f"Retention policy '{INFLUX_RP}' ({retention_days}j) créée")
            return True
        except Exception as e:
            log.error(f"Setup : {e}"); return False

    def update_retention(self, days: int) -> bool:
        if not self._ok(): return False
        try:
            self._client.alter_retention_policy(
                INFLUX_RP, INFLUX_DB, duration=f"{days}d", default=True
            )
            log.info(f"Rétention → {days}j"); return True
        except Exception as e:
            log.error(f"Update rétention : {e}"); return False

    # ── Écriture ───────────────────────────────────────────────
    def _write(self, measurement: str, fields: dict,
               tags: dict = None, ts: datetime = None) -> bool:
        if not self._ok(): return False
        try:
            self._client.write_points([{
                "measurement": measurement,
                "tags":  tags or {},
                "fields": {k: float(v) if isinstance(v, (int, float)) else str(v)
                           for k, v in fields.items()},
                "time":  (ts or datetime.utcnow()).isoformat()
            }], retention_policy=INFLUX_RP)
            return True
        except (InfluxDBClientError, InfluxDBServerError) as e:
            log.error(f"Écriture {measurement} : {e}"); return False

    def _write_batch(self, points: list) -> bool:
        if not self._ok() or not points: return False
        try:
            self._client.write_points(points, retention_policy=INFLUX_RP)
            return True
        except Exception as e:
            log.error(f"Batch : {e}"); return False

    # ── MPPT ───────────────────────────────────────────────────
    def write_mppt(self, data: dict) -> bool:
        return self._write("mppt_data", {
            "pv_power":        float(data.get("pv_power",        0)),
            "pv_voltage":      float(data.get("pv_voltage",      0)),
            "pv_current":      float(data.get("pv_current",      0)),
            "pv_energy_today": float(data.get("pv_energy_today", 0)),
            "bat_soc":         float(data.get("bat_soc",        50)),
            "bat_voltage":     float(data.get("bat_voltage",   51.2)),
            "bat_current":     float(data.get("bat_current",     0)),
            "bat_temp":        float(data.get("bat_temp",       25)),
            "load_power":      float(data.get("load_power",      0)),
            "charge_mode":     str(data.get("charge_mode",  "unknown")),
            "source":          str(data.get("source",         "modbus"))
        }, tags={"location": "ehtp"})

    def get_mppt_history(self, hours: int = 48) -> list:
        return self._query(
            f"SELECT * FROM mppt_data "
            f"WHERE time > now() - {hours}h ORDER BY time ASC"
        )

    def get_last_mppt(self) -> Optional[dict]:
        pts = self._query("SELECT * FROM mppt_data ORDER BY time DESC LIMIT 1")
        return pts[0] if pts else None

    # ── Prédictions ────────────────────────────────────────────
    def write_predictions(self, predictions: list, pred_type: str) -> bool:
        points = []
        for p in predictions:
            try:
                dt = datetime.fromisoformat(p['timestamp']) \
                     if p.get('timestamp') else datetime.utcnow()
                points.append({
                    "measurement": "predictions",
                    "tags":   {"type": pred_type},
                    "fields": {
                        "predicted_kw": float(p.get("predicted_kw",
                                               p.get("pv_corrected_kw", 0))),
                        "sigma":        float(p.get("sigma",    2.0)),
                        "ci_lower":     float(p.get("ci_lower", 0)),
                        "ci_upper":     float(p.get("ci_upper", 0)),
                        "event_kw":     float(p.get("event_kw", 0)),
                        "source":       str(p.get("source",   "model"))
                    },
                    "time": dt.isoformat()
                })
            except Exception as e:
                log.warning(f"Point préd. ignoré : {e}")
        return self._write_batch(points)

    def get_last_predictions(self, pred_type: str,
                             hours_ahead: int = 336) -> list:
        return self._query(
            f"SELECT * FROM predictions "
            f"WHERE \"type\"='{pred_type}' "
            f"AND time > now() - 35m "
            f"AND time < now() + {hours_ahead}h "
            f"ORDER BY time ASC LIMIT {hours_ahead * 2}"
        )

    def has_recent_predictions(self, max_age_min: int = 35) -> bool:
        return len(self._query(
            f"SELECT * FROM predictions "
            f"WHERE time > now() - {max_age_min}m LIMIT 1"
        )) > 0

    # ── Décisions ──────────────────────────────────────────────
    def write_decision(self, dec: dict) -> bool:
        return self._write("decisions", {
            "decision":    str(dec.get("decision",    "grid")),
            "action":      str(dec.get("action",      "idle")),
            "p_grid":      float(dec.get("p_grid",    0)),
            "p_charge":    float(dec.get("p_charge",  0)),
            "p_discharge": float(dec.get("p_discharge", 0)),
            "reason":      str(dec.get("reason",      "")),
            "mode":        str(dec.get("mode",        "normal"))
        })

    def get_last_decision(self) -> Optional[dict]:
        pts = self._query("SELECT * FROM decisions ORDER BY time DESC LIMIT 1")
        return pts[0] if pts else None

    def get_decision_history(self, hours: int = 24) -> list:
        return self._query(
            f"SELECT * FROM decisions "
            f"WHERE time > now() - {hours}h ORDER BY time ASC"
        )

    # ── Alertes ────────────────────────────────────────────────
    def write_alert(self, alert: dict) -> bool:
        return self._write("alerts", {
            "type":     str(alert.get("type",     "UNKNOWN")),
            "message":  str(alert.get("message",  "")),
            "severity": str(alert.get("severity", "info")),
            "value":    float(alert.get("value",  0))
        }, tags={"severity": alert.get("severity", "info")})

    def get_alerts(self, hours: int = 24) -> list:
        return self._query(
            f"SELECT * FROM alerts "
            f"WHERE time > now() - {hours}h "
            f"ORDER BY time DESC LIMIT 50"
        )

    # ── Batterie ───────────────────────────────────────────────
    def write_battery_state(self, state: dict) -> bool:
        return self._write("battery_state", {
            "soc":           float(state.get("soc",           50)),
            "voltage":       float(state.get("voltage",      51.2)),
            "mode":          str(state.get("mode",           "idle")),
            "cycles_equiv":  float(state.get("cycles_equiv",   0)),
            "available_kwh": float(state.get("available_kwh", 25))
        })

    def get_battery_history(self, hours: int = 24) -> list:
        return self._query(
            f"SELECT * FROM battery_state "
            f"WHERE time > now() - {hours}h ORDER BY time ASC"
        )

    # ── Niveau apprentissage ───────────────────────────────────
    def get_data_status(self) -> dict:
        """
        Détermine le mode de fonctionnement selon les données disponibles.
        LEARNING → PARTIAL → OPERATIONAL
        """
        pts = self._query(
            "SELECT COUNT(pv_power) AS n FROM mppt_data "
            "WHERE time > now() - 365d"
        )
        n       = int(pts[0]['n']) if pts else 0
        hours   = n / (3600 / MPPT_INTERVAL_S)

        if hours < MIN_HOURS_PARTIAL:
            status     = "LEARNING"
            confidence = 0
            can_predict= False
            message    = (f"Phase apprentissage — {hours:.1f}h collectées / "
                          f"{MIN_HOURS_PARTIAL}h nécessaires")
        elif hours < MIN_HOURS_FULL:
            pct        = (hours-MIN_HOURS_PARTIAL) / (MIN_HOURS_FULL-MIN_HOURS_PARTIAL)
            status     = "PARTIAL"
            confidence = int(20 + pct * 60)
            can_predict= True
            message    = (f"Prédiction partielle — {hours:.1f}h / "
                          f"{MIN_HOURS_FULL}h pour confiance maximale")
        else:
            status     = "OPERATIONAL"
            confidence = 100
            can_predict= True
            message    = "Système opérationnel — prédiction complète disponible"

        return {
            "status":         status,
            "hours_of_data":  round(hours, 1),
            "n_points":       n,
            "confidence_pct": confidence,
            "can_predict":    can_predict,
            "message":        message
        }

    # ── Stats dashboard ────────────────────────────────────────
    def get_daily_stats(self, days: int = 14) -> list:
        return self._query(
            f"SELECT mean(pv_power) AS avg_pv, "
            f"mean(load_power) AS avg_load, "
            f"mean(bat_soc) AS avg_soc, "
            f"max(pv_power) AS peak_pv "
            f"FROM mppt_data "
            f"WHERE time > now() - {days}d "
            f"GROUP BY time(1d) fill(none)"
        )

    def get_energy_today(self) -> dict:
        pts = self._query(
            "SELECT sum(pv_power) AS e_pv, sum(load_power) AS e_load "
            "FROM mppt_data WHERE time > now() - 24h"
        )
        dt_h = MPPT_INTERVAL_S / 3600
        if pts:
            return {
                "e_pv_kwh":   round(float(pts[0].get("e_pv",   0)) * dt_h, 2),
                "e_load_kwh": round(float(pts[0].get("e_load", 0)) * dt_h, 2)
            }
        return {"e_pv_kwh": 0, "e_load_kwh": 0}

    def get_autonomy_today(self) -> float:
        en = self.get_energy_today()
        pv, load = en["e_pv_kwh"], en["e_load_kwh"]
        return round(min(100, pv/load*100) if load > 0 else 0, 1)

    # ── Santé ──────────────────────────────────────────────────
    def ping(self) -> bool:
        try:
            return self._client is not None and bool(self._client.ping())
        except Exception:
            return False

    # ── Requête interne ────────────────────────────────────────
    def _query(self, q: str) -> list:
        if not self._ok(): return []
        try:
            res = self._client.query(q)
            return list(res.get_points()) if res else []
        except Exception as e:
            log.error(f"Requête : {e}"); return []


# Instance globale unique
db = InfluxClient()
