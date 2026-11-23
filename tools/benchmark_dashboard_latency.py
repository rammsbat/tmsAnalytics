"""
ST-6 / DoD #5 - Benchmark de latencia del dashboard TRA099R1: frio (Oracle) vs caliente (cache Valkey).

Llama por HTTP real a /api/v1/chart/data (misma via que el navegador), por lo que atraviesa
DATA_CACHE_CONFIG (Valkey). Frio = "force": true (omite cache y consulta Oracle en Thin Mode);
caliente = misma peticion sin force tras haber poblado la cache (se verifica "is_cached").

Seguridad (Regla 03): credenciales SOLO desde el entorno del contenedor
(SUPERSET_ADMIN_USER / SUPERSET_ADMIN_PASSWORD); nada hardcodeado ni se imprime.

Ejecucion (contenedor tms-superset-app):
    docker cp tools/benchmark_dashboard_latency.py tms-superset-app:/tmp/tools/
    docker exec tms-superset-app python /tmp/tools/benchmark_dashboard_latency.py
Exit code 0 si p95 (frio y caliente) < umbral (3.0 s por defecto, --umbral para cambiarlo).
"""
import argparse
import collections
import json
import math
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = os.environ.get("SUPERSET_URL", "http://localhost:8088")
SLUG = "reporte-diario-operacion-tra099r1"
FALLOS = collections.Counter()

ESCENARIOS = [
    ("base 11-01..11-06", "2026-11-01 : 2026-11-06", []),
    ("UNIDAD=ECO01", "2026-11-01 : 2026-11-06", [{"col": "UNIDAD", "op": "IN", "val": ["ECO01"]}]),
    ("CLIENTE (3)", "2026-11-01 : 2026-11-06", [{"col": "CLIENTE", "op": "IN", "val": [
        "PROCTER & GAMBLE MANUFACTURING MEXICO", "ALIMENTOS PROCESADOS DEL CENTRO", "ABARROTES Y CONSUMO NACIONAL"]}]),
    ("dia 91 (11-07)", "2026-11-07 : 2026-11-07", []),
    ("historico ampliado", "2026-10-01 : 2026-11-10", []),
]


def p95(values):
    s = sorted(values)
    return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def cargar_slices():
    """Lee del metastore los 12 charts del dashboard (id, tipo, params, dataset)."""
    from superset.app import create_app
    app = create_app()
    with app.app_context():
        from superset import db
        from superset.models.dashboard import Dashboard
        dash = db.session.query(Dashboard).filter_by(slug=SLUG).first()
        return [(s.id, s.slice_name, s.viz_type, json.loads(s.params), s.datasource_id) for s in dash.slices]


def query_obj(viz, params, time_range, filtros):
    q = {"time_range": time_range, "row_limit": params.get("row_limit", 100)}
    if viz == "big_number_total":
        m = params.get("metric")
        q["metrics"], q["columns"] = ([m] if m else []), []
    elif viz == "pie":
        m = params.get("metric")
        q["columns"], q["metrics"] = params.get("groupby", []), ([m] if m else [])
    elif viz == "echarts_timeseries_bar":
        q["columns"] = [params["x_axis"]] if "x_axis" in params else params.get("groupby", [])
        q["metrics"] = params.get("metrics", [])
        if "orderby" in params:
            q["orderby"] = params["orderby"]
    elif viz == "table":
        q["columns"], q["metrics"] = params.get("all_columns", []), []
        if "order_by_cols" in params:
            q["orderby"] = [json.loads(x) for x in params["order_by_cols"]]
    if filtros:
        q["filters"] = filtros
        q["adhoc_filters"] = [{"clause": "WHERE", "expressionType": "SIMPLE", "comparator": f["val"],
                               "operator": f["op"], "subject": f["col"]} for f in filtros]
    return q


class Cliente:
    def __init__(self):
        self.s = requests.Session()
        user = os.environ["SUPERSET_ADMIN_USER"]
        pwd = os.environ["SUPERSET_ADMIN_PASSWORD"]
        r = self.s.post(BASE + "/api/v1/security/login", json={
            "username": user, "password": pwd, "provider": "db", "refresh": True}, timeout=30)
        r.raise_for_status()
        self.h = {"Authorization": "Bearer " + r.json()["access_token"]}
        c = self.s.get(BASE + "/api/v1/security/csrf_token/", headers=self.h, timeout=30)
        c.raise_for_status()
        self.h.update({"X-CSRFToken": c.json()["result"], "Referer": BASE, "Content-Type": "application/json"})

    def chart(self, slice_info, escenario, force):
        _, nombre, viz, params, ds_id = slice_info
        _, tr, filtros = escenario
        body = {"datasource": {"id": ds_id, "type": "table"}, "force": force,
                "queries": [query_obj(viz, params, tr, filtros)], "result_format": "json", "result_type": "full"}
        t0 = time.perf_counter()
        r = self.s.post(BASE + "/api/v1/chart/data", headers=self.h, data=json.dumps(body), timeout=120)
        dt = time.perf_counter() - t0
        ok = r.status_code == 200
        q = r.json()["result"][0] if ok else {}
        ok = ok and q.get("status") == "success" and not q.get("error")
        if not ok:
            FALLOS[(r.status_code, (q.get("error") or r.text)[:120].replace("\n", " "))] += 1
        return nombre, dt, ok, bool(q.get("is_cached"))


