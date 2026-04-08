#!/usr/bin/env python3
"""
anomaly.py — Détection d'anomalies énergétiques GridGenius
  Seuils depuis config/anomaly_config.json (modifiable admin).
  Écrit alertes dans InfluxDB.
"""

import json, logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)
CONFIG_FILE = Path(__file__).parent.parent / "config" / "anomaly_config.json"

DEFAULT = {
    "bat_soc_critical":    15.0,
    "bat_soc_low":         25.0,
    "bat_soc_overcharge":  98.0,
    "bat_temp_high":       45.0,
    "bat_temp_critical":   55.0,
    "bat_voltage_low":     46.0,
    "bat_voltage_high":    58.5,
    "pv_voltage_low":      10.0,
    "pv_current_high":     30.0,
    "load_deviation_pct":  40.0,
    "check_load_zero_day": True
}


def _thresholds() -> dict:
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT, **json.loads(CONFIG_FILE.read_text())}
        except Exception:
            pass
    return DEFAULT.copy()


def save_thresholds(t: dict):
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(t, indent=2))


def run_anomaly_detection(data: dict, write_to_influx: bool = True) -> dict:
    T      = _thresholds()
    alerts = []
    hour   = datetime.now().hour
    ts     = datetime.now().isoformat()

    soc  = float(data.get('bat_soc',    50))
    temp = float(data.get('bat_temp',   25))
    volt = float(data.get('bat_voltage',51.2))
    pv_p = float(data.get('pv_power',   0))
    pv_v = float(data.get('pv_voltage', 0))
    pv_c = float(data.get('pv_current', 0))
    load = float(data.get('load_power', 0))
    exp  = float(data.get('expected_load', 0))

    def alert(type_, sev, msg, val=0, **kw):
        return {"type":type_,"severity":sev,"message":msg,"value":val,
                "timestamp":ts,**kw}

    # Batterie
    if soc <= T['bat_soc_critical']:
        alerts.append(alert("BAT_SOC_CRITICAL","critical",f"SOC critique : {soc}%",soc))
    elif soc <= T['bat_soc_low']:
        alerts.append(alert("BAT_SOC_LOW","warning",f"SOC faible : {soc}%",soc))
    if soc >= T['bat_soc_overcharge']:
        alerts.append(alert("BAT_OVERCHARGE","warning",f"Surcharge : {soc}%",soc))
    if temp >= T['bat_temp_critical']:
        alerts.append(alert("BAT_TEMP_CRITICAL","critical",f"Temp. critique : {temp}°C",temp))
    elif temp >= T['bat_temp_high']:
        alerts.append(alert("BAT_TEMP_HIGH","warning",f"Temp. élevée : {temp}°C",temp))
    if volt <= T['bat_voltage_low']:
        alerts.append(alert("BAT_VOLTAGE_LOW","warning",f"Tension basse : {volt}V",volt))
    if volt >= T['bat_voltage_high']:
        alerts.append(alert("BAT_VOLTAGE_HIGH","warning",f"Tension haute : {volt}V",volt))

    # PV
    if pv_p < 0:
        alerts.append(alert("PV_NEGATIVE","warning",f"Puissance PV négative : {pv_p}kW",pv_p))
    if 9 <= hour <= 16 and 0 < pv_v < T['pv_voltage_low']:
        alerts.append(alert("PV_LOW_VOLTAGE","warning",
                            f"Tension PV basse : {pv_v}V à {hour}h",pv_v))
    if pv_c > T['pv_current_high']:
        alerts.append(alert("PV_OVERCURRENT","critical",
                            f"Surintensité : {pv_c}A",pv_c))

    # Consommation
    if T['check_load_zero_day'] and 8 <= hour <= 18 and load < 0.5:
        alerts.append(alert("LOAD_ZERO_DAY","warning",
                            f"Charge nulle en journée ({hour}h)",load))
    if exp > 0:
        dev = abs(load-exp)/exp*100
        if dev >= T['load_deviation_pct']:
            d = "supérieure" if load>exp else "inférieure"
            alerts.append(alert("LOAD_DEVIATION","warning",
                                f"Conso {d} à prévision : {load:.1f}kW vs {exp:.1f}kW ({dev:.0f}%)",
                                load, expected=exp, deviation_pct=round(dev,1)))

    # Écriture InfluxDB
    if write_to_influx and alerts:
        try:
            from influx_client import db
            for a in alerts:
                db.write_alert(a)
        except Exception as e:
            log.warning(f"Alertes InfluxDB : {e}")

    status = ("critical" if any(a['severity']=='critical' for a in alerts)
              else "warning" if alerts else "ok")

    for a in alerts:
        log.warning(f"[{a['severity'].upper()}] {a['type']}: {a['message']}")

    return {"anomaly_count":len(alerts),"alerts":alerts,
            "status":status,"checked_at":ts}
