"""Carta Porte (ST-3): STG_CARTA_PORTE_CABECERA + STG_CARTA_PORTE_MERCANCIAS.

Un CFDI de Traslado con Complemento Carta Porte por viaje, emitido al despacho (no se versiona
al cerrar el viaje). `UUID_CCP` sale del RNG sembrado (sin uuid4). Las claves SAT emitidas salen
SOLO de `sat_catalogs` en config_rules.yaml (catalogos cerrados; ST-7 siembra EDW_3FN.SAT_* con
exactamente esas claves).
"""
from __future__ import annotations

import datetime as dt

from ..config import allocate
from ..rng import det_uuid, make_rng

SOURCE_SYSTEM_CCP = "CARTA_PORTE"
SERIE_CCP = "CCP"
USO_CFDI_TRASLADO = "S01"   # sin efectos fiscales (traslado)
MONEDA_TRASLADO = "XXX"


def plan_cargo(cfg: dict, rng) -> tuple[list[dict], float]:
    """Partidas de mercancia de un viaje: (items, peso_total_kg).

    El peso total = payload_capacity_kg * factor de carga <= payload <= max_gross_weight_kg
    (29,685 kg). Se reparte en centesimas de kg para que la suma sea exacta.
    """
    t, f = cfg["trip_model"], cfg["fleet"]
    cap_c = int(round(min(f["payload_capacity_kg"], cfg["constraints"]["max_gross_weight_kg"]) * 100))
    total_c = int(round(cap_c * rng.uniform(*t["load_factor_range"])))
    n = rng.randint(*t["items_per_trip"])
    parts = allocate(total_c, {i: rng.uniform(0.5, 1.5) for i in range(n)})
    products = cfg["sat_catalogs"]["productos"]
    items = [{"producto": rng.choice(products), "peso_c": parts[i]} for i in range(n)]
    return items, round(total_c / 100, 2)


def build_documents(cfg: dict, master, ti, trip, plate: str) -> tuple[dict, list[dict]]:
    """(cabecera, mercancias) de un viaje. `plate` = placa vigente del tractor ese dia (SCD2)."""
    seed = cfg["seed"]
    uuid_ccp = det_uuid(make_rng(seed, f"ccp.{ti.talon}"))
    unit = master.unit(ti.eco)
    op = master.operator(ti.operator_code)
    trailer = master.trailer_for(ti.eco)
    trailer_plate = master.trailer_plate(trailer)
    units = {u["clave"]: u for u in cfg["sat_catalogs"]["unidades"]}
    emitted = dt.datetime.combine(ti.day, dt.time(0, 0)) + dt.timedelta(minutes=ti.start_minute - 20)

    mercancias = []
    for i, it in enumerate(trip.cargo, start=1):
        p = it["producto"]
        kg = round(it["peso_c"] / 100, 2)
        mercancias.append({
            "UUID_CCP": uuid_ccp,
            "NUMERO_TALON": ti.talon,
            "NUMERO_PARTIDA": i,
            "CLAVE_PRODUCTO_SAT": p["clave"],
            "DESCRIPCION_PRODUCTO_SAT": p["descripcion"],
            "CANTIDAD": max(1.0, round(kg / p["peso_unitario_kg"], 2)),
            "CLAVE_UNIDAD_SAT": p["unidad_defecto"],
            "UNIDAD_SAT": units[p["unidad_defecto"]]["nombre"],
            "PESO_KG": kg,
            "MATERIAL_PELIGROSO_FLAG": p["material_peligroso"],
            "CLAVE_MATERIAL_PELIGROSO": None,
            "EMBALAJE_SAT": p["embalaje"],
            "UNIDAD_EMBARQUE_UE": trip.ue,
            "_ING_DAY": ti.day,
        })
    cabecera = {
        "UUID_CCP": uuid_ccp,
        "FOLIO_DOCUMENTO": f"CCP-{ti.talon}",
        "SERIE": SERIE_CCP,
        "FECHA_EMISION": emitted,
        "NUMERO_TALON": ti.talon,
        "RFC_REMITENTE": trip.client_origin["RFC_CLIENTE"],
        "NOMBRE_REMITENTE": trip.client_origin["RAZON_SOCIAL"],
        "RFC_DESTINATARIO": trip.client_destination["RFC_CLIENTE"],
        "NOMBRE_DESTINATARIO": trip.client_destination["RAZON_SOCIAL"],
        "CODIGO_ECO": ti.eco,
        "PLACA_VEHICULO": plate,
        "CONFIGURACION_SAT": unit["CONFIGURACION_SAT"],
        "NUMERO_REMOLQUE": trailer,
        "PLACA_REMOLQUE": trailer_plate,
        "RFC_OPERADOR": op["RFC_OPERADOR"],
        "NOMBRE_OPERADOR": op["NOMBRE_OPERADOR"],
        "LICENCIA_OPERADOR": op["NUMERO_LICENCIA"],
        "UBICACION_ORIGEN_CP": trip.origin,
        "UBICACION_DESTINO_CP": trip.destination,
        "DISTANCIA_DECLARADA_KM": trip.distance_km,
        "PESO_BRUTO_TOTAL_KG": trip.cargo_total_kg,
        "NUMERO_TOTAL_MERCANCIAS": len(mercancias),
        "USO_CFDI": USO_CFDI_TRASLADO,
        "MONEDA": MONEDA_TRASLADO,
        "POLIZA_RESP_CIVIL": unit["NUMERO_POLIZA_SEGURO"],
        "ASEGURADORA_RESP_CIVIL": unit["ASEGURADORA"],
        "_ING_DAY": ti.day,
    }
    return cabecera, mercancias
