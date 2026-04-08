#!/bin/bash

echo "Starting GridGenius..."

# Start InfluxDB in background (uses default ~/.influxdb path)
echo "Starting InfluxDB..."
influxd run >/tmp/influxdb.log 2>&1 &
INFLUX_PID=$!

# Wait for InfluxDB to be ready (up to 30s)
echo "Waiting for InfluxDB..."
for i in $(seq 1 30); do
    if influx -execute "SHOW DATABASES" >/dev/null 2>&1; then
        echo "InfluxDB ready after ${i}s"
        break
    fi
    sleep 1
done

# Start FastAPI backend on port 8000
echo "Starting API backend on port 8000..."
cd ai
uvicorn api:app --host localhost --port 8000 &
API_PID=$!
cd ..

# Give the API a moment to initialize
sleep 5

# Seed historical data (runs only if < 48h of data in DB)
echo "Seeding historical data if needed..."
cd ai
python3 seed_data.py &
SEED_PID=$!
cd ..

# Wait for seed to finish before starting simulator
wait $SEED_PID
echo "Seed step complete"

# Start live simulation (10s loop feeding data to API)
echo "Starting live data simulator..."
cd ai
python3 simulate.py &
SIM_PID=$!
cd ..

# Start Streamlit dashboard on port 5000
echo "Starting Streamlit dashboard on port 5000..."
cd dashboard
streamlit run app.py \
    --server.port 5000 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false &
DASH_PID=$!
cd ..

echo "GridGenius running!"
echo "Dashboard: http://localhost:5000"
echo "API docs: http://localhost:8000/docs"

# Wait for all processes
wait $INFLUX_PID $API_PID $SIM_PID $DASH_PID
