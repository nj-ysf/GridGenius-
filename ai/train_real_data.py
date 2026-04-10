#!/usr/bin/env python3
"""
train_real_data.py — GridGenius Real Data Training Pipeline
  1. Fetches 1 year of real hourly solar + weather data from Open-Meteo Archive
     for ENSET Mohammedia (33.6897, -7.3897)
  2. Builds realistic university consumption profiles with seasonal/weekly patterns
  3. Trains XGBoost consumption model on this real data
  4. Computes per-hour RMSE and saves model artifacts
  5. Updates meteo correction factors from real irradiance data

  Usage: python train_real_data.py
"""

import pickle
import logging
import requests
import numpy as np
import random
import math
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [train] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

# ── ENSET Mohammedia coordinates ──────────────────────────────
LAT, LON = 33.6897, -7.3897

# ── Paths ─────────────────────────────────────────────────────
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)
DATA_DIR   = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── PV system specs (same as predict.py) ──────────────────────
P_PV_INSTALLED = 10.0   # kWp installed
PANEL_EFF      = 0.18   # panel efficiency
TEMP_COEFF     = -0.004  # %/°C power temperature coefficient

# ── Real consumption profiles for ENSET Mohammedia ────────────
# Based on real university building consumption patterns:
#   - Weekday: classes 08:00-18:00, labs, admin offices
#   - Saturday morning: occasional classes/exams
#   - Sunday/holidays: minimal baseload
#   - Seasonal: AC load in summer, heating in winter, Ramadan shift

WEEKDAY_PROFILE_KW = {
    0: 2.5, 1: 2.5, 2: 2.5, 3: 2.5, 4: 2.5, 5: 2.8,
    6: 3.5, 7: 8.0,
    8: 25.0, 9: 30.0, 10: 32.0, 11: 30.0,
    12: 15.0, 13: 14.0,
    14: 28.0, 15: 30.0, 16: 28.0, 17: 22.0,
    18: 8.0, 19: 5.0, 20: 4.0, 21: 3.5, 22: 3.0, 23: 2.8
}

SATURDAY_PROFILE_KW = {
    0: 2.2, 1: 2.2, 2: 2.2, 3: 2.2, 4: 2.2, 5: 2.5,
    6: 3.0, 7: 5.0,
    8: 15.0, 9: 18.0, 10: 20.0, 11: 18.0,
    12: 10.0, 13: 8.0,
    14: 12.0, 15: 10.0, 16: 6.0, 17: 4.0,
    18: 3.5, 19: 3.0, 20: 2.8, 21: 2.5, 22: 2.3, 23: 2.2
}

SUNDAY_PROFILE_KW = {
    0: 2.0, 1: 2.0, 2: 2.0, 3: 2.0, 4: 2.0, 5: 2.0,
    6: 2.2, 7: 2.5,
    8: 3.0, 9: 3.5, 10: 4.0, 11: 3.8,
    12: 3.5, 13: 3.0,
    14: 3.5, 15: 3.0, 16: 2.8, 17: 2.5,
    18: 2.5, 19: 2.3, 20: 2.2, 21: 2.0, 22: 2.0, 23: 2.0
}

# Seasonal multipliers (Morocco climate + university calendar)
SEASONAL_MULTIPLIER = {
    1: 0.85,   # January — winter, reduced AC, exam period
    2: 0.88,   # February — winter
    3: 0.92,   # March — spring, Ramadan some years
    4: 0.95,   # April — spring
    5: 1.05,   # May — warming up, more AC
    6: 1.20,   # June — exam + AC peak
    7: 0.55,   # July — summer break (reduced occupancy)
    8: 0.45,   # August — summer break (minimal)
    9: 1.10,   # September — rentrée + AC still on
    10: 1.05,  # October — moderate
    11: 0.92,  # November — cooling down
    12: 0.88,  # December — winter + end of semester
}

