#!/usr/bin/env python3
"""
ST-5 - Conciliacion automatizada de KPIs de los 8 Virtual Datasets de Superset contra Oracle DW.

Renderiza (Jinja, mismo `where_in` de Superset) y ejecuta los 8 datasets reales de
superset/assets/datasets/ con el usuario BI_READER en Thin Mode (python-oracledb) y concilia cada
cifra contra consultas INDEPENDIENTES escritas sobre las tablas base de DWH_MART (claves de fecha
enteras YYYYMMDD, sin pasar por las vistas VW_* ni por el SQL de los datasets) y contra las MVs
BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA / MV_PRODUCTIVIDAD_ECO_MENSUAL.

Ventanas conciliadas (plan Fase 4, ST-5):
  1. Corte diario            2026-11-06
  2. Mes cerrado             2026-11-01 .. 2026-11-06
  3. Acumulado historico     90 dias cerrados (..2026-11-06), 91 dias (..2026-11-07) y carga completa
  4. Aislamiento dia 91      2026-11-07  (+ ECO15 SCD2)
  + DISTANCIA_DECLARADA_KM colapsada a nivel UUID_CCP (ds_06 / ds_07 / ds_08)

Seguridad (Regla 03): credenciales solo desde el entorno (BI_READER_PWD); todas las consultas
independientes usan bind variables; los datasets se renderizan igual que en Superset.

Ejecucion (contenedor tms-superset-app, que ya tiene BI_READER_PWD, oracledb y jinja2):
    docker exec tms-superset-app mkdir -p /tmp/tests
    docker cp tests/test_superset_kpi_reconciliation.py tms-superset-app:/tmp/tests/
    docker exec tms-superset-app python /tmp/tests/test_superset_kpi_reconciliation.py [-v]
Tambien es compatible con pytest (funciones test_*), si esta disponible.
"""
import functools
import glob
import os
import sys
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import oracledb
from jinja2 import Environment

oracledb.defaults.fetch_decimals = True  # NUMBER -> Decimal (conciliacion exacta al centavo)
D = Decimal

# --------------------------------------------------------------------------------------------
# Anclas numericas (valores esperados). Se contrastan ademas contra consultas independientes.
# --------------------------------------------------------------------------------------------
W_DIA = ("2026-11-06", "2026-11-06")      # corte diario
W_MES = ("2026-11-01", "2026-11-06")      # mes cerrado
W_90D = ("2026-08-09", "2026-11-06")      # 90 dias cerrados
W_91D = ("2026-08-09", "2026-11-07")      # 91 dias (incluye dia 91 parcial)
W_ALL = ("2026-08-09", "2026-12-31")      # carga completa (incluye facturas rezagadas al 11-09)
W_DIA91 = ("2026-11-07", "2026-11-07")    # dia 91 incremental
W_NOV = ("2026-11-01", "2026-11-30")      # mes calendario noviembre (semantica de la MV mensual)

A = {
    "dia06": dict(unidades=100, con_viaje=56, sin_viaje=40, inactivas=4, despachos=56, cerrados=56,
                  kms=D("20993.45"), kwh=D("4243.31"), facturado=D("4436321.95"), facturas=68),
    "mes": dict(despachos=336, cerrados=336, kms=D("123731.53"), kwh=D("23023.99"),
                facturado=D("21017482.18"), facturas=339, unidades_ds05=98, unidades_ds06=99),
    "h90": dict(despachos=5040, cerrados=5040, kms=D("1825987.38"), kwh=D("327786.44"),
                facturado=D("305177133.26"), gastos=D("17908049.79")),
    "full": dict(despachos=5045, cerrados=5043, facturas=5043, kms=D("1827114.49"), kwh=D("327999.20"),
                 facturado=D("310348743.81"), gastos=D("17918678.54"), mv_filas=399, unidades=100),
    "dia91": dict(despachos=5, cerrados=3, abiertos=2, kms=D("1127.11"), unidades=100,
                  con_viaje=5, sin_viaje=91, inactivas=4),
    # Linea base de Fase 3 (previa a la corrida incremental): 5,029 primeras facturas.
    "fase3": dict(facturas_base=5029, facturado_base=D("309227803.56"), facturas_incr=14,
                  facturado_incr=D("1120940.25")),
}

# --------------------------------------------------------------------------------------------
# Infraestructura: conexion Thin Mode, render Jinja de datasets, registro de checks
# --------------------------------------------------------------------------------------------
_CONN = None
_CUR = []          # checks del test en curso: (label, actual, esperado, ok)
RESULTS = {}       # nombre_test -> lista de checks
_RENDER_CACHE = {}
_IND_CACHE = {}


def conn():
    global _CONN
    if _CONN is None:
        pwd = os.environ.get("BI_READER_PWD")
        if not pwd:
            raise RuntimeError("BI_READER_PWD no esta definida en el entorno (Regla 03)")
        _CONN = oracledb.connect(
            user=os.environ.get("BI_READER_USER", "BI_READER"),
            password=pwd,
            dsn=os.environ.get("ORACLE_DSN", "oracle-dw:1521/FREEPDB1"),
        )
    return _CONN


def query(sql, **binds):
    cur = conn().cursor()
    try:
        cur.execute(sql, binds)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()


def datasets_dir():
    for cand in (os.environ.get("DATASETS_DIR"), "/app/assets/datasets",
                 str(Path(__file__).resolve().parent.parent / "superset" / "assets" / "datasets")):
        if cand and os.path.isdir(cand):
            return cand
    raise RuntimeError("No se encontro superset/assets/datasets")


def _where_in(values):
    """Misma salida que la macro `where_in` de Superset."""
    esc = [("'" + str(v).replace("'", "''") + "'") if isinstance(v, str) else str(v) for v in values]
    return "(" + ", ".join(esc) + ")"


_ENV = Environment()
_ENV.filters["where_in"] = _where_in


def dataset_path(n):
    files = glob.glob(os.path.join(datasets_dir(), "ds_%02d_*.sql" % n))
    assert len(files) == 1, "dataset ds_%02d no encontrado" % n
    return files[0]


def render(n, window, filters=None):
    """Renderiza ds_0N con from_dttm/to_dttm (formato Superset) y devuelve sus filas (dict)."""
    key = (n, window, tuple(sorted((k, tuple(v)) for k, v in (filters or {}).items())))
    if key not in _RENDER_CACHE:
        raw = Path(dataset_path(n)).read_text(encoding="utf-8")
        fv = filters or {}
        sql = _ENV.from_string(raw).render(
            from_dttm=window[0] + " 00:00:00",
            to_dttm=window[1] + " 00:00:00",
            filter_values=lambda col: fv.get(col, []),
        )
        assert "{%" not in sql and "{{" not in sql, "Jinja sin resolver en ds_%02d" % n
        _RENDER_CACHE[key] = query(sql)
    return _RENDER_CACHE[key]


def dk(iso):
    """'2026-11-06' -> 20261106 (clave entera de DIM_FECHA)."""
    return int(iso.replace("-", ""))


def dec(x):
    if x is None:
        return None
    return x if isinstance(x, Decimal) else D(str(x))


def rnd(x, n):
    return None if x is None else x.quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP)


def check(label, actual, expected):
    a, e = dec(actual), dec(expected)
    _CUR.append((label, a, e, a == e))


def check_true(label, cond, detail=""):
    _CUR.append((label, detail or cond, True, bool(cond)))


def reconcile(fn):
    @functools.wraps(fn)
    def wrapper():
        _CUR.clear()
        fn()
        RESULTS[fn.__name__] = list(_CUR)
        bad = [r for r in _CUR if not r[3]]
        assert not bad, "\n".join("  [FAIL] %s | actual=%s esperado=%s" % (r[0], r[1], r[2]) for r in bad)
    return wrapper


def s(rows, col):
    return sum((dec(r[col]) or D(0)) for r in rows)


