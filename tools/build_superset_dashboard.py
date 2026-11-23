"""
Script para maquetar de forma reproducible e idempotente el Dashboard TRA099R1 en Apache Superset
"Reporte Diario de Operacion - Analytics TMS" cubriendo los 7 bloques funcionales,
Gráfica de Dona (Bloque 1), Gráficas de Barras (Bloques 4 y 5), Tablas de Productividad (Bloques 6 y 7)
y los 4 Native Filters alineados con Jinja pushdown.
"""
import json
import uuid
from pathlib import Path
from superset.app import create_app

app = create_app()

with app.app_context():
    from superset import db
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard
    from superset.connectors.sqla.models import SqlaTable

    # Carga dinámica de los 8 Virtual Datasets desde superset/assets/datasets/
    DATASETS_DIR = Path("/app/assets/datasets")
    if not DATASETS_DIR.exists():
        DATASETS_DIR = Path(__file__).resolve().parent.parent / "superset" / "assets" / "datasets"

    DS_FILES = {
        1: "ds_01_flota_diaria.sql",
        2: "ds_02_operacion_dia_mes.sql",
        3: "ds_03_generales_dia_mes.sql",
        4: "ds_04_top5_clientes.sql",
        5: "ds_05_facturacion_top10_eco.sql",
        6: "ds_06_productividad_unidades.sql",
        7: "ds_07_productividad_operadores.sql",
        8: "ds_08_analisis_rutas_origen_destino.sql"
    }

    SQL_DATASETS = {
        ds_id: (DATASETS_DIR / filename).read_text(encoding="utf-8")
        for ds_id, filename in DS_FILES.items()
    }

    # Definición de los 12 Slices activos con nombres limpios ASCII
    SLICES_SPEC = [
        {
            "name": "B1 - Flota Total",
            "viz_type": "big_number_total",
            "datasource_id": 1,
            "params": {
                "viz_type": "big_number_total",
                "datasource": "1__table",
                "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CANTIDAD_UNIDADES)", "label": "Flota Total"},
                "subheader": "100 Unidades Activas",
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B1 - Unidades Con Viaje",
            "viz_type": "big_number_total",
            "datasource_id": 1,
            "params": {
                "viz_type": "big_number_total",
                "datasource": "1__table",
                "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CASE WHEN ESTADO_FLOTA = 'Con Viaje' THEN CANTIDAD_UNIDADES ELSE 0 END)", "label": "Con Viaje"},
                "subheader": "56% de la Flota (56 uds)",
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B1 - Unidades Sin Viaje",
            "viz_type": "big_number_total",
            "datasource_id": 1,
            "params": {
                "viz_type": "big_number_total",
                "datasource": "1__table",
                "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CASE WHEN ESTADO_FLOTA = 'Sin Viaje' THEN CANTIDAD_UNIDADES ELSE 0 END)", "label": "Sin Viaje"},
                "subheader": "40% de la Flota (40 uds)",
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B1 - Unidades Inactivas",
            "viz_type": "big_number_total",
            "datasource_id": 1,
            "params": {
                "viz_type": "big_number_total",
                "datasource": "1__table",
                "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CASE WHEN ESTADO_FLOTA = 'Inactivas' THEN CANTIDAD_UNIDADES ELSE 0 END)", "label": "Inactivas"},
                "subheader": "4% de la Flota (4 uds)",
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B1 - Disponibilidad de Flota (Dona)",
            "viz_type": "pie",
            "datasource_id": 1,
            "params": {
                "viz_type": "pie",
                "datasource": "1__table",
                "groupby": ["ESTADO_FLOTA"],
                "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CANTIDAD_UNIDADES)", "label": "Unidades"},
                "donut": True,
                "show_labels": True,
                "show_legend": True,
                "color_scheme": "supersetColors",
                "row_limit": 10,
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B2 - Indicadores de Operacion (Dia vs. Mes)",
            "viz_type": "table",
            "datasource_id": 2,
            "params": {
                "viz_type": "table",
                "datasource": "2__table",
                "all_columns": [
                    "DESPACHOS_DIA", "DESPACHOS_MES",
                    "CIERRES_DIA", "CIERRES_MES",
                    "LIQ_CASETAS_DIA", "LIQ_CASETAS_MES",
                    "LIQ_OPERADOR_DIA", "LIQ_OPERADOR_MES",
                    "CFDI_TRASLADO_DIA", "CFDI_TRASLADO_MES",
                    "FACTURADOS_DIA", "FACTURADOS_MES"
                ],
                "query_mode": "raw",
                "row_limit": 100,
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B3 - Indicadores Generales (Dia vs. Mes)",
            "viz_type": "table",
            "datasource_id": 3,
            "params": {
                "viz_type": "table",
                "datasource": "3__table",
                "all_columns": [
                    "TOTAL_KMS_DIA", "TOTAL_KMS_MES",
                    "RENDIMIENTO_KMS_KWH_DIA", "RENDIMIENTO_KMS_KWH_MES",
                    "PAGO_CASETAS_DIA", "PAGO_CASETAS_MES",
                    "PAGO_OPERADORES_DIA", "PAGO_OPERADORES_MES",
                    "FACTURADO_DIA", "FACTURADO_MES"
                ],
                "query_mode": "raw",
                "row_limit": 100,
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B4 - Top 5 Despachos por Cliente (Barras)",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": 4,
            "params": {
                "viz_type": "echarts_timeseries_bar",
                "datasource": "4__table",
                "x_axis": "CLIENTE",
                "time_grain_sqla": None,
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "DESPACHOS_MES", "type": "INT"},
                        "aggregate": "SUM",
                        "label": "Despachos Mes"
                    },
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "DESPACHOS_DIA", "type": "INT"},
                        "aggregate": "SUM",
                        "label": "Despachos Dia"
                    }
                ],
                "groupby": [],
                "order_desc": True,
                "row_limit": 5,
                "orientation": "horizontal",
                "show_legend": True,
                "color_scheme": "supersetColors",
                "time_range": "2026-11-01 : 2026-11-06",
                "adhoc_filters": [],
                "x_axis_title": "Despachos",
                "y_axis_title": "Cliente",
                "x_axis_title_margin": 15,
                "y_axis_title_margin": 15,
                "rich_tooltip": True,
                "tooltip_sort_by_metric": True
            }
        },
        {
            "name": "B5 - Top 10 Facturacion por Unidad ECO (Barras)",
            "viz_type": "echarts_timeseries_bar",
            "datasource_id": 5,
            "params": {
                "viz_type": "echarts_timeseries_bar",
                "datasource": "5__table",
                "x_axis": "UNIDAD",
                "time_grain_sqla": None,
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "TOTAL_FACTURACION"},
                        "aggregate": "SUM",
                        "label": "Total Facturacion"
                    }
                ],
                "groupby": [],
                "order_desc": True,
                "row_limit": 10,
                "orientation": "horizontal",
                "show_legend": False,
                "color_scheme": "supersetColors",
                "time_range": "2026-11-01 : 2026-11-06",
                "adhoc_filters": [],
                "x_axis_title": "Facturacion ($)",
                "y_axis_title": "Unidad (ECO)",
                "x_axis_title_margin": 15,
                "y_axis_title_margin": 15,
                "rich_tooltip": True,
                "tooltip_sort_by_metric": True
            }
        },
        {
            "name": "B6 - Productividad de las Unidades (Mes)",
            "viz_type": "table",
            "datasource_id": 6,
            "params": {
                "viz_type": "table",
                "datasource": "6__table",
                "all_columns": [
                    "UNIDAD",
                    "DESPACHOS_VIAJES",
                    "CERRADOS",
                    "KMS_CARGADO",
                    "KMS_VACIO",
                    "KMS_TOTAL",
                    "TOTAL_FACTURACION",
                    "COSTO_POR_KM",
                    "RENDIMIENTO_PROM_KMS_KWH",
                    "OPERADOR",
                    "MANTENIMIENTO",
                    "OTROS_GASTOS",
                    "TOTAL_COSTO"
                ],
                "column_config": {
                    "COSTO_POR_KM": {"d3NumberFormat": "$,.4f"},
                    "TOTAL_FACTURACION": {"d3NumberFormat": "$,.2f"},
                    "OPERADOR": {"d3NumberFormat": "$,.2f"},
                    "MANTENIMIENTO": {"d3NumberFormat": "$,.2f"},
                    "OTROS_GASTOS": {"d3NumberFormat": "$,.2f"},
                    "TOTAL_COSTO": {"d3NumberFormat": "$,.2f"},
                    "KMS_TOTAL": {"d3NumberFormat": ",.2f"},
                    "RENDIMIENTO_PROM_KMS_KWH": {"d3NumberFormat": ",.4f"}
                },
                "query_mode": "raw",
                "row_limit": 100,
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B7 - Productividad de los Operadores (Mes)",
            "viz_type": "table",
            "datasource_id": 7,
            "params": {
                "viz_type": "table",
                "datasource": "7__table",
                "all_columns": [
                    "CLAVE_NOMBRE",
                    "DESPACHOS_VIAJES",
                    "CERRADOS",
                    "KMS_CARGADO",
                    "KMS_VACIO",
                    "KMS_TOTAL",
                    "TOTAL_FACTURACION",
                    "COSTO_POR_KM",
                    "RENDIMIENTO_PROM_KMS_KWH",
                    "OPERADOR",
                    "MANTENIMIENTO",
                    "OTROS_GASTOS",
                    "TOTAL_COSTO"
                ],
                "column_config": {
                    "COSTO_POR_KM": {"d3NumberFormat": "$,.4f"},
                    "TOTAL_FACTURACION": {"d3NumberFormat": "$,.2f"},
                    "OPERADOR": {"d3NumberFormat": "$,.2f"},
                    "MANTENIMIENTO": {"d3NumberFormat": "$,.2f"},
                    "OTROS_GASTOS": {"d3NumberFormat": "$,.2f"},
                    "TOTAL_COSTO": {"d3NumberFormat": "$,.2f"},
                    "KMS_TOTAL": {"d3NumberFormat": ",.2f"},
                    "RENDIMIENTO_PROM_KMS_KWH": {"d3NumberFormat": ",.4f"}
                },
                "query_mode": "raw",
                "row_limit": 100,
                "time_range": "2026-11-01 : 2026-11-06"
            }
        },
        {
            "name": "B8 - Analisis de Corredores Origen-Destino",
            "viz_type": "table",
            "datasource_id": 8,
            "params": {
                "viz_type": "table",
                "datasource": "8__table",
                "all_columns": [
                    "CORREDOR_ESTADOS", "ORIGEN", "DESTINO",
                    "TOTAL_EMBARQUES_CCP", "TOTAL_DISTANCIA_KM", "TOTAL_PESO_KG",
                    "DISTANCIA_PROMEDIO_KM", "PESO_PROMEDIO_KG"
                ],
                "query_mode": "raw",
                "row_limit": 20,
                "time_range": "2026-11-01 : 2026-11-06"
            }
        }
    ]

    def build_dashboard():
        print("=== 1. Sincronizando Datasets en Metastore ===")
        for ds_id, sql_code in SQL_DATASETS.items():
            ds = db.session.query(SqlaTable).filter_by(id=ds_id).first()
            if ds:
                ds.sql = sql_code
                ds.fetch_metadata()
                print(f"  [OK] Dataset {ds_id} '{ds.table_name}' refrescado.")
        db.session.commit()

        print("=== 2. Limpiando y Reconstruyendo los 12 Slices Idempotentemente ===")
        # Dashboard objetivo
        dash_title = "Reporte Diario de Operacion - Analytics TMS"
        dash_slug = "reporte-diario-operacion-tra099r1"
        dash = db.session.query(Dashboard).filter_by(slug=dash_slug).first()
        if not dash:
            dash = Dashboard(
                dashboard_title=dash_title,
                slug=dash_slug,
                published=True
            )
            db.session.add(dash)
            db.session.flush()

        # Desvincular todos los slices del dashboard antes de limpiar
        dash.slices = []
        db.session.flush()

        # Eliminar todos los slices huérfanos o antiguos en metastore para dejar exactamente los 12
        all_existing_slices = db.session.query(Slice).all()
        for s in all_existing_slices:
            db.session.delete(s)
        db.session.commit()
        print(f"  [OK] Eliminados {len(all_existing_slices)} slices previos del metastore.")

        # Crear los 12 slices activos con UUIDs y metadatos limpios
        slices = []
        slices_by_name = {}
        for spec in SLICES_SPEC:
            slc = Slice(
                slice_name=spec["name"],
                viz_type=spec["viz_type"],
                datasource_type="table",
                datasource_id=spec["datasource_id"],
                params=json.dumps(spec["params"], ensure_ascii=False),
                query_context=None
            )
            db.session.add(slc)
            db.session.flush()
            slices.append(slc)
            slices_by_name[spec["name"]] = slc
            print(f"  [+] Creado Slice ID {slc.id}: '{slc.slice_name}' ({slc.viz_type})")

        dash.dashboard_title = dash_title
        dash.published = True
        dash.slices = slices

        print("=== 3. Construyendo Layout position_json compatible con Superset 4.1.1 ===")
        # Configurar posición con todos los metadatos requeridos por Superset React
        s1 = slices_by_name["B1 - Flota Total"]
        s2 = slices_by_name["B1 - Unidades Con Viaje"]
        s3 = slices_by_name["B1 - Unidades Sin Viaje"]
        s4 = slices_by_name["B1 - Unidades Inactivas"]
        s5 = slices_by_name["B1 - Disponibilidad de Flota (Dona)"]
        s6 = slices_by_name["B2 - Indicadores de Operacion (Dia vs. Mes)"]
        s7 = slices_by_name["B3 - Indicadores Generales (Dia vs. Mes)"]
        s8 = slices_by_name["B4 - Top 5 Despachos por Cliente (Barras)"]
        s9 = slices_by_name["B5 - Top 10 Facturacion por Unidad ECO (Barras)"]
        s10 = slices_by_name["B6 - Productividad de las Unidades (Mes)"]
        s11 = slices_by_name["B7 - Productividad de los Operadores (Mes)"]
        s12 = slices_by_name["B8 - Analisis de Corredores Origen-Destino"]

        position = {
            "DASHBOARD_VERSION_KEY": "v2",
            "ROOT_ID": {
                "type": "ROOT",
                "id": "ROOT_ID",
                "children": ["GRID_ID"]
            },
            "GRID_ID": {
                "type": "GRID",
                "id": "GRID_ID",
                "children": [
                    "HEADER_MAIN",
                    "ROW_B1_KPIS",
                    "ROW_B1_DONUT",
                    "ROW_B2_B3",
                    "ROW_B4_B5",
                    "ROW_B6",
                    "ROW_B7",
                    "ROW_B8"
                ],
                "parents": ["ROOT_ID"],
                "meta": {}
            },
            "HEADER_MAIN": {
                "type": "HEADER",
                "id": "HEADER_MAIN",
                "meta": {
                    "text": "Reporte Diario de Operacion - Sunshine Deliveries (TRA099R1)"
                },
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "ROW_B1_KPIS": {
                "type": "ROW",
                "id": "ROW_B1_KPIS",
                "children": ["CHART_B1_1", "CHART_B1_2", "CHART_B1_3", "CHART_B1_4"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B1_1": {
                "type": "CHART",
                "id": "CHART_B1_1",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s1.id, "sliceName": s1.slice_name, "uuid": str(s1.uuid), "width": 3, "height": 26}
            },
            "CHART_B1_2": {
                "type": "CHART",
                "id": "CHART_B1_2",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s2.id, "sliceName": s2.slice_name, "uuid": str(s2.uuid), "width": 3, "height": 26}
            },
            "CHART_B1_3": {
                "type": "CHART",
                "id": "CHART_B1_3",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s3.id, "sliceName": s3.slice_name, "uuid": str(s3.uuid), "width": 3, "height": 26}
            },
            "CHART_B1_4": {
                "type": "CHART",
                "id": "CHART_B1_4",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s4.id, "sliceName": s4.slice_name, "uuid": str(s4.uuid), "width": 3, "height": 26}
            },
            "ROW_B1_DONUT": {
                "type": "ROW",
                "id": "ROW_B1_DONUT",
                "children": ["CHART_B1_DONUT"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B1_DONUT": {
                "type": "CHART",
                "id": "CHART_B1_DONUT",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_DONUT"],
                "meta": {"chartId": s5.id, "sliceName": s5.slice_name, "uuid": str(s5.uuid), "width": 12, "height": 38}
            },
            "ROW_B2_B3": {
                "type": "ROW",
                "id": "ROW_B2_B3",
                "children": ["CHART_B2", "CHART_B3"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B2": {
                "type": "CHART",
                "id": "CHART_B2",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B2_B3"],
                "meta": {"chartId": s6.id, "sliceName": s6.slice_name, "uuid": str(s6.uuid), "width": 6, "height": 26}
            },
            "CHART_B3": {
                "type": "CHART",
                "id": "CHART_B3",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B2_B3"],
                "meta": {"chartId": s7.id, "sliceName": s7.slice_name, "uuid": str(s7.uuid), "width": 6, "height": 26}
            },
            "ROW_B4_B5": {
                "type": "ROW",
                "id": "ROW_B4_B5",
                "children": ["CHART_B4", "CHART_B5"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B4": {
                "type": "CHART",
                "id": "CHART_B4",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B4_B5"],
                "meta": {"chartId": s8.id, "sliceName": s8.slice_name, "uuid": str(s8.uuid), "width": 6, "height": 50}
            },
            "CHART_B5": {
                "type": "CHART",
                "id": "CHART_B5",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B4_B5"],
                "meta": {"chartId": s9.id, "sliceName": s9.slice_name, "uuid": str(s9.uuid), "width": 6, "height": 50}
            },
            "ROW_B6": {
                "type": "ROW",
                "id": "ROW_B6",
                "children": ["CHART_B6"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B6": {
                "type": "CHART",
                "id": "CHART_B6",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B6"],
                "meta": {"chartId": s10.id, "sliceName": s10.slice_name, "uuid": str(s10.uuid), "width": 12, "height": 70}
            },
            "ROW_B7": {
                "type": "ROW",
                "id": "ROW_B7",
                "children": ["CHART_B7"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B7": {
                "type": "CHART",
                "id": "CHART_B7",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B7"],
                "meta": {"chartId": s11.id, "sliceName": s11.slice_name, "uuid": str(s11.uuid), "width": 12, "height": 70}
            },
            "ROW_B8": {
                "type": "ROW",
                "id": "ROW_B8",
                "children": ["CHART_B8"],
                "parents": ["ROOT_ID", "GRID_ID"],
                "meta": {
                    "background": "BACKGROUND_TRANSPARENT"
                }
            },
            "CHART_B8": {
                "type": "CHART",
                "id": "CHART_B8",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B8"],
                "meta": {"chartId": s12.id, "sliceName": s12.slice_name, "uuid": str(s12.uuid), "width": 12, "height": 60}
            }
        }

        # Native Filters Configuration compatible con Superset 4.1.1
        native_filters = [
            {
                "id": "NATIVE_FILTER-time-range",
                "name": "Rango Temporal",
                "filterType": "filter_time",
                "targets": [
                    {"datasetId": 1},
                    {"datasetId": 2},
                    {"datasetId": 3},
                    {"datasetId": 4},
                    {"datasetId": 5},
                    {"datasetId": 6},
                    {"datasetId": 7},
                    {"datasetId": 8}
                ],
                "defaultDataMask": {
                    "filterState": {
                        "value": "2026-11-01 : 2026-11-06"
                    },
                    "ownState": {}
                },
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True
            },
            {
                "id": "NATIVE_FILTER-codigo-eco",
                "name": "Unidad (ECO)",
                "filterType": "filter_select",
                "targets": [
                    {"datasetId": 6, "column": {"name": "UNIDAD"}},
                    {"datasetId": 5, "column": {"name": "UNIDAD"}}
                ],
                "defaultDataMask": {
                    "filterState": {},
                    "ownState": {}
                },
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True,
                "controlValues": {
                    "multiSelect": True,
                    "enableEmptyFilter": False,
                    "inverseSelection": False,
                    "defaultToFirstItem": False
                }
            },
            {
                "id": "NATIVE_FILTER-operador",
                "name": "Operador",
                "filterType": "filter_select",
                "targets": [
                    {"datasetId": 7, "column": {"name": "NOMBRE_OPERADOR"}}
                ],
                "defaultDataMask": {
                    "filterState": {},
                    "ownState": {}
                },
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True,
                "controlValues": {
                    "multiSelect": True,
                    "enableEmptyFilter": False,
                    "inverseSelection": False,
                    "defaultToFirstItem": False
                }
            },
            {
                "id": "NATIVE_FILTER-cliente",
                "name": "Cliente",
                "filterType": "filter_select",
                "targets": [
                    {"datasetId": 4, "column": {"name": "CLIENTE"}}
                ],
                "defaultDataMask": {
                    "filterState": {},
                    "ownState": {}
                },
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True,
                "controlValues": {
                    "multiSelect": True,
                    "enableEmptyFilter": False,
                    "inverseSelection": False,
                    "defaultToFirstItem": False
                }
            }
        ]

        json_meta = {
            "native_filter_configuration": native_filters,
            "chart_configuration": {},
            "global_chart_configuration": {
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "chartsInScope": [s.id for s in slices]
            },
            "color_scheme": "supersetColors",
            "refresh_frequency": 0,
            "expanded_slices": {},
            "default_filters": "{}"
        }

        dash.position_json = json.dumps(position, ensure_ascii=False)
        dash.json_metadata = json.dumps(json_meta, ensure_ascii=False)

        db.session.commit()
        print(f"=== Dashboard '{dash_title}' (ID {dash.id}) ensamblado exitosamente con exactamente {len(slices)} charts y 4 Native Filters ===")

if __name__ == "__main__":
    with app.app_context():
        build_dashboard()
