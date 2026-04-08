#!/usr/bin/env python3
"""
feed_api.py — GridGenius Manual Feed Test Script
  Sends simulated MPPT data to the API every 10 seconds.
  Use this for manual testing only — the app uses simulate.py automatically.

  Usage: python3 feed_api.py
"""

import requests
import random
import time
from datetime import datetime

API = "http://localhost:8000"

PV_PROFILE = {
    0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.5,
    7: 1.5, 8: 3.0, 9: 5.0, 10: 7.0, 11: 8.5, 12: 9.0, 13: 8.8,
    14: 8.0, 15: 6.5, 16: 4.5, 17: 2.5, 18: 0.8,
    19: 0.0, 20: 0.0, 21: 0.0, 22: 0.0, 23: 0.0
}

CONSO_PROFILE = {
    0: 3, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3, 6: 4,
    7: 8, 8: 28, 9: 30, 10: 32, 11: 30, 12: 14, 13: 12,
    14: 28, 15: 30, 16: 28, 17: 22, 18: 8, 19: 6,
    20: 5, 21: 4, 22: 4, 23: 3
}

try:
    requests.get(f"{API}/health", timeout=3)
    print("GridGenius API connected\n")
except Exception:
    print("API not reachable — make sure the app is running first"); exit(1)

soc = 65.0

while True:
    now  = datetime.now()
    h    = now.hour

    pv   = max(0.0, PV_PROFILE.get(h, 0.0) + random.uniform(-0.2, 0.2))
    load = max(0.5, CONSO_PROFILE.get(h, 5) + random.uniform(-1.5, 1.5))  # kW

    bilan = pv - load
    soc  += bilan * (10 / 3600) * 100 / 50
    soc   = round(max(15.0, min(95.0, soc)), 1)

    payload = {"mppt": {
        "pv_power":    round(pv, 2),
        "pv_voltage":  round(72.0 if pv > 0.1 else 0.0, 2),
        "pv_current":  round(pv * 1000 / 72 if pv > 0.1 else 0.0, 2),
        "bat_soc":     soc,
        "bat_voltage": round(44.0 + (soc / 100) * 14.4, 2),
        "bat_current": round((pv - load) * 20, 1),
        "bat_temp":    round(26 + (soc / 100) * 4, 1),
        "load_power":  round(load, 2)
    }}

    try:
        r   = requests.post(f"{API}/decide", json=payload, timeout=5)
        dec = r.json()
        print(f"[{now.strftime('%H:%M:%S')}] "
              f"PV={pv:.2f}kW | Load={load:.2f}kW | "
              f"SOC={soc:.1f}% | -> {dec.get('decision','?').upper()} "
              f"| {dec.get('reason','')[:30]}")
    except Exception as e:
        print(f"Error: {e}")

    time.sleep(10)