# --------------------------------------------------------------------------------------------
# Consultas INDEPENDIENTES sobre DWH_MART (bind variables; claves de fecha enteras)
# --------------------------------------------------------------------------------------------
def snapshot_dia(d):
    return query(
        "SELECT COUNT(*) AS N, SUM(UNIDAD_CON_VIAJE_INDICADOR) AS CV, SUM(UNIDAD_SIN_VIAJE_INDICADOR) AS SV, "
        "SUM(UNIDAD_INACTIVA_INDICADOR) AS INA, SUM(KMS_RECORRIDOS_DIA) AS KMS, SUM(KWH_CONSUMO_DIA) AS KWH "
        "FROM DWH_MART.FACT_SNAPSHOT_FLOTA_DIARIO WHERE ID_FECHA_CORTE = :d", d=dk(d))[0]


def ind_ops(corte, mes_ini):
    """KPIs de ds_02 / ds_03 (dia = corte, mes = mes_ini..corte) desde tablas base."""
    c, m = dk(corte), dk(mes_ini)
    r = {}
    r.update(query(
        "SELECT SUM(CASE WHEN ID_FECHA_INICIO = :c THEN CONTADOR_DESPACHO ELSE 0 END) AS DESP_DIA, "
        "SUM(CONTADOR_DESPACHO) AS DESP_MES, "
        "SUM(CASE WHEN ID_FECHA_INICIO = :c THEN CONTADOR_CERRADO ELSE 0 END) AS CIER_DIA, "
        "SUM(CONTADOR_CERRADO) AS CIER_MES, "
        "SUM(CASE WHEN ID_FECHA_INICIO = :c THEN KMS_TOTAL ELSE 0 END) AS KMS_DIA, SUM(KMS_TOTAL) AS KMS_MES, "
        "SUM(CASE WHEN ID_FECHA_INICIO = :c THEN KWH_CONSUMO_ENERGIA ELSE 0 END) AS KWH_DIA, "
        "SUM(KWH_CONSUMO_ENERGIA) AS KWH_MES "
        "FROM DWH_MART.FACT_DESPACHO_VIAJE WHERE ID_FECHA_INICIO BETWEEN :m AND :c", c=c, m=m)[0])
    r.update(query(
        "SELECT SUM(CASE WHEN ID_FECHA_FACTURACION = :c THEN CONTADOR_FACTURA ELSE 0 END) AS FAC_N_DIA, "
        "SUM(CONTADOR_FACTURA) AS FAC_N_MES, "
        "SUM(CASE WHEN ID_FECHA_FACTURACION = :c THEN IMPORTE_TOTAL_FACTURADO ELSE 0 END) AS FAC_IMP_DIA, "
        "SUM(IMPORTE_TOTAL_FACTURADO) AS FAC_IMP_MES "
        "FROM DWH_MART.FACT_FACTURACION_FLETE WHERE ID_FECHA_FACTURACION BETWEEN :m AND :c", c=c, m=m)[0])
    r.update(query(
        "SELECT SUM(CASE WHEN ID_FECHA_LIQUIDACION = :c AND MONTO_CASETA > 0 THEN CONTADOR_LIQUIDACION ELSE 0 END) AS LCAS_DIA, "
        "SUM(CASE WHEN MONTO_CASETA > 0 THEN CONTADOR_LIQUIDACION ELSE 0 END) AS LCAS_MES, "
        "SUM(CASE WHEN ID_FECHA_LIQUIDACION = :c AND MONTO_OPERADOR > 0 THEN CONTADOR_LIQUIDACION ELSE 0 END) AS LOPE_DIA, "
        "SUM(CASE WHEN MONTO_OPERADOR > 0 THEN CONTADOR_LIQUIDACION ELSE 0 END) AS LOPE_MES, "
        "SUM(CASE WHEN ID_FECHA_LIQUIDACION = :c THEN MONTO_CASETA ELSE 0 END) AS PCAS_DIA, SUM(MONTO_CASETA) AS PCAS_MES, "
        "SUM(CASE WHEN ID_FECHA_LIQUIDACION = :c THEN MONTO_OPERADOR ELSE 0 END) AS POPE_DIA, SUM(MONTO_OPERADOR) AS POPE_MES "
        "FROM DWH_MART.FACT_GASTOS_LIQUIDACION WHERE ID_FECHA_LIQUIDACION BETWEEN :m AND :c", c=c, m=m)[0])
    r.update(query(
        "SELECT COUNT(DISTINCT CASE WHEN ID_FECHA_EMISION = :c THEN UUID_CCP END) AS CCP_DIA, "
        "COUNT(DISTINCT UUID_CCP) AS CCP_MES "
        "FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE WHERE ID_FECHA_EMISION BETWEEN :m AND :c", c=c, m=m)[0])
    return r


def independent(w):
    """Agregados por (ECO, operador) de las 4 tablas de hechos en la ventana w (sin Fact-to-Fact)."""
    if w in _IND_CACHE:
        return _IND_CACHE[w]
    b = dict(d1=dk(w[0]), d2=dk(w[1]))
    out = {}
    out["despacho"] = query(
        "SELECT v.CODIGO_ECO AS ECO, o.CODIGO_OPERADOR || ' - ' || o.NOMBRE_OPERADOR AS OP, COUNT(*) AS DESPACHOS, "
        "SUM(d.CONTADOR_CERRADO) AS CERRADOS, SUM(d.KMS_CARGADO) AS KMS_C, SUM(d.KMS_VACIO) AS KMS_V, "
        "SUM(d.KMS_TOTAL) AS KMS_T, SUM(d.KWH_CONSUMO_ENERGIA) AS KWH "
        "FROM DWH_MART.FACT_DESPACHO_VIAJE d "
        "JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = d.ID_VEHICULO "
        "JOIN DWH_MART.DIM_OPERADOR o ON o.ID_OPERADOR = d.ID_OPERADOR "
        "WHERE d.ID_FECHA_INICIO BETWEEN :d1 AND :d2 "
        "GROUP BY v.CODIGO_ECO, o.CODIGO_OPERADOR, o.NOMBRE_OPERADOR", **b)
    out["fact"] = query(
        "SELECT v.CODIGO_ECO AS ECO, o.CODIGO_OPERADOR || ' - ' || o.NOMBRE_OPERADOR AS OP, "
        "SUM(f.IMPORTE_TOTAL_FACTURADO) AS FAC, SUM(f.CONTADOR_FACTURA) AS FACTURAS "
        "FROM DWH_MART.FACT_FACTURACION_FLETE f "
        "JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = f.ID_VEHICULO "
        "JOIN DWH_MART.DIM_OPERADOR o ON o.ID_OPERADOR = f.ID_OPERADOR "
        "WHERE f.ID_FECHA_FACTURACION BETWEEN :d1 AND :d2 "
        "GROUP BY v.CODIGO_ECO, o.CODIGO_OPERADOR, o.NOMBRE_OPERADOR", **b)
    out["gasto"] = query(
        "SELECT v.CODIGO_ECO AS ECO, o.CODIGO_OPERADOR || ' - ' || o.NOMBRE_OPERADOR AS OP, "
        "SUM(g.MONTO_OPERADOR) AS C_OPER, SUM(g.MONTO_MANTENIMIENTO) AS C_MANT, "
        "SUM(g.MONTO_CASETA + g.MONTO_OTROS_GASTOS) AS C_OTROS, SUM(g.IMPORTE_GASTO) AS C_TOTAL "
        "FROM DWH_MART.FACT_GASTOS_LIQUIDACION g "
        "JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = g.ID_VEHICULO "
        "JOIN DWH_MART.DIM_OPERADOR o ON o.ID_OPERADOR = g.ID_OPERADOR "
        "WHERE g.ID_FECHA_LIQUIDACION BETWEEN :d1 AND :d2 "
        "GROUP BY v.CODIGO_ECO, o.CODIGO_OPERADOR, o.NOMBRE_OPERADOR", **b)
    # Distancia declarada: pares DISTINCT (UUID_CCP, distancia) => una vez por CCP (no por mercancia)
    out["ccp_dist"] = query(
        "SELECT v.CODIGO_ECO AS ECO, o.CODIGO_OPERADOR || ' - ' || o.NOMBRE_OPERADOR AS OP, "
        "SUM(u.DISTANCIA_DECLARADA_KM) AS DIST, COUNT(*) AS UUIDS "
        "FROM (SELECT DISTINCT UUID_CCP, ID_VEHICULO, ID_OPERADOR, DISTANCIA_DECLARADA_KM "
        "      FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE WHERE ID_FECHA_EMISION BETWEEN :d1 AND :d2) u "
        "JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = u.ID_VEHICULO "
        "JOIN DWH_MART.DIM_OPERADOR o ON o.ID_OPERADOR = u.ID_OPERADOR "
        "GROUP BY v.CODIGO_ECO, o.CODIGO_OPERADOR, o.NOMBRE_OPERADOR", **b)
    out["ccp_lineas"] = query(
        "SELECT v.CODIGO_ECO AS ECO, o.CODIGO_OPERADOR || ' - ' || o.NOMBRE_OPERADOR AS OP, COUNT(*) AS LINEAS, "
        "SUM(l.PESO_KG) AS PESO, SUM(l.DISTANCIA_DECLARADA_KM) AS DIST_NAIVE "
        "FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE l "
        "JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = l.ID_VEHICULO "
        "JOIN DWH_MART.DIM_OPERADOR o ON o.ID_OPERADOR = l.ID_OPERADOR "
        "WHERE l.ID_FECHA_EMISION BETWEEN :d1 AND :d2 "
        "GROUP BY v.CODIGO_ECO, o.CODIGO_OPERADOR, o.NOMBRE_OPERADOR", **b)
    _IND_CACHE[w] = out
    return out


