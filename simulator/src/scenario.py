"""Escenario operativo (ST-3): calendario, viajes, estatus diario, Carta Porte y eventos SCD2.

Orquesta los generadores puros de `generators/`:
  * backfill: ultimos N dias hasta `end_date`; el ultimo dia se corta a `snapshot_minute` y los
    viajes que aun no terminan quedan EN_TRANSITO (D7).
  * incremental: UN dia operativo nuevo (ultimo dia en BD + 1) con `--trips N` viajes. Primero CIERRA
    los viajes abiertos regenerandolos completos (misma llave => mismo plan) e insertando una
    version nueva de despacho/paradas/estatus del dia original (append-only, D7).
El estado de entrada (`State`) viene de la BD (`db_loader.load_state`) o, en --dry-run, de simular
el backfill en memoria: ambos caminos producen el mismo estado.
Operadores: se asignan CON REEMPLAZO (hay 15 operadores y ~56 viajes por dia).
"""
from __future__ import annotations

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field

from .config import ConfigError, status_counts
from .generators.carta_porte import SOURCE_SYSTEM_CCP, build_documents
from .generators.finance_erp import (
    SOURCE_SYSTEM_FINANCE,
    build_cfdi_ingreso,
    build_liquidaciones_gastos,
)
from .generators.fleet_master import SOURCE_SYSTEM_FLOTA, FleetMaster, random_plate
from .generators.fleet_status import ESTATUS_CON_VIAJE, home_yard, plan_day, status_row
from .generators.trackit_ops import SOURCE_SYSTEM_TRACKIT, TripInput, generate_trip
from .rng import make_rng

EN_RUTA = "EN_RUTA"


@dataclass(frozen=True)
class OpenTrip:
    talon: str
    talon_num: int
    eco: str
    operator_code: str
    day: dt.date
    start_minute: int
    odometer_start: float


@dataclass
class State:
    """Lo minimo que una corrida incremental necesita saber de lo ya cargado."""
    history_start: dt.date | None
    last_day: dt.date | None
    next_talon_num: int
    odometers: dict[str, float] = field(default_factory=dict)
    open_trips: list[OpenTrip] = field(default_factory=list)


@dataclass(frozen=True)
class Emission:
    table: str
    source: str
    rows: list[dict]
    suffix: str = ""


@dataclass
class ScenarioResult:
    emissions: list[Emission]
    end_state: State
    notes: list[str]
    summary: dict


def empty_state(cfg: dict) -> State:
    return State(None, None, cfg["numbering"]["talon_start"])


def initial_odometers(cfg: dict, master: FleetMaster) -> dict[str, float]:
    rng = make_rng(cfg["seed"], "fleet.odometer")
    lo, hi = cfg["fleet_status"]["initial_odometer_km_range"]
    return {u["CODIGO_ECO"]: round(rng.uniform(lo, hi), 2) for u in master.units}


class PlateBook:
    """Placa vigente por unidad y dia, segun los eventos SCD2 aplicables al historico."""

    def __init__(self, cfg: dict, master: FleetMaster, history_start: dt.date, upto: dt.date):
        self.notes: list[str] = []
        self._base = {u["CODIGO_ECO"]: u["PLACA"] for u in master.units}
        used = set(self._base.values()) | {t["PLACA_REMOLQUE"] for t in master.trailers}
        self.events: list[tuple[dt.date, str, str]] = []  # (efectiva, eco, placa nueva)
        for ev in sorted(cfg["scd2_events"], key=lambda e: (e["effective_date"], e["eco"])):
            eco, eff = ev["eco"], ev["effective_date"]
            if eco not in self._base:
                raise ConfigError(f"scd2_events: la unidad {eco} no existe en la flota")
            if not history_start < eff <= upto:
                self.notes.append(f"AVISO: evento SCD2 {eco}@{eff} omitido: fuera de la ventana "
                                  f"({history_start}, {upto}]; debe ser posterior al inicio del historico")
                continue
            plate = None
            for attempt in range(1, 200):
                cand = random_plate(make_rng(cfg["seed"], f"scd2.{eco}.{eff.isoformat()}.{attempt}"))
                if cand not in used:
                    plate = cand
                    break
            if plate is None:  # pragma: no cover - espacio de placas >> flota
                raise ConfigError(f"No se pudo generar placa nueva para {eco}")
            used.add(plate)
            self.events.append((eff, eco, plate))

    def plate_on(self, eco: str, day: dt.date) -> str:
        plate = self._base[eco]
        for eff, e, new in self.events:  # ordenados por fecha efectiva
            if e == eco and eff <= day:
                plate = new
        return plate


