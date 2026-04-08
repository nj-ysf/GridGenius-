# GridGenius — Smart Micro-Grid Management System

## Overview

GridGenius is an intelligent micro-grid management system built for the EHTP Casablanca Smart Micro-Grid Challenge (GIEW 2026). It optimizes energy consumption and storage using solar power, battery storage, and the national grid (ONEE).

## Architecture

- **Frontend**: Streamlit dashboard (port 5000)
- **Backend**: FastAPI REST API (port 8000)  
- **Database**: InfluxDB 1.x (port 8086) — time-series data for MPPT, predictions, decisions

## Project Structure

```
GridGenius/
├── ai/                 # Core Intelligence & Backend API
│   ├── api.py          # FastAPI entry point (port 8000)
│   ├── smart_engine.py # Optimization logic & event scheduling
│   ├── predict.py      # XGBoost & Open-Meteo prediction engine
│   ├── battery_model.py# Digital twin of 48V LFP battery
│   ├── collector.py    # Modbus/RS485 data collection (with simulation)
│   ├── influx_client.py# InfluxDB singleton client
│   └── anomaly.py      # Rule-based anomaly detection
├── dashboard/          # Streamlit UI
│   ├── app.py          # Main entry & navigation (port 5000)
│   └── pages/          # Sub-pages: supervision, predictions, planification, parametres
├── nodered/            # Node-RED IoT flows
├── start.sh            # Unified startup script (InfluxDB + FastAPI + Streamlit)
├── requirements.txt    # Python dependencies
└── run.sh              # Original startup script (reference)
```

## Running the Application

The app is started via the `Start application` workflow which runs `bash start.sh`.

This script:
1. Starts InfluxDB (default config at `~/.influxdb/`)
2. Starts FastAPI backend on `localhost:8000`
3. Starts Streamlit dashboard on `0.0.0.0:5000`

## Key Dependencies

- Python 3.12
- streamlit >= 1.37.0 (requires `st.fragment` support)
- fastapi 0.111.0
- uvicorn 0.30.1
- influxdb 5.3.2 (Python client for InfluxDB 1.x)
- InfluxDB 1.10.7 (system package via Nix)
- xgboost 2.0.3
- plotly 5.22.0
- pandas 2.2.2

## Data Flow

1. **MPPT data** collected via Modbus or simulation → written to InfluxDB
2. **Predictions** computed by XGBoost using weather data → stored in InfluxDB
3. **Decisions** made by smart engine every 10s → written to InfluxDB
4. **Dashboard** reads from API which reads from InfluxDB

## Learning Modes

- **LEARNING** (< 48h data): No XGBoost predictions
- **PARTIAL** (48h - 7d data): Partial predictions
- **OPERATIONAL** (> 7d data): Full predictions with high confidence

## Deployment

Configured as a VM deployment running `bash start.sh`.
