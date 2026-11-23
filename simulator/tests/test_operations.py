"""Invariantes de ST-3: TrackIt, Carta Porte, estatus diario y eventos SCD2 (sin Oracle)."""
import datetime as dt
from collections import Counter, defaultdict

import pytest

from src.batch import make_batch, stamp_rows
from src.config import ConfigError
from src.contract import validate_rows
from src.generators.fleet_master import generate_fleet_master
from src.scenario import PlateBook, backfill_days, build_backfill, build_incremental

DAYS = 90


@pytest.fixture(scope="module")
def master(cfg):
    return generate_fleet_master(cfg)


@pytest.fixture(scope="module")
def bf(cfg, master):
    return build_backfill(cfg, master, DAYS)


def rows(result, table, suffix=""):
    return [r for e in result.emissions if e.table == table and e.suffix == suffix for r in e.rows]


# ---------------------------------------------------------------- estatus diario / despachos
def test_status_has_100_units_every_day_with_56_40_4(bf, cfg):
    by_day = defaultdict(list)
    for r in rows(bf, "STG_FLOTA_ESTATUS_DIARIO"):
        by_day[r["FECHA_CORTE"]].append(r)
    assert sorted(by_day) == backfill_days(cfg["end_date"], DAYS)
    for day, day_rows in by_day.items():
        assert len(day_rows) == 100 and len({r["CODIGO_ECO"] for r in day_rows}) == 100, day
        c = Counter(r["ESTATUS_PATIO"] for r in day_rows)
        assert c["DISPONIBLE_CON_VIAJE"] == 56 and c["DISPONIBLE_SIN_VIAJE"] == 40, day
        assert c["EN_MANTENIMIENTO"] + c["INACTIVO"] == 4 and c["INACTIVO"] == 1, day


def test_con_viaje_matches_dispatches_exactly(bf):
    """A1/A2: DISPONIBLE_CON_VIAJE <=> la unidad tiene despacho ese dia (mismo talon)."""
    disp = {(r["FECHA_DESPACHO"].date(), r["CODIGO_ECO"]): r["TALON_FOLIO"]
            for r in rows(bf, "STG_TRACKIT_DESPACHO")}
    con = {(r["FECHA_CORTE"], r["CODIGO_ECO"]): r["NUMERO_TALON"]
           for r in rows(bf, "STG_FLOTA_ESTATUS_DIARIO") if r["ESTATUS_PATIO"] == "DISPONIBLE_CON_VIAJE"}
    assert con == disp
    for r in rows(bf, "STG_FLOTA_ESTATUS_DIARIO"):
        if r["ESTATUS_PATIO"] != "DISPONIBLE_CON_VIAJE":
            assert r["NUMERO_TALON"] is None and r["KMS_ODOMETRO_DIA"] == 0 and r["KWH_CONSUMO_DIA"] == 0


def test_one_dispatch_per_unit_per_day_and_unique_talons(bf):
    d = rows(bf, "STG_TRACKIT_DESPACHO")
    assert len({r["TALON_FOLIO"] for r in d}) == len(d) == 56 * DAYS
    assert len({(r["FECHA_DESPACHO"].date(), r["CODIGO_ECO"]) for r in d}) == len(d)
    assert d[0]["TALON_FOLIO"] == "GRD340"


def test_status_km_kwh_match_dispatch(bf):
    disp = {r["TALON_FOLIO"]: r for r in rows(bf, "STG_TRACKIT_DESPACHO")}
    for r in rows(bf, "STG_FLOTA_ESTATUS_DIARIO"):
        if r["NUMERO_TALON"]:
            d = disp[r["NUMERO_TALON"]]
            assert (r["KMS_ODOMETRO_DIA"], r["KWH_CONSUMO_DIA"]) == (d["KMS_TOTAL"], d["KWH_CONSUMO"])