def _event_emissions(master: FleetMaster, plates: PlateBook, after: dt.date) -> list[Emission]:
    out = []
    pending = [e for e in plates.events if e[0] > after]
    for n, (eff, eco, plate) in enumerate(pending, start=1):
        row = {**master.unit(eco), "PLACA": plate, "_ING_DAY": eff}
        out.append(Emission("STG_FLOTA_UNIDADES", SOURCE_SYSTEM_FLOTA, [row], f"-E{n:02d}"))
    return out


def _simulate(cfg: dict, master: FleetMaster, state: State, days: list[dt.date], n_trips: int,
              plates: PlateBook) -> tuple[dict[str, list[dict]], State, dict]:
    seed, tm = cfg["seed"], cfg["trip_model"]
    prefix, tnum = cfg["numbering"]["talon_prefix"], state.next_talon_num
    odo = initial_odometers(cfg, master)
    odo.update(state.odometers)
    operators = [o["CODIGO_OPERADOR"] for o in master.operators]
    out = {k: [] for k in ("despacho", "paradas", "estatus", "cp_cab", "cp_merc", "cfdi", "liquidaciones")}
    first_day, last_day = days[0], days[-1]

    # 1) Cierre de viajes abiertos de corridas previas (nueva version, D7).
    closed_now = 0
    for ot in state.open_trips:
        ti = TripInput(ot.talon, ot.talon_num, ot.eco, ot.operator_code,
                       ot.day, ot.start_minute, ot.odometer_start, None)
        trip = generate_trip(cfg, master, ti)
        for r in (trip.despacho, *trip.paradas):
            r["_ING_DAY"] = first_day
        out["despacho"].append(trip.despacho)
        out["paradas"].extend(trip.paradas)
        out["estatus"].append(status_row(ot.day, ot.eco, ESTATUS_CON_VIAJE, talon=ot.talon,
                                         yard=trip.destination, km=trip.km_total, kwh=trip.kwh,
                                         ing_day=first_day))
        # ST-4: Viaje ahora CERRADO -> emite CFDI y liquidacion en esta corrida (A4)
        out["cfdi"].append(build_cfdi_ingreso(cfg, master, ti, trip, ing_day=first_day))
        out["liquidaciones"].extend(build_liquidaciones_gastos(cfg, master, ti, trip, ing_day=first_day))
        odo[ot.eco] = trip.odometer_end
        closed_now += 1

    # 2) Dias nuevos.
    open_trips: list[OpenTrip] = []
    last_mix: Counter = Counter()
    trips_total = 0
    for day in days:
        cutoff = tm["snapshot_minute"] if day == last_day else None
        rng = make_rng(seed, f"day.{day.isoformat()}.trips")
        trips, others = plan_day(cfg, master, day, n_trips)
        day_status: dict[str, dict] = {}
        for eco in trips:
            talon = f"{prefix}{tnum}"
            op = rng.choice(operators)                     # con reemplazo
            start = rng.randint(*tm["start_minute_range"])
            ti = TripInput(talon, tnum, eco, op, day, start, odo[eco], cutoff)
            trip = generate_trip(cfg, master, ti)
            cab, merc = build_documents(cfg, master, ti, trip, plates.plate_on(eco, day))
            out["despacho"].append(trip.despacho)
            out["paradas"].extend(trip.paradas)
            out["cp_cab"].append(cab)
            out["cp_merc"].extend(merc)
            if trip.closed:
                odo[eco] = trip.odometer_end
                # ST-4: Solo viajes cerrados se facturan y liquidan (A4)
                out["cfdi"].append(build_cfdi_ingreso(cfg, master, ti, trip, ing_day=day))
                out["liquidaciones"].extend(build_liquidaciones_gastos(cfg, master, ti, trip, ing_day=day))
            else:
                open_trips.append(OpenTrip(talon, tnum, eco, op, day, start, ti.odometer_start))
            day_status[eco] = status_row(day, eco, ESTATUS_CON_VIAJE, talon=talon,
                                         yard=trip.destination if trip.closed else EN_RUTA,
                                         km=trip.km_total, kwh=trip.kwh)
            tnum += 1
            trips_total += 1
        for eco, estatus in others.items():
            day_status[eco] = status_row(day, eco, estatus, yard=home_yard(master, eco))
        out["estatus"].extend(day_status[e] for e in sorted(day_status))
        if day == last_day:
            last_mix = Counter(r["ESTATUS_PATIO"] for r in day_status.values())

    end_state = State(state.history_start or first_day, last_day, tnum, odo, open_trips)
    summary = {"dias": len(days), "viajes_nuevos": trips_total, "viajes_cerrados_ahora": closed_now,
               "viajes_abiertos_al_corte": len(open_trips),
               "mezcla_ultimo_dia": dict(sorted(last_mix.items()))}
    return out, end_state, summary


