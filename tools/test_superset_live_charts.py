"""
Script de validación en vivo de Charts y Filtros Nativos de Superset
contra Oracle DW (Thin Mode) simulando llamadas a /api/v1/chart/data
con los nombres de filtros nativos (UNIDAD, NOMBRE_OPERADOR, CLIENTE, time_range).
"""
import json
from superset.app import create_app

app = create_app()

with app.app_context():
    from superset import db
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard
    from superset.connectors.sqla.models import SqlaTable
    from superset.common.query_context_factory import QueryContextFactory

    def test_live_charts():
        print("==================================================================")
        print("  VALIDACIÓN EN VIVO DE CHARTS Y NATIVE FILTERS EN APACHE SUPERSET")
        print("==================================================================")
        
        dash = db.session.query(Dashboard).filter_by(slug="reporte-diario-operacion-tra099r1").first()
        if not dash:
            print("[ERROR] Dashboard no encontrado")
            return
            
        slices = dash.slices
        print(f"Total Slices asociados al Dashboard '{dash.dashboard_title}': {len(slices)}")
        
        test_scenarios = [
            {
                "name": "1. Escenario Base (Corte cerrado 2026-11-01 a 2026-11-06)",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": []
            },
            {
                "name": "2. Native Filter UNIDAD = 'ECO01'",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": [{"col": "UNIDAD", "op": "IN", "val": ["ECO01"]}]
            },
            {
                "name": "3. Native Filter Multi-valor UNIDAD IN ('ECO01', 'ECO02', 'ECO15')",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": [{"col": "UNIDAD", "op": "IN", "val": ["ECO01", "ECO02", "ECO15"]}]
            },
            {
                "name": "4. Native Filter Multi-valor CLIENTE (3 Clientes)",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": [{"col": "CLIENTE", "op": "IN", "val": [
                    "PROCTER & GAMBLE MANUFACTURING MEXICO",
                    "ALIMENTOS PROCESADOS DEL CENTRO",
                    "ABARROTES Y CONSUMO NACIONAL"
                ]}]
            },
            {
                "name": "5. Native Filter Multi-valor OPERADOR (2 Operadores)",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": [{"col": "NOMBRE_OPERADOR", "op": "IN", "val": [
                    "MARÍA JOSÉ LILIANA MEDINA",
                    "FABIOLA SANABRIA"
                ]}]
            },
            {
                "name": "6. Aislamiento Día 91 (2026-11-07)",
                "time_range": "2026-11-07 : 2026-11-07",
                "extra_filters": []
            },
            {
                "name": "7. Rango Temporal Extendido (2026-10-01 : 2026-11-10)",
                "time_range": "2026-10-01 : 2026-11-10",
                "extra_filters": []
            },
            {
                "name": "8. Rango Temporal Historico (2026-10-01 : 2026-10-16)",
                "time_range": "2026-10-01 : 2026-10-16",
                "extra_filters": []
            }
        ]
        
        all_passed = True
        
        for sc in test_scenarios:
            print(f"\n--- {sc['name']} ---")
            for slc in slices:
                params = json.loads(slc.params)
                ds_id = slc.datasource_id
                viz = slc.viz_type
                
                # Armar query context
                query_obj = {
                    "time_range": sc["time_range"],
                    "row_limit": params.get("row_limit", 100)
                }
                
                if viz == "big_number_total":
                    metric_def = params.get("metric")
                    query_obj["metrics"] = [metric_def] if metric_def else []
                    query_obj["columns"] = []
                elif viz == "pie":
                    query_obj["columns"] = params.get("groupby", [])
                    metric_def = params.get("metric")
                    query_obj["metrics"] = [metric_def] if metric_def else []
                elif viz == "echarts_timeseries_bar":
                    query_obj["columns"] = [params["x_axis"]] if "x_axis" in params else params.get("groupby", [])
                    query_obj["metrics"] = params.get("metrics", [])
                    if "orderby" in params:
                        query_obj["orderby"] = params["orderby"]
                elif viz == "table":
                    cols = params.get("all_columns", [])
                    query_obj["columns"] = cols
                    query_obj["metrics"] = []
                    if "order_by_cols" in params:
                        query_obj["orderby"] = [json.loads(x) for x in params["order_by_cols"]]
                
                if sc["extra_filters"]:
                    query_obj["filters"] = sc["extra_filters"]
                    query_obj["adhoc_filters"] = [
                        {
                            "clause": "WHERE",
                            "expressionType": "SIMPLE",
                            "comparator": f["val"],
                            "operator": f["op"],
                            "subject": f["col"]
                        } for f in sc["extra_filters"]
                    ]
                
                try:
                    qc = QueryContextFactory().create(
                        datasource={"type": "table", "id": ds_id},
                        queries=[query_obj],
                        result_type="full",
                        force=True
                    )
                    payload = qc.get_payload()
                    q_res = payload["queries"][0]
                    status = q_res.get("status")
                    error = q_res.get("error")
                    data = q_res.get("data", [])
                    
                    if status == "success" and error is None:
                        first_row = data[0] if data else {}
                        first_row_str = str(first_row)
                        if len(first_row_str) > 85:
                            first_row_str = first_row_str[:82] + "..."
                        print(f"  [PASS] {slc.slice_name:46} ({viz:22}) | Rows: {len(data):3} | {first_row_str}")
                    else:
                        print(f"  [FAIL] {slc.slice_name:46} ({viz:22}) | Status: {status} | Error: {error}")
                        all_passed = False
                except Exception as e:
                    print(f"  [ERROR] {slc.slice_name:46} ({viz:22}) | Excepcion: {str(e)}")
                    all_passed = False

        print("\n--- 7. Validación de Endpoints de Filtros Nativos (Select Options) ---")
        # Los IDs de dataset no son portables entre entornos/re-importaciones: se resuelven
        # a partir del chart del bloque correspondiente (B6, B7, B4) del dashboard.
        def ds_id_of(prefix):
            return next(s.datasource_id for s in slices if s.slice_name.startswith(prefix))

        filter_endpoints = [
            {"name": "Filtro UNIDAD (ds_06)", "dataset_id": ds_id_of("B6 -"), "col": "UNIDAD", "min_rows": 90},
            {"name": "Filtro NOMBRE_OPERADOR (ds_07)", "dataset_id": ds_id_of("B7 -"), "col": "NOMBRE_OPERADOR", "min_rows": 10},
            {"name": "Filtro CLIENTE (ds_04)", "dataset_id": ds_id_of("B4 -"), "col": "CLIENTE", "min_rows": 5}
        ]
        for fe in filter_endpoints:
            try:
                qc = QueryContextFactory().create(
                    datasource={"type": "table", "id": fe["dataset_id"]},
                    queries=[{"columns": [fe["col"]], "row_limit": 1000}],
                    result_type="full",
                    force=True
                )
                payload = qc.get_payload()
                q_res = payload["queries"][0]
                status = q_res.get("status")
                data = q_res.get("data", [])
                if status == "success" and len(data) >= fe["min_rows"]:
                    sample_vals = [d[fe["col"]] for d in data[:3]]
                    print(f"  [PASS] {fe['name']:40} | Rows: {len(data):3} | Samples: {sample_vals}")
                else:
                    print(f"  [FAIL] {fe['name']:40} | Status: {status} | Rows: {len(data)}")
                    all_passed = False
            except Exception as e:
                print(f"  [ERROR] {fe['name']:40} | Excepcion: {str(e)}")
                all_passed = False

        print("\n==================================================================")
        if all_passed:
            print("  RESULTADO: 100% de Charts y Native Filters validados exitosamente (PASS)")
        else:
            print("  RESULTADO: Se detectaron fallos en la validación")
        print("==================================================================")

if __name__ == "__main__":
    with app.app_context():
        test_live_charts()
