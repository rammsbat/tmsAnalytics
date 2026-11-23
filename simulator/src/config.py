"""Carga y validacion de config_rules.yaml (rangos, mezcla de estatus, fechas)."""
from __future__ import annotations

import datetime as dt
import math
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config_rules.yaml"


class ConfigError(ValueError):
    """config_rules.yaml invalido."""


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _pair(value: Any, name: str, lo_hi_int: bool = False) -> tuple:
    _need(isinstance(value, (list, tuple)) and len(value) == 2, f"{name} debe ser [min, max]")
    a, b = value
    _need(a <= b, f"{name}: min > max")
    if lo_hi_int:
        _need(all(isinstance(x, int) for x in (a, b)), f"{name} debe contener enteros")
    return a, b


def _date(value: Any, name: str) -> dt.date:
    if isinstance(value, dt.datetime):
        raise ConfigError(f"{name} debe ser una fecha (YYYY-MM-DD)")
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"{name} invalida: {value!r}") from exc


def validate(cfg: dict) -> dict:
    """Valida y normaliza (fechas -> date). Devuelve un dict nuevo."""
    _need(isinstance(cfg, dict), "config_rules.yaml debe ser un mapa")
    for key in ("seed", "end_date", "fleet_size", "fleet_status_mix", "date_range_backfill",
                "fleet", "pricing_model", "cost_model", "constraints"):
        _need(key in cfg, f"falta la clave '{key}'")
    out = dict(cfg)
    _need(isinstance(cfg["seed"], int) and not isinstance(cfg["seed"], bool), "seed debe ser entero")
    out["end_date"] = _date(cfg["end_date"], "end_date")
    _need(isinstance(cfg["fleet_size"], int) and cfg["fleet_size"] > 0, "fleet_size debe ser > 0")

    mix = cfg["fleet_status_mix"]
    for k in ("with_trip", "without_trip", "inactive"):
        _need(k in mix and 0 <= mix[k] <= 1, f"fleet_status_mix.{k} fuera de [0,1]")
    _need(math.isclose(sum(mix[k] for k in ("with_trip", "without_trip", "inactive")), 1.0,
                       abs_tol=1e-9), "fleet_status_mix debe sumar 1.0")

    dr = cfg["date_range_backfill"]
    _need(isinstance(dr["days"], int) and dr["days"] > 0, "date_range_backfill.days debe ser > 0")
    preset = dict(dr.get("preset_draft") or {})
    if preset:
        preset["start"] = _date(preset["start"], "preset_draft.start")
        preset["end"] = _date(preset["end"], "preset_draft.end")
        _need(preset["start"] <= preset["end"], "preset_draft: start > end")
    out["date_range_backfill"] = {**dr, "preset_draft": preset}

    f = cfg["fleet"]
    for k in ("operators", "trailers", "insurance_policies"):
        _need(isinstance(f[k], int) and f[k] > 0, f"fleet.{k} debe ser entero > 0")
    _need(f["insurance_policies"] <= cfg["fleet_size"], "fleet.insurance_policies > fleet_size")
    _need(f["trailers"] >= cfg["fleet_size"], "fleet.trailers debe ser >= fleet_size")
    _pair(f["model_year_range"], "fleet.model_year_range", True)
    lo, hi = _pair(f["policy_valid_days_range"], "fleet.policy_valid_days_range", True)
    _need(lo > 0, "fleet.policy_valid_days_range debe ser > 0")
    c = cfg["constraints"]
    _need(0 < f["payload_capacity_kg"] <= c["max_gross_weight_kg"],
          "fleet.payload_capacity_kg debe estar en (0, max_gross_weight_kg]")

    p = cfg["pricing_model"]
    _need(p["base_rate"] >= 0 and p["rate_per_km"] >= 0, "pricing_model: tarifas negativas")
    for s in p.get("surcharges", []):
        _need(0 <= s["probability"] <= 1 and s["amount"] >= 0, f"recargo invalido: {s.get('name')}")
    _need(0 <= p["iva_rate"] < 1 and 0 <= p["iva_retention_rate"] < 1, "pricing_model: tasas IVA")
    _pair(p["invoice_lag_days"], "pricing_model.invoice_lag_days", True)

    co = cfg["cost_model"]
    _need(co["operator_pay"]["per_km"] >= 0 and co["operator_pay"]["per_trip"] >= 0,
          "cost_model.operator_pay negativo")
    _need(0 <= co["maintenance"]["probability_per_trip"] <= 1, "cost_model.maintenance.probability")
    _pair(co["maintenance"]["amount_range"], "cost_model.maintenance.amount_range")

    lo, hi = _pair(c["stops_per_trip"], "constraints.stops_per_trip", True)
    _need(lo >= 2, "constraints.stops_per_trip: minimo 2 (inicio y fin)")
    _pair(c["energy_efficiency_km_per_kwh"], "constraints.energy_efficiency_km_per_kwh")
    _need(c["max_gross_weight_kg"] > 0, "constraints.max_gross_weight_kg debe ser > 0")
    return out


def load_config(path: Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG
    with p.open("r", encoding="utf-8") as fh:
        return validate(yaml.safe_load(fh))


def status_counts(fleet_size: int, mix: dict) -> dict[str, int]:
    """Reparte la flota con el metodo del mayor residuo (suma exacta, 56/40/4 para 100)."""
    keys = ("with_trip", "without_trip", "inactive")
    raw = {k: fleet_size * mix[k] for k in keys}
    counts = {k: int(math.floor(raw[k] + 1e-9)) for k in keys}
    rest = fleet_size - sum(counts.values())
    for k in sorted(keys, key=lambda k: (raw[k] - counts[k]), reverse=True)[:rest]:
        counts[k] += 1
    return counts