_FIELDS = [("despacho", "DESPACHOS", "despachos"), ("despacho", "CERRADOS", "cerrados"),
           ("despacho", "KMS_C", "kms_c"), ("despacho", "KMS_V", "kms_v"), ("despacho", "KMS_T", "kms_t"),
           ("despacho", "KWH", "kwh"), ("fact", "FAC", "fac"), ("fact", "FACTURAS", "facturas"),
           ("gasto", "C_OPER", "c_oper"), ("gasto", "C_MANT", "c_mant"), ("gasto", "C_OTROS", "c_otros"),
           ("gasto", "C_TOTAL", "c_total"), ("ccp_dist", "DIST", "dist"), ("ccp_dist", "UUIDS", "uuids"),
           ("ccp_lineas", "PESO", "peso"), ("ccp_lineas", "LINEAS", "lineas"),
           ("ccp_lineas", "DIST_NAIVE", "dist_naive")]


def rollup(w, by):
    """by = 'eco' -> clave CODIGO_ECO ; by = 'op' -> 'CODIGO - NOMBRE'. Devuelve {clave: {metrica: Decimal}}."""
    ind = independent(w)
    acc = defaultdict(lambda: defaultdict(D))
    for src, col, name in _FIELDS:
        for r in ind[src]:
            acc[r["ECO"] if by == "eco" else r["OP"]][name] += dec(r[col])
    return acc


DS_MAP = {  # columna del dataset -> metrica independiente
    "DESPACHOS_VIAJES": "despachos", "CERRADOS": "cerrados", "KMS_CARGADO": "kms_c", "KMS_VACIO": "kms_v",
    "KMS_TOTAL": "kms_t", "TOTAL_FACTURACION": "fac", "OPERADOR": "c_oper", "MANTENIMIENTO": "c_mant",
    "OTROS_GASTOS": "c_otros", "TOTAL_COSTO": "c_total", "DISTANCIA_DECLARADA_KM": "dist",
    "PESO_DECLARADO_KG": "peso",
}


def compare_productividad(tag, rows, w, by, keycol):
    """Concilia fila por fila ds_06 (by='eco') o ds_07 (by='op') contra la rollup independiente."""
    exp = rollup(w, by)
    got = {r[keycol]: r for r in rows}
    check_true("%s: claves unicas (sin duplicados SCD2/operador)" % tag, len(got) == len(rows),
               "%d filas vs %d claves" % (len(rows), len(got)))
    check("%s: #filas == #claves independientes" % tag, len(got), len(exp))
    check_true("%s: mismo conjunto de claves" % tag, set(got) == set(exp),
               "dif=%s" % sorted(set(got) ^ set(exp)))
    bad = 0
    for k in sorted(set(got) & set(exp)):
        r, e = got[k], exp[k]
        for col, m in DS_MAP.items():
            if dec(r[col]) != e[m]:
                bad += 1
                _CUR.append(("%s[%s].%s" % (tag, k, col), dec(r[col]), e[m], False))
        cpk = rnd(e["fac"] / e["kms_t"], 4) if e["kms_t"] else None
        rnk = rnd(e["kms_t"] / e["kwh"], 4) if e["kwh"] else None
        for col, val in (("COSTO_POR_KM", cpk), ("RENDIMIENTO_PROM_KMS_KWH", rnk),
                         ("MARGEN_OPERATIVO", e["fac"] - e["c_total"])):
            if dec(r[col]) != val:
                bad += 1
                _CUR.append(("%s[%s].%s" % (tag, k, col), dec(r[col]), val, False))
    check("%s: celdas conciliadas con diferencia (14 columnas x claves)" % tag, bad, 0)
    return got, exp


# --------------------------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------------------------
@reconcile
def test_00_conexion_thin_mode_bi_reader():
    check_true("conexion en Thin Mode (python-oracledb)", conn().thin, "thin=%s" % conn().thin)
    check_true("usuario de sesion = BI_READER", query("SELECT USER AS U FROM DUAL")[0]["U"] == "BI_READER")
    check("8 Virtual Datasets en superset/assets/datasets", len(glob.glob(os.path.join(datasets_dir(), "ds_0?_*.sql"))), 8)
    for n in range(1, 9):
        rows = render(n, W_MES)
        check_true("ds_%02d renderiza y ejecuta (filas>0)" % n, len(rows) > 0, "%d filas" % len(rows))