def _ops_emissions(rows: dict[str, list[dict]]) -> list[Emission]:
    return [
        Emission("STG_TRACKIT_DESPACHO", SOURCE_SYSTEM_TRACKIT, rows["despacho"]),
        Emission("STG_TRACKIT_PARADAS", SOURCE_SYSTEM_TRACKIT, rows["paradas"]),
        Emission("STG_CARTA_PORTE_CABECERA", SOURCE_SYSTEM_CCP, rows["cp_cab"]),
        Emission("STG_CARTA_PORTE_MERCANCIAS", SOURCE_SYSTEM_CCP, rows["cp_merc"]),
        Emission("STG_FLOTA_ESTATUS_DIARIO", SOURCE_SYSTEM_FLOTA, rows["estatus"]),
        Emission("STG_CFDI_INGRESO", SOURCE_SYSTEM_FINANCE, rows["cfdi"]),
        Emission("STG_LIQUIDACIONES_GASTOS", SOURCE_SYSTEM_FINANCE, rows["liquidaciones"]),
    ]


def backfill_days(end_date: dt.date, days: int) -> list[dt.date]:
    return [end_date - dt.timedelta(days=days - 1 - i) for i in range(days)]


def build_backfill(cfg: dict, master: FleetMaster, days: int) -> ScenarioResult:
    day_list = backfill_days(cfg["end_date"], days)
    start = day_list[0]
    plates = PlateBook(cfg, master, start, cfg["end_date"])
    n_trips = status_counts(cfg["fleet_size"], cfg["fleet_status_mix"])["with_trip"]
    rows, end_state, summary = _simulate(cfg, master, empty_state(cfg), day_list, n_trips, plates)
    emissions = [Emission("STG_FLOTA_UNIDADES", SOURCE_SYSTEM_FLOTA,
                          [{**u, "_ING_DAY": start} for u in master.units])]
    emissions += _event_emissions(master, plates, start - dt.timedelta(days=1))
    emissions += _ops_emissions(rows)
    summary["eventos_scd2"] = len(plates.events)
    return ScenarioResult(emissions, end_state, plates.notes, summary)


def build_incremental(cfg: dict, master: FleetMaster, state: State, n_trips: int) -> ScenarioResult:
    if state.last_day is None or state.history_start is None:
        raise ConfigError("--mode incremental requiere un backfill previo (STG_TRACKIT_DESPACHO vacia)")
    day = state.last_day + dt.timedelta(days=1)
    plates = PlateBook(cfg, master, state.history_start, day)
    rows, end_state, summary = _simulate(cfg, master, state, [day], n_trips, plates)
    emissions = _event_emissions(master, plates, state.last_day) + _ops_emissions(rows)
    summary["eventos_scd2"] = len([e for e in plates.events if e[0] > state.last_day])
    return ScenarioResult(emissions, end_state, plates.notes, summary)
