-- =============================================================================
-- Script      : 05_views_bi_semantic.sql
-- Proyecto    : Analytics TMS - Sunshine Deliveries
-- Esquema     : BI_SEMANTIC
-- Propósito   : Capa semántica y de presentación para Apache Superset:
--               Vistas de rol (Ubicación Origen/Destino/Parada), vistas base
--               directas para las 10 dimensiones y 6 hechos, Vistas Materializadas
--               SE2 compatibles con patrón Drill-Across y procedimiento seguro
--               AUTHID DEFINER de refresco para ETL_RUNNER.
-- Autor/Fecha : Oracle DW Architect / 2026-11-22
-- Fuente      : docs/Arquitectura-dw-analytics-tms.docx (§4, §6, §7)
--
-- Compatibilidad Oracle SE2 (ver .bob/rules/02-licensing-oracle-guardrails.md):
--   * NO usar ENABLE QUERY REWRITE en Vistas Materializadas (requiere EE).
--   * MVs creadas con BUILD IMMEDIATE REFRESH COMPLETE ON DEMAND.
--   * Refresco por demanda encapsulado en SP_REFRESH_MV_SEMANTIC.
--
-- Idempotencia: el script puede ejecutarse más de una vez sin error.
-- =============================================================================

SET DEFINE OFF;
WHENEVER SQLERROR EXIT SQL.SQLCODE;

-- =============================================================================
-- 1. VISTAS DE ROL SOBRE DIM_UBICACION
-- =============================================================================

-- 1.1 VW_DIM_UBICACION_ORIGEN
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_UBICACION_ORIGEN AS
SELECT
    ID_UBICACION            AS ID_ORIGEN_UBICACION,
    CODIGO_UBICACION        AS CODIGO_UBICACION_ORIGEN,
    NOMBRE_UBICACION        AS NOMBRE_UBICACION_ORIGEN,
    CODIGO_POSTAL           AS CODIGO_POSTAL_ORIGEN,
    ESTADO                  AS ESTADO_ORIGEN,
    MUNICIPIO               AS MUNICIPIO_ORIGEN,
    LATITUD                 AS LATITUD_ORIGEN,
    LONGITUD                AS LONGITUD_ORIGEN,
    TIPO_UBICACION          AS TIPO_UBICACION_ORIGEN
FROM DWH_MART.DIM_UBICACION;

COMMENT ON TABLE BI_SEMANTIC.VW_DIM_UBICACION_ORIGEN IS 'Vista de Rol: Dimensión Ubicación con rol de Origen / Remitente.';

-- 1.2 VW_DIM_UBICACION_DESTINO
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_UBICACION_DESTINO AS
SELECT
    ID_UBICACION            AS ID_DESTINO_UBICACION,
    CODIGO_UBICACION        AS CODIGO_UBICACION_DESTINO,
    NOMBRE_UBICACION        AS NOMBRE_UBICACION_DESTINO,
    CODIGO_POSTAL           AS CODIGO_POSTAL_DESTINO,
    ESTADO                  AS ESTADO_DESTINO,
    MUNICIPIO               AS MUNICIPIO_DESTINO,
    LATITUD                 AS LATITUD_DESTINO,
    LONGITUD                AS LONGITUD_DESTINO,
    TIPO_UBICACION          AS TIPO_UBICACION_DESTINO
FROM DWH_MART.DIM_UBICACION;

COMMENT ON TABLE BI_SEMANTIC.VW_DIM_UBICACION_DESTINO IS 'Vista de Rol: Dimensión Ubicación con rol de Destino / Entrega.';

-- 1.3 VW_DIM_UBICACION_PARADA
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_UBICACION_PARADA AS
SELECT
    ID_UBICACION            AS ID_UBICACION_PARADA,
    CODIGO_UBICACION        AS CODIGO_UBICACION_PARADA,
    NOMBRE_UBICACION        AS NOMBRE_UBICACION_PARADA,
    CODIGO_POSTAL           AS CODIGO_POSTAL_PARADA,
    ESTADO                  AS ESTADO_PARADA,
    MUNICIPIO               AS MUNICIPIO_PARADA,
    LATITUD                 AS LATITUD_PARADA,
    LONGITUD                AS LONGITUD_PARADA,
    TIPO_UBICACION          AS TIPO_UBICACION_PARADA
FROM DWH_MART.DIM_UBICACION;

COMMENT ON TABLE BI_SEMANTIC.VW_DIM_UBICACION_PARADA IS 'Vista de Rol: Dimensión Ubicación con rol de Parada / Hito en ruta.';