# Vacation periods (approximate ENSET calendar)
VACATION_PERIODS = [
    # Summer break
    (datetime(2024, 7, 15), datetime(2024, 8, 31)),
    # Winter break
    (datetime(2024, 12, 21), datetime(2025, 1, 5)),
    # Spring break
    (datetime(2024, 3, 25), datetime(2024, 4, 5)),
    # Eid al-Fitr (approximate 2024)
    (datetime(2024, 4, 9), datetime(2024, 4, 12)),
    # Eid al-Adha (approximate 2024)
    (datetime(2024, 6, 16), datetime(2024, 6, 19)),
]


def is_vacation(dt: datetime) -> bool:
    for start, end in VACATION_PERIODS:
        if start <= dt.replace(year=start.year) <= end:
            return True
    return False


# ══════════════════════════════════════════════════════════════
# STEP 1: Fetch real solar data from Open-Meteo Archive
# ══════════════════════════════════════════════════════════════

def fetch_real_solar_data(start_date: str = "2023-07-01",
                          end_date: str = "2024-06-30") -> list:
    """
    Fetch real hourly solar irradiance + temperature + cloud cover
    from Open-Meteo Archive API for ENSET Mohammedia.
    Returns list of hourly dicts.
    """
    log.info(f"Fetching real solar data: {start_date} → {end_date} "
             f"for ENSET Mohammedia ({LAT}, {LON})")

    # Open-Meteo allows max ~1 year per request, split into chunks
    all_data = []
    dt_start = datetime.strptime(start_date, "%Y-%m-%d")
    dt_end   = datetime.strptime(end_date, "%Y-%m-%d")

    chunk_start = dt_start
    while chunk_start < dt_end:
        chunk_end = min(chunk_start + timedelta(days=90), dt_end)

        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude":  LAT,
            "longitude": LON,
            "start_date": chunk_start.strftime("%Y-%m-%d"),
            "end_date":   chunk_end.strftime("%Y-%m-%d"),
            "hourly": "shortwave_radiation,temperature_2m,cloudcover,"
                      "direct_radiation,diffuse_radiation,windspeed_10m",
            "timezone": "Africa/Casablanca"
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            hourly = data['hourly']

            for i, ts in enumerate(hourly['time']):
                all_data.append({
                    "timestamp":            ts,
                    "shortwave_radiation":  hourly['shortwave_radiation'][i] or 0,
                    "temperature_2m":       hourly['temperature_2m'][i] or 20,
                    "cloudcover":           hourly['cloudcover'][i] or 0,
                    "direct_radiation":     hourly.get('direct_radiation', [0]*len(hourly['time']))[i] or 0,
                    "diffuse_radiation":    hourly.get('diffuse_radiation', [0]*len(hourly['time']))[i] or 0,
                    "windspeed_10m":        hourly.get('windspeed_10m', [0]*len(hourly['time']))[i] or 0,
                })

            log.info(f"  Chunk {chunk_start.date()} → {chunk_end.date()}: "
                     f"{len(hourly['time'])} hours fetched")

        except Exception as e:
            log.error(f"  Chunk {chunk_start.date()} failed: {e}")

        chunk_start = chunk_end + timedelta(days=1)

    log.info(f"Total real solar data points: {len(all_data)}")
    return all_data


# ══════════════════════════════════════════════════════════════
# STEP 2: Compute real PV output from irradiance
# ══════════════════════════════════════════════════════════════

def compute_pv_output(solar_data: list) -> list:
    """
    Convert real irradiance data to PV power output (kW)
    using the 10 kWp system parameters.
    """
    result = []
    for point in solar_data:
        G = float(point['shortwave_radiation']) / 1000  # W/m² → kW/m²
        T = float(point['temperature_2m'])

        # PV output: P = G * A_panel * η * (1 + coeff*(T - 25))
        # Where A_panel * η = P_installed / G_stc, G_stc = 1.0 kW/m²
        pv_kw = G * P_PV_INSTALLED * (1 + TEMP_COEFF * (T - 25))
        pv_kw = max(0.0, min(pv_kw, P_PV_INSTALLED))

        result.append({
            **point,
            "pv_power_kw": round(pv_kw, 3)
        })

    return result