@reconcile
def test_01_corte_diario_20261106():
    a = A["dia06"]
    # --- ds_01 (Bloque 1): flota 100 = 56/40/4
    rows = {r["ESTADO_FLOTA"]: r for r in render(1, W_DIA)}
    check("ds_01 unidades totales", s(rows.values(), "CANTIDAD_UNIDADES"), a["unidades"])
    check("ds_01 Con Viaje", rows["Con Viaje"]["CANTIDAD_UNIDADES"], a["con_viaje"])
    check("ds_01 Sin Viaje", rows["Sin Viaje"]["CANTIDAD_UNIDADES"], a["sin_viaje"])
    check("ds_01 Inactivas", rows["Inactivas"]["CANTIDAD_UNIDADES"], a["inactivas"])
    check("ds_01 % Con Viaje", rows["Con Viaje"]["PORCENTAJE_FLOTA"], D("56.00"))
    check("ds_01 % Sin Viaje", rows["Sin Viaje"]["PORCENTAJE_FLOTA"], D("40.00"))
    check("ds_01 % Inactivas", rows["Inactivas"]["PORCENTAJE_FLOTA"], D("4.00"))
    check("ds_01 kms del dia", s(rows.values(), "TOTAL_KMS_DIA"), a["kms"])
    snap = snapshot_dia(W_DIA[0])
    check("snapshot independiente: unidades", snap["N"], a["unidades"])
    check("snapshot independiente: Con Viaje", snap["CV"], a["con_viaje"])
    check("snapshot independiente: Sin Viaje", snap["SV"], a["sin_viaje"])
    check("snapshot independiente: Inactivas", snap["INA"], a["inactivas"])
    mv = query("SELECT * FROM BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA WHERE ID_FECHA_CORTE = :d", d=dk(W_DIA[0]))[0]
    check("MV_METRICAS_FLOTA_DIARIA: total unidades", mv["TOTAL_UNIDADES_FLOTA"], a["unidades"])
    check("MV_METRICAS_FLOTA_DIARIA: PCT_CON_VIAJE", mv["PCT_CON_VIAJE"], D("56.00"))
    check("MV_METRICAS_FLOTA_DIARIA: PCT_SIN_VIAJE", mv["PCT_SIN_VIAJE"], D("40.00"))
    check("MV_METRICAS_FLOTA_DIARIA: PCT_INACTIVAS", mv["PCT_INACTIVAS"], D("4.00"))
    check("MV_METRICAS_FLOTA_DIARIA: kms dia (== ds_01)", mv["TOTAL_KMS_DIA"], s(rows.values(), "TOTAL_KMS_DIA"))

    # --- ds_02 / ds_03 (Bloques 2 y 3): columnas *_DIA
    i = ind_ops(W_DIA[0], "2026-11-01")
    r2, r3 = render(2, W_DIA)[0], render(3, W_DIA)[0]
    check("ds_02 DESPACHOS_DIA (viajes)", r2["DESPACHOS_DIA"], a["despachos"])
    check("ds_02 CIERRES_DIA (viajes cerrados)", r2["CIERRES_DIA"], a["cerrados"])
    check("ds_02 FACTURADOS_DIA == fact. independiente", r2["FACTURADOS_DIA"], i["FAC_N_DIA"])
    check("ds_02 FACTURADOS_DIA (CFDI emitidos el dia)", r2["FACTURADOS_DIA"], a["facturas"])
    check("ds_02 LIQ_CASETAS_DIA", r2["LIQ_CASETAS_DIA"], i["LCAS_DIA"])
    check("ds_02 LIQ_OPERADOR_DIA", r2["LIQ_OPERADOR_DIA"], i["LOPE_DIA"])
    check("ds_02 CFDI_TRASLADO_DIA", r2["CFDI_TRASLADO_DIA"], i["CCP_DIA"])
    check("ds_03 TOTAL_KMS_DIA (kms del corte)", r3["TOTAL_KMS_DIA"], a["kms"])
    check("ds_03 TOTAL_KMS_DIA == snapshot independiente", r3["TOTAL_KMS_DIA"], snap["KMS"])
    check("ds_03 RENDIMIENTO_KMS_KWH_DIA", r3["RENDIMIENTO_KMS_KWH_DIA"], rnd(a["kms"] / a["kwh"], 2))
    check("ds_03 RENDIMIENTO_KMS_KWH_DIA ~4.95", r3["RENDIMIENTO_KMS_KWH_DIA"], D("4.95"))
    check("ds_03 PAGO_CASETAS_DIA", r3["PAGO_CASETAS_DIA"], i["PCAS_DIA"])
    check("ds_03 PAGO_OPERADORES_DIA", r3["PAGO_OPERADORES_DIA"], i["POPE_DIA"])
    check("ds_03 FACTURADO_DIA (facturacion exacta del corte)", r3["FACTURADO_DIA"], a["facturado"])
    check("ds_03 FACTURADO_DIA == fact. independiente", r3["FACTURADO_DIA"], i["FAC_IMP_DIA"])

    # --- ds_04: despachos del dia por cliente
    r4 = render(4, W_DIA)
    check("ds_04 sum DESPACHOS_DIA == ds_02", s(r4, "DESPACHOS_DIA"), a["despachos"])

    # --- ds_05..ds_08 con ventana de 1 dia: cuadran con los mismos KPI del corte
    r6, r7, r5 = render(6, W_DIA), render(7, W_DIA), render(5, W_DIA)
    check("ds_06 despachos del dia", s(r6, "DESPACHOS_VIAJES"), a["despachos"])
    check("ds_06 cerrados del dia", s(r6, "CERRADOS"), a["cerrados"])
    check("ds_06 kms del dia", s(r6, "KMS_TOTAL"), a["kms"])
    check("ds_06 facturacion del dia", s(r6, "TOTAL_FACTURACION"), a["facturado"])
    check("ds_05 facturacion del dia", s(r5, "TOTAL_FACTURACION"), a["facturado"])
    check("ds_07 despachos del dia", s(r7, "DESPACHOS_VIAJES"), a["despachos"])
    check("ds_07 kms del dia", s(r7, "KMS_TOTAL"), a["kms"])
    compare_productividad("ds_06@dia", r6, W_DIA, "eco", "UNIDAD")
    compare_productividad("ds_07@dia", r7, W_DIA, "op", "CLAVE_NOMBRE")


