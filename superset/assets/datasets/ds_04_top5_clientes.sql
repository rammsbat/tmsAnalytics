-- =============================================================================
-- Dataset   : ds_04_top5_clientes.sql
-- Propósito : Bloque 4 — Top 5 Despachos por Cliente (Día vs. Mes)
-- Fuente    : docs/Draft-dashboard-TMS.pdf (Bloque 4) & draft_dashboard_kpis.md
-- Patrón    : Una sola pasada por CTE (rango mes) + Agregación condicional para Día
-- =============================================================================

{% set fecha_corte = to_dttm[:10] if to_dttm else '2026-11-06' %}

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
      {% if filter_values('CODIGO_ECO') %}
      AND v.CODIGO_ECO IN {{ filter_values('CODIGO_ECO') | where_in }}
      {% endif %}
      {% if filter_values('NOMBRE_OPERADOR') %}
      AND o.NOMBRE_OPERADOR IN {{ filter_values('NOMBRE_OPERADOR') | where_in }}
      {% endif %}
      {% if filter_values('RAZON_SOCIAL') %}
      AND c.RAZON_SOCIAL IN {{ filter_values('RAZON_SOCIAL') | where_in }}
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
