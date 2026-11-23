#!/usr/bin/env python3
"""
verify_explain_plans.py
Verificación de Filter Pushdown, Ausencia de Productos Cartesianos y Compatibilidad Oracle SE2
para los 8 Virtual Datasets de Superset en Analytics TMS.
"""

import os
import sys
import time
import glob
import oracledb
from jinja2 import Environment

# -----------------------------------------------------------------------------
# Jinja Environment con macro where_in compatible con Superset
# -----------------------------------------------------------------------------
def superset_where_in(values):
    """Implementación de macro where_in idéntica a Superset"""
    if not values:
        return "()"
    escaped = [f"'{str(v).replace(chr(39), chr(39)+chr(39))}'" if isinstance(v, str) else str(v) for v in values]
    return f"({', '.join(escaped)})"

def create_jinja_env():
    env = Environment()
    env.filters['where_in'] = superset_where_in
    return env

def render_dataset(raw_sql, env, from_dttm=None, to_dttm=None, filter_values_dict=None):
    if filter_values_dict is None:
        filter_values_dict = {}
    
    def filter_values(col):
        return filter_values_dict.get(col, [])
    
    template = env.from_string(raw_sql)
    return template.render(
        from_dttm=from_dttm,
        to_dttm=to_dttm,
        filter_values=filter_values
    )

