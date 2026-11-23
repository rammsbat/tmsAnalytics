"""Maestros de flota y catalogos auxiliares (ST-2). 100% deterministas (D6).

Todo valor sale de un RNG sembrado por (seed, stream); no hay datetime.now() ni uuid4().
`units` alimenta STG_FLOTA_UNIDADES; el resto de catalogos vive en memoria y lo consumen
los generadores operativos (TrackIt, Carta Porte, ERP) en ST-3/ST-4.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from faker import Faker

from ..config import status_counts
from ..rng import derive_seed, make_rng

SOURCE_SYSTEM_FLOTA = "FLOTA"
CONFIG_SAT_TRACTOR = "C3R2"        # tractor con remolque (spec 4.2)
TIPO_PERMISO_SCT = "TPAF01"        # autotransporte federal de carga general
TIPO_UNIDAD = "TRACTOCAMION"

# (marca, modelo): unidades electricas (el KPI de rendimiento es km/kWh).
_MODELS = [
    ("Freightliner", "eCascadia"),
    ("Volvo", "VNR Electric"),
    ("Kenworth", "T680E"),
    ("Peterbilt", "579EV"),
]
_INSURERS = ["Qualitas", "Chubb Seguros", "AXA Seguros", "GNP Seguros", "HDI Seguros", "Mapfre"]

# Clientes sinteticos: razon social tipo Draft; RFC generados (no reales) por RNG.
_CLIENT_NAMES = [
    "PROCTER & GAMBLE MANUFACTURING MEXICO",
    "DISTRIBUIDORA NORTE DEL BAJIO",
    "ABARROTES Y CONSUMO NACIONAL",
    "LOGISTICA RETAIL OCCIDENTE",
    "COMERCIALIZADORA DEL PACIFICO",
    "ALIMENTOS PROCESADOS DEL CENTRO",
]

# Ubicaciones (codigo, nombre, CP, estado, municipio, lat, lon, tipo). IMESA/SMO/MERCURIO: Draft.
_LOCATIONS = [
    ("IMESA", "IMESA Planta Apaseo", "38160", "Guanajuato", "Apaseo el Grande", 20.5489, -100.6881, "PLANTA_CEDIS"),
    ("SMO", "SMO Centro de Distribucion", "54713", "Mexico", "Cuautitlan Izcalli", 19.6485, -99.2171, "PLANTA_CEDIS"),
    ("MERCURIO", "Mercurio CEDIS Guadalajara", "45010", "Jalisco", "Zapopan", 20.7214, -103.3910, "PLANTA_CEDIS"),
    ("CEDIS_QRO", "CEDIS Queretaro", "76246", "Queretaro", "El Marques", 20.5881, -100.2800, "PLANTA_CEDIS"),
    ("CEDIS_MTY", "CEDIS Monterrey", "66600", "Nuevo Leon", "Apodaca", 25.7817, -100.1883, "PLANTA_CEDIS"),
    ("CEDIS_PUE", "CEDIS Puebla", "72710", "Puebla", "Cuautlancingo", 19.1010, -98.2600, "PLANTA_CEDIS"),
    ("CEDIS_LEO", "CEDIS Leon", "37545", "Guanajuato", "Leon", 21.1250, -101.6860, "PLANTA_CEDIS"),
    ("CEDIS_VER", "CEDIS Veracruz", "91697", "Veracruz", "Veracruz", 19.1738, -96.1342, "PLANTA_CEDIS"),
]

_PLATE_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"
_VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # sin I, O, Q (norma VIN)
_RFC_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_RFC_HOMO = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


@dataclass(frozen=True)
class FleetMaster:
    end_date: dt.date
    company: dict
    units: list[dict]            # -> STG_FLOTA_UNIDADES (sin columnas de auditoria)
    trailers: list[dict]
    operators: list[dict]
    clients: list[dict]
    locations: list[dict]
    policies: list[dict]
    daily_status_plan: dict[str, int] = field(default_factory=dict)  # cuenta objetivo 56/40/4


def _rfc(rng, letters: int, base_year: int) -> str:
    """RFC sintetico: N letras + AAMMDD + homoclave de 3 (personas moral=3, fisica=4)."""
    year = rng.randint(base_year, base_year + 30) % 100
    month, day = rng.randint(1, 12), rng.randint(1, 28)
    return ("".join(rng.choice(_RFC_LETTERS) for _ in range(letters))
            + f"{year:02d}{month:02d}{day:02d}"
            + "".join(rng.choice(_RFC_HOMO) for _ in range(3)))


def _unique(rng, used: set[str], make) -> str:
    while True:
        value = make()
        if value not in used:
            used.add(value)
            return value


def _plate(rng) -> str:
    # Placa federal de carga: 2 digitos + 2 letras + 2 digitos (p. ej. 45AX12)
    return (f"{rng.randint(10, 99)}" + rng.choice(_PLATE_LETTERS) + rng.choice(_PLATE_LETTERS)
            + f"{rng.randint(10, 99)}")


def generate_fleet_master(cfg: dict) -> FleetMaster:
    seed, end_date = cfg["seed"], cfg["end_date"]
    fcfg, constraints = cfg["fleet"], cfg["constraints"]
    n_units = cfg["fleet_size"]

    used_plates: set[str] = set()
    used_vins: set[str] = set()
    used_motors: set[str] = set()

    # --- Aseguradoras / polizas -------------------------------------------------
    rng_pol = make_rng(seed, "fleet.policies")
    lo, hi = fcfg["policy_valid_days_range"]
    policies = []
    for i in range(fcfg["insurance_policies"]):
        insurer = _INSURERS[i % len(_INSURERS)]
        policies.append({
            "NUMERO_POLIZA": f"POL-{rng_pol.randint(10_000_000, 99_999_999)}-{i + 1:02d}",
            "ASEGURADORA": insurer,
            "VIGENCIA_HASTA": end_date + dt.timedelta(days=rng_pol.randint(lo, hi)),
        })

    # --- Remolques (CAJA01..) ---------------------------------------------------
    rng_rem = make_rng(seed, "fleet.trailers")
    trailers = [{
        "NUMERO_ECONOMICO_REMOLQUE": f"CAJA{i:02d}",
        "PLACA_REMOLQUE": _unique(rng_rem, used_plates, lambda: _plate(rng_rem)),
    } for i in range(1, fcfg["trailers"] + 1)]

    # --- Tractores (STG_FLOTA_UNIDADES) ----------------------------------------
    rng_u = make_rng(seed, "fleet.units")
    y_lo, y_hi = fcfg["model_year_range"]
    per_policy = -(-n_units // len(policies))  # ceil: unidades por poliza
    units = []
    for i in range(1, n_units + 1):
        brand, model = rng_u.choice(_MODELS)
        pol = policies[(i - 1) // per_policy]
        plate = _unique(rng_u, used_plates, lambda: _plate(rng_u))
        vin = _unique(rng_u, used_vins, lambda: "".join(rng_u.choice(_VIN_CHARS) for _ in range(17)))
        motor = _unique(rng_u, used_motors, lambda: "MTR-" + "".join(
            rng_u.choice("0123456789ABCDEF") for _ in range(10)))
        units.append({
            "CODIGO_ECO": f"ECO{i:02d}",
            "TIPO_UNIDAD": TIPO_UNIDAD,
            "PLACA": plate,
            "ANIO_MODELO": rng_u.randint(y_lo, y_hi),
            "MARCA": brand,
            "MODELO": model,
            "CONFIGURACION_SAT": CONFIG_SAT_TRACTOR,
            "TIPO_PERMISO_SCT": TIPO_PERMISO_SCT,
            "NUMERO_PERMISO_SCT": f"{TIPO_PERMISO_SCT}-{rng_u.randint(2019, 2025)}-{rng_u.randint(100000, 999999)}",
            "PESO_BRUTO_MAX_KG": constraints["max_gross_weight_kg"],
            "CAPACIDAD_CARGA_KG": fcfg["payload_capacity_kg"],
            "NUMERO_SERIE_VIN": vin,
            "NUMERO_MOTOR": motor,
            "NUMERO_POLIZA_SEGURO": pol["NUMERO_POLIZA"],
            "ASEGURADORA": pol["ASEGURADORA"],
            "VIGENCIA_POLIZA": pol["VIGENCIA_HASTA"],
            "ESTATUS_INVENTARIO": fcfg["inventory_status"],
        })

    # --- Operadores (Faker sembrado de forma independiente) ---------------------
    rng_op = make_rng(seed, "fleet.operators")
    fake = Faker("es_MX")
    fake.seed_instance(derive_seed(seed, "fleet.operators.faker"))
    used_names: set[str] = set()
    operators = []
    for i in range(1, fcfg["operators"] + 1):
        name = _unique(rng_op, used_names, lambda: fake.name().upper()[:120])
        operators.append({
            "CODIGO_OPERADOR": f"OP{i:03d}",
            "NOMBRE_OPERADOR": name,
            "RFC_OPERADOR": _rfc(rng_op, 4, 1965),
            "NUMERO_LICENCIA": f"LF-{rng_op.randint(10_000_000, 99_999_999)}",
        })

    # --- Clientes, ubicaciones y emisor -----------------------------------------
    rng_cli = make_rng(seed, "fleet.clients")
    clients = [{"RFC_CLIENTE": _rfc(rng_cli, 3, 1960), "RAZON_SOCIAL": n,
                "REGIMEN_FISCAL": "601", "USO_CFDI": "G03"} for n in _CLIENT_NAMES]
    company = {"RFC_EMISOR": _rfc(make_rng(seed, "fleet.company"), 3, 2010),
               "RAZON_SOCIAL": "SUNSHINE DELIVERIES"}
    locations = [dict(zip(("CODIGO_UBICACION", "NOMBRE_UBICACION", "CODIGO_POSTAL", "ESTADO",
                            "MUNICIPIO", "LATITUD", "LONGITUD", "TIPO_UBICACION"), loc))
                 for loc in _LOCATIONS]

    return FleetMaster(end_date, company, units, trailers, operators, clients, locations,
                       policies, status_counts(n_units, cfg["fleet_status_mix"]))