-- =============================================================================
-- 2. VISTAS BASE DIRECTAS DE DIMENSIONES (10)
-- =============================================================================

CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_FECHA AS SELECT * FROM DWH_MART.DIM_FECHA;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_HORA AS SELECT * FROM DWH_MART.DIM_HORA;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_VEHICULO AS SELECT * FROM DWH_MART.DIM_VEHICULO;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_REMOLQUE AS SELECT * FROM DWH_MART.DIM_REMOLQUE;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_OPERADOR AS SELECT * FROM DWH_MART.DIM_OPERADOR;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_CLIENTE AS SELECT * FROM DWH_MART.DIM_CLIENTE;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_UBICACION AS SELECT * FROM DWH_MART.DIM_UBICACION;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_PRODUCTO_SAT AS SELECT * FROM DWH_MART.DIM_PRODUCTO_SAT;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_POLIZA AS SELECT * FROM DWH_MART.DIM_POLIZA;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_DIM_PERFIL_VIAJE AS SELECT * FROM DWH_MART.DIM_PERFIL_VIAJE;


-- =============================================================================
-- 3. VISTAS BASE DIRECTAS DE HECHOS (6)
-- =============================================================================

CREATE OR REPLACE VIEW BI_SEMANTIC.VW_FACT_DESPACHO_VIAJE AS SELECT * FROM DWH_MART.FACT_DESPACHO_VIAJE;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_FACT_EVENTOS_PARADA AS SELECT * FROM DWH_MART.FACT_EVENTOS_PARADA;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_FACT_LINEAS_CARGA_CARTAPORTE AS SELECT * FROM DWH_MART.FACT_LINEAS_CARGA_CARTAPORTE;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_FACT_SNAPSHOT_FLOTA_DIARIO AS SELECT * FROM DWH_MART.FACT_SNAPSHOT_FLOTA_DIARIO;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_FACT_FACTURACION_FLETE AS SELECT * FROM DWH_MART.FACT_FACTURACION_FLETE;
CREATE OR REPLACE VIEW BI_SEMANTIC.VW_FACT_GASTOS_LIQUIDACION AS SELECT * FROM DWH_MART.FACT_GASTOS_LIQUIDACION;
-- =============================================================================
-- 4. VISTAS MATERIALIZADAS SE2 COMPATIBLES (IDEMPOTENCIA PL/SQL)
-- =============================================================================

-- 4.1 MV_METRICAS_FLOTA_DIARIA (Agregado diario de inventario y estado de flota)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE MATERIALIZED VIEW BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA
    BUILD IMMEDIATE
    REFRESH COMPLETE ON DEMAND
    AS
    SELECT
        s.ID_FECHA_CORTE,
        f.FECHA,
        f.ANIO,
        f.MES,
        f.DIA,
        COUNT(s.ID_VEHICULO)                    AS TOTAL_UNIDADES_FLOTA,
        SUM(s.UNIDAD_CON_VIAJE_INDICADOR)       AS UNIDADES_CON_VIAJE,
        SUM(s.UNIDAD_SIN_VIAJE_INDICADOR)       AS UNIDADES_SIN_VIAJE,
        SUM(s.UNIDAD_INACTIVA_INDICADOR)        AS UNIDADES_INACTIVAS,
        SUM(s.KMS_RECORRIDOS_DIA)               AS TOTAL_KMS_DIA,
        SUM(s.KWH_CONSUMO_DIA)                  AS TOTAL_KWH_DIA,
        ROUND(SUM(s.UNIDAD_CON_VIAJE_INDICADOR) * 100.0 / NULLIF(COUNT(s.ID_VEHICULO), 0), 2) AS PCT_CON_VIAJE,
        ROUND(SUM(s.UNIDAD_SIN_VIAJE_INDICADOR) * 100.0 / NULLIF(COUNT(s.ID_VEHICULO), 0), 2) AS PCT_SIN_VIAJE,
        ROUND(SUM(s.UNIDAD_INACTIVA_INDICADOR)  * 100.0 / NULLIF(COUNT(s.ID_VEHICULO), 0), 2) AS PCT_INACTIVAS
    FROM DWH_MART.FACT_SNAPSHOT_FLOTA_DIARIO s
    JOIN DWH_MART.DIM_FECHA f ON s.ID_FECHA_CORTE = f.ID_FECHA
    GROUP BY
        s.ID_FECHA_CORTE,
        f.FECHA,
        f.ANIO,
        f.MES,
        f.DIA';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 AND SQLCODE != -12006 THEN RAISE; END IF;
