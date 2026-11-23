import datetime as dt

import pytest

from src.batch import make_batch, stamp_rows
from src.config import ConfigError, status_counts, validate
from src.contract import validate_rows
from src.generators.fleet_master import generate_fleet_master


def test_status_counts_100_is_56_40_4(cfg):
    assert status_counts(100, cfg["fleet_status_mix"]) == {"with_trip": 56, "without_trip": 40, "inactive": 4}


def test_status_counts_always_sum_to_fleet(cfg):
    for n in (1, 7, 9, 99, 101):
        assert sum(status_counts(n, cfg["fleet_status_mix"]).values()) == n


def test_config_is_calibrated(cfg):
    assert cfg["fleet_size"] == 100 and cfg["end_date"] == dt.date(2026, 11, 6)
    p = cfg["pricing_model"]
    # Draft: ECO01 $89,088.00 en 595 km
    fixed = sum(s["amount"] for s in p["surcharges"] if s["probability"] == 1.0)
    assert round(p["base_rate"] + 595 * p["rate_per_km"] + fixed, 2) == 89088.00


@pytest.mark.parametrize("mutate,fragment", [
    (lambda c: c["fleet_status_mix"].update(inactive=0.10), "sumar 1.0"),
    (lambda c: c.update(end_date="2026-13-45"), "end_date"),
    (lambda c: c.update(fleet_size=0), "fleet_size"),
    (lambda c: c["constraints"].update(stops_per_trip=[12, 4]), "min > max"),
    (lambda c: c["fleet"].update(payload_capacity_kg=40000), "payload_capacity_kg"),
    (lambda c: c.pop("seed"), "seed"),
])
def test_config_validation_rejects(cfg_copy, mutate, fragment):
    mutate(cfg_copy)
    with pytest.raises(ConfigError) as exc:
        validate(cfg_copy)
    assert fragment in str(exc.value)


def test_fleet_master_shape(cfg):
    m = generate_fleet_master(cfg)
    ecos = [u["CODIGO_ECO"] for u in m.units]
    assert len(m.units) == 100
    assert ecos == [f"ECO{i:02d}" for i in range(1, 101)]
    assert len(set(ecos)) == 100
    assert len(m.operators) == 15 and len(m.clients) >= 5
    assert {"IMESA", "SMO", "MERCURIO"} <= {l["CODIGO_UBICACION"] for l in m.locations}
    assert m.trailers[4]["NUMERO_ECONOMICO_REMOLQUE"] == "CAJA05"
    assert m.daily_status_plan == {"with_trip": 56, "without_trip": 40, "inactive": 4}


def test_fleet_master_uniqueness(cfg):
    m = generate_fleet_master(cfg)
    plates = [u["PLACA"] for u in m.units] + [t["PLACA_REMOLQUE"] for t in m.trailers]
    assert len(plates) == len(set(plates))
    for key in ("NUMERO_SERIE_VIN", "NUMERO_MOTOR"):
        vals = [u[key] for u in m.units]
        assert len(vals) == len(set(vals))
    assert all(len(u["NUMERO_SERIE_VIN"]) == 17 for u in m.units)
    assert len({o["CODIGO_OPERADOR"] for o in m.operators}) == 15
    assert len({o["NOMBRE_OPERADOR"] for o in m.operators}) == 15
    assert len({p["NUMERO_POLIZA"] for p in m.policies}) == len(m.policies)


def test_fleet_physical_rules(cfg):
    m = generate_fleet_master(cfg)
    for u in m.units:
        assert 0 < u["CAPACIDAD_CARGA_KG"] <= u["PESO_BRUTO_MAX_KG"] <= 29685
        assert u["VIGENCIA_POLIZA"] > m.end_date          # poliza vigente a end_date
        assert 2022 <= u["ANIO_MODELO"] <= 2026
    # cada unidad referencia una poliza existente
    pol = {p["NUMERO_POLIZA"] for p in m.policies}
    assert {u["NUMERO_POLIZA_SEGURO"] for u in m.units} <= pol


def test_determinism_same_seed_same_output(cfg):
    a, b = generate_fleet_master(cfg), generate_fleet_master(cfg)
    assert a.units == b.units and a.operators == b.operators and a.clients == b.clients
    assert a.trailers == b.trailers and a.policies == b.policies


def test_different_seed_changes_output(cfg_copy):
    base = generate_fleet_master(cfg_copy)
    cfg_copy["seed"] = 43
    other = generate_fleet_master(cfg_copy)
    assert base.units != other.units


def test_units_pass_ddl_contract(cfg, contract):
    m = generate_fleet_master(cfg)
    batch = make_batch("backfill", cfg["end_date"], cfg["seed"], 1)
    validate_rows(contract["STG_FLOTA_UNIDADES"], stamp_rows(m.units, batch, "FLOTA"))


def test_batch_id_is_unique_per_run_and_deterministic(cfg):
    b1 = make_batch("backfill", cfg["end_date"], cfg["seed"], 1)
    b2 = make_batch("backfill", cfg["end_date"], cfg["seed"], 2)
    assert b1.batch_id == "SIM-BACKFILL-20261106-s42-001"
    assert b1.batch_id != b2.batch_id
    day = cfg["end_date"]
    assert b2.ingested_at(day) > b1.ingested_at(day)      # D7: version mas reciente
    assert b1.ingested_at(day + dt.timedelta(days=1)) > b2.ingested_at(day)
    assert make_batch("backfill", cfg["end_date"], cfg["seed"], 1) == b1
    assert len(b1.batch_id) <= 64
    with pytest.raises(ValueError):
        make_batch("backfill", cfg["end_date"], cfg["seed"], 0)
