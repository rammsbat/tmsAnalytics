"""Estatus diario de patio (ST-3): STG_FLOTA_ESTATUS_DIARIO, 100 filas por dia (A1/A2).

La asignacion del dia decide PRIMERO que unidades salen a viaje y luego se derivan los
despachos: `DISPONIBLE_CON_VIAJE` coincide 1 a 1 con las unidades que tienen un despacho ese dia.
Mezcla diaria (100 unidades): 56 con viaje / 40 sin viaje / 4 inactivas (3 EN_MANTENIMIENTO +
1 INACTIVO segun `fleet_status.inactive_split`).
"""
from __future__ import annotations

import datetime as dt

from ..config import ConfigError, allocate, status_counts
from ..rng import make_rng

ESTATUS_CON_VIAJE = "DISPONIBLE_CON_VIAJE"
ESTATUS_SIN_VIAJE = "DISPONIBLE_SIN_VIAJE"
ESTATUS_MANTENIMIENTO = "EN_MANTENIMIENTO"
ESTATUS_INACTIVO = "INACTIVO"

_OBSERVACIONES = {
    ESTATUS_MANTENIMIENTO: "Mantenimiento programado en taller",
    ESTATUS_INACTIVO: "Unidad inactiva sin asignacion",
}


def plan_day(cfg: dict, master, day: dt.date, n_trips: int) -> tuple[list[str], dict[str, str]]:
    """(unidades con viaje, {eco: estatus} del resto) para `day`. Determinista por (seed, dia)."""
    ecos = [u["CODIGO_ECO"] for u in master.units]
    n_inactive = status_counts(len(ecos), cfg["fleet_status_mix"])["inactive"]
    if n_trips < 0 or n_trips + n_inactive > len(ecos):
        raise ConfigError(f"No se pueden asignar {n_trips} viajes: la flota de {len(ecos)} unidades "
                          f"deja como maximo {len(ecos) - n_inactive} disponibles")
    order = list(ecos)
    make_rng(cfg["seed"], f"day.{day.isoformat()}.units").shuffle(order)
    inactive = order[:n_inactive]
    trips = order[n_inactive:n_inactive + n_trips]
    idle = order[n_inactive + n_trips:]

    others: dict[str, str] = {eco: ESTATUS_SIN_VIAJE for eco in idle}
    split = allocate(n_inactive, cfg["fleet_status"]["inactive_split"])
    it = iter(inactive)
    for state in (ESTATUS_MANTENIMIENTO, ESTATUS_INACTIVO):
        for _ in range(split.get(state, 0)):
            others[next(it)] = state
    return trips, others


def home_yard(master, eco: str) -> str:
    """Patio base de la unidad (estable: no depende del dia)."""
    return master.locations[int(eco[3:]) % len(master.locations)]["CODIGO_UBICACION"]


def status_row(day: dt.date, eco: str, estatus: str, *, talon: str | None = None,
               yard: str, km: float = 0.0, kwh: float = 0.0, observaciones: str | None = None,
               ing_day: dt.date | None = None) -> dict:
    return {
        "FECHA_CORTE": day,
        "CODIGO_ECO": eco,
        "ESTATUS_PATIO": estatus,
        "NUMERO_TALON": talon,
        "UBICACION_PATIO": yard,
        "KMS_ODOMETRO_DIA": km,
        "KWH_CONSUMO_DIA": kwh,
        "OBSERVACIONES": observaciones if observaciones is not None else _OBSERVACIONES.get(estatus),
        "_ING_DAY": ing_day or day,
    }
