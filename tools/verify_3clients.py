"""
Verificación de métricas filtradas por 3 clientes para B2, B3, B5, B6 y B7
"""
from jinja2 import Environment
from pathlib import Path
from superset.app import create_app

app = create_app()
with app.app_context():
    from superset import db
    from superset.models.core import Database

    three_clients = [
        'PROCTER & GAMBLE MANUFACTURING MEXICO',
        'ALIMENTOS PROCESADOS DEL CENTRO',
        'ABARROTES Y CONSUMO NACIONAL'
    ]

    env = Environment()
    def where_in_filter(vals):
        formatted = ["'" + str(v).replace("'", "''") + "'" for v in vals]
        return "(" + ", ".join(formatted) + ")"
    env.filters["where_in"] = where_in_filter

    db_obj = db.session.query(Database).filter_by(database_name="Analytics_TMS_Oracle").first()
    
    datasets = [
        (2, "ds_02_operacion_dia_mes.sql", "B2 - Indicadores de Operacion (Dia vs. Mes)"),
        (3, "ds_03_generales_dia_mes.sql", "B3 - Indicadores Generales (Dia vs. Mes)"),
        (5, "ds_05_facturacion_top10_eco.sql", "B5 - Top 10 Facturacion por Unidad ECO (Barras)"),
        (6, "ds_06_productividad_unidades.sql", "B6 - Productividad de las Unidades (Mes)"),
        (7, "ds_07_productividad_operadores.sql", "B7 - Productividad de los Operadores (Mes)")
    ]

    print("================================================================================")
    print("  RESULTADOS CONSOLIDADOS CON FILTRO MULTI-VALOR DE 3 CLIENTES (01-06 NOV)")
    print("  Clientes: P&G, Alimentos Procesados del Centro, Abarrotes y Consumo Nacional")
    print("================================================================================")

    with db_obj.get_sqla_engine() as engine:
        with engine.connect() as conn:
            for ds_id, filename, chart_title in datasets:
                raw_sql = Path(f"/app/assets/datasets/{filename}").read_text(encoding="utf-8")
                t = env.from_string(raw_sql)
                rendered = t.render(
                    from_dttm="2026-11-01 00:00:00",
                    to_dttm="2026-11-06 23:59:59",
                    filter_values=lambda x: three_clients if x in ("CLIENTE", "RAZON_SOCIAL") else []
                )
                rows = conn.execute(rendered).fetchall()
                print(f"\n--- {chart_title} ({filename}) | Total Filas: {len(rows)} ---")
                if ds_id in (2, 3):
                    row_dict = dict(rows[0])
                    for k, v in row_dict.items():
                        print(f"    {k:28} : {v}")
                elif ds_id == 5:
                    print(f"    Top 5 ECOs (de {len(rows)}):")
                    for r in rows[:5]:
                        rd = {k.upper(): v for k, v in dict(r).items()}
                        print(f"      Unidad: {rd['UNIDAD']:6} | Facturacion: ${rd['TOTAL_FACTURACION']:>12,.2f} | Facturas: {rd['TOTAL_FACTURAS']}")
                elif ds_id in (6, 7):
                    dim_col = "UNIDAD" if ds_id == 6 else "CLAVE_NOMBRE"
                    print(f"    Primeras 3 filas (de {len(rows)}):")
                    for r in rows[:3]:
                        rd = {k.upper(): v for k, v in dict(r).items()}
                        print(f"      {rd[dim_col]:35} | Despachos: {rd['DESPACHOS_VIAJES']:2} | Facturacion: ${rd['TOTAL_FACTURACION']:>10,.2f} | Kms: {rd['KMS_TOTAL']:>8,.2f} | Costo: ${rd['TOTAL_COSTO']:>9,.2f}")
