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
                "name": "4. Native Filter CLIENTE = 'PROCTER & GAMBLE MANUFACTURING MEXICO'",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": [{"col": "CLIENTE", "op": "IN", "val": ["PROCTER & GAMBLE MANUFACTURING MEXICO"]}]
            },
            {
                "name": "5. Native Filter OPERADOR = 'OP001 - MARÍA JOSÉ LILIANA MEDINA'",
                "time_range": "2026-11-01 : 2026-11-06",
                "extra_filters": [{"col": "NOMBRE_OPERADOR", "op": "IN", "val": ["MARÍA JOSÉ LILIANA MEDINA"]}]
            },
            {
                "name": "6. Aislamiento Día 91 (2026-11-07)",
                "time_range": "2026-11-07 : 2026-11-07",
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
                    query_obj["columns"] = params.get("groupby", [])
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

        print("\n==================================================================")
        if all_passed:
            print("  RESULTADO: 100% de Charts y Escenarios validados exitosamente (PASS)")
        else:
            print("  RESULTADO: Se detectaron fallos en la validación")
        print("==================================================================")

if __name__ == "__main__":
    with app.app_context():
        test_live_charts()
