-- =============================================================================
-- Dataset   : ds_08_analisis_rutas_origen_destino.sql
-- Propósito : Análisis Geográfico y Corredores Origen - Destino (Vistas de Rol)
-- Fuente    : oracle/ddl/05_views_bi_semantic.sql (VW_FACT_LINEAS_CARGA_CARTAPORTE)
-- =============================================================================

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
