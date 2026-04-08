#!/usr/bin/env python3
"""
predict.py — Prédiction IA GridGenius
  - Lit l'historique depuis InfluxDB (source unique)
  - XGBoost : prédiction consommation (lag features)
  - Open-Meteo : prédiction PV + correction bias horaire
  - Gère les états LEARNING / PARTIAL / OPERATIONAL
  - Écrit les résultats dans InfluxDB
  - Δt : 30 min
"""

import pickle, logging, requests
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

log = logging.getLogger(__name__)

# ── Constantes globales (importées par tous les modules) ────────
DELTA_T_H      = 0.5
P_PV_INSTALLED = 10.0
P_LOAD_MAX     = 40.0
LAT, LON       = 33.5731, -7.5898

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

PV_PROFILE = {
    0:0.0,1:0.0,2:0.0,3:0.0,4:0.0,5:0.0,6:0.5,
    7:1.5,8:3.0,9:5.0,10:7.0,11:8.5,12:9.0,13:8.8,
    14:8.0,15:6.5,16:4.5,17:2.5,18:0.8,
    19:0.0,20:0.0,21:0.0,22:0.0,23:0.0
}
CONSO_PROFILE = {
    0:3,1:3,2:3,3:3,4:3,5:3,6:3,
    7:8,8:28,9:28,10:28,11:28,12:12,13:12,
    14:25,15:25,16:25,17:25,18:5,19:5,20:5,21:5,22:5,23:5
}


# ── Open-Meteo + correction bias horaire ───────────────────────
class WeatherFetcher:
    URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self):
        p = MODELS_DIR / "meteo_correction.pkl"
        self.correction = pickle.load(open(p,'rb')) if p.exists() \
                          else {h: 1.0 for h in range(24)}

    def update_correction(self, mppt_history: list):
        """mppt_history : liste de dicts depuis InfluxDB"""
        ratios = defaultdict(list)
        for r in mppt_history:
            ts = r.get('time') or r.get('timestamp','')
            try:
                h  = datetime.fromisoformat(ts.replace('Z','+00:00')).hour
                pm = float(r.get('pv_meteo', 0))
                if pm > 0.1:
                    ratios[h].append(float(r['pv_power']) / pm)
            except Exception:
                pass
        for h, v in ratios.items():
            if v: self.correction[h] = float(np.mean(v))
        pickle.dump(self.correction, open(MODELS_DIR/"meteo_correction.pkl",'wb'))

    def fetch(self, days: int = 14) -> list:
        try:
            resp = requests.get(self.URL, timeout=10, params={
                "latitude": LAT, "longitude": LON,
                "hourly": ["shortwave_radiation","temperature_2m","cloudcover"],
                "forecast_days": min(days, 16),
                "timezone": "Africa/Casablanca"
            })
            resp.raise_for_status()
            hourly = resp.json()['hourly']
            result = []
            for i, ts in enumerate(hourly['time']):
                dt  = datetime.fromisoformat(ts)
                h   = dt.hour
                G   = float(hourly['shortwave_radiation'][i] or 0) / 1000
                T   = float(hourly['temperature_2m'][i] or 25)
                cld = float(hourly['cloudcover'][i] or 0)
                pv  = max(0, min(G*(P_PV_INSTALLED/0.18)*0.18*(1-0.004*(T-25)),
                                 P_PV_INSTALLED))
                pv_corr = max(0, min(pv*self.correction.get(h,1.0), P_PV_INSTALLED))
                for half in range(2):
                    result.append({
                        "timestamp":       (dt+timedelta(minutes=30*half)).isoformat(),
                        "hour":            h,
                        "cloudcover":      cld,
                        "pv_estimate_kw":  round(pv, 3),
                        "pv_corrected_kw": round(pv_corr, 3)
                    })
            log.info(f"Open-Meteo : {len(result)} points ({days}j)")
            return result
        except Exception as e:
            log.warning(f"Open-Meteo indisponible ({e}) → profil solaire fixe")
            now = datetime.now().replace(minute=0, second=0, microsecond=0)
            return [{"timestamp":(now+timedelta(minutes=30*i)).isoformat(),
                     "hour":(now+timedelta(minutes=30*i)).hour,
                     "cloudcover":0,
                     "pv_estimate_kw": PV_PROFILE.get((now+timedelta(minutes=30*i)).hour,0),
                     "pv_corrected_kw":PV_PROFILE.get((now+timedelta(minutes=30*i)).hour,0)}
                    for i in range(days*48)]