@reconcile
def test_02_mes_cerrado_20261101_20261106():
    a = A["mes"]
    i = ind_ops(W_MES[1], W_MES[0])
    r2, r3 = render(2, W_MES)[0], render(3, W_MES)[0]
    # --- Bloque 2
    check("ds_02 DESPACHOS_MES", r2["DESPACHOS_MES"], a["despachos"])
    check("ds_02 DESPACHOS_MES == independiente", r2["DESPACHOS_MES"], i["DESP_MES"])
    check("ds_02 CIERRES_MES", r2["CIERRES_MES"], i["CIER_MES"])
    check("ds_02 FACTURADOS_MES", r2["FACTURADOS_MES"], a["facturas"])
    check("ds_02 FACTURADOS_MES == independiente", r2["FACTURADOS_MES"], i["FAC_N_MES"])
    check("ds_02 LIQ_CASETAS_MES", r2["LIQ_CASETAS_MES"], i["LCAS_MES"])
    check("ds_02 LIQ_OPERADOR_MES", r2["LIQ_OPERADOR_MES"], i["LOPE_MES"])
    check("ds_02 CFDI_TRASLADO_MES (UUID_CCP distintos)", r2["CFDI_TRASLADO_MES"], i["CCP_MES"])
    # --- Bloque 3: viajes, kms, kWh, rendimiento, facturacion y gastos
    check("ds_03 TOTAL_KMS_MES", r3["TOTAL_KMS_MES"], a["kms"])
    check("ds_03 TOTAL_KMS_MES == independiente", r3["TOTAL_KMS_MES"], i["KMS_MES"])
    check("kWh del mes (independiente)", i["KWH_MES"], a["kwh"])
    check("ds_03 RENDIMIENTO_KMS_KWH_MES", r3["RENDIMIENTO_KMS_KWH_MES"], rnd(i["KMS_MES"] / i["KWH_MES"], 2))
    check("ds_03 FACTURADO_MES", r3["FACTURADO_MES"], a["facturado"])
    check("ds_03 FACTURADO_MES == independiente", r3["FACTURADO_MES"], i["FAC_IMP_MES"])
    check("ds_03 PAGO_CASETAS_MES", r3["PAGO_CASETAS_MES"], i["PCAS_MES"])
    check("ds_03 PAGO_OPERADORES_MES", r3["PAGO_OPERADORES_MES"], i["POPE_MES"])
    gastos = independent(W_MES)["gasto"]
    check("gastos del mes: operador+mant+otros == IMPORTE_GASTO",
          s(gastos, "C_OPER") + s(gastos, "C_MANT") + s(gastos, "C_OTROS"), s(gastos, "C_TOTAL"))
    # --- Bloque 4: clientes
    r4 = render(4, W_MES)
    exp = {r["CLI"]: r for r in query(
        "SELECT c.RAZON_SOCIAL AS CLI, "
        "SUM(CASE WHEN d.ID_FECHA_INICIO = :c THEN d.CONTADOR_DESPACHO ELSE 0 END) AS DIA, "
        "SUM(d.CONTADOR_DESPACHO) AS MES, SUM(d.KMS_TOTAL) AS KMS "
        "FROM DWH_MART.FACT_DESPACHO_VIAJE d JOIN DWH_MART.DIM_CLIENTE c ON c.ID_CLIENTE = d.ID_CLIENTE_ORIGEN "
        "WHERE d.ID_FECHA_INICIO BETWEEN :m AND :c GROUP BY c.RAZON_SOCIAL", c=dk(W_MES[1]), m=dk(W_MES[0]))}
    got = {r["CLIENTE"]: r for r in r4}
    check("ds_04 #clientes == independiente", len(got), len(exp))
    check_true("ds_04 mismo conjunto de clientes", set(got) == set(exp))
    check("ds_04 diferencias DIA/MES/KMS por cliente",
          sum(1 for k in set(got) & set(exp) for c1, c2 in (("DESPACHOS_DIA", "DIA"), ("DESPACHOS_MES", "MES"), ("KMS_MES", "KMS"))
              if dec(got[k][c1]) != dec(exp[k][c2])), 0)
    check("ds_04 sum DESPACHOS_MES", s(r4, "DESPACHOS_MES"), a["despachos"])
    top5_ds = [dec(r["DESPACHOS_MES"]) for r in r4[:5]]
    top5_ind = sorted((dec(v["MES"]) for v in exp.values()), reverse=True)[:5]
    check_true("ds_04 Top 5 (valores) == Top 5 independiente", top5_ds == top5_ind, "%s vs %s" % (top5_ds, top5_ind))
    # --- Bloque 5: ds_05 por ECO
    r5 = render(5, W_MES)
    froll = defaultdict(D)
    for r in independent(W_MES)["fact"]:
        froll[r["ECO"]] += dec(r["FAC"])
    got5 = {r["UNIDAD"]: dec(r["TOTAL_FACTURACION"]) for r in r5}
    check("ds_05 unidades con facturacion", len(r5), a["unidades_ds05"])
    check_true("ds_05 TOTAL_FACTURACION por ECO == independiente", got5 == dict(froll))
    check("ds_05 sum TOTAL_FACTURACION", s(r5, "TOTAL_FACTURACION"), a["facturado"])
    check_true("ds_05 ordenado DESC (Top 10 valido)", [dec(r["TOTAL_FACTURACION"]) for r in r5] ==
               sorted((dec(r["TOTAL_FACTURACION"]) for r in r5), reverse=True))
    # --- Bloques 6 y 7 fila por fila + cuadre exacto entre ambos
    r6, r7 = render(6, W_MES), render(7, W_MES)
    compare_productividad("ds_06@mes", r6, W_MES, "eco", "UNIDAD")
    compare_productividad("ds_07@mes", r7, W_MES, "op", "CLAVE_NOMBRE")
    check("ds_06 filas (unidades con actividad)", len(r6), a["unidades_ds06"])
    for col in ("DESPACHOS_VIAJES", "CERRADOS", "KMS_CARGADO", "KMS_VACIO", "KMS_TOTAL", "TOTAL_FACTURACION",
                "OPERADOR", "MANTENIMIENTO", "OTROS_GASTOS", "TOTAL_COSTO", "MARGEN_OPERATIVO",
                "DISTANCIA_DECLARADA_KM", "PESO_DECLARADO_KG"):
        check("cuadre ds_06 == ds_07 (al centavo): %s" % col, s(r6, col), s(r7, col))
    check("ds_06 sum despachos", s(r6, "DESPACHOS_VIAJES"), a["despachos"])
    check("ds_06 sum kms", s(r6, "KMS_TOTAL"), a["kms"])
    check("ds_06 sum facturacion", s(r6, "TOTAL_FACTURACION"), a["facturado"])
    check("ds_06 sum TOTAL_COSTO == gastos del mes", s(r6, "TOTAL_COSTO"), s(gastos, "C_TOTAL"))
    check("ds_06 KMS_TOTAL == KMS_CARGADO + KMS_VACIO",
          s(r6, "KMS_TOTAL"), s(r6, "KMS_CARGADO") + s(r6, "KMS_VACIO"))
    check("ds_06 TOTAL_COSTO == OPERADOR + MANTENIMIENTO + OTROS_GASTOS",
          s(r6, "TOTAL_COSTO"), s(r6, "OPERADOR") + s(r6, "MANTENIMIENTO") + s(r6, "OTROS_GASTOS"))


@reconcile
def test_03_98_vs_99_unidades_eco97():
    k5 = {r["UNIDAD"] for r in render(5, W_MES)}
    k6 = {r["UNIDAD"] for r in render(6, W_MES)}
    check("ds_05 unidades (solo con facturacion)", len(k5), 98)
    check("ds_06 unidades (con cualquier actividad)", len(k6), 99)
    check_true("ds_06 - ds_05 == {ECO97}", (k6 - k5) == {"ECO97"}, str(sorted(k6 - k5)))
    check_true("ds_05 subconjunto de ds_06", k5 <= k6)
    eco97 = query(
        "SELECT (SELECT COUNT(*) FROM DWH_MART.FACT_DESPACHO_VIAJE d JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = d.ID_VEHICULO "
        "         WHERE v.CODIGO_ECO = 'ECO97' AND d.ID_FECHA_INICIO BETWEEN :d1 AND :d2) AS VIAJES, "
        "       (SELECT COUNT(*) FROM DWH_MART.FACT_FACTURACION_FLETE f JOIN DWH_MART.DIM_VEHICULO v ON v.ID_VEHICULO = f.ID_VEHICULO "
        "         WHERE v.CODIGO_ECO = 'ECO97' AND f.ID_FECHA_FACTURACION BETWEEN :d1 AND :d2) AS FACTURAS "
        "FROM DUAL", d1=dk(W_MES[0]), d2=dk(W_MES[1]))[0]
    check_true("ECO97 tiene viajes en la ventana", eco97["VIAJES"] > 0, "viajes=%s" % eco97["VIAJES"])
    check("ECO97 sin facturas en la ventana (causa de 98 vs 99)", eco97["FACTURAS"], 0)
    row97 = next(r for r in render(6, W_MES) if r["UNIDAD"] == "ECO97")
    check("ds_06 ECO97 TOTAL_FACTURACION = 0", row97["TOTAL_FACTURACION"], 0)
    check_true("ds_06 ECO97 DESPACHOS_VIAJES > 0", row97["DESPACHOS_VIAJES"] > 0)
    flota = query("SELECT COUNT(DISTINCT CODIGO_ECO) AS N FROM DWH_MART.DIM_VEHICULO WHERE ID_VEHICULO <> -1")[0]["N"]
    check("flota (CODIGO_ECO distintos)", flota, 100)
    sin_actividad = query(
        "SELECT v.CODIGO_ECO AS ECO FROM (SELECT DISTINCT CODIGO_ECO FROM DWH_MART.DIM_VEHICULO WHERE ID_VEHICULO <> -1) v "
        "WHERE v.CODIGO_ECO NOT IN (SELECT vv.CODIGO_ECO FROM DWH_MART.FACT_DESPACHO_VIAJE d "
        "   JOIN DWH_MART.DIM_VEHICULO vv ON vv.ID_VEHICULO = d.ID_VEHICULO WHERE d.ID_FECHA_INICIO BETWEEN :d1 AND :d2) "
        "AND v.CODIGO_ECO NOT IN (SELECT vv.CODIGO_ECO FROM DWH_MART.FACT_FACTURACION_FLETE f "
        "   JOIN DWH_MART.DIM_VEHICULO vv ON vv.ID_VEHICULO = f.ID_VEHICULO WHERE f.ID_FECHA_FACTURACION BETWEEN :d1 AND :d2) "
        "AND v.CODIGO_ECO NOT IN (SELECT vv.CODIGO_ECO FROM DWH_MART.FACT_GASTOS_LIQUIDACION g "
        "   JOIN DWH_MART.DIM_VEHICULO vv ON vv.ID_VEHICULO = g.ID_VEHICULO WHERE g.ID_FECHA_LIQUIDACION BETWEEN :d1 AND :d2) "
        "AND v.CODIGO_ECO NOT IN (SELECT vv.CODIGO_ECO FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE l "
        "   JOIN DWH_MART.DIM_VEHICULO vv ON vv.ID_VEHICULO = l.ID_VEHICULO WHERE l.ID_FECHA_EMISION BETWEEN :d1 AND :d2)",
        d1=dk(W_MES[0]), d2=dk(W_MES[1]))
    check_true("100 - 99 = 1 unidad sin actividad en el mes (ECO22)",
               [r["ECO"] for r in sin_actividad] == ["ECO22"], str([r["ECO"] for r in sin_actividad]))


