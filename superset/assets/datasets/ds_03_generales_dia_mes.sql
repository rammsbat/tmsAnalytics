-- =============================================================================
-- Dataset   : ds_03_generales_dia_mes.sql
-- Propósito : Bloque 3 — Indicadores Generales (Día vs. Mes)
-- Fuente    : docs/Draft-dashboard-TMS.pdf (Bloque 3) & draft_dashboard_kpis.md
-- Patrón    : Una sola pasada por CTE (rango mes) + Agregación condicional para Día
-- =============================================================================

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
