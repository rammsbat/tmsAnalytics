-- =============================================================================
-- Dataset   : ds_06_productividad_unidades.sql
-- Propósito : Bloque 6 — Tabla de Productividad de las Unidades (Mes)
-- Fuente    : docs/Draft-dashboard-TMS.pdf (Bloque 6) & draft_dashboard_kpis.md
-- Patrón    : Drill-Across estricto (4 CTEs + FULL OUTER JOIN)
-- SCD2      : Agrupación por llave natural CODIGO_ECO
-- No Aditivo: DISTANCIA_DECLARADA_KM colapsada por UUID_CCP
-- =============================================================================

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