def _historico(window, tag, anchors=None):
    r6, r7, r5 = render(6, window), render(7, window), render(5, window)
    compare_productividad("ds_06@" + tag, r6, window, "eco", "UNIDAD")
    compare_productividad("ds_07@" + tag, r7, window, "op", "CLAVE_NOMBRE")
    for col in ("DESPACHOS_VIAJES", "CERRADOS", "KMS_TOTAL", "TOTAL_FACTURACION", "TOTAL_COSTO",
                "DISTANCIA_DECLARADA_KM"):
        check("cuadre ds_06 == ds_07 @%s: %s" % (tag, col), s(r6, col), s(r7, col))
    check("ds_05 == ds_06 facturacion @%s" % tag, s(r5, "TOTAL_FACTURACION"), s(r6, "TOTAL_FACTURACION"))
    if anchors:
        check("ds_06 despachos @%s" % tag, s(r6, "DESPACHOS_VIAJES"), anchors["despachos"])
        check("ds_06 cerrados @%s" % tag, s(r6, "CERRADOS"), anchors["cerrados"])
        check("ds_06 kms @%s" % tag, s(r6, "KMS_TOTAL"), anchors["kms"])
        check("ds_06 facturacion @%s" % tag, s(r6, "TOTAL_FACTURACION"), anchors["facturado"])
        if "gastos" in anchors:
            check("ds_06 gastos @%s" % tag, s(r6, "TOTAL_COSTO"), anchors["gastos"])
    return r6


@reconcile
def test_04_acumulado_90_dias_cerrados():
    a = A["h90"]
    r6 = _historico(W_90D, "90d", a)
    # kms/kWh de los viajes (ds_06) cuadran con el snapshot de flota (MV) de los mismos 90 dias
    mv = query("SELECT COUNT(*) AS DIAS, SUM(TOTAL_KMS_DIA) AS KMS, SUM(TOTAL_KWH_DIA) AS KWH "
               "FROM BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA WHERE ID_FECHA_CORTE BETWEEN :d1 AND :d2",
               d1=dk(W_90D[0]), d2=dk(W_90D[1]))[0]
    check("MV_METRICAS_FLOTA_DIARIA: 90 dias", mv["DIAS"], 90)
    check("MV_METRICAS: kms 90d == ds_06 kms (snapshot vs despacho)", mv["KMS"], s(r6, "KMS_TOTAL"))
    check("MV_METRICAS: kms 90d (ancla)", mv["KMS"], a["kms"])
    check("MV_METRICAS: kWh 90d (ancla)", mv["KWH"], a["kwh"])
    check("rendimiento global 90d (kms/kWh)", rnd(mv["KMS"] / mv["KWH"], 2), D("5.57"))
    # Reconstruccion de la linea base de Fase 3 (previa a la corrida incremental)
    f = A["fase3"]
    base = query("SELECT COUNT(*) AS N, SUM(IMPORTE_TOTAL_FACTURADO) AS IMP FROM "
                 "(SELECT IMPORTE_TOTAL_FACTURADO FROM DWH_MART.FACT_FACTURACION_FLETE "
                 " ORDER BY ID_FACT_FACTURACION FETCH FIRST :n ROWS ONLY)", n=f["facturas_base"])[0]
    check("Fase 3: 5,029 primeras facturas = $309,227,803.56", base["IMP"], f["facturado_base"])
    check("Fase 3 + 14 CFDI incrementales = total 91 dias",
          f["facturado_base"] + f["facturado_incr"], A["full"]["facturado"])
    check("Kms 90d actuales + dia 91 = kms 91 dias",
          a["kms"] + A["dia91"]["kms"], A["full"]["kms"])


