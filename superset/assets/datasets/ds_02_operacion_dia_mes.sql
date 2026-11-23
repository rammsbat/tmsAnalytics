-- =============================================================================
-- Dataset   : ds_02_operacion_dia_mes.sql
-- Propósito : Bloque 2 — Indicadores de Operación (Día vs. Mes)
-- Fuente    : docs/Draft-dashboard-TMS.pdf (Bloque 2) & draft_dashboard_kpis.md
-- Patrón    : Una sola pasada por CTE (rango mes) + Agregación condicional para Día
-- =============================================================================

{% set from_date = from_dttm[:10] if from_dttm else '2026-11-01' %}
{% set to_date = to_dttm[:10] if to_dttm else '2026-11-06' %}
{% set ecos = filter_values('CODIGO_ECO') or filter_values('UNIDAD') %}
{% set operadores = filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR') %}
{% set clientes = filter_values('RAZON_SOCIAL') or filter_values('CLIENTE') %}

WITH CTE_CORTE AS (
    SELECT COALESCE(MAX(FECHA), DATE '2026-11-06') AS FECHA_CORTE
    FROM BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA
    WHERE FECHA >= TO_DATE('{{ from_date }}', 'YYYY-MM-DD')
      AND FECHA <= TO_DATE('{{ to_date }}', 'YYYY-MM-DD')
),
CTE_DESPACHOS AS (
    SELECT
        1                                                                                                      AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = c.FECHA_CORTE THEN d.CONTADOR_DESPACHO ELSE 0 END)                            AS DESPACHOS_DIA,
        SUM(d.CONTADOR_DESPACHO)                                                                               AS DESPACHOS_MES,
        SUM(CASE WHEN f.FECHA = c.FECHA_CORTE THEN d.CONTADOR_CERRADO ELSE 0 END)                             AS CIERRES_DIA,
        SUM(d.CONTADOR_CERRADO)                                                                                AS CIERRES_MES
    FROM BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE d
    CROSS JOIN CTE_CORTE c
    JOIN BI_SEMANTIC.VW_DIM_FECHA f
        ON d.ID_FECHA_INICIO = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v
        ON d.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o
        ON d.ID_OPERADOR = o.ID_OPERADOR
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE cli
        ON d.ID_CLIENTE_ORIGEN = cli.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(c.FECHA_CORTE, 'MM')
      AND f.FECHA <= c.FECHA_CORTE
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if operadores %}
      AND o.NOMBRE_OPERADOR IN {{ operadores | where_in }}
      {% endif %}
      {% if clientes %}
      AND cli.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
),
CTE_LIQUIDACIONES AS (
    SELECT
        1                                                                                                      AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = c.FECHA_CORTE AND g.MONTO_CASETA > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END)   AS LIQ_CASETAS_DIA,
        SUM(CASE WHEN g.MONTO_CASETA > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END)                               AS LIQ_CASETAS_MES,
        SUM(CASE WHEN f.FECHA = c.FECHA_CORTE AND g.MONTO_OPERADOR > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END) AS LIQ_OPERADOR_DIA,
        SUM(CASE WHEN g.MONTO_OPERADOR > 0 THEN g.CONTADOR_LIQUIDACION ELSE 0 END)                             AS LIQ_OPERADOR_MES
    FROM BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION g
    CROSS JOIN CTE_CORTE c
    JOIN BI_SEMANTIC.VW_DIM_FECHA f
        ON g.ID_FECHA_LIQUIDACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v
        ON g.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_OPERADOR o
        ON g.ID_OPERADOR = o.ID_OPERADOR
    WHERE f.FECHA >= TRUNC(c.FECHA_CORTE, 'MM')
      AND f.FECHA <= c.FECHA_CORTE
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
        COUNT(DISTINCT CASE WHEN f.FECHA = c.FECHA_CORTE THEN cp.UUID_CCP END)                                AS CFDI_TRASLADO_DIA,
        COUNT(DISTINCT cp.UUID_CCP)                                                                           AS CFDI_TRASLADO_MES
    FROM BI_SEMANTIC.VW_FACT_LINEAS_CARGA_CARTAPORTE cp
    CROSS JOIN CTE_CORTE c
    JOIN BI_SEMANTIC.VW_DIM_FECHA f
        ON cp.ID_FECHA_EMISION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v
        ON cp.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE cli
        ON cp.ID_CLIENTE_REMITENTE = cli.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(c.FECHA_CORTE, 'MM')
      AND f.FECHA <= c.FECHA_CORTE
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND cli.RAZON_SOCIAL IN {{ clientes | where_in }}
      {% endif %}
),
CTE_FACTURACION AS (
    SELECT
        1                                                                                                           AS JOIN_KEY,
        SUM(CASE WHEN f.FECHA = c.FECHA_CORTE THEN fac.CONTADOR_FACTURA ELSE 0 END)                                AS FACTURADOS_DIA,
        SUM(fac.CONTADOR_FACTURA)                                                                                AS FACTURADOS_MES
    FROM BI_SEMANTIC.VW_FACT_FACTURACION_FLETE fac
    CROSS JOIN CTE_CORTE c
    JOIN BI_SEMANTIC.VW_DIM_FECHA f
        ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
    JOIN BI_SEMANTIC.VW_DIM_VEHICULO v
        ON fac.ID_VEHICULO = v.ID_VEHICULO
    JOIN BI_SEMANTIC.VW_DIM_CLIENTE cli
        ON fac.ID_CLIENTE = cli.ID_CLIENTE
    WHERE f.FECHA >= TRUNC(c.FECHA_CORTE, 'MM')
      AND f.FECHA <= c.FECHA_CORTE
      {% if ecos %}
      AND v.CODIGO_ECO IN {{ ecos | where_in }}
      {% endif %}
      {% if clientes %}
      AND cli.RAZON_SOCIAL IN {{ clientes | where_in }}
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
FULL OUTER JOIN CTE_LIQUIDACIONES l   USING (JOIN_KEY)
FULL OUTER JOIN CTE_CARTAPORTE cp     USING (JOIN_KEY)
FULL OUTER JOIN CTE_FACTURACION fac   USING (JOIN_KEY)