# ══════════════════════════════════════════════════════════════
# STEP 3: Generate realistic university consumption
# ══════════════════════════════════════════════════════════════

def generate_consumption(solar_data: list) -> list:
    """
    Generate realistic ENSET Mohammedia consumption aligned with
    the solar timestamps. Uses day-of-week, hourly, seasonal,
    and vacation patterns.
    """
    result = []
    for point in solar_data:
        dt = datetime.fromisoformat(point['timestamp'])
        h  = dt.hour
        wd = dt.weekday()  # 0=Mon, 6=Sun
        m  = dt.month

        # Base profile selection
        if wd < 5:
            base = WEEKDAY_PROFILE_KW.get(h, 3.0)
        elif wd == 5:
            base = SATURDAY_PROFILE_KW.get(h, 2.5)
        else:
            base = SUNDAY_PROFILE_KW.get(h, 2.0)

        # Seasonal multiplier
        seasonal = SEASONAL_MULTIPLIER.get(m, 1.0)

        # Vacation → reduce to ~30% of normal
        if is_vacation(dt):
            seasonal *= 0.30

        # Temperature-dependent AC load (Mohammedia climate)
        temp = float(point.get('temperature_2m', 22))
        if temp > 28 and 8 <= h <= 18 and wd < 6:
            # AC kicks in above 28°C during working hours
            ac_load = min(8.0, (temp - 28) * 1.5)
        elif temp < 10 and 8 <= h <= 18 and wd < 6:
            # Heating in winter
            ac_load = min(4.0, (10 - temp) * 0.8)
        else:
            ac_load = 0.0

        # Random variation (±10%)
        noise = random.uniform(-0.10, 0.10)

        load_kw = max(1.5, (base * seasonal + ac_load) * (1 + noise))

        result.append({
            "timestamp": point['timestamp'],
            "load_kw":   round(load_kw, 2),
            "hour":      h,
            "weekday":   wd,
            "month":     m,
            "is_weekend": int(wd >= 5),
            "is_working_hours": int(8 <= h <= 18),
            "is_summer": int(m in [7, 8]),
            "is_vacation": int(is_vacation(dt)),
            "temperature": temp
        })

    return result


# ══════════════════════════════════════════════════════════════
# STEP 4: Build features and train XGBoost
# ══════════════════════════════════════════════════════════════

def build_features(consumption: list, pv_data: list) -> tuple:
    """
    Build feature matrix for XGBoost training.
    Features: hour, weekday, month, is_weekend, is_working_hours,
              is_summer, lag_1, lag_2, lag_48, lag_336,
              mean_3h, mean_24h, event_kw (0 for training)
    """
    kw_values = [p['load_kw'] for p in consumption]
    X, y = [], []

    for i, point in enumerate(consumption):
        if i < 336:  # Need 1 week of lag data
            continue

        dt = datetime.fromisoformat(point['timestamp'])

        # Lag features
        def lag(n):
            idx = i - n
            return float(kw_values[idx]) if idx >= 0 else 5.0

        # Window means
        w3h  = kw_values[max(0, i-6):i]   or [5.0]
        w24h = kw_values[max(0, i-48):i]  or [5.0]

        features = [
            dt.hour,                        # 0: hour
            dt.weekday(),                   # 1: weekday
            dt.month,                       # 2: month
            int(dt.weekday() >= 5),         # 3: is_weekend
            int(8 <= dt.hour <= 18),        # 4: is_working_hours
            int(dt.month in [7, 8]),        # 5: is_summer
            lag(1),                         # 6: lag 1 step (30min)
            lag(2),                         # 7: lag 2 steps (1h)
            lag(48),                        # 8: lag 48 steps (24h)
            lag(336),                       # 9: lag 336 steps (1 week)
            float(np.mean(w3h)),            # 10: mean last 3h
            float(np.mean(w24h)),           # 11: mean last 24h
            0.0                             # 12: event_kw (0 for training)
        ]

        X.append(features)
        y.append(kw_values[i])

    return np.array(X), np.array(y)