@reconcile
def test_05_acumulado_91_dias_vs_mv_productividad():
    a = A["full"]
    r6 = _historico(W_ALL, "91d", a)
    # --- MV_PRODUCTIVIDAD_ECO_MENSUAL: totales y fila por unidad
    tot = query("SELECT COUNT(*) AS FILAS, COUNT(DISTINCT UNIDAD) AS UNIDADES, SUM(DESPACHOS_VIAJES) AS DESP, "
                "SUM(CERRADOS) AS CERR, SUM(KMS_TOTAL) AS KMS, SUM(TOTAL_FACTURACION) AS FAC, "
                "SUM(TOTAL_COSTO) AS COSTO FROM BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL")[0]
    check("MV_PRODUCTIVIDAD: filas", tot["FILAS"], a["mv_filas"])
    check("MV_PRODUCTIVIDAD: unidades", tot["UNIDADES"], a["unidades"])
    check("MV_PRODUCTIVIDAD: facturacion total ($310,348,743.81)", tot["FAC"], a["facturado"])
    check("MV_PRODUCTIVIDAD: kms totales (1,827,114.49)", tot["KMS"], a["kms"])
    check("MV_PRODUCTIVIDAD: despachos", tot["DESP"], a["despachos"])
    check("MV_PRODUCTIVIDAD: cerrados", tot["CERR"], a["cerrados"])
    check("MV_PRODUCTIVIDAD: gastos", tot["COSTO"], a["gastos"])
    check("ds_06 facturacion == MV", s(r6, "TOTAL_FACTURACION"), tot["FAC"])
    check("ds_06 kms == MV", s(r6, "KMS_TOTAL"), tot["KMS"])
    mv_units = query(
        "SELECT UNIDAD, SUM(DESPACHOS_VIAJES) AS DESP, SUM(CERRADOS) AS CERR, SUM(KMS_CARGADO) AS KC, "
        "SUM(KMS_VACIO) AS KV, SUM(KMS_TOTAL) AS KT, SUM(TOTAL_FACTURACION) AS FAC, SUM(OPERADOR) AS OPE, "
        "SUM(MANTENIMIENTO) AS MAN, SUM(OTROS_GASTOS) AS OTR, SUM(TOTAL_COSTO) AS TC "
        "FROM BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL GROUP BY UNIDAD")
    mv = {r["UNIDAD"]: r for r in mv_units}
    got = {r["UNIDAD"]: r for r in r6}
    pairs = (("DESPACHOS_VIAJES", "DESP"), ("CERRADOS", "CERR"), ("KMS_CARGADO", "KC"), ("KMS_VACIO", "KV"),
             ("KMS_TOTAL", "KT"), ("TOTAL_FACTURACION", "FAC"), ("OPERADOR", "OPE"), ("MANTENIMIENTO", "MAN"),
             ("OTROS_GASTOS", "OTR"), ("TOTAL_COSTO", "TC"))
    check_true("ds_06 y MV: mismo conjunto de unidades (ECO22 incluido o no)", set(got) <= set(mv) and
               set(mv) - set(got) <= {"ECO22"}, str(sorted(set(mv) ^ set(got))))
    check("ds_06 vs MV por unidad: celdas con diferencia",
          sum(1 for k in got for c, m in pairs if dec(got[k][c]) != dec(mv[k][m])), 0)
    # --- Mes calendario noviembre: ds_06 (11-01..11-30) == MV (ANIO=2026, MES=11) por unidad
    rn = render(6, W_NOV)
    mvn = {r["UNIDAD"]: r for r in query(
        "SELECT UNIDAD, SUM(DESPACHOS_VIAJES) AS DESP, SUM(CERRADOS) AS CERR, SUM(KMS_CARGADO) AS KC, "
        "SUM(KMS_VACIO) AS KV, SUM(KMS_TOTAL) AS KT, SUM(TOTAL_FACTURACION) AS FAC, SUM(OPERADOR) AS OPE, "
        "SUM(MANTENIMIENTO) AS MAN, SUM(OTROS_GASTOS) AS OTR, SUM(TOTAL_COSTO) AS TC "
        "FROM BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL WHERE ANIO = :a AND MES = :m GROUP BY UNIDAD", a=2026, m=11)}
    gotn = {r["UNIDAD"]: r for r in rn}
    check("MV noviembre: unidades == ds_06 noviembre", len(gotn), len(mvn))
    check("ds_06 vs MV noviembre por unidad: celdas con diferencia",
          sum(1 for k in gotn for c, m in pairs if dec(gotn[k][c]) != dec(mvn[k][m])), 0)
    # --- Rendimiento
    prom = query("SELECT ROUND(AVG(RENDIMIENTO_PROM_KMS_KWH), 2) AS P FROM BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL")[0]["P"]
    check("MV rendimiento promedio de filas (Fase 3 reportaba 5.68; 5.67 tras incremental)", prom, D("5.67"))
    kwh = query("SELECT SUM(KWH_CONSUMO_ENERGIA) AS KWH FROM DWH_MART.FACT_DESPACHO_VIAJE")[0]["KWH"]
    check("kWh totales 91 dias", kwh, a["kwh"])
    check("rendimiento global 91d (kms/kWh)", rnd(a["kms"] / kwh, 2), D("5.57"))
    # --- ds_01 vs MV_METRICAS_FLOTA_DIARIA: los 91 dias
    mvd = {r["ID_FECHA_CORTE"]: r for r in query(
        "SELECT * FROM BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA WHERE ID_FECHA_CORTE BETWEEN :d1 AND :d2",
        d1=dk(W_91D[0]), d2=dk(W_91D[1]))}
    check("MV_METRICAS: 91 dias", len(mvd), 91)
    bad = 0
    for key, m in sorted(mvd.items()):
        iso = "%04d-%02d-%02d" % (key // 10000, key // 100 % 100, key % 100)
        rows = {r["ESTADO_FLOTA"]: dec(r["CANTIDAD_UNIDADES"]) for r in render(1, (iso, iso))}
        got3 = (rows.get("Con Viaje", D(0)), rows.get("Sin Viaje", D(0)), rows.get("Inactivas", D(0)))
        exp3 = (dec(m["UNIDADES_CON_VIAJE"]), dec(m["UNIDADES_SIN_VIAJE"]), dec(m["UNIDADES_INACTIVAS"]))
        if got3 != exp3 or sum(got3) != 100:
            bad += 1
            _CUR.append(("ds_01 vs MV @%s" % iso, got3, exp3, False))
    check("ds_01 vs MV_METRICAS: dias con diferencia (de 91)", bad, 0)
    check("MV_METRICAS: kms 91d", sum(dec(m["TOTAL_KMS_DIA"]) for m in mvd.values()), a["kms"])
    check("MV_METRICAS: kWh 91d", sum(dec(m["TOTAL_KWH_DIA"]) for m in mvd.values()), a["kwh"])


@reconcile
def test_06_aislamiento_dia_91_20261107():
    a = A["dia91"]
    rows = {r["ESTADO_FLOTA"]: r for r in render(1, W_DIA91)}
    check("ds_01 unidades totales", s(rows.values(), "CANTIDAD_UNIDADES"), a["unidades"])
    check("ds_01 Con Viaje", rows["Con Viaje"]["CANTIDAD_UNIDADES"], a["con_viaje"])
    check("ds_01 Sin Viaje", rows["Sin Viaje"]["CANTIDAD_UNIDADES"], a["sin_viaje"])
    check("ds_01 Inactivas", rows["Inactivas"]["CANTIDAD_UNIDADES"], a["inactivas"])
    check("ds_01 % Con Viaje", rows["Con Viaje"]["PORCENTAJE_FLOTA"], D("5.00"))
    check("ds_01 % Sin Viaje", rows["Sin Viaje"]["PORCENTAJE_FLOTA"], D("91.00"))
    check("ds_01 % Inactivas", rows["Inactivas"]["PORCENTAJE_FLOTA"], D("4.00"))
    snap = snapshot_dia(W_DIA91[0])
    check("snapshot independiente: Con Viaje", snap["CV"], a["con_viaje"])
    check("snapshot independiente: Sin Viaje", snap["SV"], a["sin_viaje"])
    check("snapshot independiente: Inactivas", snap["INA"], a["inactivas"])
    i = ind_ops(W_DIA91[1], "2026-11-01")
    r2, r3 = render(2, W_DIA91)[0], render(3, W_DIA91)[0]
    check("ds_02 DESPACHOS_DIA (5 viajes nuevos)", r2["DESPACHOS_DIA"], a["despachos"])
    check("ds_02 CIERRES_DIA (3 cerrados)", r2["CIERRES_DIA"], a["cerrados"])
    check("viajes abiertos del dia 91 (despachos - cierres)", r2["DESPACHOS_DIA"] - r2["CIERRES_DIA"], a["abiertos"])
    check("ds_02 DESPACHOS_DIA == independiente", r2["DESPACHOS_DIA"], i["DESP_DIA"])
    check("ds_03 TOTAL_KMS_DIA", r3["TOTAL_KMS_DIA"], a["kms"])
    check("ds_03 TOTAL_KMS_DIA == snapshot independiente", r3["TOTAL_KMS_DIA"], snap["KMS"])
    abiertos_total = query("SELECT COUNT(*) AS N FROM DWH_MART.FACT_DESPACHO_VIAJE WHERE CONTADOR_CERRADO = 0")[0]["N"]
    check("viajes abiertos en todo el DW (los 2 del dia 91)", abiertos_total, 2)
    # --- ds_04..ds_07 aislados al dia 91
    r4, r6, r7 = render(4, W_DIA91), render(6, W_DIA91), render(7, W_DIA91)
    check("ds_04 sum DESPACHOS_DIA", s(r4, "DESPACHOS_DIA"), a["despachos"])
    check("ds_06 despachos", s(r6, "DESPACHOS_VIAJES"), a["despachos"])
    check("ds_06 cerrados", s(r6, "CERRADOS"), a["cerrados"])
    check("ds_06 kms", s(r6, "KMS_TOTAL"), a["kms"])
    check("ds_07 despachos", s(r7, "DESPACHOS_VIAJES"), a["despachos"])
    compare_productividad("ds_06@dia91", r6, W_DIA91, "eco", "UNIDAD")
    compare_productividad("ds_07@dia91", r7, W_DIA91, "op", "CLAVE_NOMBRE")
    # --- ECO15: 2 versiones SCD2, 1 sola fila en ds_05/ds_06 (y 1 sola unidad en ds_01)
    ver = query("SELECT ID_VEHICULO, PLACA, VERSION_ACTIVA FROM DWH_MART.DIM_VEHICULO WHERE CODIGO_ECO = 'ECO15' "
                "ORDER BY FECHA_INICIO_VALIDEZ")
    check("DIM_VEHICULO: ECO15 con 2 versiones SCD2", len(ver), 2)
    check_true("DIM_VEHICULO: v1 inactiva / v2 activa y placas distintas",
               [v["VERSION_ACTIVA"] for v in ver] == ["0", "1"] and ver[0]["PLACA"] != ver[1]["PLACA"],
               str([(v["ID_VEHICULO"], v["PLACA"], v["VERSION_ACTIVA"]) for v in ver]))
    ids = [v["ID_VEHICULO"] for v in ver]
    for tag, w in (("11-06", W_DIA), ("11-07", W_DIA91)):
        u = render(1, w, {"CODIGO_ECO": ["ECO15"]})
        check("ds_01 filtro ECO15 @%s: exactamente 1 unidad (no 2 versiones)" % tag, s(u, "CANTIDAD_UNIDADES"), 1)
    for n, tag in ((5, "ds_05"), (6, "ds_06")):
        filas = [r for r in render(n, W_ALL) if r["UNIDAD"] == "ECO15"]
        check("%s ECO15 @carga completa: exactamente 1 fila" % tag, len(filas), 1)
    r15 = next(r for r in render(6, W_ALL) if r["UNIDAD"] == "ECO15")
    e15 = query(
        "SELECT (SELECT COUNT(*) FROM DWH_MART.FACT_DESPACHO_VIAJE WHERE ID_VEHICULO IN (:a, :b)) AS DESP, "
        "(SELECT SUM(KMS_TOTAL) FROM DWH_MART.FACT_DESPACHO_VIAJE WHERE ID_VEHICULO IN (:a, :b)) AS KMS, "
        "(SELECT SUM(IMPORTE_TOTAL_FACTURADO) FROM DWH_MART.FACT_FACTURACION_FLETE WHERE ID_VEHICULO IN (:a, :b)) AS FAC, "
        "(SELECT SUM(IMPORTE_GASTO) FROM DWH_MART.FACT_GASTOS_LIQUIDACION WHERE ID_VEHICULO IN (:a, :b)) AS COSTO FROM DUAL",
        a=ids[0], b=ids[1])[0]
    check("ds_06 ECO15 despachos == suma de ambas versiones", r15["DESPACHOS_VIAJES"], e15["DESP"])
    check("ds_06 ECO15 kms == suma de ambas versiones", r15["KMS_TOTAL"], e15["KMS"])
    check("ds_06 ECO15 facturacion == suma de ambas versiones", r15["TOTAL_FACTURACION"], e15["FAC"])
    check("ds_06 ECO15 costo == suma de ambas versiones", r15["TOTAL_COSTO"], e15["COSTO"])
    # Observacion: la v2 (placa 47LL35) solo tiene snapshot el dia 91; los 5 viajes del dia 91 son de otras ECO.
    check("ds_06 @dia 91: filas de ECO15 (v2 sin viajes ese dia)", len([r for r in r6 if r["UNIDAD"] == "ECO15"]), 0)


@reconcile
def test_07_distancia_declarada_colapsada_por_uuid_ccp():
    inv = query("SELECT COUNT(*) AS N FROM (SELECT UUID_CCP FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE "
                "GROUP BY UUID_CCP HAVING MIN(DISTANCIA_DECLARADA_KM) <> MAX(DISTANCIA_DECLARADA_KM))")[0]["N"]
    check("invariante: 0 UUID_CCP con distancias distintas entre mercancias", inv, 0)
    multi = query("SELECT COUNT(*) AS N FROM (SELECT UUID_CCP FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE "
                  "GROUP BY UUID_CCP HAVING COUNT(*) > 1)")[0]["N"]
    check_true("precondicion: hay CCP con varias mercancias (riesgo de multiplicacion)", multi > 0, "%s CCP multi-linea" % multi)
    for tag, w in (("mes", W_MES), ("90d", W_90D), ("91d", W_ALL)):
        ind = independent(w)
        colapsada = s(ind["ccp_dist"], "DIST")
        naive = s(ind["ccp_lineas"], "DIST_NAIVE")
        uuids, lineas = s(ind["ccp_dist"], "UUIDS"), s(ind["ccp_lineas"], "LINEAS")
        r6, r7 = render(6, w), render(7, w)
        check("[%s] ds_06 DISTANCIA_DECLARADA_KM == suma por UUID_CCP" % tag, s(r6, "DISTANCIA_DECLARADA_KM"), colapsada)
        check("[%s] ds_07 DISTANCIA_DECLARADA_KM == suma por UUID_CCP" % tag, s(r7, "DISTANCIA_DECLARADA_KM"), colapsada)
        check_true("[%s] ds_06 NO es la suma por mercancia (%s vs %s)" % (tag, s(r6, "DISTANCIA_DECLARADA_KM"), naive),
                   s(r6, "DISTANCIA_DECLARADA_KM") != naive and naive > colapsada)
        check_true("[%s] factor de multiplicacion evitado = lineas/CCP (%s/%s)" % (tag, lineas, uuids),
                   naive / colapsada > D("1.5"), "x%s" % rnd(naive / colapsada, 2))
        check("[%s] peso (aditivo por mercancia) ds_06 == ds_07" % tag, s(r6, "PESO_DECLARADO_KG"), s(r7, "PESO_DECLARADO_KG"))
        check("[%s] peso ds_06 == suma de lineas independiente" % tag, s(r6, "PESO_DECLARADO_KG"), s(ind["ccp_lineas"], "PESO"))
    # ds_08: embarques = CCP distintos; distancia colapsada
    for tag, w in (("mes", W_MES), ("91d", W_ALL)):
        r8 = render(8, w)
        ind = query(
            "SELECT COUNT(*) AS EMB, SUM(u.DISTANCIA_DECLARADA_KM) AS DIST FROM (SELECT DISTINCT UUID_CCP, DISTANCIA_DECLARADA_KM "
            "FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE WHERE ID_FECHA_EMISION BETWEEN :d1 AND :d2 "
            "AND ID_ORIGEN_UBICACION <> -1 AND ID_DESTINO_UBICACION <> -1) u", d1=dk(w[0]), d2=dk(w[1]))[0]
        peso = query("SELECT SUM(PESO_KG) AS P FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE WHERE ID_FECHA_EMISION BETWEEN :d1 AND :d2 "
                     "AND ID_ORIGEN_UBICACION <> -1 AND ID_DESTINO_UBICACION <> -1", d1=dk(w[0]), d2=dk(w[1]))[0]["P"]
        check("[%s] ds_08 TOTAL_EMBARQUES_CCP == CCP distintos" % tag, s(r8, "TOTAL_EMBARQUES_CCP"), ind["EMB"])
        check("[%s] ds_08 TOTAL_DISTANCIA_KM colapsada por UUID_CCP" % tag, s(r8, "TOTAL_DISTANCIA_KM"), ind["DIST"])
        check("[%s] ds_08 TOTAL_PESO_KG == suma de mercancias" % tag, s(r8, "TOTAL_PESO_KG"), peso)
    check("ds_08 @91d: embarques == 5,045 CCP", s(render(8, W_ALL), "TOTAL_EMBARQUES_CCP"), A["full"]["despachos"])


# --------------------------------------------------------------------------------------------
# Ejecucion standalone (sin pytest)
# --------------------------------------------------------------------------------------------
def main(argv):
    verbose = "-v" in argv
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    total_checks = 0
    print("=" * 96)
    print(" ST-5 - Conciliacion de KPIs Superset <-> Oracle DW (BI_READER, Thin Mode)")
    print("=" * 96)
    for name, fn in tests:
        try:
            fn()
            status, err = "PASS", ""
        except Exception as exc:  # noqa: BLE001 - se reporta y se continua
            status, err = "FAIL", str(exc)
            failed += 1
        checks = RESULTS.get(name, list(_CUR))
        total_checks += len(checks)
        print("[%s] %-60s %4d checks" % (status, name, len(checks)))
        if verbose:
            for label, act, exp, ok in checks:
                print("     %s %-78s %s" % ("ok " if ok else "XX ", label[:78], act if ok else "%s != %s" % (act, exp)))
        if err:
            print(err)
    print("-" * 96)
    print("RESULTADO: %d/%d grupos PASS | %d aserciones evaluadas" % (len(tests) - failed, len(tests), total_checks))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
