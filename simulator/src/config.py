"""Carga y validacion de config_rules.yaml (rangos, mezcla de estatus, catalogos SAT, fechas)."""
from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config_rules.yaml"
_ECO_RE = re.compile(r"^ECO\d{2,3}$")
_INACTIVE_STATES = ("EN_MANTENIMIENTO", "INACTIVO")


class ConfigError(ValueError):
    """config_rules.yaml invalido."""


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ConfigError(msg)


def _pair(value: Any, name: str, ints: bool = False) -> tuple:
    _need(isinstance(value, (list, tuple)) and len(value) == 2, f"{name} debe ser [min, max]")
    a, b = value
    _need(a <= b, f"{name}: min > max")
    if ints:
        _need(all(isinstance(x, int) and not isinstance(x, bool) for x in (a, b)),
              f"{name} debe contener enteros")
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


def _gauss_spec(spec: Any, name: str) -> None:
    _need(isinstance(spec, dict) and all(k in spec for k in ("mean", "sd", "min", "max")),
          f"{name} requiere mean, sd, min y max")
    _need(spec["sd"] >= 0 and spec["min"] <= spec["max"], f"{name}: sd/min/max invalidos")


def _catalog(cfg: dict) -> dict:
    cat = cfg.get("sat_catalogs")
    _need(isinstance(cat, dict), "falta 'sat_catalogs'")
    for key in ("productos", "unidades", "configuracion_autotransporte", "tipos_permiso"):
        items = cat.get(key)
        _need(isinstance(items, list) and items, f"sat_catalogs.{key} debe ser una lista no vacia")
        claves = [str(i.get("clave", "")) for i in items]
        _need(all(claves), f"sat_catalogs.{key}: todas las entradas requieren 'clave'")
        _need(len(claves) == len(set(claves)), f"sat_catalogs.{key}: claves duplicadas")
    return cat


