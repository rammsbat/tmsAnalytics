"""Motor de viajes TrackItWeb (ST-3): STG_TRACKIT_DESPACHO + STG_TRACKIT_PARADAS.

Cada viaje es una funcion PURA de (seed, talon, unidad, operador, dia, hora de inicio, odometro,
corte): todo el azar sale de `make_rng(seed, "trip.<talon>[.aN]")`. Por eso un viaje abierto
(EN_TRANSITO) se puede regenerar completo despues para cerrarlo (D7) sin guardar su plan.

Reglas fisicas:
  * KMS_TOTAL = KMS_CARGADO + KMS_VACIO exacto (aritmetica en centesimas de km).
  * Rendimiento 2.0-11.6 km/kWh; bateria final > 0.
  * 4-12 paradas; el viaje NUNCA cruza la medianoche (A2): si no cabe se reduce el numero de paradas.
  * Retrasos gaussianos por tramo y por servicio; LAG_* y estadia se calculan desde los timestamps.
  * Viaje abierto (corte): KMS = 0 y odometro/bateria final NULL hasta el cierre (evita doble conteo).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field

from ..config import allocate
from ..rng import gauss_int, make_rng
from .carta_porte import plan_cargo

SOURCE_SYSTEM_TRACKIT = "TRACKITWEB"
ESTATUS_CERRADO = "CERRADO"
ESTATUS_EN_TRANSITO = "EN_TRANSITO"
MAX_END_MINUTE = 1438  # 23:58: un viaje = un dia


@dataclass(frozen=True)
class TripInput:
    talon: str
    talon_num: int
    eco: str
    operator_code: str
    day: dt.date
    start_minute: int
    odometer_start: float
    cutoff: int | None  # minuto del dia de corte; None = viaje completo


@dataclass
class TripOutput:
    despacho: dict
    paradas: list[dict]
    closed: bool
    origin: str
    destination: str
    client_origin: dict
    client_destination: dict
    ue: str
    cargo: list[dict]
    cargo_total_kg: float
    distance_km: float
    km_total: float          # 0.0 mientras el viaje esta abierto
    kwh: float               # 0.0 mientras el viaje esta abierto
    odometer_end: float | None
    end_minute: int
    stops: int


def _c(x: float) -> int:
    return int(round(x * 100))


def _f(c: int) -> float:
    return round(c / 100, 2)


def _ts(day: dt.date, minute: int) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0, 0)) + dt.timedelta(minutes=minute)


@dataclass
class _Stop:
    seq: int
    code: str
    kind: str
    leg_c: int
    plan_arr: int
    plan_dep: int
    real_arr: int
    real_dep: int


def _timeline(cfg: dict, rng, locs: list[str], origin: str, dest: str, n: int, km_c: int,
              speed: float, start: int) -> list[_Stop]:
    t = cfg["trip_model"]
    legs = allocate(km_c, {i: rng.uniform(0.5, 1.5) for i in range(n - 1)})
    codes = [origin]
    for k in range(2, n):  # intermedias
        banned = {codes[-1]} | ({dest} if k == n - 1 else set())
        codes.append(rng.choice([c for c in locs if c not in banned]))
    codes.append(dest)
    kinds = ["INICIO VIAJE"]
    for k in range(2, n):
        kinds.append("CARGA" if k == 2 else "DESCARGA" if k == n - 1
                     else rng.choice(("RECOLECCION", "CARGA", "DESCARGA")))
    kinds.append("FIN VIAJE")

    stops = [_Stop(1, codes[0], kinds[0], 0, start, start, start, start + max(0, gauss_int(rng, t["service_overrun_minutes"])))]
    for k in range(2, n + 1):
        prev = stops[-1]
        leg_c = legs[k - 2]
        leg_plan = max(15, math.ceil(leg_c / 100 / speed * 60))
        intermediate = 1 < k < n
        svc = gauss_int(rng, t["service_minutes"]) if intermediate else 0
        over = gauss_int(rng, t["service_overrun_minutes"]) if intermediate else 0
        delay = gauss_int(rng, t["leg_delay_minutes"])
        plan_arr = prev.plan_dep + leg_plan
        real_arr = prev.real_dep + leg_plan + delay
        stops.append(_Stop(k, codes[k - 1], kinds[k - 1], leg_c, plan_arr, plan_arr + svc,
                           real_arr, real_arr + svc + over))
    return stops


def generate_trip(cfg: dict, master, ti: TripInput) -> TripOutput:
    seed, t, cons = cfg["seed"], cfg["trip_model"], cfg["constraints"]
    rng = make_rng(seed, f"trip.{ti.talon}")
    locs = [loc["CODIGO_UBICACION"] for loc in master.locations]
    origin, dest = rng.sample(locs, 2)
    c_org, c_dst = rng.sample(master.clients, 2)
    km_c = rng.randint(_c(t["km_range"][0]), _c(t["km_range"][1]))
    speed = rng.uniform(*t["speed_kmh_range"])
    if rng.random() < t["empty_zero_prob"]:
        vac_c = 0
    else:
        vac_c = int(round(km_c * rng.uniform(*t["empty_km_share_range"])))
    car_c = km_c - vac_c
    elo, ehi = cons["energy_efficiency_km_per_kwh"]
    eff = rng.triangular(elo + 0.05, ehi - 0.05, t["efficiency_mode"])
    kwh = round(_f(km_c) / eff, 2)
    batt0 = round(rng.uniform(*t["battery_start_pct_range"]), 2)
    batt1 = round(batt0 - kwh / t["battery_capacity_kwh"] * 100, 2)
    cargo, cargo_kg = plan_cargo(cfg, rng)
    n0 = rng.randint(*cons["stops_per_trip"])
    min_stops = cons["stops_per_trip"][0]
    ue = f"UE-{ti.talon}"

    stops = None
    for n in range(n0, min_stops - 1, -1):
        stops = _timeline(cfg, make_rng(seed, f"trip.{ti.talon}.a{n}"), locs, origin, dest, n,
                          km_c, speed, ti.start_minute)
        if stops[-1].real_arr <= MAX_END_MINUTE:
            break
    else:  # pragma: no cover - la validacion de config acota el peor caso
        raise RuntimeError(f"El viaje {ti.talon} no cabe en un dia")
    n = len(stops)
    end_minute = stops[-1].real_arr
    closed = ti.cutoff is None or end_minute <= ti.cutoff

    paradas = []
    names = {loc["CODIGO_UBICACION"]: loc["NOMBRE_UBICACION"] for loc in master.locations}
    for s in stops:
        cutoff = ti.cutoff
        arrived = cutoff is None or s.real_arr <= cutoff
        departed = cutoff is None or s.real_dep <= cutoff
        status = "COMPLETADA" if departed else "EN_CURSO" if arrived else "PENDIENTE"
        paradas.append({
            "TALON_FOLIO": ti.talon,
            "NUMERO_SECUENCIA": s.seq,
            "CODIGO_UBICACION": s.code,
            "NOMBRE_UBICACION": names[s.code],
            "TIPO_EVENTO": s.kind,
            "FECHA_HORA_PROGRAMADA": _ts(ti.day, s.plan_arr),
            "FECHA_HORA_LLEGADA_REAL": _ts(ti.day, s.real_arr) if arrived else None,
            "FECHA_HORA_SALIDA_REAL": _ts(ti.day, s.real_dep) if departed else None,
            "UNIDAD_EMBARQUE_UE": ue if s.kind in ("CARGA", "DESCARGA") else None,
            "KMS_TRAMO": _f(s.leg_c) if arrived else 0.0,
            "LAG_LLEGADA_MINUTOS": float(s.real_arr - s.plan_arr) if arrived else None,
            "LAG_SALIDA_MINUTOS": float(s.real_dep - s.plan_dep) if departed else None,
            "TIEMPO_ESTADIA_MINUTOS": float(s.real_dep - s.real_arr) if departed else None,
            "ESTATUS_PARADA": status,
            "_ING_DAY": ti.day,
        })

    odo_end = round(ti.odometer_start + _f(km_c), 2) if closed else None
    despacho = {
        "TALON_FOLIO": ti.talon,
        "FECHA_DESPACHO": _ts(ti.day, ti.start_minute),
        "HORA_DESPACHO": f"{ti.start_minute // 60:02d}:{ti.start_minute % 60:02d}:00",
        "CODIGO_ECO": ti.eco,
        "CODIGO_REMOLQUE": master.trailer_for(ti.eco),
        "CODIGO_OPERADOR": ti.operator_code,
        "TAG_IAVE": f"IAVE-{ti.eco}",
        "CLIENTE_ORIGEN": c_org["RAZON_SOCIAL"],
        "CLIENTE_DESTINO": c_dst["RAZON_SOCIAL"],
        "ODOMETRO_INICIAL": ti.odometer_start,
        "ODOMETRO_FINAL": odo_end,
        "KMS_CARGADO": _f(car_c) if closed else 0.0,
        "KMS_VACIO": _f(vac_c) if closed else 0.0,
        "KMS_TOTAL": _f(km_c) if closed else 0.0,
        "BATERIA_INICIAL_PCT": batt0,
        "BATERIA_FINAL_PCT": batt1 if closed else None,
        "KWH_CONSUMO": kwh if closed else 0.0,
        "RENDIMIENTO_KMS_KWH": round(_f(km_c) / kwh, 4) if closed else 0.0,
        "PESO_BRUTO_KG": cargo_kg,
        "TOTAL_PARADAS": n,
        "ESTATUS_DESPACHO": ESTATUS_CERRADO if closed else ESTATUS_EN_TRANSITO,
        "FECHA_CIERRE": _ts(ti.day, end_minute) if closed else None,
        "_ING_DAY": ti.day,
    }
    return TripOutput(despacho, paradas, closed, origin, dest, c_org, c_dst, ue, cargo, cargo_kg,
                      _f(km_c), _f(km_c) if closed else 0.0, kwh if closed else 0.0, odo_end,
                      end_minute, n)