END;
/
COMMENT ON MATERIALIZED VIEW BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA IS 'Vista Materializada SE2: Resumen diario de disponibilidad de la flota de 100 unidades.';

-- 4.2 MV_PRODUCTIVIDAD_ECO_MENSUAL (Drill-Across estricto: Despacho + Facturación + Gastos)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE MATERIALIZED VIEW BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL
    BUILD IMMEDIATE
    REFRESH COMPLETE ON DEMAND
    AS
    WITH CTE_DESPACHO AS (
        SELECT
            f.ANIO,
            f.MES,
            f.NOMBRE_MES,
            d.ID_VEHICULO,
            COUNT(d.ID_FACT_DESPACHO)           AS DESPACHOS_VIAJES,
            SUM(d.CONTADOR_CERRADO)             AS CERRADOS,
            SUM(d.KMS_CARGADO)                  AS KMS_CARGADO,
            SUM(d.KMS_VACIO)                    AS KMS_VACIO,
            SUM(d.KMS_TOTAL)                    AS KMS_TOTAL,
            SUM(d.KWH_CONSUMO_ENERGIA)          AS KWH_CONSUMO_TOTAL
        FROM DWH_MART.FACT_DESPACHO_VIAJE d
        JOIN DWH_MART.DIM_FECHA f ON d.ID_FECHA_INICIO = f.ID_FECHA
        GROUP BY f.ANIO, f.MES, f.NOMBRE_MES, d.ID_VEHICULO
    ),
    CTE_FACTURACION AS (
        SELECT
            f.ANIO,
            f.MES,
            fac.ID_VEHICULO,
            SUM(fac.IMPORTE_TOTAL_FACTURADO)    AS TOTAL_FACTURACION,
            SUM(fac.CONTADOR_FACTURA)           AS TOTAL_FACTURAS
        FROM DWH_MART.FACT_FACTURACION_FLETE fac
        JOIN DWH_MART.DIM_FECHA f ON fac.ID_FECHA_FACTURACION = f.ID_FECHA
        GROUP BY f.ANIO, f.MES, fac.ID_VEHICULO
    ),
    CTE_GASTOS AS (
        SELECT
            f.ANIO,
            f.MES,
            g.ID_VEHICULO,
            SUM(g.MONTO_OPERADOR)               AS COSTO_OPERADOR,
            SUM(g.MONTO_MANTENIMIENTO)          AS COSTO_MANTENIMIENTO,
            SUM(g.MONTO_CASETA + g.MONTO_OTROS_GASTOS) AS OTROS_GASTOS,
            SUM(g.IMPORTE_GASTO)                AS TOTAL_COSTO
        FROM DWH_MART.FACT_GASTOS_LIQUIDACION g
        JOIN DWH_MART.DIM_FECHA f ON g.ID_FECHA_LIQUIDACION = f.ID_FECHA
        GROUP BY f.ANIO, f.MES, g.ID_VEHICULO
    ),
    CTE_DRILLACROSS AS (
        SELECT
            COALESCE(d.ANIO, fac.ANIO, g.ANIO)                     AS ANIO,
            COALESCE(d.MES, fac.MES, g.MES)                       AS MES,
            COALESCE(d.NOMBRE_MES, TO_CHAR(COALESCE(d.MES, fac.MES, g.MES))) AS NOMBRE_MES,
            COALESCE(d.ID_VEHICULO, fac.ID_VEHICULO, g.ID_VEHICULO) AS ID_VEHICULO,
            NVL(d.DESPACHOS_VIAJES, 0)                             AS DESPACHOS_VIAJES,
            NVL(d.CERRADOS, 0)                                     AS CERRADOS,
            NVL(d.KMS_CARGADO, 0)                                  AS KMS_CARGADO,
            NVL(d.KMS_VACIO, 0)                                    AS KMS_VACIO,
            NVL(d.KMS_TOTAL, 0)                                    AS KMS_TOTAL,
            NVL(d.KWH_CONSUMO_TOTAL, 0)                            AS KWH_CONSUMO_TOTAL,
            NVL(fac.TOTAL_FACTURACION, 0)                          AS TOTAL_FACTURACION,
            NVL(fac.TOTAL_FACTURAS, 0)                             AS TOTAL_FACTURAS,
            NVL(g.COSTO_OPERADOR, 0)                               AS COSTO_OPERADOR,
            NVL(g.COSTO_MANTENIMIENTO, 0)                          AS COSTO_MANTENIMIENTO,
            NVL(g.OTROS_GASTOS, 0)                                 AS OTROS_GASTOS,
            NVL(g.TOTAL_COSTO, 0)                                  AS TOTAL_COSTO
        FROM CTE_DESPACHO d
        FULL OUTER JOIN CTE_FACTURACION fac
            ON  d.ANIO = fac.ANIO
            AND d.MES  = fac.MES
            AND d.ID_VEHICULO = fac.ID_VEHICULO
        FULL OUTER JOIN CTE_GASTOS g
            ON  COALESCE(d.ANIO, fac.ANIO) = g.ANIO
            AND COALESCE(d.MES, fac.MES)   = g.MES
            AND COALESCE(d.ID_VEHICULO, fac.ID_VEHICULO) = g.ID_VEHICULO
    )
    SELECT
        v.CODIGO_ECO                                               AS UNIDAD,
        v.PLACA,
        da.ANIO,
        da.MES,
        da.NOMBRE_MES,
        da.DESPACHOS_VIAJES,
        da.CERRADOS,
        da.KMS_CARGADO,
        da.KMS_VACIO,
        da.KMS_TOTAL,
        da.TOTAL_FACTURACION,
        ROUND(da.TOTAL_FACTURACION / NULLIF(da.KMS_TOTAL, 0), 4)   AS FACTURACION_POR_KM,
        ROUND(da.KMS_TOTAL / NULLIF(da.KWH_CONSUMO_TOTAL, 0), 4)   AS RENDIMIENTO_PROM_KMS_KWH,
        da.COSTO_OPERADOR                                          AS OPERADOR,
        da.COSTO_MANTENIMIENTO                                     AS MANTENIMIENTO,
        da.OTROS_GASTOS                                            AS OTROS_GASTOS,
        da.TOTAL_COSTO
    FROM CTE_DRILLACROSS da
    JOIN DWH_MART.DIM_VEHICULO v ON da.ID_VEHICULO = v.ID_VEHICULO';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 AND SQLCODE != -12006 THEN RAISE; END IF;