PAUSA_S = 1.2  # Superset limita la API a 50 req/s por cliente (429): una carga = 12 req; se deja "think time" entre cargas


def dashboard_load(cli, slices, esc, force):
    """Simula la carga del dashboard: los 12 charts en paralelo (como el navegador)."""
    time.sleep(PAUSA_S)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(slices)) as ex:
        res = list(ex.map(lambda si: cli.chart(si, esc, force), slices))
    return time.perf_counter() - t0, res


def resumen(titulo, valores, umbral):
    v = valores
    linea = "  %-34s n=%3d  media=%7.1f ms  p50=%7.1f ms  p95=%7.1f ms  max=%7.1f ms  [%s]" % (
        titulo, len(v), statistics.mean(v) * 1000, statistics.median(v) * 1000, p95(v) * 1000, max(v) * 1000,
        "PASS" if p95(v) < umbral else "FAIL")
    print(linea)
    return p95(v) < umbral


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--umbral", type=float, default=3.0, help="p95 maximo en segundos")
    ap.add_argument("--reps", type=int, default=5, help="repeticiones de carga de dashboard por escenario")
    a = ap.parse_args()

    slices = cargar_slices()
    cli = Cliente()
    print("=" * 96)
    print("  DoD #5 - Latencia dashboard TRA099R1 | %d charts | umbral p95 < %.1f s | Valkey DATA_CACHE activa" % (len(slices), a.umbral))
    print("=" * 96)

    frio_chart, cal_chart, frio_dash, cal_dash, errores, no_cached = [], [], [], [], 0, 0
    for esc in ESCENARIOS:
        print("\n--- Escenario: %s ---" % esc[0])
        f_dash, c_dash = [], []
        for _ in range(a.reps):
            dt, res = dashboard_load(cli, slices, esc, force=True)       # FRIO: omite cache, pega a Oracle
            f_dash.append(dt)
            frio_chart += [r[1] for r in res]
            errores += sum(1 for r in res if not r[2])
        dashboard_load(cli, slices, esc, force=True)                       # deja la cache poblada
        for _ in range(a.reps):
            dt, res = dashboard_load(cli, slices, esc, force=False)       # CALIENTE: cache Valkey
            c_dash.append(dt)
            cal_chart += [r[1] for r in res]
            errores += sum(1 for r in res if not r[2])
            no_cached += sum(1 for r in res if r[2] and not r[3])
        frio_dash += f_dash
        cal_dash += c_dash
        print("  dashboard frio     : %s ms" % ", ".join("%.0f" % (x * 1000) for x in f_dash))
        print("  dashboard caliente : %s ms" % ", ".join("%.0f" % (x * 1000) for x in c_dash))

    print("\n" + "=" * 96)
    print("  RESULTADOS (latencia de extremo a extremo por HTTP)")
    print("=" * 96)
    ok = [
        resumen("chart individual FRIO (Oracle)", frio_chart, a.umbral),
        resumen("chart individual CALIENTE (Valkey)", cal_chart, a.umbral),
        resumen("carga dashboard FRIO (12 en //)", frio_dash, a.umbral),
        resumen("carga dashboard CALIENTE (12 en //)", cal_dash, a.umbral),
    ]
    mejora = statistics.mean(frio_chart) / max(statistics.mean(cal_chart), 1e-9)
    print("\n  Aceleracion media por cache (chart): x%.1f | respuestas calientes sin is_cached=True: %d | errores: %d"
          % (mejora, no_cached, errores))
    for (code, msg), n in FALLOS.most_common(5):
        print("  fallo x%d: HTTP %s %s" % (n, code, msg))
    final = all(ok) and errores == 0 and no_cached == 0
    print("\nRESULTADO DoD #5: %s" % ("PASS (p95 < %.1f s en frio y caliente, cache Valkey efectiva)" % a.umbral if final else "FAIL"))
    return 0 if final else 1


if __name__ == "__main__":
    sys.exit(main())
