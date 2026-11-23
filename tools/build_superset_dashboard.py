"""
Script para maquetar de forma reproducible el Dashboard TRA099R1 en Apache Superset
"Reporte Diario de Operación — Analytics TMS" cubriendo los 7 bloques funcionales,
Gráfica de Dona (Bloque 1), Gráficas de Barras (Bloques 4 y 5), Tablas de Productividad (Bloques 6 y 7)
y los 4 Native Filters alineados con Jinja pushdown.
"""
import json
from pathlib import Path
from superset.app import create_app

app = create_app()

with app.app_context():
    from superset import db
    from superset.models.slice import Slice
    from superset.models.dashboard import Dashboard
    from superset.connectors.sqla.models import SqlaTable

    # SQL de los 8 datasets con soporte dual de alias para Native Filters
    SQL_DATASETS = {
        1: """-- ds_01_flota_diaria.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}

SELECT
    f.FECHA                                                    AS FECHA_CORTE,
    CASE 
        WHEN s.UNIDAD_CON_VIAJE_INDICADOR = 1 THEN 'Con Viaje'
        WHEN s.UNIDAD_SIN_VIAJE_INDICADOR = 1 THEN 'Sin Viaje'
        ELSE 'Inactivas'
    END                                                        AS ESTADO_FLOTA,
    COUNT(s.ID_VEHICULO)                                       AS CANTIDAD_UNIDADES,
    ROUND(COUNT(s.ID_VEHICULO) * 100.0 / NULLIF(SUM(COUNT(s.ID_VEHICULO)) OVER (), 0), 2) AS PORCENTAJE_FLOTA,
    SUM(s.KMS_RECORRIDOS_DIA)                                  AS TOTAL_KMS_DIA,
    SUM(s.KWH_CONSUMO_DIA)                                     AS TOTAL_KWH_DIA
FROM BI_SEMANTIC.VW_FACT_SNAPSHOT_FLOTA_DIARIO s
JOIN BI_SEMANTIC.VW_DIM_FECHA f 
    ON s.ID_FECHA_CORTE = f.ID_FECHA
JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
    ON s.ID_VEHICULO = v.ID_VEHICULO
WHERE f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
  AND s.ID_VEHICULO <> -1
  {% if ecos %}
  AND v.CODIGO_ECO IN {{ ecos | where_in }}
  {% endif %}
GROUP BY
    f.FECHA,
    CASE 
        WHEN s.UNIDAD_CON_VIAJE_INDICADOR = 1 THEN 'Con Viaje'
        WHEN s.UNIDAD_SIN_VIAJE_INDICADOR = 1 THEN 'Sin Viaje'
        ELSE 'Inactivas'
    END
""",
        2: """-- ds_02_operacion_dia_mes.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_DESPACHOS AS (
    SELECT
        1                                                                                                      AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN d.CONTADOR_DESPACHO ELSE 0 END) AS DESPACHOS_DIA,
        SUM(d.CONTADOR_DESPACHO)                                                                               AS DESPACHOS_MES,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN d.CONTADOR_CERRADO ELSE 0 END)  AS CIERRES_DIA,
        SUM(d.CONTADOR_CERRADO)                                                                                AS CIERRES_MES
    FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON d.ID_FECHA_INICIO = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON d.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON d.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON d.ID_CLIENTE_ORIGEN = c.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
),
CTE_LIQUIDACIONES AS (
    SELECT
        1                                                                                                      AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') AND g.MONTO_CASETA > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END)   AS LIQ_CASETAS_DIA,
        SUM(CASE WHEN g.MONTO_CASETA > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END)                                                              AS LIQ_CASETAS_MES,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') AND g.MONTO_OPERADOR > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END) AS LIQ_OPERADOR_DIA,
        SUM(CASE WHEN g.MONTO_OPERADOR > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END)                                                            AS LIQ_OPERADOR_MES
    FROM BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION g
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON g.ID_FECHA_LIQUIDACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON g.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON g.ID_OPERADOR = o.ID_OPERADOR
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
),
CTE_CARTAPORTE AS (
    SELECT
        1                                                                                                     AS JOIN_KEY,
        COUNT(DISTINCT CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN cp.UUID_CCP END) AS CFDI_TRASLADO_DIA,
        COUNT(DISTINCT cp.UUID_CCP)                                                                           AS CFDI_TRASLADO_MES
    FROM BI_SEMANTIC.VW_FACT_LINEAS_CARGA_CARTAPORTE cp
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON cp.ID_FECHA_EMISION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON cp.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON cp.ID_CLIENTE_REMITENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
),
CTE_FACTURACION AS (
    SELECT
        1                                                                                                           AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN fac.CONTADOR_FACTURA ELSE 0 END) AS FACTURADOS_DIA,
        SUM(fac.CONTADOR_FACTURA)                                                                                AS FACTURADOS_MES
    FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON fac.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON fac.ID_CLIENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
)
SELECT
    NVL(d.DESPACHOS_DIA, 0)     AS DESPACHOS_DIA,
    NVL(d.DESPACHOS_MES, 0)     AS DESPACHOS_MES,
    NVL(d.CIERRES_DIA, 0)       AS CIERRES_DIA,
    NVL(d.CIERRES_MES, 0)       AS CIERRES_MES,
    NVL(l.LIQ_CASETAS_DIA, 0)   AS LIQ_CASETAS_DIA,
    NVL(l.LIQ_CASETAS_MES, 0)   AS LIQ_CASETAS_MES,
    NVL(l.LIQ_OPERADOR_DIA, 0)  AS LIQ_OPERADOR_DIA,
    NVL(l.LIQ_OPERADOR_MES, 0)  AS LIQ_OPERADOR_MES,
    NVL(cp.CFDI_TRASLADO_DIA, 0) AS CFDI_TRASLADO_DIA,
    NVL(cp.CFDI_TRASLADO_MES, 0) AS CFDI_TRASLADO_MES,
    NVL(fac.FACTURADOS_DIA, 0)   AS FACTURADOS_DIA,
    NVL(fac.FACTURADOS_MES, 0)   AS FACTURADOS_MES
FROM CTE_DESPACHOS d
JOIN CTE_LIQUIDACIONES l   ON d.JOIN_KEY = l.JOIN_KEY
JOIN CTE_CARTAPORTE cp     ON d.JOIN_KEY = cp.JOIN_KEY
JOIN CTE_FACTURACION fac   ON d.JOIN_KEY = fac.JOIN_KEY
""",
        3: """-- ds_03_generales_dia_mes.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_DESPACHOS_GEN AS (
    SELECT
        1                                                                                                          AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN d.KMS_TOTAL ELSE 0 END)           AS TOTAL_KMS_DIA,
        SUM(d.KMS_TOTAL)                                                                                           AS TOTAL_KMS_MES,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN d.KWH_CONSUMO_ENERGIA ELSE 0 END) AS TOTAL_KWH_DIA,
        SUM(d.KWH_CONSUMO_ENERGIA)                                                                                AS TOTAL_KWH_MES
    FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON d.ID_FECHA_INICIO = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON d.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON d.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON d.ID_CLIENTE_ORIGEN = c.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
),
CTE_GASTOS_GEN AS (
    SELECT
        1                                                                                                      AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN g.MONTO_CASETA ELSE 0 END)   AS PAGO_CASETAS_DIA,
        SUM(g.MONTO_CASETA)                                                                                   AS PAGO_CASETAS_MES,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN g.MONTO_OPERADOR ELSE 0 END) AS PAGO_OPERADORES_DIA,
        SUM(g.MONTO_OPERADOR)                                                                                 AS PAGO_OPERADORES_MES
    FROM BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION g
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON g.ID_FECHA_LIQUIDACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON g.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON g.ID_OPERADOR = o.ID_OPERADOR
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
),
CTE_FACTURACION_GEN AS (
    SELECT
        1                                                                                                                 AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN fac.IMPORTE_TOTAL_FACTURADO ELSE 0 END) AS FACTURADO_DIA,
        SUM(fac.IMPORTE_TOTAL_FACTURADO)                                                                                AS FACTURADO_MES
    FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON fac.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON fac.ID_CLIENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
)
SELECT
    NVL(d.TOTAL_KMS_DIA, 0)                                                      AS TOTAL_KMS_DIA,
    NVL(d.TOTAL_KMS_MES, 0)                                                      AS TOTAL_KMS_MES,
    ROUND(NVL(d.TOTAL_KMS_DIA, 0) / NULLIF(NVL(d.TOTAL_KWH_DIA, 0), 0), 2)       AS RENDIMIENTO_KMS_KWH_DIA,
    ROUND(NVL(d.TOTAL_KMS_MES, 0) / NULLIF(NVL(d.TOTAL_KWH_MES, 0), 0), 2)       AS RENDIMIENTO_KMS_KWH_MES,
    NVL(g.PAGO_CASETAS_DIA, 0)                                                   AS PAGO_CASETAS_DIA,
    NVL(g.PAGO_CASETAS_MES, 0)                                                   AS PAGO_CASETAS_MES,
    NVL(g.PAGO_OPERADORES_DIA, 0)                                                AS PAGO_OPERADORES_DIA,
    NVL(g.PAGO_OPERADORES_MES, 0)                                                AS PAGO_OPERADORES_MES,
    NVL(fac.FACTURADO_DIA, 0)                                                    AS FACTURADO_DIA,
    NVL(fac.FACTURADO_MES, 0)                                                    AS FACTURADO_MES
FROM CTE_DESPACHOS_GEN d
JOIN CTE_GASTOS_GEN g      ON d.JOIN_KEY = g.JOIN_KEY
JOIN CTE_FACTURACION_GEN fac ON d.JOIN_KEY = fac.JOIN_KEY
""",
        4: """-- ds_04_top5_clientes.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_CLIENTES AS (
    SELECT
        c.RAZON_SOCIAL                                                                                         AS CLIENTE,
        c.RFC_CLIENTE                                                                                          AS RFC,
        SUM(CASE WHEN f.FECHA = TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD') THEN d.CONTADOR_DESPACHO ELSE 0 END) AS DESPACHOS_DIA,
        SUM(d.CONTADOR_DESPACHO)                                                                               AS DESPACHOS_MES,
        SUM(d.KMS_TOTAL)                                                                                       AS KMS_MES
    FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON d.ID_FECHA_INICIO = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON d.ID_CLIENTE_ORIGEN = c.ID_CLIENTE
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON d.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON d.ID_OPERADOR = o.ID_OPERADOR
    WHERE f.FECHA >= TRUNC(TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD'), 'MM')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND c.ID_CLIENTE <> -1
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        c.RAZON_SOCIAL,
        c.RFC_CLIENTE
)
SELECT
    CLIENTE,
    RFC,
    DESPACHOS_DIA,
    DESPACHOS_MES,
    KMS_MES
FROM CTE_CLIENTES
ORDER BY
    DESPACHOS_MES DESC,
    DESPACHOS_DIA DESC
""",
        5: """-- ds_05_facturacion_top10_eco.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set fecha_inicio = from_dttm[:10] if from_dttm else '2026-11-01' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

SELECT
    v.CODIGO_ECO                                               AS UNIDAD,
    SUM(fac.IMPORTE_TOTAL_FACTURADO)                           AS TOTAL_FACTURACION,
    SUM(fac.CONTADOR_FACTURA)                                  AS TOTAL_FACTURAS,
    SUM(fac.IMPORTE_SUBTOTAL)                                  AS TOTAL_SUBTOTAL,
    SUM(fac.IMPORTE_IVA_TRASLADADO)                            AS TOTAL_IVA_TRASLADADO,
    SUM(fac.IMPORTE_IVA_RETENIDO)                              AS TOTAL_IVA_RETENIDO
FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
JOIN BI_SEMANTIC.VW_DIM_FECHA f 
    ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
    ON fac.ID_VEHICULO = v.ID_VEHICULO
JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
    ON fac.ID_CLIENTE = c.ID_CLIENTE
WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
  AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
  AND v.ID_VEHICULO <> -1
  {% if ecos %}
  AND v.CODIGO_ECO IN {{ ecos | where_in }}
  {% endif %}
  {% if clientes %}
  AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
  {% endif %}
GROUP BY
    v.CODIGO_ECO
ORDER BY
    TOTAL_FACTURACION DESC
""",
        6: """-- ds_06_productividad_unidades.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set fecha_inicio = from_dttm[:10] if from_dttm else '2026-11-01' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_DESPACHO AS (
    SELECT
        v.CODIGO_ECO,
        COUNT(d.ID_FACT_DESPACHO)                                  AS DESPACHOS_VIAJES,
        SUM(d.CONTADOR_CERRADO)                                     AS CERRADOS,
        SUM(d.KMS_CARGADO)                                          AS KMS_CARGADO,
        SUM(d.KMS_VACIO)                                            AS KMS_VACIO,
        SUM(d.KMS_TOTAL)                                            AS KMS_TOTAL,
        SUM(d.KWH_CONSUMO_ENERGIA)                                  AS KWH_CONSUMO_TOTAL
    FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON d.ID_FECHA_INICIO = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON d.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON d.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON d.ID_CLIENTE_ORIGEN = c.ID_CLIENTE
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND v.ID_VEHICULO <> -1
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        v.CODIGO_ECO
),
CTE_CARGA_CCP AS (
    SELECT
        cp.UUID_CCP,
        v.CODIGO_ECO,
        MAX(cp.DISTANCIA_DECLARADA_KM)                             AS DISTANCIA_CCP,
        SUM(cp.PESO_KG)                                            AS PESO_TOTAL_CCP
    FROM BI_SEMANTIC.VW_FACT_LINEAS_CARGA_CARTAPORTE cp
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON cp.ID_FECHA_EMISION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON cp.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON cp.ID_CLIENTE_REMITENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND v.ID_VEHICULO <> -1
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        cp.UUID_CCP,
        v.CODIGO_ECO
),
CTE_CARGA AS (
    SELECT
        CODIGO_ECO,
        SUM(DISTANCIA_CCP)                                         AS TOTAL_DISTANCIA_DECLARADA_KM,
        SUM(PESO_TOTAL_CCP)                                        AS TOTAL_PESO_DECLARADO_KG
    FROM CTE_CARGA_CCP
    GROUP BY
        CODIGO_ECO
),
CTE_FACTURACION AS (
    SELECT
        v.CODIGO_ECO,
        SUM(fac.IMPORTE_TOTAL_FACTURADO)                           AS TOTAL_FACTURACION,
        SUM(fac.CONTADOR_FACTURA)                                  AS TOTAL_FACTURAS
    FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON fac.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON fac.ID_CLIENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND v.ID_VEHICULO <> -1
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        v.CODIGO_ECO
),
CTE_GASTOS AS (
    SELECT
        v.CODIGO_ECO,
        SUM(g.MONTO_OPERADOR)                                      AS COSTO_OPERADOR,
        SUM(g.MONTO_MANTENIMIENTO)                                 AS COSTO_MANTENIMIENTO,
        SUM(g.MONTO_CASETA + g.MONTO_OTROS_GASTOS)                 AS OTROS_GASTOS,
        SUM(g.IMPORTE_GASTO)                                      AS TOTAL_COSTO
    FROM BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION g
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON g.ID_FECHA_LIQUIDACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON g.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON g.ID_OPERADOR = o.ID_OPERADOR
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND v.ID_VEHICULO <> -1
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
    GROUP BY
        v.CODIGO_ECO
),
CTE_DRILLACROSS AS (
    SELECT
        COALESCE(d.CODIGO_ECO, cg.CODIGO_ECO, fac.CODIGO_ECO, g.CODIGO_ECO) AS CODIGO_ECO,
        NVL(d.DESPACHOS_VIAJES, 0)                                 AS DESPACHOS_VIAJES,
        NVL(d.CERRADOS, 0)                                         AS CERRADOS,
        NVL(d.KMS_CARGADO, 0)                                      AS KMS_CARGADO,
        NVL(d.KMS_VACIO, 0)                                        AS KMS_VACIO,
        NVL(d.KMS_TOTAL, 0)                                        AS KMS_TOTAL,
        NVL(d.KWH_CONSUMO_TOTAL, 0)                                AS KWH_CONSUMO_TOTAL,
        NVL(cg.TOTAL_DISTANCIA_DECLARADA_KM, 0)                    AS TOTAL_DISTANCIA_DECLARADA_KM,
        NVL(cg.TOTAL_PESO_DECLARADO_KG, 0)                         AS TOTAL_PESO_DECLARADO_KG,
        NVL(fac.TOTAL_FACTURACION, 0)                              AS TOTAL_FACTURACION,
        NVL(fac.TOTAL_FACTURAS, 0)                                 AS TOTAL_FACTURAS,
        NVL(g.COSTO_OPERADOR, 0)                                   AS COSTO_OPERADOR,
        NVL(g.COSTO_MANTENIMIENTO, 0)                              AS COSTO_MANTENIMIENTO,
        NVL(g.OTROS_GASTOS, 0)                                     AS OTROS_GASTOS,
        NVL(g.TOTAL_COSTO, 0)                                      AS TOTAL_COSTO
    FROM CTE_DESPACHO d
    FULL OUTER JOIN CTE_CARGA cg
        ON d.CODIGO_ECO = cg.CODIGO_ECO
    FULL OUTER JOIN CTE_FACTURACION fac
        ON COALESCE(d.CODIGO_ECO, cg.CODIGO_ECO) = fac.CODIGO_ECO
    FULL OUTER JOIN CTE_GASTOS g
        ON COALESCE(d.CODIGO_ECO, cg.CODIGO_ECO, fac.CODIGO_ECO) = g.CODIGO_ECO
)
SELECT
    da.CODIGO_ECO                                                  AS UNIDAD,
    da.DESPACHOS_VIAJES                                            AS DESPACHOS_VIAJES,
    da.CERRADOS                                                    AS CERRADOS,
    da.KMS_CARGADO                                                 AS KMS_CARGADO,
    da.KMS_VACIO                                                   AS KMS_VACIO,
    da.KMS_TOTAL                                                   AS KMS_TOTAL,
    da.TOTAL_FACTURACION                                           AS TOTAL_FACTURACION,
    ROUND(da.TOTAL_FACTURACION / NULLIF(da.KMS_TOTAL, 0), 4)       AS COSTO_POR_KM,
    ROUND(da.KMS_TOTAL / NULLIF(da.KWH_CONSUMO_TOTAL, 0), 4)       AS RENDIMIENTO_PROM_KMS_KWH,
    da.COSTO_OPERADOR                                              AS OPERADOR,
    da.COSTO_MANTENIMIENTO                                         AS MANTENIMIENTO,
    da.OTROS_GASTOS                                                AS OTROS_GASTOS,
    da.TOTAL_COSTO                                                 AS TOTAL_COSTO,
    da.TOTAL_FACTURACION - da.TOTAL_COSTO                          AS MARGEN_OPERATIVO,
    da.TOTAL_DISTANCIA_DECLARADA_KM                                AS DISTANCIA_DECLARADA_KM,
    da.TOTAL_PESO_DECLARADO_KG                                     AS PESO_DECLARADO_KG
FROM CTE_DRILLACROSS da
ORDER BY
    da.TOTAL_FACTURACION DESC,
    da.KMS_TOTAL DESC
""",
        7: """-- ds_07_productividad_operadores.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set fecha_inicio = from_dttm[:10] if from_dttm else '2026-11-01' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_DESPACHO AS (
    SELECT
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR,
        COUNT(d.ID_FACT_DESPACHO)                                  AS DESPACHOS_VIAJES,
        SUM(d.CONTADOR_CERRADO)                                     AS CERRADOS,
        SUM(d.KMS_CARGADO)                                          AS KMS_CARGADO,
        SUM(d.KMS_VACIO)                                            AS KMS_VACIO,
        SUM(d.KMS_TOTAL)                                            AS KMS_TOTAL,
        SUM(d.KWH_CONSUMO_ENERGIA)                                  AS KWH_CONSUMO_TOTAL
    FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON d.ID_FECHA_INICIO = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON d.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON d.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON d.ID_CLIENTE_ORIGEN = c.ID_CLIENTE
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND o.ID_OPERADOR <> -1
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR
),
CTE_CARGA_CCP AS (
    SELECT
        cp.UUID_CCP,
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR,
        MAX(cp.DISTANCIA_DECLARADA_KM)                             AS DISTANCIA_CCP,
        SUM(cp.PESO_KG)                                            AS PESO_TOTAL_CCP
    FROM BI_SEMANTIC.VW_FACT_LINEAS_CARGA_CARTAPORTE cp
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON cp.ID_FECHA_EMISION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON cp.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON cp.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON cp.ID_CLIENTE_REMITENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND o.ID_OPERADOR <> -1
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        cp.UUID_CCP,
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR
),
CTE_CARGA AS (
    SELECT
        CODIGO_OPERADOR,
        NOMBRE_OPERADOR,
        SUM(DISTANCIA_CCP)                                         AS TOTAL_DISTANCIA_DECLARADA_KM,
        SUM(PESO_TOTAL_CCP)                                        AS TOTAL_PESO_DECLARADO_KG
    FROM CTE_CARGA_CCP
    GROUP BY
        CODIGO_OPERADOR,
        NOMBRE_OPERADOR
),
CTE_FACTURACION AS (
    SELECT
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR,
        SUM(fac.IMPORTE_TOTAL_FACTURADO)                           AS TOTAL_FACTURACION,
        SUM(fac.CONTADOR_FACTURA)                                  AS TOTAL_FACTURAS
    FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON fac.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON fac.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON fac.ID_CLIENTE = c.ID_CLIENTE
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND o.ID_OPERADOR <> -1
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR
),
CTE_GASTOS AS (
    SELECT
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR,
        SUM(g.MONTO_OPERADOR)                                      AS COSTO_OPERADOR,
        SUM(g.MONTO_MANTENIMIENTO)                                 AS COSTO_MANTENIMIENTO,
        SUM(g.MONTO_CASETA + g.MONTO_OTROS_GASTOS)                 AS OTROS_GASTOS,
        SUM(g.IMPORTE_GASTO)                                      AS TOTAL_COSTO
    FROM BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION g
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON g.ID_FECHA_LIQUIDACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o 
        ON g.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON g.ID_VEHICULO = v.ID_VEHICULO
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND o.ID_OPERADOR <> -1
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
    GROUP BY
        o.CODIGO_OPERADOR,
        o.NOMBRE_OPERADOR
),
CTE_DRILLACROSS AS (
    SELECT
        COALESCE(d.CODIGO_OPERADOR, cg.CODIGO_OPERADOR, fac.CODIGO_OPERADOR, g.CODIGO_OPERADOR) AS CODIGO_OPERADOR,
        COALESCE(d.NOMBRE_OPERADOR, cg.NOMBRE_OPERADOR, fac.NOMBRE_OPERADOR, g.NOMBRE_OPERADOR) AS NOMBRE_OPERADOR,
        NVL(d.DESPACHOS_VIAJES, 0)                                 AS DESPACHOS_VIAJES,
        NVL(d.CERRADOS, 0)                                         AS CERRADOS,
        NVL(d.KMS_CARGADO, 0)                                      AS KMS_CARGADO,
        NVL(d.KMS_VACIO, 0)                                        AS KMS_VACIO,
        NVL(d.KMS_TOTAL, 0)                                        AS KMS_TOTAL,
        NVL(d.KWH_CONSUMO_TOTAL, 0)                                AS KWH_CONSUMO_TOTAL,
        NVL(cg.TOTAL_DISTANCIA_DECLARADA_KM, 0)                    AS TOTAL_DISTANCIA_DECLARADA_KM,
        NVL(cg.TOTAL_PESO_DECLARADO_KG, 0)                         AS TOTAL_PESO_DECLARADO_KG,
        NVL(fac.TOTAL_FACTURACION, 0)                              AS TOTAL_FACTURACION,
        NVL(fac.TOTAL_FACTURAS, 0)                                 AS TOTAL_FACTURAS,
        NVL(g.COSTO_OPERADOR, 0)                                   AS COSTO_OPERADOR,
        NVL(g.COSTO_MANTENIMIENTO, 0)                              AS COSTO_MANTENIMIENTO,
        NVL(g.OTROS_GASTOS, 0)                                     AS OTROS_GASTOS,
        NVL(g.TOTAL_COSTO, 0)                                      AS TOTAL_COSTO
    FROM CTE_DESPACHO d
    FULL OUTER JOIN CTE_CARGA cg
        ON  d.CODIGO_OPERADOR = cg.CODIGO_OPERADOR
        AND d.NOMBRE_OPERADOR = cg.NOMBRE_OPERADOR
    FULL OUTER JOIN CTE_FACTURACION fac
        ON  COALESCE(d.CODIGO_OPERADOR, cg.CODIGO_OPERADOR) = fac.CODIGO_OPERADOR
        AND COALESCE(d.NOMBRE_OPERADOR, cg.NOMBRE_OPERADOR) = fac.NOMBRE_OPERADOR
    FULL OUTER JOIN CTE_GASTOS g
        ON  COALESCE(d.CODIGO_OPERADOR, cg.CODIGO_OPERADOR, fac.CODIGO_OPERADOR) = g.CODIGO_OPERADOR
        AND COALESCE(d.NOMBRE_OPERADOR, cg.NOMBRE_OPERADOR, fac.NOMBRE_OPERADOR) = g.NOMBRE_OPERADOR
)
SELECT
    da.CODIGO_OPERADOR || ' - ' || da.NOMBRE_OPERADOR              AS CLAVE_NOMBRE,
    da.CODIGO_OPERADOR                                             AS CODIGO_OPERADOR,
    da.NOMBRE_OPERADOR                                             AS NOMBRE_OPERADOR,
    da.DESPACHOS_VIAJES                                            AS DESPACHOS_VIAJES,
    da.CERRADOS                                                    AS CERRADOS,
    da.KMS_CARGADO                                                 AS KMS_CARGADO,
    da.KMS_VACIO                                                   AS KMS_VACIO,
    da.KMS_TOTAL                                                   AS KMS_TOTAL,
    da.TOTAL_FACTURACION                                           AS TOTAL_FACTURACION,
    ROUND(da.TOTAL_FACTURACION / NULLIF(da.KMS_TOTAL, 0), 4)       AS COSTO_POR_KM,
    ROUND(da.KMS_TOTAL / NULLIF(da.KWH_CONSUMO_TOTAL, 0), 4)       AS RENDIMIENTO_PROM_KMS_KWH,
    da.COSTO_OPERADOR                                              AS OPERADOR,
    da.COSTO_MANTENIMIENTO                                         AS MANTENIMIENTO,
    da.OTROS_GASTOS                                                AS OTROS_GASTOS,
    da.TOTAL_COSTO                                                 AS TOTAL_COSTO,
    da.TOTAL_FACTURACION - da.TOTAL_COSTO                          AS MARGEN_OPERATIVO,
    da.TOTAL_DISTANCIA_DECLARADA_KM                                AS DISTANCIA_DECLARADA_KM,
    da.TOTAL_PESO_DECLARADO_KG                                     AS PESO_DECLARADO_KG
FROM CTE_DRILLACROSS da
ORDER BY
    da.TOTAL_FACTURACION DESC,
    da.KMS_TOTAL DESC
""",
        8: """-- ds_08_analisis_rutas_origen_destino.sql
{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set fecha_inicio = from_dttm[:10] if from_dttm else '2026-11-01' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_CCP_RUTAS AS (
    SELECT
        cp.UUID_CCP,
        o.ESTADO_ORIGEN || ' -> ' || dst.ESTADO_DESTINO        AS CORREDOR_ESTADOS,
        o.NOMBRE_UBICACION_ORIGEN                              AS ORIGEN,
        o.MUNICIPIO_ORIGEN                                     AS MUNICIPIO_ORIGEN,
        o.ESTADO_ORIGEN                                        AS ESTADO_ORIGEN,
        o.LATITUD_ORIGEN                                       AS LATITUD_ORIGEN,
        o.LONGITUD_ORIGEN                                      AS LONGITUD_ORIGEN,
        dst.NOMBRE_UBICACION_DESTINO                           AS DESTINO,
        dst.MUNICIPIO_DESTINO                                  AS MUNICIPIO_DESTINO,
        dst.ESTADO_DESTINO                                     AS ESTADO_DESTINO,
        dst.LATITUD_DESTINO                                    AS LATITUD_DESTINO,
        dst.LONGITUD_DESTINO                                   AS LONGITUD_DESTINO,
        c.RAZON_SOCIAL                                         AS CLIENTE,
        v.CODIGO_ECO                                           AS UNIDAD,
        op.NOMBRE_OPERADOR                                     AS OPERADOR,
        MAX(cp.DISTANCIA_DECLARADA_KM)                         AS DISTANCIA_CCP,
        SUM(cp.PESO_KG)                                        AS PESO_TOTAL_CCP
    FROM BI_SEMANTIC.VW_FACT_LINEAS_CARGA_CARTAPORTE cp
    JOIN BI_SEMANTIC.VW_DIM_FECHA f 
        ON cp.ID_FECHA_EMISION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_UBICACION_ORIGEN o 
        ON cp.ID_ORIGEN_UBICACION = o.ID_ORIGEN_UBICACION
    JOIN BI_SEMANTIC.VW_DIM_UBICACION_DESTINO dst 
        ON cp.ID_DESTINO_UBICACION = dst.ID_DESTINO_UBICACION
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE c 
        ON cp.ID_CLIENTE_REMITENTE = c.ID_CLIENTE
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v 
        ON cp.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR op 
        ON cp.ID_OPERADOR = op.ID_OPERADOR
    WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
      AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
      AND o.ID_ORIGEN_UBICACION <> -1
      AND dst.ID_DESTINO_UBICACION <> -1
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND op.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if clientes %}
      AND c.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
    GROUP BY
        cp.UUID_CCP,
        o.ESTADO_ORIGEN,
        dst.ESTADO_DESTINO,
        o.NOMBRE_UBICACION_ORIGEN,
        o.MUNICIPIO_ORIGEN,
        o.LATITUD_ORIGEN,
        o.LONGITUD_ORIGEN,
        dst.NOMBRE_UBICACION_DESTINO,
        dst.MUNICIPIO_DESTINO,
        dst.ESTADO_DESTINO,
        dst.LATITUD_DESTINO,
        dst.LONGITUD_DESTINO,
        c.RAZON_SOCIAL,
        v.CODIGO_ECO,
        op.NOMBRE_OPERADOR
)
SELECT
    CORREDOR_ESTADOS,
    ORIGEN,
    MUNICIPIO_ORIGEN,
    ESTADO_ORIGEN,
    LATITUD_ORIGEN,
    LONGITUD_ORIGEN,
    DESTINO,
    MUNICIPIO_DESTINO,
    ESTADO_DESTINO,
    LATITUD_DESTINO,
    LONGITUD_DESTINO,
    COUNT(UUID_CCP)                                            AS TOTAL_EMBARQUES_CCP,
    SUM(DISTANCIA_CCP)                                         AS TOTAL_DISTANCIA_KM,
    SUM(PESO_TOTAL_CCP)                                        AS TOTAL_PESO_KG,
    ROUND(AVG(DISTANCIA_CCP), 2)                               AS DISTANCIA_PROMEDIO_KM,
    ROUND(AVG(PESO_TOTAL_CCP), 2)                              AS PESO_PROMEDIO_KG
FROM CTE_CCP_RUTAS
GROUP BY
    CORREDOR_ESTADOS,
    ORIGEN,
    MUNICIPIO_ORIGEN,
    ESTADO_ORIGEN,
    LATITUD_ORIGEN,
    LONGITUD_ORIGEN,
    DESTINO,
    MUNICIPIO_DESTINO,
    ESTADO_DESTINO,
    LATITUD_DESTINO,
    LONGITUD_DESTINO
ORDER BY
    TOTAL_EMBARQUES_CCP DESC
"""
    }

    def get_or_create_slice(slice_name, viz_type, datasource_id, params):
        slc = db.session.query(Slice).filter_by(slice_name=slice_name).first()
        if not slc:
            slc = Slice(
                slice_name=slice_name,
                viz_type=viz_type,
                datasource_type='table',
                datasource_id=datasource_id,
                params=json.dumps(params, ensure_ascii=False)
            )
            db.session.add(slc)
            db.session.flush()
            print(f"  [+] Creado Slice ID {slc.id}: '{slice_name}' ({viz_type})")
        else:
            slc.viz_type = viz_type
            slc.datasource_id = datasource_id
            slc.params = json.dumps(params, ensure_ascii=False)
            db.session.flush()
            print(f"  [*] Actualizado Slice ID {slc.id}: '{slice_name}' ({viz_type})")
        return slc

    def build_dashboard():
        print("=== Iniciando sincronización de Datasets y Construcción de Dashboard TRA099R1 ===")
        
        # 1. Sincronizar SQL y metadatos de los 8 Datasets
        for ds_id, sql_code in SQL_DATASETS.items():
            ds = db.session.query(SqlaTable).filter_by(id=ds_id).first()
            if ds:
                ds.sql = sql_code
                ds.fetch_metadata()
                print(f"  [OK] Dataset {ds_id} '{ds.table_name}' actualizado y metadatos refrescados.")
        db.session.commit()
        
        slices = []
        
        # ---------------------------------------------------------------------
        # BLOQUE 1: Indicadores Diarios de Flota (ds_01)
        # ---------------------------------------------------------------------
        # KPI 1: Flota Total
        p_flota_total = {
            "viz_type": "big_number_total",
            "datasource": "1__table",
            "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CANTIDAD_UNIDADES)", "label": "Flota Total"},
            "subheader": "100 Unidades Activas",
            "time_range": "2026-11-01 : 2026-11-06"
        }
        s_flota_total = get_or_create_slice("B1 - Flota Total", "big_number_total", 1, p_flota_total)
        slices.append(s_flota_total)
        
        # KPI 2: Con Viaje
        p_flota_con_viaje = {
            "viz_type": "big_number_total",
            "datasource": "1__table",
            "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CASE WHEN ESTADO_FLOTA = 'Con Viaje' THEN CANTIDAD_UNIDADES ELSE 0 END)", "label": "Con Viaje"},
            "subheader": "56% de la Flota (56 uds)",
            "time_range": "2026-11-01 : 2026-11-06"
        }
        s_flota_con_viaje = get_or_create_slice("B1 - Unidades Con Viaje", "big_number_total", 1, p_flota_con_viaje)
        slices.append(s_flota_con_viaje)
        
        # KPI 3: Sin Viaje
        p_flota_sin_viaje = {
            "viz_type": "big_number_total",
            "datasource": "1__table",
            "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CASE WHEN ESTADO_FLOTA = 'Sin Viaje' THEN CANTIDAD_UNIDADES ELSE 0 END)", "label": "Sin Viaje"},
            "subheader": "40% de la Flota (40 uds)",
            "time_range": "2026-11-01 : 2026-11-06"
        }
        s_flota_sin_viaje = get_or_create_slice("B1 - Unidades Sin Viaje", "big_number_total", 1, p_flota_sin_viaje)
        slices.append(s_flota_sin_viaje)
        
        # KPI 4: Inactivas
        p_flota_inactivas = {
            "viz_type": "big_number_total",
            "datasource": "1__table",
            "metric": {"expressionType": "SQL", "sqlExpression": "SUM(CASE WHEN ESTADO_FLOTA = 'Inactivas' THEN CANTIDAD_UNIDADES ELSE 0 END)", "label": "Inactivas"},
            "subheader": "4% de la Flota (4 uds)",
            "time_range": "2026-11-01 : 2026-11-06"
        }
        s_flota_inactivas = get_or_create_slice("B1 - Unidades Inactivas", "big_number_total", 1, p_flota_inactivas)
        slices.append(s_flota_inactivas)
        
        # DONA: Disponibilidad de Flota (Pie con donut: true)
        p_flota_dona = {
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
        s_flota_dona = get_or_create_slice("B1 - Disponibilidad de Flota (Dona)", "pie", 1, p_flota_dona)
        slices.append(s_flota_dona)
        
        # ---------------------------------------------------------------------
        # BLOQUE 2: Indicadores de Operación Día vs Mes (ds_02)
        # ---------------------------------------------------------------------
        p_operacion = {
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
        s_operacion = get_or_create_slice("B2 - Indicadores de Operación (Día vs. Mes)", "table", 2, p_operacion)
        slices.append(s_operacion)
        
        # ---------------------------------------------------------------------
        # BLOQUE 3: Indicadores Generales Día vs Mes (ds_03)
        # ---------------------------------------------------------------------
        p_generales = {
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
        s_generales = get_or_create_slice("B3 - Indicadores Generales (Día vs. Mes)", "table", 3, p_generales)
        slices.append(s_generales)
        
        # ---------------------------------------------------------------------
        # BLOQUE 4: Top 5 Despachos por Cliente (ds_04) - Gráfica de Barras
        # ---------------------------------------------------------------------
        p_top5_clientes = {
            "viz_type": "echarts_timeseries_bar",
            "datasource": "4__table",
            "groupby": ["CLIENTE"],
            "metrics": [
                {"expressionType": "SQL", "sqlExpression": "SUM(DESPACHOS_MES)", "label": "Despachos Mes"},
                {"expressionType": "SQL", "sqlExpression": "SUM(DESPACHOS_DIA)", "label": "Despachos Día"}
            ],
            "orderby": [[{"expressionType": "SQL", "sqlExpression": "SUM(DESPACHOS_MES)", "label": "Despachos Mes"}, False]],
            "row_limit": 5,
            "orientation": "horizontal",
            "show_legend": True,
            "time_range": "2026-11-01 : 2026-11-06"
        }
        s_top5_clientes = get_or_create_slice("B4 - Top 5 Despachos por Cliente (Barras)", "echarts_timeseries_bar", 4, p_top5_clientes)
        slices.append(s_top5_clientes)
        
        # ---------------------------------------------------------------------
        # BLOQUE 5: Facturación Top 10 Unidades ECO (ds_05) - Gráfica de Barras
        # ---------------------------------------------------------------------
        p_top10_eco = {
            "viz_type": "echarts_timeseries_bar",
            "datasource": "5__table",
            "groupby": ["UNIDAD"],
            "metrics": [
                {"expressionType": "SQL", "sqlExpression": "SUM(TOTAL_FACTURACION)", "label": "Total Facturación"}
            ],
            "orderby": [[{"expressionType": "SQL", "sqlExpression": "SUM(TOTAL_FACTURACION)", "label": "Total Facturación"}, False]],
            "row_limit": 10,
            "orientation": "horizontal",
            "show_legend": False,
            "time_range": "2026-11-01 : 2026-11-06"
        }
        s_top10_eco = get_or_create_slice("B5 - Top 10 Facturación por Unidad ECO (Barras)", "echarts_timeseries_bar", 5, p_top10_eco)
        slices.append(s_top10_eco)
        
        # ---------------------------------------------------------------------
        # BLOQUE 6: Productividad de las Unidades (ds_06) - 13 columnas
        # ---------------------------------------------------------------------
        p_prod_unidades = {
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
        s_prod_unidades = get_or_create_slice("B6 - Productividad de las Unidades (Mes)", "table", 6, p_prod_unidades)
        slices.append(s_prod_unidades)
        
        # ---------------------------------------------------------------------
        # BLOQUE 7: Productividad de los Operadores (ds_07) - 13 columnas
        # ---------------------------------------------------------------------
        p_prod_operadores = {
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
        s_prod_operadores = get_or_create_slice("B7 - Productividad de los Operadores (Mes)", "table", 7, p_prod_operadores)
        slices.append(s_prod_operadores)
        
        # ---------------------------------------------------------------------
        # BLOQUE 8 (Complementario): Análisis de Corredores (ds_08)
        # ---------------------------------------------------------------------
        p_corredores = {
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
        s_corredores = get_or_create_slice("B8 - Análisis de Corredores Origen-Destino", "table", 8, p_corredores)
        slices.append(s_corredores)
        
        # ---------------------------------------------------------------------
        # CONSTRUCCIÓN DEL DASHBOARD TRA099R1
        # ---------------------------------------------------------------------
        dash_title = "Reporte Diario de Operación — Analytics TMS"
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
            print(f"  [+] Creado Dashboard ID {dash.id}: '{dash_title}'")
        else:
            dash.dashboard_title = dash_title
            dash.published = True
            db.session.flush()
            print(f"  [*] Actualizado Dashboard ID {dash.id}: '{dash_title}'")
            
        dash.slices = slices
        
        # Native Filters Configuration (UNIDAD, NOMBRE_OPERADOR, CLIENTE, Rango Temporal)
        native_filters = [
            {
                "id": "NATIVE_FILTER-time-range",
                "name": "Rango Temporal",
                "filterType": "filter_time",
                "targets": [{"datasetId": i} for i in range(1, 9)],
                "defaultDataMask": {
                    "filterState": {
                        "value": "2026-11-01 : 2026-11-06"
                    }
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
                    {"datasetId": 1, "column": {"name": "ESTADO_FLOTA"}},
                    {"datasetId": 2, "column": {"name": "UNIDAD"}},
                    {"datasetId": 3, "column": {"name": "UNIDAD"}},
                    {"datasetId": 4, "column": {"name": "UNIDAD"}},
                    {"datasetId": 5, "column": {"name": "UNIDAD"}},
                    {"datasetId": 6, "column": {"name": "UNIDAD"}},
                    {"datasetId": 7, "column": {"name": "UNIDAD"}},
                    {"datasetId": 8, "column": {"name": "UNIDAD"}}
                ],
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True,
                "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "inverseSelection": False}
            },
            {
                "id": "NATIVE_FILTER-operador",
                "name": "Operador",
                "filterType": "filter_select",
                "targets": [
                    {"datasetId": 2, "column": {"name": "NOMBRE_OPERADOR"}},
                    {"datasetId": 3, "column": {"name": "NOMBRE_OPERADOR"}},
                    {"datasetId": 4, "column": {"name": "NOMBRE_OPERADOR"}},
                    {"datasetId": 6, "column": {"name": "NOMBRE_OPERADOR"}},
                    {"datasetId": 7, "column": {"name": "NOMBRE_OPERADOR"}},
                    {"datasetId": 8, "column": {"name": "NOMBRE_OPERADOR"}}
                ],
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True,
                "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "inverseSelection": False}
            },
            {
                "id": "NATIVE_FILTER-cliente",
                "name": "Cliente",
                "filterType": "filter_select",
                "targets": [
                    {"datasetId": 2, "column": {"name": "CLIENTE"}},
                    {"datasetId": 3, "column": {"name": "CLIENTE"}},
                    {"datasetId": 4, "column": {"name": "CLIENTE"}},
                    {"datasetId": 5, "column": {"name": "CLIENTE"}},
                    {"datasetId": 6, "column": {"name": "CLIENTE"}},
                    {"datasetId": 7, "column": {"name": "CLIENTE"}},
                    {"datasetId": 8, "column": {"name": "CLIENTE"}}
                ],
                "cascadeParentIds": [],
                "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
                "isInstant": True,
                "controlValues": {"multiSelect": True, "enableEmptyFilter": False, "inverseSelection": False}
            }
        ]
        
        # Position Layout JSON
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
                "parents": ["ROOT_ID"]
            },
            "HEADER_MAIN": {
                "type": "HEADER",
                "id": "HEADER_MAIN",
                "meta": {
                    "text": "Reporte Diario de Operación — Sunshine Deliveries (TRA099R1)"
                },
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "ROW_B1_KPIS": {
                "type": "ROW",
                "id": "ROW_B1_KPIS",
                "children": ["CHART_B1_1", "CHART_B1_2", "CHART_B1_3", "CHART_B1_4"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B1_1": {
                "type": "CHART",
                "id": "CHART_B1_1",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s_flota_total.id, "width": 3, "height": 30, "sliceName": s_flota_total.slice_name}
            },
            "CHART_B1_2": {
                "type": "CHART",
                "id": "CHART_B1_2",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s_flota_con_viaje.id, "width": 3, "height": 30, "sliceName": s_flota_con_viaje.slice_name}
            },
            "CHART_B1_3": {
                "type": "CHART",
                "id": "CHART_B1_3",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s_flota_sin_viaje.id, "width": 3, "height": 30, "sliceName": s_flota_sin_viaje.slice_name}
            },
            "CHART_B1_4": {
                "type": "CHART",
                "id": "CHART_B1_4",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_KPIS"],
                "meta": {"chartId": s_flota_inactivas.id, "width": 3, "height": 30, "sliceName": s_flota_inactivas.slice_name}
            },
            "ROW_B1_DONUT": {
                "type": "ROW",
                "id": "ROW_B1_DONUT",
                "children": ["CHART_B1_DONUT"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B1_DONUT": {
                "type": "CHART",
                "id": "CHART_B1_DONUT",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B1_DONUT"],
                "meta": {"chartId": s_flota_dona.id, "width": 12, "height": 40, "sliceName": s_flota_dona.slice_name}
            },
            "ROW_B2_B3": {
                "type": "ROW",
                "id": "ROW_B2_B3",
                "children": ["CHART_B2", "CHART_B3"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B2": {
                "type": "CHART",
                "id": "CHART_B2",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B2_B3"],
                "meta": {"chartId": s_operacion.id, "width": 6, "height": 45, "sliceName": s_operacion.slice_name}
            },
            "CHART_B3": {
                "type": "CHART",
                "id": "CHART_B3",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B2_B3"],
                "meta": {"chartId": s_generales.id, "width": 6, "height": 45, "sliceName": s_generales.slice_name}
            },
            "ROW_B4_B5": {
                "type": "ROW",
                "id": "ROW_B4_B5",
                "children": ["CHART_B4", "CHART_B5"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B4": {
                "type": "CHART",
                "id": "CHART_B4",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B4_B5"],
                "meta": {"chartId": s_top5_clientes.id, "width": 6, "height": 50, "sliceName": s_top5_clientes.slice_name}
            },
            "CHART_B5": {
                "type": "CHART",
                "id": "CHART_B5",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B4_B5"],
                "meta": {"chartId": s_top10_eco.id, "width": 6, "height": 50, "sliceName": s_top10_eco.slice_name}
            },
            "ROW_B6": {
                "type": "ROW",
                "id": "ROW_B6",
                "children": ["CHART_B6"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B6": {
                "type": "CHART",
                "id": "CHART_B6",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B6"],
                "meta": {"chartId": s_prod_unidades.id, "width": 12, "height": 70, "sliceName": s_prod_unidades.slice_name}
            },
            "ROW_B7": {
                "type": "ROW",
                "id": "ROW_B7",
                "children": ["CHART_B7"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B7": {
                "type": "CHART",
                "id": "CHART_B7",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B7"],
                "meta": {"chartId": s_prod_operadores.id, "width": 12, "height": 70, "sliceName": s_prod_operadores.slice_name}
            },
            "ROW_B8": {
                "type": "ROW",
                "id": "ROW_B8",
                "children": ["CHART_B8"],
                "parents": ["ROOT_ID", "GRID_ID"]
            },
            "CHART_B8": {
                "type": "CHART",
                "id": "CHART_B8",
                "children": [],
                "parents": ["ROOT_ID", "GRID_ID", "ROW_B8"],
                "meta": {"chartId": s_corredores.id, "width": 12, "height": 60, "sliceName": s_corredores.slice_name}
            }
        }
        
        json_meta = {
            "native_filter_configuration": native_filters,
            "chart_configuration": {},
            "global_chart_configuration": {"scope": {"rootPath": ["ROOT_ID"], "excluded": []}, "chartsInScope": [s.id for s in slices]},
            "color_scheme": "supersetColors",
            "refresh_frequency": 0,
            "expanded_slices": {},
            "default_filters": "{}"
        }
        
        dash.position_json = json.dumps(position, ensure_ascii=False)
        dash.json_metadata = json.dumps(json_meta, ensure_ascii=False)
        
        db.session.commit()
        print(f"=== Dashboard '{dash_title}' (ID {dash.id}) actualizado exitosamente con {len(slices)} charts (Dona, Barras y Tablas) y 4 Native Filters ===")

if __name__ == "__main__":
    with app.app_context():
        build_dashboard()