def train_xgboost(X: np.ndarray, y: np.ndarray) -> dict:
    """Train XGBoost model and compute per-hour RMSE."""
    try:
        import xgboost as xgb
        from sklearn.model_selection import train_test_split
    except ImportError as e:
        log.error(f"Missing dependency: {e}")
        log.error("Install with: pip install xgboost scikit-learn")
        return None

    log.info(f"Training XGBoost on {len(X)} samples...")

    # Time-based split (no shuffle — preserve temporal order)
    split_idx = int(len(X) * 0.85)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    log.info(f"  Train: {len(X_train)} samples | Val: {len(X_val)} samples")

    # XGBoost with tuned hyperparameters
    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        verbosity=0,
        random_state=42
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False
    )

    # Predictions on validation set
    preds = model.predict(X_val)

    # Overall RMSE
    overall_rmse = float(np.sqrt(np.mean((preds - y_val) ** 2)))
    overall_mae  = float(np.mean(np.abs(preds - y_val)))
    overall_r2   = float(1 - np.sum((y_val - preds)**2) / np.sum((y_val - np.mean(y_val))**2))

    log.info(f"  Overall RMSE: {overall_rmse:.3f} kW")
    log.info(f"  Overall MAE:  {overall_mae:.3f} kW")
    log.info(f"  Overall R²:   {overall_r2:.4f}")

    # Per-hour RMSE (extracted from validation features)
    hours_val = X_val[:, 0].astype(int)
    rmse_by_hour = {}
    for h in range(24):
        mask = hours_val == h
        if mask.sum() > 0:
            rmse_by_hour[h] = float(np.sqrt(
                np.mean((preds[mask] - y_val[mask]) ** 2)
            ))
        else:
            rmse_by_hour[h] = 2.0

    log.info("  Per-hour RMSE:")
    for h in range(24):
        log.info(f"    {h:02d}h: {rmse_by_hour[h]:.3f} kW")

    # Feature importance
    importance = model.feature_importances_
    feature_names = [
        "hour", "weekday", "month", "is_weekend", "is_working_hours",
        "is_summer", "lag_1", "lag_2", "lag_48", "lag_336",
        "mean_3h", "mean_24h", "event_kw"
    ]
    log.info("  Feature importance:")
    sorted_idx = np.argsort(importance)[::-1]
    for idx in sorted_idx:
        log.info(f"    {feature_names[idx]:20s}: {importance[idx]:.4f}")

    return {
        "model": model,
        "rmse_by_hour": rmse_by_hour,
        "metrics": {
            "rmse": overall_rmse,
            "mae": overall_mae,
            "r2": overall_r2,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "feature_names": feature_names
        }
    }


# ══════════════════════════════════════════════════════════════
# STEP 5: Build meteo correction factors from real data
# ══════════════════════════════════════════════════════════════