def validate(cfg: dict) -> dict:
    """Valida y normaliza (fechas -> date). Devuelve un dict nuevo."""
    _need(isinstance(cfg, dict), "config_rules.yaml debe ser un mapa")
    for key in ("seed", "end_date", "fleet_size", "fleet_status_mix", "date_range_backfill",
                "fleet", "sat_catalogs", "pricing_model", "cost_model", "constraints",
                "numbering", "fleet_status", "trip_model"):
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

    f, c = cfg["fleet"], cfg["constraints"]
    for k in ("operators", "trailers", "insurance_policies"):
        _need(isinstance(f[k], int) and f[k] > 0, f"fleet.{k} debe ser entero > 0")
    _need(f["insurance_policies"] <= cfg["fleet_size"], "fleet.insurance_policies > fleet_size")
    _need(f["trailers"] >= cfg["fleet_size"], "fleet.trailers debe ser >= fleet_size")
    _pair(f["model_year_range"], "fleet.model_year_range", True)
    lo, _hi = _pair(f["policy_valid_days_range"], "fleet.policy_valid_days_range", True)
    _need(lo > 0, "fleet.policy_valid_days_range debe ser > 0")
    _need(c["max_gross_weight_kg"] > 0, "constraints.max_gross_weight_kg debe ser > 0")
    _need(0 < f["payload_capacity_kg"] <= c["max_gross_weight_kg"],
          "fleet.payload_capacity_kg debe estar en (0, max_gross_weight_kg]")

    # --- Catalogos SAT cerrados: las claves emitidas deben existir en el catalogo -------------
    cat = _catalog(cfg)
    unidades = {u["clave"] for u in cat["unidades"]}
    for p in cat["productos"]:
        for k in ("descripcion", "unidad_defecto", "material_peligroso", "embalaje", "peso_unitario_kg"):
            _need(k in p, f"sat_catalogs.productos[{p['clave']}] requiere '{k}'")
        _need(p["unidad_defecto"] in unidades,
              f"sat_catalogs.productos[{p['clave']}].unidad_defecto no esta en sat_catalogs.unidades")
        _need(p["peso_unitario_kg"] > 0, f"sat_catalogs.productos[{p['clave']}].peso_unitario_kg > 0")
    _need(f["configuracion_sat"] in {x["clave"] for x in cat["configuracion_autotransporte"]},
          "fleet.configuracion_sat no esta en sat_catalogs.configuracion_autotransporte")
    _need(f["tipo_permiso_sct"] in {x["clave"] for x in cat["tipos_permiso"]},
          "fleet.tipo_permiso_sct no esta en sat_catalogs.tipos_permiso")

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

    lo, _hi = _pair(c["stops_per_trip"], "constraints.stops_per_trip", True)
    _need(lo >= 4, "constraints.stops_per_trip: minimo 4 (inicio, 2 intermedias y fin)")
    elo, ehi = _pair(c["energy_efficiency_km_per_kwh"], "constraints.energy_efficiency_km_per_kwh")
    _need(elo > 0, "constraints.energy_efficiency_km_per_kwh debe ser > 0")

    n = cfg["numbering"]
    _need(isinstance(n["talon_prefix"], str) and n["talon_prefix"].isalpha(), "numbering.talon_prefix: letras")
    _need(isinstance(n["talon_start"], int) and n["talon_start"] >= 0, "numbering.talon_start >= 0")

    split = cfg["fleet_status"]["inactive_split"]
    _need(set(split) == set(_INACTIVE_STATES), f"fleet_status.inactive_split requiere {_INACTIVE_STATES}")
    _need(math.isclose(sum(split.values()), 1.0, abs_tol=1e-9), "fleet_status.inactive_split debe sumar 1.0")
    _pair(cfg["fleet_status"]["initial_odometer_km_range"], "fleet_status.initial_odometer_km_range")

    t = cfg["trip_model"]
    kmlo, kmhi = _pair(t["km_range"], "trip_model.km_range")
    _need(kmlo > 0, "trip_model.km_range debe ser > 0")
    _pair(t["speed_kmh_range"], "trip_model.speed_kmh_range")
    smlo, smhi = _pair(t["start_minute_range"], "trip_model.start_minute_range", True)
    _need(0 <= smlo and smhi < 1440, "trip_model.start_minute_range fuera de un dia")
    _need(0 <= t["empty_zero_prob"] <= 1, "trip_model.empty_zero_prob fuera de [0,1]")
    _pair(t["empty_km_share_range"], "trip_model.empty_km_share_range")
    _need(elo < t["efficiency_mode"] < ehi, "trip_model.efficiency_mode fuera de energy_efficiency")
    _pair(t["battery_start_pct_range"], "trip_model.battery_start_pct_range")
    llo, lhi = _pair(t["load_factor_range"], "trip_model.load_factor_range")
    _need(0 < llo and lhi <= 1, "trip_model.load_factor_range debe estar en (0, 1]")
    ilo, _ihi = _pair(t["items_per_trip"], "trip_model.items_per_trip", True)
    _need(ilo >= 1, "trip_model.items_per_trip: minimo 1")
    for key in ("service_minutes", "service_overrun_minutes", "leg_delay_minutes"):
        _gauss_spec(t[key], f"trip_model.{key}")
    _need(t["service_minutes"]["min"] >= 10 and
          t["service_minutes"]["min"] + t["service_overrun_minutes"]["min"] >= 1,
          "trip_model: el servicio real debe ser positivo (evita fechas invertidas)")
    _need(t["leg_delay_minutes"]["min"] > -15, "trip_model.leg_delay_minutes.min debe ser > -15")
    # Un viaje = un dia (A2): cota del peor caso con el MINIMO de paradas (el generador reduce
    # paradas si un viaje no cabe) debe terminar antes de las 23:58.
    min_stops = lo
    worst = (smhi + kmhi / t["speed_kmh_range"][0] * 60
             + (min_stops - 2) * (t["service_minutes"]["max"] + t["service_overrun_minutes"]["max"])
             + min_stops * t["leg_delay_minutes"]["max"] + min_stops)
    _need(worst <= 1438, f"trip_model: peor caso del viaje ({worst:.0f} min) cruza la medianoche (A2)")
    _need(50 < t["battery_capacity_kwh"] and
          t["battery_start_pct_range"][0] - kmhi / (elo + 0.05) / t["battery_capacity_kwh"] * 100 > 0,
          "trip_model: bateria insuficiente para el viaje mas largo con la peor eficiencia")
    _need(0 <= t["snapshot_minute"] < 1440, "trip_model.snapshot_minute fuera de un dia")
    _need(t["snapshot_minute"] > smhi, "trip_model.snapshot_minute debe ser posterior al inicio de los viajes")

    events = []
    for i, ev in enumerate(cfg.get("scd2_events") or []):
        _need(isinstance(ev, dict) and {"eco", "effective_date", "change"} <= set(ev),
              f"scd2_events[{i}] requiere eco, effective_date y change")
        _need(_ECO_RE.match(str(ev["eco"])) is not None, f"scd2_events[{i}].eco invalido: {ev['eco']!r}")
        _need(ev["change"] == "PLACA", f"scd2_events[{i}].change soportado: PLACA")
        events.append({**ev, "effective_date": _date(ev["effective_date"], f"scd2_events[{i}].effective_date")})
    _need(len({(e["eco"], e["effective_date"]) for e in events}) == len(events),
          "scd2_events: (eco, effective_date) duplicado")
    out["scd2_events"] = events
    return out


def load_config(path: Path | None = None) -> dict:
    p = Path(path) if path else DEFAULT_CONFIG
    with p.open("r", encoding="utf-8") as fh:
        return validate(yaml.safe_load(fh))


def allocate(total: int, weights: dict) -> dict:
    """Reparte `total` con el metodo del mayor residuo (suma exacta).

    Los pesos se normalizan: no necesitan sumar 1.
    """
    wsum = sum(weights.values())
    if wsum <= 0:
        raise ConfigError("allocate: la suma de pesos debe ser > 0")
    raw = {k: total * w / wsum for k, w in weights.items()}
    counts = {k: int(math.floor(v + 1e-9)) for k, v in raw.items()}
    rest = total - sum(counts.values())
    for k in sorted(raw, key=lambda k: (raw[k] - counts[k]), reverse=True)[:rest]:
        counts[k] += 1
    return counts


def status_counts(fleet_size: int, mix: dict) -> dict[str, int]:
    """56/40/4 para 100 unidades."""
    return allocate(fleet_size, {k: mix[k] for k in ("with_trip", "without_trip", "inactive")})
