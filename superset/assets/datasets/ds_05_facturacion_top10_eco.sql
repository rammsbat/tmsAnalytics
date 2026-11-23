-- =============================================================================
-- Dataset   : ds_05_facturacion_top10_eco.sql
-- Propósito : Bloque 5 — Facturación por Unidad (Top 10 del Mes)
-- Fuente    : docs/Draft-dashboard-TMS.pdf (Bloque 5) & draft_dashboard_kpis.md
-- SCD2      : Agrupación por llave natural CODIGO_ECO unificando versiones
-- =============================================================================

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
JOIN BI_SEMANTIC.VW_DIM_CLIENTE cli 
    ON fac.ID_CLIENTE = cli.ID_CLIENTE
WHERE f.FECHA >= TO_DATE('{{ fecha_inicio }}', 'YYYY-MM-DD')
  AND f.FECHA <= TO_DATE('{{ fecha_corte }}', 'YYYY-MM-DD')
  AND v.ID_VEHICULO <> -1
  {% if ecos %}
  AND v.CODIGO_ECO IN {{ ecos | where_in }}
  {% endif %}
  {% if clientes %}
  AND cli.RAZON_SOCIAL IN {{ clientes | where_in }}
  {% endif %}
GROUP BY
    v.CODIGO_ECO
ORDER BY
    TOTAL_FACTURACION DESC