# ---------------------------------------------------------------- reglas fisicas
def test_trip_physics(bf, cfg):
    cons = cfg["constraints"]
    elo, ehi = cons["energy_efficiency_km_per_kwh"]
    for r in rows(bf, "STG_TRACKIT_DESPACHO"):
        assert round(r["KMS_CARGADO"] + r["KMS_VACIO"], 2) == r["KMS_TOTAL"]
        assert 0 < r["PESO_BRUTO_KG"] <= cons["max_gross_weight_kg"]
        assert cons["stops_per_trip"][0] <= r["TOTAL_PARADAS"] <= cons["stops_per_trip"][1]
        assert r["FECHA_DESPACHO"].date() == (r["FECHA_CIERRE"] or r["FECHA_DESPACHO"]).date()  # un dia
        if r["ESTATUS_DESPACHO"] == "CERRADO":
            assert r["KMS_TOTAL"] > 0
            assert elo <= r["RENDIMIENTO_KMS_KWH"] <= ehi
            assert r["BATERIA_FINAL_PCT"] > 0
            assert r["FECHA_CIERRE"] >= r["FECHA_DESPACHO"]
            assert round(r["ODOMETRO_INICIAL"] + r["KMS_TOTAL"], 2) == r["ODOMETRO_FINAL"]
        else:  # EN_TRANSITO: sin doble conteo hasta el cierre
            assert r["KMS_TOTAL"] == 0 and r["ODOMETRO_FINAL"] is None and r["BATERIA_FINAL_PCT"] is None


def test_stops_dates_and_lags(bf):
    by_talon = defaultdict(list)
    for p in rows(bf, "STG_TRACKIT_PARADAS"):
        by_talon[p["TALON_FOLIO"]].append(p)
    disp = {r["TALON_FOLIO"]: r for r in rows(bf, "STG_TRACKIT_DESPACHO")}
    assert set(by_talon) == set(disp)
    for talon, stops in by_talon.items():
        stops.sort(key=lambda s: s["NUMERO_SECUENCIA"])
        assert [s["NUMERO_SECUENCIA"] for s in stops] == list(range(1, disp[talon]["TOTAL_PARADAS"] + 1))
        assert stops[0]["TIPO_EVENTO"] == "INICIO VIAJE"
        closed = disp[talon]["ESTATUS_DESPACHO"] == "CERRADO"
        assert (stops[-1]["TIPO_EVENTO"] == "FIN VIAJE") and (stops[-1]["ESTATUS_PARADA"] == "COMPLETADA") == closed
        prev_dep = None
        for s in stops:
            arr, dep = s["FECHA_HORA_LLEGADA_REAL"], s["FECHA_HORA_SALIDA_REAL"]
            if arr and dep:
                assert dep >= arr
                assert s["TIEMPO_ESTADIA_MINUTOS"] == (dep - arr).total_seconds() / 60
            if arr:
                assert s["LAG_LLEGADA_MINUTOS"] == (arr - s["FECHA_HORA_PROGRAMADA"]).total_seconds() / 60
                if prev_dep:
                    assert arr >= prev_dep
            prev_dep = dep or prev_dep
        if closed:
            assert round(sum(s["KMS_TRAMO"] for s in stops), 2) == disp[talon]["KMS_TOTAL"]


def test_only_last_day_has_open_trips(bf, cfg):
    open_ = [r for r in rows(bf, "STG_TRACKIT_DESPACHO") if r["ESTATUS_DESPACHO"] == "EN_TRANSITO"]
    assert open_ and {r["FECHA_DESPACHO"].date() for r in open_} == {cfg["end_date"]}
    assert len(open_) == bf.summary["viajes_abiertos_al_corte"]


def test_odometers_are_continuous_per_unit(bf):
    last = {}
    for r in sorted(rows(bf, "STG_TRACKIT_DESPACHO"), key=lambda r: r["FECHA_DESPACHO"]):
        if r["CODIGO_ECO"] in last:
            assert r["ODOMETRO_INICIAL"] == last[r["CODIGO_ECO"]]
        if r["ODOMETRO_FINAL"] is not None:
            last[r["CODIGO_ECO"]] = r["ODOMETRO_FINAL"]


def test_operators_assigned_with_replacement(bf, master):
    ops = Counter(r["CODIGO_OPERADOR"] for r in rows(bf, "STG_TRACKIT_DESPACHO"))
    valid = {o["CODIGO_OPERADOR"] for o in master.operators}
    assert set(ops) <= valid and len(ops) == 15
    per_day = Counter((r["FECHA_DESPACHO"].date(), r["CODIGO_OPERADOR"]) for r in rows(bf, "STG_TRACKIT_DESPACHO"))
    assert max(per_day.values()) > 1          # un operador atiende varios viajes por dia (56 viajes, 15 operadores)


