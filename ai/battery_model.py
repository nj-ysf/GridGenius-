#!/usr/bin/env python3
"""
battery_model.py — Modèle SOC LFP 48V / 50 kWh (GridGenius)
  Instance globale unique : battery
  DELTA_T_H importé depuis predict.py
"""

import logging
import numpy as np
from dataclasses import dataclass
from datetime import datetime
from predict import DELTA_T_H, PV_PROFILE

log = logging.getLogger(__name__)


@dataclass
class BatteryConfig:
    capacity_kwh:       float = 50.0
    soc_min:            float = 0.10
    soc_max:            float = 0.95
    eta_charge:         float = 0.95
    eta_discharge:      float = 0.95
    p_max_charge_kw:    float = 10.0
    p_max_discharge_kw: float = 15.0
    p_losses_kw:        float = 0.05
    cost_per_cycle:     float = 0.50
    v_min:              float = 44.0
    v_max:              float = 58.4
    v_nominal:          float = 51.2

    def to_dict(self): return self.__dict__

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if hasattr(cls, k)})


class BatteryModel:
    """
    P_net = P_PV + P_grid - P_load - P_losses
    Surplus  → charge   : SOC += η_c · P_charge · Δt / C
    Déficit  → décharge : SOC -= P_discharge · Δt / (η_d · C)
    Contraintes : SOC ∈ [soc_min, soc_max], P ≤ P_max
    """

    def __init__(self, config: BatteryConfig = None, initial_soc: float = 0.50):
        self.cfg          = config or BatteryConfig()
        self.soc          = float(np.clip(initial_soc,
                                          self.cfg.soc_min, self.cfg.soc_max))
        self.mode         = "idle"
        self.cycles_equiv = 0.0
        self.energy_in    = 0.0
        self.energy_out   = 0.0

    # ── Propriétés ─────────────────────────────────────────────
    @property
    def soc_pct(self):
        return round(self.soc * 100, 1)

    @property
    def voltage(self):
        return self.cfg.v_min + self.soc*(self.cfg.v_max - self.cfg.v_min)

    @property
    def is_low(self):
        return self.soc <= self.cfg.soc_min + 0.10

    @property
    def is_full(self):
        return self.soc >= self.cfg.soc_max - 0.02

    @property
    def available_kwh(self):
        return (self.soc - self.cfg.soc_min) * self.cfg.capacity_kwh

    # ── Pas de simulation ───────────────────────────────────────
    def step(self, p_pv: float, p_load: float,
             p_grid: float = 0.0, dt: float = DELTA_T_H) -> dict:
        cfg        = self.cfg
        p_net      = p_pv + p_grid - p_load - cfg.p_losses_kw
        p_charge   = p_discharge = 0.0
        p_grid_act = p_grid

        if p_net > 0:
            p_charge  = min(p_net*cfg.eta_charge, cfg.p_max_charge_kw)
            headroom  = (cfg.soc_max-self.soc)*cfg.capacity_kwh/dt
            p_charge  = max(0, min(p_charge, headroom))
            self.mode = "charge" if p_charge > 0.001 else "idle"
        elif p_net < 0:
            p_discharge = min(abs(p_net)/cfg.eta_discharge, cfg.p_max_discharge_kw)
            available   = (self.soc-cfg.soc_min)*cfg.capacity_kwh/dt
            p_discharge = max(0, min(p_discharge, available))
            p_missing   = abs(p_net) - cfg.p_losses_kw - p_discharge*cfg.eta_discharge
            if p_missing > 0.1 and p_grid == 0:
                p_grid_act += p_missing
            self.mode = "discharge" if p_discharge > 0.001 else "idle"
        else:
            self.mode = "idle"

        delta   = (cfg.eta_charge*p_charge
                   - p_discharge/cfg.eta_discharge
                   - cfg.p_losses_kw) * dt / cfg.capacity_kwh
        new_soc = float(np.clip(self.soc+delta, cfg.soc_min, cfg.soc_max))

        self.energy_in    += p_charge    * dt
        self.energy_out   += p_discharge * dt
        self.cycles_equiv += p_discharge * dt / cfg.capacity_kwh

        imbalance = abs((p_pv+p_grid_act+p_discharge)*dt -
                        (p_load+p_charge+cfg.p_losses_kw)*dt)
        if imbalance > 0.01:
            log.warning(f"Déséquilibre énergie : {imbalance:.4f} kWh")

        self.soc = new_soc
        return {
            "soc":           self.soc_pct,
            "voltage":       round(self.voltage, 2),
            "mode":          self.mode,
            "p_charge":      round(p_charge, 3),
            "p_discharge":   round(p_discharge, 3),
            "p_grid_actual": round(p_grid_act, 3),
            "balance_ok":    imbalance < 0.01,
            "alerts":        self._alerts()
        }

    def _alerts(self) -> list:
        alerts = []
        cfg    = self.cfg
        if self.soc <= cfg.soc_min + 0.02:
            alerts.append({"type":"SOC_CRITICAL","severity":"critical",
                           "message":f"SOC critique : {self.soc_pct}%"})
        elif self.soc <= cfg.soc_min + 0.10:
            alerts.append({"type":"SOC_LOW","severity":"warning",
                           "message":f"SOC faible : {self.soc_pct}%"})
        if self.soc >= cfg.soc_max - 0.01:
            alerts.append({"type":"SOC_FULL","severity":"info",
                           "message":f"Batterie pleine : {self.soc_pct}%"})
        return alerts

    # ── Projection SOC (pour smart_engine scoring) ─────────────
    def project_summary(self, pv_fc: list, conso_fc: list,
                        initial_soc: float = None) -> dict:
        saved    = self.soc
        self.soc = float(np.clip(initial_soc if initial_soc is not None
                                 else self.soc, self.cfg.soc_min, self.cfg.soc_max))
        soc_vals, e_grid, e_pv, e_load = [], 0, 0, 0

        for pv_p, co_p in zip(pv_fc, conso_fc):
            p_pv  = float(pv_p.get('pv_corrected_kw',
                                    pv_p.get('predicted_kw', 0)))
            p_load= float(co_p.get('predicted_kw', 5))
            r     = self.step(p_pv, p_load)
            soc_vals.append(self.soc)
            e_grid += r['p_grid_actual'] * DELTA_T_H
            e_pv   += p_pv   * DELTA_T_H
            e_load += p_load * DELTA_T_H

        self.soc  = saved
        e_total   = e_pv + e_grid
        return {
            "soc_min":       round(min(soc_vals)*100, 1) if soc_vals else 0,
            "soc_max":       round(max(soc_vals)*100, 1) if soc_vals else 0,
            "soc_final":     round(soc_vals[-1]*100, 1)  if soc_vals else 0,
            "soc_mean":      round(float(np.mean(soc_vals))*100, 1) if soc_vals else 0,
            "e_grid_kwh":    round(e_grid, 2),
            "e_pv_kwh":      round(e_pv, 2),
            "e_load_kwh":    round(e_load, 2),
            "grid_dependency": round(e_grid/e_total, 3) if e_total > 0 else 1.0,
            "autonomy_pct":  round((1-e_grid/e_total)*100, 1) if e_total > 0 else 0,
            "cycles_added":  round(self.cycles_equiv, 3)
        }

    # ── Pré-charge ──────────────────────────────────────────────
    def compute_precharge(self, soc_target: float,
                          p_pv_avail: float,
                          hours_before: float = 2.0) -> dict:
        soc_needed = soc_target - self.soc
        if soc_needed <= 0:
            return {"needed": False,
                    "message": f"SOC suffisant : {self.soc_pct}% ≥ {soc_target*100:.0f}%"}
        e_needed   = soc_needed * self.cfg.capacity_kwh / self.cfg.eta_charge
        e_pv_avail = p_pv_avail * hours_before
        e_grid     = max(0, e_needed - e_pv_avail)
        p_grid     = min(e_grid/hours_before, self.cfg.p_max_charge_kw) \
                     if hours_before > 0 else 0
        return {
            "needed":          True,
            "soc_current_pct": self.soc_pct,
            "soc_target_pct":  round(soc_target*100, 1),
            "e_needed_kwh":    round(e_needed, 2),
            "e_pv_avail_kwh":  round(e_pv_avail, 2),
            "e_grid_kwh":      round(e_grid, 2),
            "p_grid_kw":       round(p_grid, 2),
            "duration_h":      round(hours_before, 1),
            "feasible":        e_grid <= e_needed * 0.6
        }

    def update_from_mppt(self, mppt: dict):
        """Mise à jour depuis données MPPT temps réel"""
        self.soc = float(np.clip(
            float(mppt.get('bat_soc', self.soc*100)) / 100, 0, 1
        ))

    def to_dict(self) -> dict:
        return {
            "soc":           self.soc_pct,
            "voltage":       round(self.voltage, 2),
            "mode":          self.mode,
            "is_low":        self.is_low,
            "is_full":       self.is_full,
            "available_kwh": round(self.available_kwh, 2),
            "cycles_equiv":  round(self.cycles_equiv, 3)
        }


# Instance globale unique
battery = BatteryModel()
