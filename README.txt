╔══════════════════════════════════════════════════════════╗
║          GridGenius — EHTP CASABLANCA                    ║
║          Smart Micro-Grid Challenge — GIEW 2026          ║
╚══════════════════════════════════════════════════════════╝

STRUCTURE
─────────
GridGenius/
├── ai/
│   ├── influx_client.py   Source unique données (InfluxDB 1.x)
│   ├── collector.py       Modbus RS485 → MQTT
│   ├── predict.py         XGBoost + Open-Meteo (14j)
│   ├── battery_model.py   SOC dynamique LFP 48V
│   ├── smart_engine.py    Décision IA + planification événements
│   ├── anomaly.py         Détection anomalies
│   └── api.py             FastAPI port 8000
├── dashboard/
│   ├── app.py             Entry point Streamlit port 8501
│   └── pages/
│       ├── supervision.py     Temps réel (fragment 2s)
│       ├── predictions.py     Prédictions 14j
│       ├── planification.py   Événements + recommandations
│       └── parametres.py      Config admin
├── nodered/gridgenius_flow.json
├── systemd/systemd_services.txt
└── requirements.txt

INSTALLATION (Raspberry Pi 4)
─────────────────────────────
# InfluxDB
sudo apt install influxdb -y
sudo systemctl enable influxdb && sudo systemctl start influxdb
influx -execute "CREATE DATABASE microgrid"

# Dépendances Python
pip install -r requirements.txt --break-system-packages

# Copier les fichiers
cp -r ai/ /home/pi/GridGenius/ai/
cp -r dashboard/ /home/pi/GridGenius/dashboard/

# Services systemd
sudo cp systemd/systemd_services.txt /tmp/
# Voir instructions dans systemd_services.txt

DÉMARRAGE
─────────
sudo systemctl start gridgenius-api gridgenius-dashboard nodered

ACCÈS
─────
Streamlit  : http://[IP_PI]:8501
FastAPI    : http://[IP_PI]:8000/docs
Node-RED   : http://[IP_PI]:1880

TEST WINDOWS
────────────
cd ai       && uvicorn api:app --port 8000    (terminal 1)
cd dashboard && streamlit run app.py           (terminal 2)
Note : collector.py → simulation automatique sans matériel

ARCHITECTURE
────────────
[MPPT] → RS485 → collector.py → MQTT
                                  ↓
                             Node-RED
                             ├── InfluxDB (stockage)
                             ├── (30min) GET /predict
                             ├── (10s)   POST /decide → api.py
                             │              ↓ SAFE_MODE si KO
                             └── GPIO relais
                             Streamlit → api.py → InfluxDB

4 FONCTIONS GIEW 2026
─────────────────────
1. Alimentation  → smart_engine.decide() (heuristique IA)
2. Stockage      → battery_model.py (SOC dynamique LFP)
3. Planification → smart_engine.recommend_slots()
                   Score = α·PV + β·SOC - γ·Grid - δ·Conflit
4. Dashboard     → Streamlit multipage temps réel
