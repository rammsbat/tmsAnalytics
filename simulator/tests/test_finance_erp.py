"""Invariantes de ST-4: ERP Financiero (CFDI Ingreso 4.0 y Liquidaciones de Gastos)."""
import datetime as dt
from decimal import Decimal
import re
from collections import Counter, defaultdict

import pytest

from src.batch import make_batch, stamp_rows
from src.contract import validate_rows
from src.generators.fleet_master import generate_fleet_master
from src.generators.trackit_ops import TripInput, generate_trip
from src.generators.finance_erp import build_cfdi_ingreso, build_liquidaciones_gastos
from src.scenario import build_backfill, build_incremental

DAYS = 90
UUID_RE = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


@pytest.fixture(scope="module")
def master(cfg):
    return generate_fleet_master(cfg)


@pytest.fixture(scope="module")
def bf(cfg, master):
    return build_backfill(cfg, master, DAYS)


def rows(result, table, suffix=""):
    return [r for e in result.emissions if e.table == table and e.suffix == suffix for r in e.rows]


# ---------------------------------------------------------------- Contrato DDL
def test_cfdi_and_liquidaciones_pass_contract(bf, contract, cfg):
    batch = make_batch("backfill", cfg["end_date"], cfg["seed"], 1)
    for name in ("STG_CFDI_INGRESO", "STG_LIQUIDACIONES_GASTOS"):
        table_rows = rows(bf, name)
        assert len(table_rows) > 0, f"{name} debe tener filas"
        stamped = stamp_rows(table_rows, batch, "ERP_FINANCIERO")
        validate_rows(contract[name], stamped)


# ---------------------------------------------------------------- Viajes cerrados e incremental (A4)
def test_cfdi_and_liquidaciones_only_emitted_for_closed_trips(bf):
    despachos = rows(bf, "STG_TRACKIT_DESPACHO")
    cfdi = rows(bf, "STG_CFDI_INGRESO")
    liq = rows(bf, "STG_LIQUIDACIONES_GASTOS")

    closed_talons = {r["TALON_FOLIO"] for r in despachos if r["ESTATUS_DESPACHO"] == "CERRADO"}
    open_talons = {r["TALON_FOLIO"] for r in despachos if r["ESTATUS_DESPACHO"] == "EN_TRANSITO"}

    assert len(open_talons) == 11
    assert len(closed_talons) == len(despachos) - 11 == 5029

    cfdi_talons = {r["NUMERO_TALON"] for r in cfdi}
    liq_talons = {r["NUMERO_TALON"] for r in liq}

    # Cada viaje cerrado tiene exactamente 1 CFDI y 1 grupo de liquidaciones
    assert cfdi_talons == closed_talons
    assert len(cfdi) == len(closed_talons)
    assert liq_talons == closed_talons

    # Ningun viaje abierto tiene CFDI ni liquidacion en el backfill
    assert not (cfdi_talons & open_talons)
    assert not (liq_talons & open_talons)


def test_incremental_invoices_and_liquidates_closed_open_trips(cfg, master, bf):
    inc = build_incremental(cfg, master, bf.end_state, n_trips=5)
    cfdi_inc = rows(inc, "STG_CFDI_INGRESO")
    liq_inc = rows(inc, "STG_LIQUIDACIONES_GASTOS")
    desp_inc = rows(inc, "STG_TRACKIT_DESPACHO")

    # 11 viajes que venian abiertos + 5 nuevos = 16 despachos
    assert len(desp_inc) == 16
    closed_desp = [r for r in desp_inc if r["ESTATUS_DESPACHO"] == "CERRADO"]
    closed_talons = {r["TALON_FOLIO"] for r in closed_desp}

    # Solo los viajes cerrados (11 anteriores cerrados + cerrados del dia nuevo) se facturan
    assert len(cfdi_inc) == len(closed_desp)
    assert {r["NUMERO_TALON"] for r in cfdi_inc} == closed_talons

    # Los 11 talones abiertos al corte del backfill ahora estan 100% facturados y liquidados
    open_bf_talons = {ot.talon for ot in bf.end_state.open_trips}
    assert len(open_bf_talons) == 11
    assert open_bf_talons.issubset({r["NUMERO_TALON"] for r in cfdi_inc})
    assert open_bf_talons.issubset({r["NUMERO_TALON"] for r in liq_inc})


# ---------------------------------------------------------------- Cuadre fiscal al centavo
def test_cfdi_fiscal_math_exact_to_cent(bf):
    cfdi = rows(bf, "STG_CFDI_INGRESO")
    for r in cfdi:
        subtotal = Decimal(str(r["IMPORTE_SUBTOTAL"]))
        descuento = Decimal(str(r["IMPORTE_DESCUENTO"]))
        iva_trasladado = Decimal(str(r["IMPORTE_IVA_TRASLADADO"]))
        iva_retenido = Decimal(str(r["IMPORTE_IVA_RETENIDO"]))
        total = Decimal(str(r["IMPORTE_TOTAL"]))

        # Importes estrictamente positivos
        assert subtotal > 0
        assert total > 0
        assert descuento == 0
        assert r["MONEDA"] == "MXN"
        assert r["TIPO_CAMBIO"] == 1.0
        assert r["ESTATUS_FACTURA"] == "TIMBRADA"
        assert r["METODO_PAGO"] == "PPD"
        assert r["FORMA_PAGO"] == "99"

        # Tasas fiscales exactas
        base = subtotal - descuento
        assert iva_trasladado == round(base * Decimal("0.16"), 2)
        assert iva_retenido == round(base * Decimal("0.04"), 2)

        # Cuadre total al centavo
        assert total == base + iva_trasladado - iva_retenido

        # UUID determinista valido
        assert UUID_RE.match(r["UUID_INGRESO"]) is not None