END;
/
COMMENT ON MATERIALIZED VIEW BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL IS 'Vista Materializada SE2: Matriz mensual de productividad por vehículo aplicando patrón Drill-Across (Draft Dashboard Bloque 6).';


-- =============================================================================
-- 5. PROCEDIMIENTO AUTHID DEFINER PARA REFRESCO DE VISTAS MATERIALIZADAS
-- =============================================================================

CREATE OR REPLACE PROCEDURE BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC
AUTHID DEFINER AS
BEGIN
    DBMS_MVIEW.REFRESH(
        list           => 'BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA, BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL',
        method         => 'C',
        atomic_refresh => TRUE
    );
END;
/
-- SP_REFRESH_MV_SEMANTIC: Procedimiento seguro AUTHID DEFINER para refrescar Vistas Materializadas en SE2


-- =============================================================================
-- 6. ASIGNACIÓN DE PRIVILEGIOS A BI_READER Y ETL_RUNNER
-- =============================================================================

DECLARE
    TYPE t_obj IS TABLE OF VARCHAR2(60);
    v_views t_obj := t_obj(
        'VW_DIM_UBICACION_ORIGEN',
        'VW_DIM_UBICACION_DESTINO',
        'VW_DIM_UBICACION_PARADA',
        'VW_DIM_FECHA',
        'VW_DIM_HORA',
        'VW_DIM_VEHICULO',
        'VW_DIM_REMOLQUE',
        'VW_DIM_OPERADOR',
        'VW_DIM_CLIENTE',
        'VW_DIM_UBICACION',
        'VW_DIM_PRODUCTO_SAT',
        'VW_DIM_POLIZA',
        'VW_DIM_PERFIL_VIAJE',
        'VW_FACT_DESPACHO_VIAJE',
        'VW_FACT_EVENTOS_PARADA',
        'VW_FACT_LINEAS_CARGA_CARTAPORTE',
        'VW_FACT_SNAPSHOT_FLOTA_DIARIO',
        'VW_FACT_FACTURACION_FLETE',
        'VW_FACT_GASTOS_LIQUIDACION',
        'MV_METRICAS_FLOTA_DIARIA',
        'MV_PRODUCTIVIDAD_ECO_MENSUAL'
    );
BEGIN
    FOR i IN 1..v_views.COUNT LOOP
        EXECUTE IMMEDIATE 'GRANT SELECT ON BI_SEMANTIC.' || v_views(i) || ' TO BI_READER';
    END LOOP;
END;
/

-- Permiso de ejecución del procedimiento de refresco para el usuario de ETL
GRANT EXECUTE ON BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC TO ETL_RUNNER;

EXIT;
-- =============================================================================
-- Fin del script: 05_views_bi_semantic.sql
-- =============================================================================