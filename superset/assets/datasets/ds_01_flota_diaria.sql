-- =============================================================================
-- Dataset   : ds_01_flota_diaria.sql
-- Propósito : Bloque 1 — Indicadores Diarios de Flota (KPIs + Dona de Disponibilidad)
-- Fuente    : docs/Draft-dashboard-TMS.pdf (Bloque 1) & draft_dashboard_kpis.md
-- Tabla Base: BI_SEMANTIC.VW_FACT_SNAPSHOT_FLOTA_DIARIO / VW_DIM_VEHICULO / VW_DIM_FECHA
-- Filtro    : Día de corte (por defecto to_dttm o '2026-11-06')
-- =============================================================================

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