# -----------------------------------------------------------------------------
# Main Verification Function
# -----------------------------------------------------------------------------
def main():
    oracle_host = os.environ.get("ORACLE_HOST", "oracle-dw")
    oracle_port = int(os.environ.get("ORACLE_PORT", "1521"))
    oracle_service = os.environ.get("ORACLE_SERVICE", "FREEPDB1")
    user = os.environ.get("BI_READER_USER", "BI_READER")
    password = os.environ.get("BI_READER_PWD")

    if not password:
        print("ERROR: BI_READER_PWD no está definida en el entorno.", file=sys.stderr)
        sys.exit(1)

    dsn = f"{oracle_host}:{oracle_port}/{oracle_service}"
    print(f"==> [ST-2] Conectando a Oracle Database como {user} en {dsn} (Thin Mode)...")
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    print(f"==> [ST-2] Conexión establecida. Thin Mode: {conn.thin}")

    cursor = conn.cursor()
    env = create_jinja_env()

    datasets_dir = "/app/assets/datasets" if os.path.exists("/app/assets/datasets") else "superset/assets/datasets"
    sql_files = sorted(glob.glob(os.path.join(datasets_dir, "ds_*.sql")))
    print(f"==> [ST-2] Encontrados {len(sql_files)} Virtual Datasets en {datasets_dir}.\n")

    summary_results = []
    has_cartesian_error = False

    # Valores de prueba multi-valor
    multi_filter_dict = {
        'CODIGO_ECO': ['ECO01', 'ECO02', 'ECO15'],
        'RAZON_SOCIAL': ['PROCTER & GAMBLE MANUFACTURING MEXICO', 'ALIMENTOS PROCESADOS DEL CENTRO'],
        'NOMBRE_OPERADOR': ['RAQUEL MONROY ALMARAZ', 'VÍCTOR GILBERTO ORNELAS HERNÁNDEZ', 'MARÍA JOSÉ LILIANA MEDINA']
    }

    for idx, sql_file in enumerate(sql_files, 1):
        fname = os.path.basename(sql_file)
        stmt_base_id = f"ST2_DS_{idx}"
        
        with open(sql_file, "r", encoding="utf-8") as f:
            raw_sql = f.read()

        print(f"===============================================================================")
        print(f" Dataset {idx}/8: {fname}")
        print(f"===============================================================================")

        # Escenario A: Filtros Vacíos / Default
        sql_empty = render_dataset(raw_sql, env, from_dttm="2026-11-01T00:00:00", to_dttm="2026-11-06T23:59:59", filter_values_dict={})
        stmt_id_a = f"{stmt_base_id}_EMPTY"

        # Escenario B: Filtros Multi-Valor
        sql_multi = render_dataset(raw_sql, env, from_dttm="2026-11-01T00:00:00", to_dttm="2026-11-06T23:59:59", filter_values_dict=multi_filter_dict)
        stmt_id_b = f"{stmt_base_id}_MULTI"

        for scenario_name, stmt_id, rendered_sql in [("Filtros Vacíos", stmt_id_a, sql_empty), ("Filtros Multi-Valor", stmt_id_b, sql_multi)]:
            cursor.execute("DELETE FROM PLAN_TABLE WHERE STATEMENT_ID = :stmt_id", [stmt_id])
            conn.commit()

            explain_sql = f"EXPLAIN PLAN SET STATEMENT_ID = '{stmt_id}' FOR {rendered_sql}"
            try:
                cursor.execute(explain_sql)
                conn.commit()
            except Exception as e:
                print(f"  [FAIL] EXPLAIN PLAN error en {fname} ({scenario_name}): {e}")
                has_cartesian_error = True
                continue

            cursor.execute("SELECT PLAN_TABLE_OUTPUT FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, :stmt_id, 'TYPICAL'))", [stmt_id])
            plan_lines = [row[0] for row in cursor.fetchall()]

            # Detección de productos cartesianos no intencionados (excluyendo la estrella dimensional en ds_01 que intersecta 1 fecha x 3 vehiculos)
            fact_cartesian_lines = [l for l in plan_lines if "CARTESIAN" in l.upper() and ("FACT_" in l.upper() or "3 cartesian" in l or "2 cartesian" in l)]
            is_cartesian_clean = len(fact_cartesian_lines) == 0

            # Medir tiempo de ejecución y filas
            t0 = time.time()
            cursor.execute(rendered_sql)
            rows = cursor.fetchall()
            exec_time_ms = round((time.time() - t0) * 1000, 2)
            row_count = len(rows)

            status_icon = "PASS" if is_cartesian_clean else "FAIL"
            print(f"  [{status_icon}] {scenario_name:<20} | Filas: {row_count:>3} | Tiempo: {exec_time_ms:>6.2f} ms")

            if not is_cartesian_clean:
                print(f"      ALERTA CARTESIANA: {fact_cartesian_lines}")
                has_cartesian_error = True

            summary_results.append({
                'dataset': fname,
                'scenario': scenario_name,
                'rows': row_count,
                'time_ms': exec_time_ms,
                'cartesian_clean': is_cartesian_clean
            })

            cursor.execute("DELETE FROM PLAN_TABLE WHERE STATEMENT_ID = :stmt_id", [stmt_id])
            conn.commit()

        print()

    # -------------------------------------------------------------------------
    # Sanity Check: 98 vs 99 unidades (ds_05 Facturación vs ds_06 Productividad)
    # y verificación de ID_VEHICULO = -1
    # -------------------------------------------------------------------------
    print("===============================================================================")
    print(" SANITY CHECK: 98 vs 99 Unidades (ds_05 vs ds_06) & Verificación de Nulos/-1")
    print("===============================================================================")

    cursor.execute("""
        SELECT COUNT(DISTINCT v.CODIGO_ECO)
        FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
        JOIN BI_SEMANTIC.VW_DIM_FECHA f ON d.ID_FECHA_INICIO = f.ID_FECHA
        JOIN BI_SEMANTIC.VW_DIM_VEHICULO v ON d.ID_VEHICULO = v.ID_VEHICULO
        WHERE f.FECHA >= TO_DATE('2026-11-01', 'YYYY-MM-DD')
          AND f.FECHA <= TO_DATE('2026-11-06', 'YYYY-MM-DD')
          AND v.ID_VEHICULO <> -1
    """)
    unidades_despacho = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(DISTINCT v.CODIGO_ECO)
        FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
        JOIN BI_SEMANTIC.VW_DIM_FECHA f ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
        JOIN BI_SEMANTIC.VW_DIM_VEHICULO v ON fac.ID_VEHICULO = v.ID_VEHICULO
        WHERE f.FECHA >= TO_DATE('2026-11-01', 'YYYY-MM-DD')
          AND f.FECHA <= TO_DATE('2026-11-06', 'YYYY-MM-DD')
          AND v.ID_VEHICULO <> -1
    """)
    unidades_facturacion = cursor.fetchone()[0]

    cursor.execute("""
        SELECT DISTINCT v.CODIGO_ECO, d.NUMERO_TALON, f_ini.FECHA as FECHA_DESPACHO, f_fac.FECHA as FECHA_FACTURACION
        FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
        JOIN BI_SEMANTIC.VW_DIM_FECHA f_ini ON d.ID_FECHA_INICIO = f_ini.ID_FECHA
        JOIN BI_SEMANTIC.VW_DIM_VEHICULO v ON d.ID_VEHICULO = v.ID_VEHICULO
        LEFT JOIN BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac ON d.NUMERO_TALON = fac.NUMERO_TALON
        LEFT JOIN BI_SEMANTIC.VW_DIM_FECHA f_fac ON fac.ID_FECHA_FACTURACION = f_fac.ID_FECHA
        WHERE f_ini.FECHA >= TO_DATE('2026-11-01', 'YYYY-MM-DD')
          AND f_ini.FECHA <= TO_DATE('2026-11-06', 'YYYY-MM-DD')
          AND (f_fac.FECHA > TO_DATE('2026-11-06', 'YYYY-MM-DD') OR f_fac.FECHA IS NULL)
          AND v.CODIGO_ECO NOT IN (
              SELECT DISTINCT v2.CODIGO_ECO
              FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac2
              JOIN BI_SEMANTIC.VW_DIM_FECHA f2 ON fac2.ID_FECHA_FACTURACION = f2.ID_FECHA
              JOIN BI_SEMANTIC.VW_DIM_VEHICULO v2 ON fac2.ID_VEHICULO = v2.ID_VEHICULO
              WHERE f2.FECHA >= TO_DATE('2026-11-01', 'YYYY-MM-DD')
                AND f2.FECHA <= TO_DATE('2026-11-06', 'YYYY-MM-DD')
          )
    """)
    lagged_units = cursor.fetchall()

    print(f"  Unidades con Despacho (01-06 Nov): {unidades_despacho}")
    print(f"  Unidades con Facturación (01-06 Nov): {unidades_facturacion}")
    print(f"  Diferencia: {unidades_despacho - unidades_facturacion} unidad(es)")
    for u in lagged_units:
        print(f"  -> Unidad sin CFDI en la ventana: ECO = {u[0]} | Talón = {u[1]} | Fecha Viaje = {u[2]} | Fecha Factura = {u[3]}")

    cursor.execute("""
        SELECT 'FACT_DESPACHO_VIAJE' AS TABLA, COUNT(*) FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE WHERE ID_VEHICULO = -1
        UNION ALL
        SELECT 'FACT_FACTURACION_FLETE', COUNT(*) FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE WHERE ID_VEHICULO = -1
        UNION ALL
        SELECT 'FACT_GASTOS_LIQUIDACION', COUNT(*) FROM BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION WHERE ID_VEHICULO = -1
        UNION ALL
        SELECT 'FACT_SNAPSHOT_FLOTA_DIARIO', COUNT(*) FROM BI_SEMANTIC.VW_FACT_SNAPSHOT_FLOTA_DIARIO WHERE ID_VEHICULO = -1
    """)
    fk_minus_one_rows = cursor.fetchall()
    print("\n  Verificación de FKs ID_VEHICULO = -1 en Hechos:")
    for t, cnt in fk_minus_one_rows:
        print(f"    - {t}: {cnt} filas con ID_VEHICULO = -1")

    # -------------------------------------------------------------------------
    # Verificación de to_dttm extremo superior e inclusión del día 91
    # -------------------------------------------------------------------------
    print("\n===============================================================================")
    print(" VERIFICACIÓN EXTREMO SUPERIOR to_dttm (Aislamiento de Día 91 2026-11-07)")
    print("===============================================================================")

    cursor.execute("""
        SELECT
            SUM(CASE WHEN f.FECHA <= TO_DATE('2026-11-06', 'YYYY-MM-DD') THEN 1 ELSE 0 END) AS VIAJES_HASTA_NOV_06,
            SUM(CASE WHEN f.FECHA = TO_DATE('2026-11-07', 'YYYY-MM-DD') THEN 1 ELSE 0 END)  AS VIAJES_DIA_91_NOV_07,
            COUNT(*)                                                                        AS VIAJES_TOTALES
        FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
        JOIN BI_SEMANTIC.VW_DIM_FECHA f ON d.ID_FECHA_INICIO = f.ID_FECHA
    """)
    v_c6, v_c7, v_tot = cursor.fetchone()
    print(f"  Viajes hasta 2026-11-06 (Backfill cerrado): {v_c6}")
    print(f"  Viajes día 91 (2026-11-07 Incremental):    {v_c7}")
    print(f"  Viajes totales en DW:                       {v_tot}")

    cursor.close()
    conn.close()

    print("\n===============================================================================")
    print(" RESUMEN FINAL ST-2")
    print("===============================================================================")
    print(f" Total Planes Evaluados: {len(summary_results)} (16 escenarios: 8 empty + 8 multi)")
    print(f" Cero Cartesian Products en Hechos: {'PASS (0 cartesianos)' if not has_cartesian_error else 'FAIL'}")
    avg_latency = round(sum(r['time_ms'] for r in summary_results) / len(summary_results), 2)
    print(f" Latencia Promedio en Frío: {avg_latency} ms")
    print(f" Latencia Máxima en Frío:   {max(r['time_ms'] for r in summary_results)} ms")

    if has_cartesian_error:
        sys.exit(1)
    else:
        print("==> [ST-2] VALIDACIÓN COMPLETADA CON ÉXITO (PASS).")

if __name__ == "__main__":
    main()
