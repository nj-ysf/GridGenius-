#!/bin/bash

echo "🚀 Starting GridGenius..."

# Activate virtual environment (if you have one)
if [ -d ".venv" ]; then
    echo "🔹 Activating virtual environment..."
    source .venv/bin/activate
fi

# Start FastAPI backend
echo "🔹 Starting API (port 8000)..."
cd ai
uvicorn api:app --host 0.0.0.0 --port 8000 &
API_PID=$!
cd ..

# Start Streamlit dashboard
echo "🔹 Starting Dashboard (port 8501)..."
cd dashboard
streamlit run app.py --server.port 8501 &
DASH_PID=$!
cd ..

echo "✅ GridGenius is running!"
echo "📊 Dashboard: http://localhost:8501"
echo "⚙️ API docs: http://localhost:8000/docs"

# Wait for processes
wait $API_PID $DASH_PID