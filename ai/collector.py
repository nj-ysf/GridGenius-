#!/usr/bin/env python3
"""
collector.py — Lecture Modbus RS485 → MQTT (GridGenius)
  Appelé par Node-RED (exec node) toutes les 10s.
  Retourne JSON via stdout → Node-RED écrit dans InfluxDB.
  Mode simulation automatique si matériel absent.
"""

import json, sys, logging
from datetime import datetime
from predict import PV_PROFILE, CONSO_PROFILE

logging.basicConfig(level=logging.WARNING,
                    format='%(asctime)s [collector] %(levelname)s: %(message)s')
log = logging.getLogger(__name__)

SERIAL_PORT = "/dev/ttyUSB0"
BAUD_RATE   = 115200
SLAVE_ID    = 1
TIMEOUT     = 3

REG = {
    "pv_voltage":      0x3100,
    "pv_current":      0x3101,
    "pv_power":        0x3102,
    "pv_energy_today": 0x330C,
    "bat_voltage":     0x3104,
    "bat_current":     0x3105,
    "bat_soc":         0x311A,
    "bat_temp":        0x3110,
    "load_power":      0x310E,
    "charge_status":   0x3201,
}


def simulate() -> dict:
    """Données simulées réalistes — profils partagés depuis predict.py"""
    import time
    h     = datetime.now().hour
    pv_kw = max(0, PV_PROFILE.get(h, 0.0) + 0.3*((time.time()%10-5)/5))
    lkw   = CONSO_PROFILE.get(h, 5.0)
    return {
        "pv_voltage":      round(72.0 if pv_kw > 0 else 0.0, 2),
        "pv_current":      round(pv_kw/72.0 if pv_kw > 0 else 0.0, 2),
        "pv_power":        round(pv_kw, 2),
        "pv_energy_today": round(pv_kw * h * 0.9 / 10, 2),
        "bat_voltage":     51.2,
        "bat_current":     round((pv_kw - lkw/1000)*10, 2),
        "bat_soc":         55.0,
        "bat_temp":        28.5,
        "load_power":      round(lkw, 2),
        "charge_mode":     "mppt" if pv_kw > 0 else "idle",
        "timestamp":       datetime.now().isoformat(),
        "source":          "simulation"
    }


def _read_reg(client, reg, scale=0.01):
    try:
        r = client.read_input_registers(reg, count=1, slave=SLAVE_ID)
        if r.isError(): return 0.0
        raw = r.registers[0]
        if raw > 32767: raw -= 65536
        return round(raw * scale, 2)
    except Exception:
        return 0.0


def read_mppt() -> dict:
    try:
        from pymodbus.client import ModbusSerialClient
    except ImportError:
        from pymodbus.client.sync import ModbusSerialClient

    client = ModbusSerialClient(method='rtu', port=SERIAL_PORT,
                                baudrate=BAUD_RATE, stopbits=1,
                                bytesize=8, parity='N', timeout=TIMEOUT)
    if not client.connect():
        log.warning(f"Modbus indisponible sur {SERIAL_PORT} → simulation")
        return simulate()

    try:
        r          = client.read_input_registers(REG['charge_status'], 1, slave=SLAVE_ID)
        status     = r.registers[0] if not r.isError() else 0
        mode_map   = {0:"idle",1:"float",2:"boost",3:"equalization",4:"mppt"}
        return {
            "pv_voltage":      _read_reg(client, REG['pv_voltage']),
            "pv_current":      _read_reg(client, REG['pv_current']),
            "pv_power":        _read_reg(client, REG['pv_power']),
            "pv_energy_today": _read_reg(client, REG['pv_energy_today']),
            "bat_voltage":     _read_reg(client, REG['bat_voltage']),
            "bat_current":     _read_reg(client, REG['bat_current']),
            "bat_soc":         _read_reg(client, REG['bat_soc'], 1.0),
            "bat_temp":        _read_reg(client, REG['bat_temp']),
            "load_power":      _read_reg(client, REG['load_power']),
            "charge_mode":     mode_map.get((status>>2)&0x07, "unknown"),
            "timestamp":       datetime.now().isoformat(),
            "source":          "modbus"
        }
    finally:
        client.close()


if __name__ == "__main__":
    try:
        data = simulate() if "--simulate" in sys.argv else read_mppt()
        print(json.dumps(data))
    except Exception as e:
        log.error(f"Erreur collector : {e}")
        print(json.dumps(simulate()))
