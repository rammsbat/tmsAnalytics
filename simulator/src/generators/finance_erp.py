"""ERP Financiero (ST-4): STG_CFDI_INGRESO + STG_LIQUIDACIONES_GASTOS.

Genera facturacion comercial (CFDI Ingreso 4.0) y liquidacion de gastos de viaje:
  * Solo para viajes CERRADOS (A4): los viajes abiertos no se facturan ni liquidan hasta su cierre.
  * Cuadre fiscal al centavo con Decimal (ROUND_HALF_UP):
      IMPORTE_TOTAL = SUBTOTAL - DESCUENTO + IVA - RETENCION (16% IVA, 4% retencion flete).
  * Moneda MXN, tipo de cambio 1.0, importes >= 0, UUID determinista desde el RNG sembrado.
  * Granularidad de liquidacion (H5): un FOLIO_LIQUIDACION unico por viaje cerrado con multiples
    lineas atomicas (2-4 CASETA, 1 OPERADOR, MANTENIMIENTO y OTROS opcionales).
    Sin emitir COMBUSTIBLE_ENERGIA (flota electrica).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from typing import TYPE_CHECKING

from ..config import allocate
from ..rng import det_uuid, make_rng

if TYPE_CHECKING:
    from ..generators.fleet_master import FleetMaster
    from ..generators.trackit_ops import TripInput, TripOutput

SOURCE_SYSTEM_FINANCE = "ERP_FINANCIERO"
SERIE_FACTURA = "F"
MONEDA_MXN = "MXN"
METODO_PAGO_PPD = "PPD"
FORMA_PAGO_99 = "99"
ESTATUS_FACTURA_TIMBRADA = "TIMBRADA"
ESTATUS_LIQ_APROBADA = "APROBADA"

_CENT = Decimal("0.01")
_ZERO = Decimal("0.00")
_ONE = Decimal("1.0000")


def _dec(val: float | int | str) -> Decimal:
    return Decimal(str(val))


def _round_dec(val: Decimal) -> Decimal:
    return val.quantize(_CENT, rounding=ROUND_HALF_UP)


def _to_float(val: Decimal) -> float:
    return float(val)


def build_cfdi_ingreso(cfg: dict, master: FleetMaster, ti: TripInput,
                       trip: TripOutput, ing_day: dt.date) -> dict:
    """Genera 1 CFDI de Ingreso 4.0 para un viaje cerrado con cuadre fiscal exacto al centavo."""
    seed = cfg["seed"]
    pcfg = cfg["pricing_model"]
    rng = make_rng(seed, f"finance.cfdi.{ti.talon}")

    uuid_ingreso = det_uuid(make_rng(seed, f"cfdi.ingreso.{ti.talon}"))
    factura_id = f"F-{ti.talon}"

    # Base + Tarifa/km
    base_rate = _dec(pcfg["base_rate"])
    rate_km = _dec(pcfg["rate_per_km"])
    km_total = _dec(trip.km_total)
    subtotal = base_rate + (rate_km * km_total)

    # Recargos configurados
    for sc in pcfg.get("surcharges", []):
        prob = sc.get("probability", 1.0)
        if rng.random() < prob:
            subtotal += _dec(sc["amount"])

    subtotal = _round_dec(subtotal)
    descuento = _ZERO

    # Tasas fiscales: 16% IVA trasladado, 4% IVA retenido (autotransporte federal)
    iva_rate = _dec(pcfg["iva_rate"])
    ret_rate = _dec(pcfg["iva_retention_rate"])

    base_gravable = subtotal - descuento
    iva_trasladado = _round_dec(base_gravable * iva_rate)
    iva_retenido = _round_dec(base_gravable * ret_rate)

    # Cuadre fiscal al centavo
    total = base_gravable + iva_trasladado - iva_retenido

    # Fecha de factura con lag configurable respecto al cierre del viaje
    lag_days_lo, lag_days_hi = pcfg["invoice_lag_days"]
    lag_days = rng.randint(lag_days_lo, lag_days_hi)
    lag_minutes = rng.randint(10, 180)
    fecha_cierre = trip.despacho.get("FECHA_CIERRE")
    if fecha_cierre is not None:
        fecha_factura = fecha_cierre + dt.timedelta(days=lag_days, minutes=lag_minutes)
    else:
        fecha_factura = dt.datetime.combine(ti.day, dt.time(18, 0)) + dt.timedelta(days=lag_days)

    client_dst = trip.client_destination

    return {
        "UUID_INGRESO": uuid_ingreso,
        "FACTURA_ID": factura_id,
        "SERIE": SERIE_FACTURA,
        "FECHA_FACTURA": fecha_factura,
        "NUMERO_TALON": ti.talon,
        "RFC_EMISOR": master.company["RFC_EMISOR"],
        "RFC_RECEPTOR": client_dst["RFC_CLIENTE"],
        "RAZON_SOCIAL_RECEPTOR": client_dst["RAZON_SOCIAL"],
        "USO_CFDI": client_dst.get("USO_CFDI", "G03"),
        "REGIMEN_FISCAL_RECEPTOR": client_dst.get("REGIMEN_FISCAL", "601"),
        "MONEDA": MONEDA_MXN,
        "TIPO_CAMBIO": 1.0,
        "IMPORTE_SUBTOTAL": _to_float(subtotal),
        "IMPORTE_DESCUENTO": _to_float(descuento),
        "IMPORTE_IVA_TRASLADADO": _to_float(iva_trasladado),
        "IMPORTE_IVA_RETENIDO": _to_float(iva_retenido),
        "IMPORTE_TOTAL": _to_float(total),
        "METODO_PAGO": METODO_PAGO_PPD,
        "FORMA_PAGO": FORMA_PAGO_99,
        "ESTATUS_FACTURA": ESTATUS_FACTURA_TIMBRADA,
        "_ING_DAY": ing_day,
    }


def build_liquidaciones_gastos(cfg: dict, master: FleetMaster, ti: TripInput,
                               trip: TripOutput, ing_day: dt.date) -> list[dict]:
    """Genera lineas atomicas de liquidacion de gastos para un viaje cerrado (H5).

    Genera:
      - 2 a 4 registros de tipo 'CASETA' (peaje IAVE distribuido).
      - 1 registro de tipo 'OPERADOR' (pago base + por km).
      - Opcional: 1 registro 'MANTENIMIENTO' (probabilidad configurable).
      - Opcional: 1 registro 'OTROS' (gastos operativos menores).
      - NUNCA emite 'COMBUSTIBLE_ENERGIA'.
    Todas las lineas comparten el mismo FOLIO_LIQUIDACION.
    """
    seed = cfg["seed"]
    cost_cfg = cfg["cost_model"]
    rng = make_rng(seed, f"finance.liq.{ti.talon}")

    folio_liq = f"LIQ-{ti.talon}"
    fecha_cierre = trip.despacho.get("FECHA_CIERRE")
    if fecha_cierre is not None:
        fecha_liq = fecha_cierre + dt.timedelta(minutes=rng.randint(30, 240))
    else:
        fecha_liq = dt.datetime.combine(ti.day, dt.time(20, 0))

    km_total = _dec(trip.km_total)
    trailer = master.trailer_for(ti.eco)
    rows: list[dict] = []

    # 1. Casetas (2 a 4 registros atomicos)
    toll_rate = _dec(cost_cfg["tolls_iave"]["rate_per_km"])
    total_toll = _round_dec(toll_rate * km_total)
    total_toll_cents = int(round(_to_float(total_toll) * 100))

    # Numero de plazas de caseta (2 a 4)
    plazas_per_100km = cost_cfg["tolls_iave"].get("plazas_per_100km", 1.4)
    expected_plazas = max(2, min(4, int(round(_to_float(km_total) / 100.0 * plazas_per_100km))))
    n_plazas = max(2, min(4, rng.randint(expected_plazas - 1, expected_plazas + 1)))

    if total_toll_cents > 0:
        weights = {i: rng.uniform(0.7, 1.3) for i in range(n_plazas)}
        toll_parts = allocate(total_toll_cents, weights)
        for i in range(n_plazas):
            cents = toll_parts[i]
            if cents > 0:
                rows.append({
                    "FOLIO_LIQUIDACION": folio_liq,
                    "FECHA_LIQUIDACION": fecha_liq,
                    "NUMERO_TALON": ti.talon,
                    "CODIGO_ECO": ti.eco,
                    "CODIGO_REMOLQUE": trailer,
                    "CODIGO_OPERADOR": ti.operator_code,
                    "TIPO_GASTO": "CASETA",
                    "SUBTIPO_GASTO": "PEAJE_IAVE",
                    "IMPORTE_GASTO": round(cents / 100.0, 2),
                    "REFERENCIA_COMPROBANTE": f"IAVE-{ti.talon}-{i + 1:02d}",
                    "ESTATUS_LIQUIDACION": ESTATUS_LIQ_APROBADA,
                    "_ING_DAY": ing_day,
                })

    # 2. Pago al operador (1 linea)
    op_base = _dec(cost_cfg["operator_pay"]["per_trip"])
    op_km_rate = _dec(cost_cfg["operator_pay"]["per_km"])
    op_total = _round_dec(op_base + (op_km_rate * km_total))
    if op_total > _ZERO:
        rows.append({
            "FOLIO_LIQUIDACION": folio_liq,
            "FECHA_LIQUIDACION": fecha_liq,
            "NUMERO_TALON": ti.talon,
            "CODIGO_ECO": ti.eco,
            "CODIGO_REMOLQUE": trailer,
            "CODIGO_OPERADOR": ti.operator_code,
            "TIPO_GASTO": "OPERADOR",
            "SUBTIPO_GASTO": "SUELDO_FLETE_KM",
            "IMPORTE_GASTO": _to_float(op_total),
            "REFERENCIA_COMPROBANTE": f"NOM-{ti.operator_code}-{ti.talon}",
            "ESTATUS_LIQUIDACION": ESTATUS_LIQ_APROBADA,
            "_ING_DAY": ing_day,
        })

    # 3. Mantenimiento menor en ruta (opcional, segun probabilidad)
    maint_prob = cost_cfg["maintenance"].get("probability_per_trip", 0.02)
    if rng.random() < maint_prob:
        m_lo, m_hi = cost_cfg["maintenance"]["amount_range"]
        m_amount = _round_dec(_dec(rng.uniform(m_lo, m_hi)))
        subtipos_maint = ["REVISION_FRENOS", "CALIBRACION_LLANTAS", "AJUSTE_SUSPENSION", "TALLER_ELECTRICO"]
        rows.append({
            "FOLIO_LIQUIDACION": folio_liq,
            "FECHA_LIQUIDACION": fecha_liq,
            "NUMERO_TALON": ti.talon,
            "CODIGO_ECO": ti.eco,
            "CODIGO_REMOLQUE": trailer,
            "CODIGO_OPERADOR": ti.operator_code,
            "TIPO_GASTO": "MANTENIMIENTO",
            "SUBTIPO_GASTO": rng.choice(subtipos_maint),
            "IMPORTE_GASTO": _to_float(m_amount),
            "REFERENCIA_COMPROBANTE": f"FAC-TALLER-{rng.randint(10000, 99999)}",
            "ESTATUS_LIQUIDACION": ESTATUS_LIQ_APROBADA,
            "_ING_DAY": ing_day,
        })

    # 4. Otros gastos menores (opcional, 4% prob: maniobras extraordinarias, bascula, estacionamiento seguro)
    if rng.random() < 0.04:
        otros_amount = _round_dec(_dec(rng.uniform(180.0, 550.0)))
        subtipos_otros = ["BASCULA_PESAJE", "ESTACIONAMIENTO_SEGURO", "SANITIZACION_CAJA"]
        rows.append({
            "FOLIO_LIQUIDACION": folio_liq,
            "FECHA_LIQUIDACION": fecha_liq,
            "NUMERO_TALON": ti.talon,
            "CODIGO_ECO": ti.eco,
            "CODIGO_REMOLQUE": trailer,
            "CODIGO_OPERADOR": ti.operator_code,
            "TIPO_GASTO": "OTROS",
            "SUBTIPO_GASTO": rng.choice(subtipos_otros),
            "IMPORTE_GASTO": _to_float(otros_amount),
            "REFERENCIA_COMPROBANTE": f"REC-DIV-{rng.randint(1000, 9999)}",
            "ESTATUS_LIQUIDACION": ESTATUS_LIQ_APROBADA,
            "_ING_DAY": ing_day,
        })

    return rows
