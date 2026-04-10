#!/usr/bin/env python3
"""
simulate.py — GridGenius Data Simulator
  Feeds realistic simulated MPPT data to the API every 10 seconds.
  Runs as a background process until the API is available, then loops.
  Fixed version: load_power in kW (not divided by 1000).
"""

import requests
import math
import random
import time
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [simulate] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

API = os.getenv("API_BASE_URL", "http://localhost:8000")

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

def wait_for_api(max_wait=60):
    log.info(f"Waiting for API at {API}...")
    for i in range(max_wait):
        try:
            r = requests.get(f"{API}/health", timeout=3)
            if r.status_code == 200:
                log.info("API ready — starting simulation")
                return True
        except Exception:
            pass
        time.sleep(1)
    log.error("API not reachable after timeout")
    return False


def run():
    if not wait_for_api(max_wait=60):
        return

    soc = 65.0
    log.info("Simulation loop started (10s interval)")

    while True:
        now  = datetime.now()
        h    = now.hour
        mins = now.minute

        # Smooth PV variation using sine for sub-hour interpolation
        base_pv  = PV_PROFILE.get(h, 0.0)
        next_pv  = PV_PROFILE.get((h + 1) % 24, 0.0)
        interp   = mins / 60.0
        pv_base  = base_pv + (next_pv - base_pv) * interp
        noise    = random.uniform(-0.15, 0.15)
        pv       = round(max(0.0, pv_base + noise), 2)

        # Load in kW with small random variation
        load_base = CONSO_PROFILE.get(h, 5)
        load      = round(max(0.5, load_base + random.uniform(-1.5, 1.5)), 2)

        # Battery SOC dynamics
        bilan = pv - load
        soc  += bilan * (10 / 3600) * 100 / 50  # 50 kWh battery, 10s steps
        soc   = round(max(15.0, min(95.0, soc)), 1)

        bat_voltage = round(44.0 + (soc / 100) * 14.4, 2)
        bat_current = round((pv - load) * 20, 1)
        bat_temp    = round(25.0 + (soc / 100) * 5 + random.uniform(-0.5, 0.5), 1)

        payload = {"mppt": {
            "pv_power":    pv,
            "pv_voltage":  round(72.0 if pv > 0.1 else 0.0, 2),
            "pv_current":  round(pv * 1000 / 72 if pv > 0.1 else 0.0, 2),
            "bat_soc":     soc,
            "bat_voltage": bat_voltage,
            "bat_current": bat_current,
            "bat_temp":    bat_temp,
            "load_power":  load
        }}

        try:
            r   = requests.post(f"{API}/decide", json=payload, timeout=5)
            dec = r.json()
            log.info(
                f"[{now.strftime('%H:%M:%S')}] "
                f"PV={pv:.1f}kW | Load={load:.1f}kW | "
                f"SOC={soc:.1f}% | → {dec.get('decision','?').upper()} "
                f"| {dec.get('reason','')[:30]}"
            )
        except Exception as e:
            log.warning(f"API error: {e}")

        time.sleep(10)


if __name__ == "__main__":
    run()
