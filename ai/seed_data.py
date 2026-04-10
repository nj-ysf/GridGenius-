#!/usr/bin/env python3
"""
seed_data.py — GridGenius Historical Data Seeder
  Writes 52 hours of simulated MPPT data directly into InfluxDB
  so the system exits LEARNING mode and XGBoost can be trained.
  Runs once at startup if InfluxDB has < 48h of data.
"""

import sys
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [seed] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

# PV profile based on real Mohammedia irradiance (Open-Meteo Archive)
PV_PROFILE = {
    0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.3,
    7: 1.2, 8: 2.8, 9: 4.8, 10: 6.8, 11: 8.2, 12: 8.8, 13: 8.6,
    14: 7.8, 15: 6.2, 16: 4.2, 17: 2.3, 18: 0.6,
    19: 0.0, 20: 0.0, 21: 0.0, 22: 0.0, 23: 0.0
}

# ENSET Mohammedia consumption profile (educational institution, kW)
CONSO_PROFILE = {
    0: 2.5, 1: 2.5, 2: 2.5, 3: 2.5, 4: 2.5, 5: 2.8, 6: 3.5,
    7: 8, 8: 25, 9: 30, 10: 32, 11: 30, 12: 15, 13: 14,
    14: 28, 15: 30, 16: 28, 17: 22, 18: 8, 19: 5,
    20: 4, 21: 3.5, 22: 3, 23: 2.8
}


def seed(hours: int = 52):
    try:
        sys.path.insert(0, str(__file__ and __import__('pathlib').Path(__file__).parent))
        from influx_client import db
    except Exception as e:
        log.error(f"Cannot connect to InfluxDB: {e}")
        return False

    status = db.get_data_status()
    model_exists = (Path(__file__).parent / "models" / "xgb_consumption.pkl").exists()

    if status['hours_of_data'] >= 48:
        log.info(f"Already have {status['hours_of_data']:.1f}h of data — skipping seed")
        if not model_exists:
            log.info("Model not trained yet — training now on existing data...")
            try:
                from predict import engine as pred_engine
                ok = pred_engine.retrain(db)
                log.info(f"XGBoost training {'succeeded' if ok else 'deferred'}")
            except Exception as e:
                log.warning(f"XGBoost training error: {e}")
        return True

    log.info(f"Seeding {hours}h of historical data into InfluxDB...")

    now   = datetime.utcnow()
    start = now - timedelta(hours=hours)
    soc   = 65.0
    count = 0

    t = start
    while t <= now:
        h   = t.hour
        pv  = max(0.0, PV_PROFILE.get(h, 0.0) + random.uniform(-0.2, 0.2))
        load = max(0.5, CONSO_PROFILE.get(h, 5) + random.uniform(-2.0, 2.0))

        bilan = pv - load
        soc  += bilan * (10 / 3600) * 100 / 50
        soc   = max(15.0, min(95.0, soc))

        mppt = {
            "pv_power":        round(pv, 2),
            "pv_voltage":      round(72.0 if pv > 0.1 else 0.0, 2),
            "pv_current":      round(pv * 1000 / 72 if pv > 0.1 else 0.0, 2),
            "pv_energy_today": round(pv * h * 0.9 / 10, 2),
            "bat_voltage":     round(44.0 + (soc / 100) * 14.4, 2),
            "bat_current":     round((pv - load) * 20, 1),
            "bat_soc":         round(soc, 1),
            "bat_temp":        round(25.0 + (soc / 100) * 5 + random.uniform(-0.5, 0.5), 1),
            "load_power":      round(load, 2),
            "charge_mode":     "mppt" if pv > 0.1 else "idle",
            "source":          "simulation"
        }

        db._write("mppt_data", {
            k: float(v) if isinstance(v, (int, float)) else str(v)
            for k, v in mppt.items()
        }, tags={"location": "ehtp"}, ts=t)

        count += 1
        t += timedelta(seconds=10)

        if count % 1000 == 0:
            log.info(f"  Seeded {count} points ({(t - start).total_seconds()/3600:.1f}h)")

    log.info(f"Seed complete: {count} data points written ({hours}h of history)")

    # Trigger XGBoost training now that we have enough data
    try:
        from predict import engine as pred_engine
        log.info("Training XGBoost model on seeded data...")
        ok = pred_engine.retrain(db)
        if ok:
            log.info("XGBoost model trained successfully!")
        else:
            log.warning("XGBoost training deferred (will retry at midnight)")
    except Exception as e:
        log.warning(f"XGBoost training error: {e}")

    return True


if __name__ == "__main__":
    seed()