# ── XGBoost consommation ───────────────────────────────────────
class XGBoostPredictor:
    """
    Entraînement et prédiction depuis données InfluxDB.
    Pas de prédiction si données insuffisantes (LEARNING).
    Retrain journalier automatique.
    """

    def __init__(self):
        self.model        = None
        self.rmse_by_hour = {h: 2.0 for h in range(24)}
        self._load()

    def _load(self):
        mp = MODELS_DIR / "xgb_consumption.pkl"
        rp = MODELS_DIR / "xgb_rmse.pkl"
        if mp.exists():
            self.model        = pickle.load(open(mp,'rb'))
            self.rmse_by_hour = pickle.load(open(rp,'rb')) if rp.exists() \
                                else self.rmse_by_hour
            log.info("XGBoost chargé")

    def _features(self, dt, hist_kw, event_kw=0.0):
        def lag(n):
            i = len(hist_kw) - n
            return float(hist_kw[i]) if i >= 0 else CONSO_PROFILE.get(dt.hour, 5)
        w3h  = hist_kw[-6:]  if len(hist_kw) >= 6  else hist_kw
        w24h = hist_kw[-48:] if len(hist_kw) >= 48 else hist_kw
        return [
            dt.hour, dt.weekday(), dt.month,
            int(dt.weekday()>=5), int(8<=dt.hour<=18),
            int(dt.month in [7,8]),
            lag(1), lag(2), lag(48), lag(336),
            float(np.mean(w3h))  if w3h  else 5.0,
            float(np.mean(w24h)) if w24h else 5.0,
            float(event_kw)
        ]

    def train_from_influx(self, db) -> bool:
        """
        Entraîne le modèle depuis l'historique InfluxDB.
        Appelé par Node-RED (retrain journalier à minuit).
        Retourne False si données insuffisantes.
        """
        status = db.get_data_status()
        if not status['can_predict']:
            log.info(f"Entraînement impossible : {status['message']}")
            return False
        try:
            import xgboost as xgb
            from sklearn.model_selection import train_test_split

            history = db.get_mppt_history(hours=status['hours_of_data'])
            if len(history) < 100:
                log.warning("Historique insuffisant pour l'entraînement")
                return False

            kw = [float(r.get('load_power', 5)) for r in history]
            X, y = [], []
            for i, r in enumerate(history):
                if i < 48: continue
                try:
                    ts = r.get('time') or r.get('timestamp','')
                    dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
                    X.append(self._features(dt, kw[max(0,i-336):i]))
                    y.append(kw[i])
                except Exception:
                    pass

            if len(X) < 50:
                return False

            X, y   = np.array(X), np.array(y)
            Xtr,Xv,ytr,yv = train_test_split(X, y, test_size=0.1, shuffle=False)
            m = xgb.XGBRegressor(n_estimators=200, max_depth=5,
                                  learning_rate=0.05, verbosity=0)
            m.fit(Xtr, ytr, eval_set=[(Xv,yv)], verbose=False)

            preds = m.predict(Xv)
            rmse  = {}
            val_h = history[len(Xtr)+48:]
            for h in range(24):
                idx = [i for i,r in enumerate(val_h) if i < len(preds) and
                       datetime.fromisoformat((r.get('time') or r.get('timestamp','')).
                                              replace('Z','+00:00')).hour == h]
                rmse[h] = float(np.sqrt(np.mean([(preds[i]-yv[i])**2
                                                  for i in idx]))) if idx else 2.0

            pickle.dump(m,    open(MODELS_DIR/"xgb_consumption.pkl",'wb'))
            pickle.dump(rmse, open(MODELS_DIR/"xgb_rmse.pkl",'wb'))
            self.model, self.rmse_by_hour = m, rmse
            log.info(f"XGBoost entraîné ({len(X)} points)")
            return True

        except Exception as e:
            log.error(f"Erreur entraînement XGBoost : {e}")
            return False

    def predict(self, horizon_ts: list, hist_kw: list,
                events: list = None, confidence: int = 100) -> list:
        """
        Prédit la consommation.
        Si modèle absent → retourne None (état LEARNING).
        """
        if self.model is None:
            return None   # Signale l'état LEARNING à l'orchestrateur

        events, result, kw_hist = events or [], [], list(hist_kw)

        def ev_kw(dt):
            ts, day = dt.strftime("%H:%M"), dt.strftime("%Y-%m-%d")
            return sum(float(e.get('expected_kw',0)) for e in events
                       if e.get('date')==day
                       and e.get('start','00:00')<=ts<=e.get('end','23:59'))

        for ts in horizon_ts:
            dt  = datetime.fromisoformat(ts) if isinstance(ts,str) else ts
            ekw = ev_kw(dt)
            try:
                pred = float(self.model.predict(
                    np.array([self._features(dt, kw_hist, ekw)]))[0])
                pred = max(pred, ekw, 0)
                src  = "xgboost"
            except Exception:
                pred = CONSO_PROFILE.get(dt.hour,5) + ekw
                src  = "profile"

            sigma = self.rmse_by_hour.get(dt.hour, 2.0)
            # Augmenter l'incertitude si confiance réduite
            sigma = sigma * (1 + (100-confidence)/100)

            result.append({
                "timestamp":    dt.isoformat(),
                "hour":         dt.hour,
                "predicted_kw": round(pred, 2),
                "event_kw":     round(ekw, 2),
                "sigma":        round(sigma, 2),
                "ci_lower":     round(max(0, pred-1.96*sigma), 2),
                "ci_upper":     round(min(P_LOAD_MAX, pred+1.96*sigma), 2),
                "source":       src
            })
            kw_hist.append(pred)
        return result