# ---------------------------------------------------------------- Carta Porte
def test_carta_porte_links_weight_and_closed_sat_catalogs(bf, cfg):
    cab = {c["NUMERO_TALON"]: c for c in rows(bf, "STG_CARTA_PORTE_CABECERA")}
    disp = {r["TALON_FOLIO"]: r for r in rows(bf, "STG_TRACKIT_DESPACHO")}
    assert set(cab) == set(disp) and len({c["UUID_CCP"] for c in cab.values()}) == len(cab)
    by_uuid = defaultdict(list)
    for m in rows(bf, "STG_CARTA_PORTE_MERCANCIAS"):
        by_uuid[m["UUID_CCP"]].append(m)
    cat = cfg["sat_catalogs"]
    productos = {p["clave"] for p in cat["productos"]}
    unidades = {u["clave"] for u in cat["unidades"]}
    for talon, c in cab.items():
        items = by_uuid[c["UUID_CCP"]]
        total = round(sum(i["PESO_KG"] for i in items), 2)
        assert total == c["PESO_BRUTO_TOTAL_KG"] == disp[talon]["PESO_BRUTO_KG"]
        assert 0 < total <= cfg["constraints"]["max_gross_weight_kg"]
        assert c["NUMERO_TOTAL_MERCANCIAS"] == len(items)
        assert [i["NUMERO_PARTIDA"] for i in items] == list(range(1, len(items) + 1))
        for i in items:
            assert i["PESO_KG"] > 0 and i["CLAVE_PRODUCTO_SAT"] in productos
            assert i["CLAVE_UNIDAD_SAT"] in unidades and i["UNIDAD_EMBARQUE_UE"] == f"UE-{talon}"
        assert c["CONFIGURACION_SAT"] in {x["clave"] for x in cat["configuracion_autotransporte"]}
        assert c["CODIGO_ECO"] == disp[talon]["CODIGO_ECO"]


def test_ue_in_stops_matches_cargo(bf):
    ue_stops = {p["UNIDAD_EMBARQUE_UE"] for p in rows(bf, "STG_TRACKIT_PARADAS") if p["UNIDAD_EMBARQUE_UE"]}
    ue_cargo = {m["UNIDAD_EMBARQUE_UE"] for m in rows(bf, "STG_CARTA_PORTE_MERCANCIAS")}
    assert ue_stops <= ue_cargo


# ---------------------------------------------------------------- SCD2
def test_scd2_events_have_later_effective_date_and_new_plates(bf, cfg, master):
    start = backfill_days(cfg["end_date"], DAYS)[0]
    base = rows(bf, "STG_FLOTA_UNIDADES")
    assert len(base) == 100 and {r["_ING_DAY"] for r in base} == {start}
    ev1, ev2 = rows(bf, "STG_FLOTA_UNIDADES", "-E01"), rows(bf, "STG_FLOTA_UNIDADES", "-E02")
    assert [r["CODIGO_ECO"] for r in ev1 + ev2] == ["ECO07", "ECO42"]
    for ev, spec in zip(ev1 + ev2, cfg["scd2_events"]):
        assert ev["_ING_DAY"] == spec["effective_date"] > start
        assert ev["PLACA"] != master.unit(ev["CODIGO_ECO"])["PLACA"]
    plates = [u["PLACA"] for u in base] + [e["PLACA"] for e in ev1 + ev2] + [t["PLACA_REMOLQUE"] for t in master.trailers]
    assert len(plates) == len(set(plates))


def test_carta_porte_uses_plate_valid_that_day(bf, cfg, master):
    ev = {r["CODIGO_ECO"]: (r["_ING_DAY"], r["PLACA"]) for sfx in ("-E01", "-E02")
          for r in rows(bf, "STG_FLOTA_UNIDADES", sfx)}
    seen_old = seen_new = 0
    for c in rows(bf, "STG_CARTA_PORTE_CABECERA"):
        eco, day = c["CODIGO_ECO"], c["FECHA_EMISION"].date()
        if eco in ev:
            eff, new = ev[eco]
            if day >= eff:
                assert c["PLACA_VEHICULO"] == new
                seen_new += 1
            else:
                assert c["PLACA_VEHICULO"] == master.unit(eco)["PLACA"]
                seen_old += 1
    assert seen_old > 0 and seen_new > 0


def test_scd2_event_outside_window_is_omitted_with_notice(cfg_copy, master):
    cfg_copy["scd2_events"] = [{"eco": "ECO07", "effective_date": dt.date(2026, 7, 1), "change": "PLACA"}]
    result = build_backfill(cfg_copy, master, 30)
    assert rows(result, "STG_FLOTA_UNIDADES", "-E01") == []
    assert result.notes and "omitido" in result.notes[0]


