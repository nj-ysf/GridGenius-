#!/usr/bin/env bash
#
# GridGenius — full local stack (InfluxDB 1.x + API + seed + simulator + dashboard)
#
# Usage (from this folder):
#   chmod +x start.sh && ./start.sh
#
# Prerequisites:
#   • Python deps: pip install -r requirements.txt (prefer a venv: ../.venv or ./.venv)
#   • InfluxDB 1.8: either on PATH, or unpack the official zip so you have:
#       ./influxdb-1.8.10/influxdb-1.8.10-1/influxd(.exe) and influx(.exe)
#
# Optional env:
#   INFLUXD_BIN   — full path to influxd (overrides auto-detect)
#   INFLUX_BIN    — full path to influx CLI (overrides auto-detect)
#   DASH_PORT     — Streamlit port (default 8501, same as README)
#

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " GridGenius — starting (project: $ROOT)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Python / venv ─────────────────────────────────────────────
if [[ -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/.venv/bin/activate"
  echo "[venv] Using: $ROOT/.venv"
elif [[ -f "$ROOT/../.venv/Scripts/activate" ]]; then
  # Windows venv next to repo folder (common layout)
  # shellcheck source=/dev/null
  source "$ROOT/../.venv/Scripts/activate"
  echo "[venv] Using: $ROOT/../.venv"
elif [[ -f "$ROOT/../.venv/bin/activate" ]]; then
  # shellcheck source=/dev/null
  source "$ROOT/../.venv/bin/activate"
  echo "[venv] Using: $ROOT/../.venv"
fi

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || PY="python"
command -v "$PY" >/dev/null 2>&1 || { echo "ERROR: python not found. Create a venv and install requirements.txt"; exit 1; }

# ── Locate InfluxDB 1.x binaries ────────────────────────────────
resolve_influxd() {
  if [[ -n "${INFLUXD_BIN:-}" ]]; then
    echo "$INFLUXD_BIN"
    return
  fi
  local cands=(
    "$ROOT/influxdb-1.8.10/influxdb-1.8.10-1/influxd.exe"
    "$ROOT/influxdb-1.8.10/influxdb-1.8.10-1/influxd"
  )
  local p
  for p in "${cands[@]}"; do
    if [[ -f "$p" ]]; then
      echo "$p"
      return
    fi
  done
  if command -v influxd >/dev/null 2>&1; then
    command -v influxd
    return
  fi
  echo ""
}

resolve_influx_cli() {
  if [[ -n "${INFLUX_BIN:-}" ]]; then
    echo "$INFLUX_BIN"
    return
  fi
  local cands=(
    "$ROOT/influxdb-1.8.10/influxdb-1.8.10-1/influx.exe"
    "$ROOT/influxdb-1.8.10/influxdb-1.8.10-1/influx"
  )
  local p
  for p in "${cands[@]}"; do
    if [[ -f "$p" ]]; then
      echo "$p"
      return
    fi
  done
  if command -v influx >/dev/null 2>&1; then
    command -v influx
    return
  fi
  echo ""
}

INFLUXD_PATH="$(resolve_influxd)"
INFLUX_PATH="$(resolve_influx_cli)"

if [[ -z "$INFLUXD_PATH" ]]; then
  echo "ERROR: influxd not found."
  echo "  Install InfluxDB 1.8, or unpack it under:"
  echo "    $ROOT/influxdb-1.8.10/influxdb-1.8.10-1/"
  echo "  Or set INFLUXD_BIN to the full path."
  exit 1
fi

echo "[influx] daemon: $INFLUXD_PATH"
[[ -n "$INFLUX_PATH" ]] && echo "[influx] CLI:    $INFLUX_PATH"

# ── Start InfluxDB 1.x (no 'run' subcommand — that is for v2) ───
echo "Starting InfluxDB (logs: $LOG_DIR/influxdb.log)..."
"$INFLUXD_PATH" >>"$LOG_DIR/influxdb.log" 2>&1 &
INFLUX_PID=$!

wait_influx_ready() {
  local i
  for i in $(seq 1 40); do
    if command -v curl >/dev/null 2>&1; then
      local code
      code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8086/ping 2>/dev/null || echo 000)"
      if [[ "$code" == "204" ]]; then
        echo "InfluxDB ready (HTTP $code) after ${i}s"
        return 0
      fi
    fi
    if [[ -n "$INFLUX_PATH" ]]; then
      if "$INFLUX_PATH" -execute "SHOW DATABASES" >/dev/null 2>&1; then
        echo "InfluxDB ready after ${i}s"
        return 0
      fi
    fi
    sleep 1
  done
  echo "ERROR: InfluxDB did not become ready on :8086 — see $LOG_DIR/influxdb.log"
  kill "$INFLUX_PID" 2>/dev/null || true
  exit 1
}

wait_influx_ready

if [[ -n "$INFLUX_PATH" ]]; then
  "$INFLUX_PATH" -execute "CREATE DATABASE microgrid" >/dev/null 2>&1 || true
fi

# ── API (FastAPI) ───────────────────────────────────────────────
echo "Starting API on http://127.0.0.1:8000 ..."
(
  cd "$ROOT/ai"
  exec "$PY" -m uvicorn api:app --host 127.0.0.1 --port 8000
) >>"$LOG_DIR/api.log" 2>&1 &
API_PID=$!

# Wait until /health responds
for i in $(seq 1 30); do
  if command -v curl >/dev/null 2>&1; then
    code="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null || echo 000)"
    if [[ "$code" == "200" ]]; then
      echo "API ready after ${i}s"
      break
    fi
  fi
  sleep 1
done

# ── Seed DB (foreground — skips if ≥48h data already) ───────────
echo "Seeding historical data if needed..."
(
  cd "$ROOT/ai"
  exec "$PY" seed_data.py
) >>"$LOG_DIR/seed.log" 2>&1
echo "Seed step complete."

# ── Live simulator (10s loop → POST /decide) ────────────────────
echo "Starting live simulator..."
(
  cd "$ROOT/ai"
  exec "$PY" simulate.py
) >>"$LOG_DIR/simulate.log" 2>&1 &
SIM_PID=$!

# ── Streamlit dashboard ─────────────────────────────────────────
DASH_PORT="${DASH_PORT:-8501}"
echo "Starting Streamlit on port $DASH_PORT ..."
(
  cd "$ROOT/dashboard"
  exec "$PY" -m streamlit run app.py \
    --server.port "$DASH_PORT" \
    --server.address 127.0.0.1 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
) >>"$LOG_DIR/dashboard.log" 2>&1 &
DASH_PID=$!

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " GridGenius is running"
echo "   Dashboard : http://127.0.0.1:${DASH_PORT}"
echo "   API docs  : http://127.0.0.1:8000/docs"
echo "   Health    : http://127.0.0.1:8000/health"
echo " Logs: $LOG_DIR/"
echo " Stop: Ctrl+C here, then kill remaining python/influxd if needed."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

wait $INFLUX_PID $API_PID $SIM_PID $DASH_PID