# ── Orchestrateur ──────────────────────────────────────────────
class PredictionEngine:
    """
    Point d'entrée unique pour les prédictions.
    Lit depuis InfluxDB, écrit les résultats dans InfluxDB.
    """

    def __init__(self):
        self.weather = WeatherFetcher()
        self.xgb     = XGBoostPredictor()

    def predict(self, db, days: int = 14, events: list = None) -> dict:
        """
        Lance la prédiction complète.
        db : instance InfluxClient (source unique)
        Retourne dict avec status, pv[], consumption[], daily_summary{}
        """
        from influx_client import InfluxClient
        events   = events or []
        status   = db.get_data_status()
        start_dt = datetime.now().replace(minute=0, second=0, microsecond=0)

        # ── PV : toujours disponible (Open-Meteo) ──────────────
        wp = [p for p in self.weather.fetch(days)
              if datetime.fromisoformat(p['timestamp']) >= start_dt]

        # ── Consommation : selon état apprentissage ────────────
        if not status['can_predict']:
            # LEARNING → pas de prédiction
            return {
                "status":        "LEARNING",
                "message":       status['message'],
                "hours_of_data": status['hours_of_data'],
                "confidence_pct": 0,
                "pv":            wp,
                "consumption":   None,
                "daily_summary": None,
                "generated_at":  datetime.now().isoformat()
            }

        # Récupérer historique récent depuis InfluxDB
        history = db.get_mppt_history(hours=336)
        hist_kw = [float(r.get('load_power', 5)) for r in history] \
                  if history else [5.0] * 48

        conso = self.xgb.predict(
            [p['timestamp'] for p in wp],
            hist_kw,
            events,
            status['confidence_pct']
        )

        if conso is None:
            # XGBoost pas encore entraîné
            return {
                "status":         "LEARNING",
                "message":        "Modèle XGBoost non entraîné — données insuffisantes",
                "hours_of_data":  status['hours_of_data'],
                "confidence_pct": 0,
                "pv":             wp,
                "consumption":    None,
                "daily_summary":  None,
                "generated_at":   datetime.now().isoformat()
            }

        # Résumé journalier
        daily = {}
        for i in range(days):
            day   = str((start_dt+timedelta(days=i)).date())
            pv_d  = [p for p in wp    if p['timestamp'].startswith(day)]
            co_d  = [p for p in conso if p['timestamp'].startswith(day)]
            pv_kwh= sum(p['pv_corrected_kw']*DELTA_T_H for p in pv_d)
            co_kwh= sum(p['predicted_kw']   *DELTA_T_H for p in co_d)
            daily[day] = {
                "date":            day,
                "pv_kwh":          round(pv_kwh, 2),
                "consumption_kwh": round(co_kwh, 2),
                "autonomy_pct":    round(min(100,pv_kwh/co_kwh*100)
                                         if co_kwh>0 else 0, 1),
                "peak_pv_kw":      round(max((p['pv_corrected_kw']
                                              for p in pv_d), default=0), 2),
                "peak_conso_kw":   round(max((p['predicted_kw']
                                              for p in co_d), default=0), 2),
                "is_autonomous":   pv_kwh >= co_kwh
            }

        result = {
            "status":         status['status'],
            "message":        status['message'],
            "confidence_pct": status['confidence_pct'],
            "horizon_days":   days,
            "start":          start_dt.isoformat(),
            "delta_t_min":    int(DELTA_T_H*60),
            "n_points":       len(wp),
            "pv":             wp,
            "consumption":    conso,
            "daily_summary":  daily,
            "generated_at":   datetime.now().isoformat()
        }

        # Écrire dans InfluxDB pour que /decide puisse lire
        db.write_predictions(wp,    "pv")
        db.write_predictions(conso, "consumption")

        log.info(f"Prédiction {days}j | statut={status['status']} | "
                 f"confiance={status['confidence_pct']}%")
        return result

    def retrain(self, db) -> bool:
        """Retrain journalier depuis InfluxDB (appelé par Node-RED à minuit)"""
        ok = self.xgb.train_from_influx(db)
        if ok:
            self.weather.update_correction(db.get_mppt_history(hours=720))
        return ok


engine = PredictionEngine()