def test_cfdi_calibration_draft_trip(cfg, master):
    """Calibracion ECO01: 595 km -> 1,000 + 595*147.50 + 325.50 = $89,088.00."""
    ti = TripInput("GRD999", 999, "ECO01", "OP001", dt.date(2026, 11, 1), 360, 10000.0, None)
    trip = generate_trip(cfg, master, ti)
    # Forzamos 595.0 km para verificar la formula exacta
    trip.km_total = 595.0
    cfdi = build_cfdi_ingreso(cfg, master, ti, trip, dt.date(2026, 11, 1))

    # Base $1,000 + 595 * $147.50 ($87,762.50) + maniobras ($325.50) = $89,088.00
    assert cfdi["IMPORTE_SUBTOTAL"] == 89088.00
    assert cfdi["IMPORTE_IVA_TRASLADADO"] == 14254.08
    assert cfdi["IMPORTE_IVA_RETENIDO"] == 3563.52
    assert cfdi["IMPORTE_TOTAL"] == 99778.56


# ---------------------------------------------------------------- Granularidad de Liquidacion (H5)
def test_liquidaciones_granularity_and_types(bf):
    liq = rows(bf, "STG_LIQUIDACIONES_GASTOS")
    by_folio = defaultdict(list)
    for r in liq:
        by_folio[r["FOLIO_LIQUIDACION"]].append(r)
        assert r["IMPORTE_GASTO"] > 0
        assert r["ESTATUS_LIQUIDACION"] == "APROBADA"
        assert r["TIPO_GASTO"] in ("CASETA", "OPERADOR", "MANTENIMIENTO", "OTROS")

    # Prohibicion explicita: sin COMBUSTIBLE_ENERGIA
    tipos_presentes = {r["TIPO_GASTO"] for r in liq}
    assert "COMBUSTIBLE_ENERGIA" not in tipos_presentes

    # Cada folio tiene multiples lineas atomicas
    for folio, lines in by_folio.items():
        assert len(lines) >= 3  # min: 2 casetas + 1 operador
        tipo_counts = Counter(line["TIPO_GASTO"] for line in lines)
        assert 2 <= tipo_counts["CASETA"] <= 4, f"{folio} casetas: {tipo_counts['CASETA']}"
        assert tipo_counts["OPERADOR"] == 1, f"{folio} operador: {tipo_counts['OPERADOR']}"
        assert tipo_counts["MANTENIMIENTO"] <= 1
        assert tipo_counts["OTROS"] <= 1

        # Todas las lineas del folio comparten NUMERO_TALON, CODIGO_ECO, CODIGO_OPERADOR
        talons = {line["NUMERO_TALON"] for line in lines}
        ecos = {line["CODIGO_ECO"] for line in lines}
        ops = {line["CODIGO_OPERADOR"] for line in lines}
        assert len(talons) == 1
        assert len(ecos) == 1
        assert len(ops) == 1


# ---------------------------------------------------------------- Margen Operativo Positivo
def test_positive_operating_margin(bf):
    cfdi = rows(bf, "STG_CFDI_INGRESO")
    liq = rows(bf, "STG_LIQUIDACIONES_GASTOS")

    ingresos_por_talon = {r["NUMERO_TALON"]: r["IMPORTE_SUBTOTAL"] for r in cfdi}
    gastos_por_talon = defaultdict(float)
    for r in liq:
        gastos_por_talon[r["NUMERO_TALON"]] += r["IMPORTE_GASTO"]

    # Para cada viaje cerrado, el ingreso supera a los costos directos de viaje
    for talon, ingreso in ingresos_por_talon.items():
        gasto = gastos_por_talon[talon]
        assert gasto > 0, f"talon {talon} sin gastos"
        assert ingreso > gasto, f"talon {talon} ingreso {ingreso} <= gasto {gasto}"

    total_ingreso = sum(ingresos_por_talon.values())
    total_gasto = sum(gastos_por_talon.values())
    assert total_ingreso > 0 and total_gasto > 0
    margen_global_pct = (total_ingreso - total_gasto) / total_ingreso
    assert margen_global_pct > 0.85  # Margen global fuertemente positivo (~93%)


# ---------------------------------------------------------------- Determinismo
def test_finance_generation_is_deterministic(cfg, master):
    ti = TripInput("GRD500", 500, "ECO10", "OP005", dt.date(2026, 11, 2), 400, 20000.0, None)
    t1 = generate_trip(cfg, master, ti)
    t2 = generate_trip(cfg, master, ti)

    c1 = build_cfdi_ingreso(cfg, master, ti, t1, dt.date(2026, 11, 2))
    c2 = build_cfdi_ingreso(cfg, master, ti, t2, dt.date(2026, 11, 2))
    assert c1 == c2

    l1 = build_liquidaciones_gastos(cfg, master, ti, t1, dt.date(2026, 11, 2))
    l2 = build_liquidaciones_gastos(cfg, master, ti, t2, dt.date(2026, 11, 2))
    assert l1 == l2
