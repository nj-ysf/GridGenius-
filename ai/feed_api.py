import requests, math, random, time
from datetime import datetime

API    = "http://localhost:8000"
PYTHON = r"C:\Users\Moussa\AppData\Local\Programs\Python\Python310\python.exe"
soc    = 65.0

PV_PROFILE = {
    0:0,1:0,2:0,3:0,4:0,5:0,6:0.5,
    7:1.5,8:3.0,9:5.0,10:7.0,11:8.5,12:9.0,13:8.8,
    14:8.0,15:6.5,16:4.5,17:2.5,18:0.8,
    19:0,20:0,21:0,22:0,23:0
}
CONSO_PROFILE = {
    0:3,1:3,2:3,3:3,4:3,5:3,6:4,
    7:8,8:28,9:30,10:32,11:30,12:14,13:12,
    14:28,15:30,16:28,17:22,18:8,19:6,
    20:5,21:4,22:4,23:3
}

try:
    requests.get(f"{API}/health", timeout=3)
    print("✅ GridGenius API connectee\n")
except:
    print("❌ API non accessible — lancez Terminal 2 d'abord !"); exit(1)

while True:
    now  = datetime.now()
    h    = now.hour
    pv   = max(0, PV_PROFILE.get(h, 0) * (0.88 + random.uniform(0, 0.15)))
    load = CONSO_PROFILE.get(h, 5) / 1000

    bilan = pv - load
    soc  += bilan * (10/3600) * 100 / 50
    soc   = round(max(15.0, min(95.0, soc)), 1)

    payload = {"mppt": {
        "pv_power":    round(pv, 2),
        "pv_voltage":  round(72.0 if pv > 0.1 else 0.0, 2),
        "pv_current":  round(pv*1000/72 if pv > 0.1 else 0, 2),
        "bat_soc":     soc,
        "bat_voltage": round(44.0 + (soc/100)*14.4, 2),
        "bat_current": round((pv - load)*20, 1),
        "bat_temp":    round(26 + (soc/100)*4, 1),
        "load_power":  round(load, 3)
    }}

    try:
        r   = requests.post(f"{API}/decide", json=payload, timeout=5)
        dec = r.json()
        print(f"[{now.strftime('%H:%M:%S')}] "
              f"PV={pv:.2f}kW | Charge={load:.2f}kW | "
              f"SOC={soc:.1f}% | → {dec.get('decision','?').upper()} "
              f"| {dec.get('reason','')[:25]}")
    except Exception as e:
        print(f"❌ {e}")

    time.sleep(10)