def test_scd2_event_equal_to_history_start_is_rejected_as_window(cfg_copy, master):
    start = backfill_days(cfg_copy["end_date"], 30)[0]
    cfg_copy["scd2_events"] = [{"eco": "ECO07", "effective_date": start, "change": "PLACA"}]
    assert build_backfill(cfg_copy, master, 30).notes        # no es posterior al inicio: omitido


def test_scd2_unknown_unit_fails(cfg_copy, master):
    cfg_copy["scd2_events"] = [{"eco": "ECO101", "effective_date": dt.date(2026, 10, 1), "change": "PLACA"}]
    with pytest.raises(ConfigError):
        PlateBook(cfg_copy, master, dt.date(2026, 8, 9), dt.date(2026, 11, 6))

# ---------------------------------------------------------------- incremental
def test_incremental_closes_open_trips_and_continues_numbering(cfg, master, bf):
    inc = build_incremental(cfg, master, bf.end_state, 5)
    disp = rows(inc, "STG_TRACKIT_DESPACHO")
    open_before = {t.talon for t in bf.end_state.open_trips}
    closed = [r for r in disp if r["TALON_FOLIO"] in open_before]
    assert len(closed) == len(open_before) == 11 and all(r["ESTATUS_DESPACHO"] == "CERRADO" for r in closed)
    new = [r for r in disp if r["TALON_FOLIO"] not in open_before]
    assert [r["TALON_FOLIO"] for r in new][0] == f"GRD{340 + 56 * DAYS}"
    assert all(r["FECHA_DESPACHO"].date() == cfg["end_date"] + dt.timedelta(days=1) for r in new)
    # la version de cierre supera a la apertura en INGESTED_AT (D7)
    b1, b2 = make_batch("backfill", cfg["end_date"], cfg["seed"], 1), make_batch("incremental", cfg["end_date"], cfg["seed"], 2)
    day_open = cfg["end_date"]
    assert b2.ingested_at(closed[0]["_ING_DAY"]) > b1.ingested_at(day_open)
    status = rows(inc, "STG_FLOTA_ESTATUS_DIARIO")
    assert len([s for s in status if s["FECHA_CORTE"] == cfg["end_date"]]) == 11   # cierres del dia anterior
    assert len([s for s in status if s["FECHA_CORTE"] == cfg["end_date"] + dt.timedelta(days=1)]) == 100


def test_incremental_requires_prior_backfill(cfg, master):
    from src.scenario import empty_state
    with pytest.raises(ConfigError):
        build_incremental(cfg, master, empty_state(cfg), 5)


def test_incremental_too_many_trips_is_rejected(cfg, master, bf):
    with pytest.raises(ConfigError):
        build_incremental(cfg, master, bf.end_state, 97)     # 100 - 4 inactivas = 96 maximo


# ---------------------------------------------------------------- determinismo y contrato
def test_scenario_is_deterministic(cfg, master, bf):
    again = build_backfill(cfg, master, DAYS)
    for a, b in zip(bf.emissions, again.emissions):
        assert (a.table, a.suffix, a.rows) == (b.table, b.suffix, b.rows)


def test_different_seed_changes_trips(cfg_copy, master, bf):
    cfg_copy["seed"] = 7
    other = build_backfill(cfg_copy, generate_fleet_master(cfg_copy), 3)
    assert rows(other, "STG_TRACKIT_DESPACHO")[0]["KMS_TOTAL"] != rows(bf, "STG_TRACKIT_DESPACHO")[0]["KMS_TOTAL"]


def test_every_emission_passes_ddl_contract(bf, contract, cfg):
    batch = make_batch("backfill", cfg["end_date"], cfg["seed"], 1)
    for e in bf.emissions:
        validate_rows(contract[e.table], stamp_rows(e.rows, batch, e.source))


def test_ingested_at_reflects_operational_day(bf, cfg):
    batch = make_batch("backfill", cfg["end_date"], cfg["seed"], 1)
    stamped = stamp_rows(rows(bf, "STG_TRACKIT_DESPACHO")[:1], batch, "TRACKITWEB")
    assert stamped[0]["INGESTED_AT"].date() == stamped[0]["FECHA_DESPACHO"].date()
    assert "_ING_DAY" not in stamped[0]