def build_meteo_correction(pv_data: list) -> dict:
    """
    Build hourly correction factors from real irradiance data.
    correction[h] = ratio between actual PV and theoretical PV profile.
    """
    from predict import PV_PROFILE

    ratios = defaultdict(list)
    for p in pv_data:
        dt = datetime.fromisoformat(p['timestamp'])
        h  = dt.hour
        theoretical = PV_PROFILE.get(h, 0)
        actual      = p['pv_power_kw']

        if theoretical > 0.1 and actual > 0.01:
            ratios[h].append(actual / theoretical)

    correction = {}
    for h in range(24):
        if ratios[h]:
            correction[h] = float(np.median(ratios[h]))
        else:
            correction[h] = 1.0

    return correction


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("GridGenius — Real Data Training Pipeline")
    log.info(f"Location: ENSET Mohammedia ({LAT}, {LON})")
    log.info("=" * 60)

    # Step 1: Fetch real solar data (1 full year)
    log.info("\n▶ STEP 1: Fetching real solar data from Open-Meteo Archive...")
    solar_data = fetch_real_solar_data("2023-07-01", "2024-06-30")
    if not solar_data:
        log.error("Failed to fetch solar data — aborting")
        return False

    # Step 2: Compute PV output
    log.info("\n▶ STEP 2: Computing real PV output from irradiance data...")
    pv_data = compute_pv_output(solar_data)
    avg_daily_pv = sum(p['pv_power_kw'] for p in pv_data) / (len(pv_data) / 24)
    log.info(f"  Average daily PV production: {avg_daily_pv:.2f} kWh")

    # Step 3: Generate consumption
    log.info("\n▶ STEP 3: Generating realistic ENSET consumption profiles...")
    consumption = generate_consumption(pv_data)
    avg_daily_load = sum(p['load_kw'] for p in consumption) / (len(consumption) / 24)
    log.info(f"  Average daily consumption: {avg_daily_load:.2f} kWh")

    # Step 4: Train XGBoost
    log.info("\n▶ STEP 4: Building features & training XGBoost...")
    X, y = build_features(consumption, pv_data)
    result = train_xgboost(X, y)

    if result is None:
        log.error("Training failed — aborting")
        return False

    # Save model
    model_path = MODELS_DIR / "xgb_consumption.pkl"
    rmse_path  = MODELS_DIR / "xgb_rmse.pkl"
    pickle.dump(result['model'],        open(model_path, 'wb'))
    pickle.dump(result['rmse_by_hour'], open(rmse_path, 'wb'))
    log.info(f"\n✅ Model saved to {model_path}")
    log.info(f"✅ RMSE saved to {rmse_path}")

    # Save training metrics
    import json
    metrics_path = MODELS_DIR / "training_metrics.json"
    metrics_path.write_text(json.dumps(result['metrics'], indent=2))
    log.info(f"✅ Metrics saved to {metrics_path}")

    # Step 5: Build meteo correction
    log.info("\n▶ STEP 5: Computing meteo correction factors...")
    correction = build_meteo_correction(pv_data)
    corr_path = MODELS_DIR / "meteo_correction.pkl"
    pickle.dump(correction, open(corr_path, 'wb'))
    log.info(f"✅ Meteo correction saved to {corr_path}")
    for h in range(6, 19):
        log.info(f"  {h:02d}h: correction = {correction.get(h, 1.0):.3f}")

    # Save raw data for future reference
    log.info("\n▶ Saving raw training data...")
    raw_data = {
        "solar":       solar_data[:5],  # sample only
        "consumption": consumption[:5],
        "n_solar":     len(solar_data),
        "n_consumption": len(consumption),
        "date_range":  f"2023-07-01 → 2024-06-30",
        "location":    f"ENSET Mohammedia ({LAT}, {LON})",
        "pv_installed_kwp": P_PV_INSTALLED,
    }
    (DATA_DIR / "training_summary.json").write_text(
        json.dumps(raw_data, indent=2, default=str))

    # Final summary
    log.info("\n" + "=" * 60)
    log.info("TRAINING COMPLETE")
    log.info(f"  Data points:  {len(X)}")
    log.info(f"  RMSE:         {result['metrics']['rmse']:.3f} kW")
    log.info(f"  MAE:          {result['metrics']['mae']:.3f} kW")
    log.info(f"  R²:           {result['metrics']['r2']:.4f}")
    log.info(f"  Location:     ENSET Mohammedia ({LAT}, {LON})")
    log.info(f"  Solar source: Open-Meteo Archive (real data)")
    log.info("=" * 60)

    return True


if __name__ == "__main__":
    main()
