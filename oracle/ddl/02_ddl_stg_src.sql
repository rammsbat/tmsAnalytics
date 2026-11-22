-- =============================================================================
-- Script      : 02_ddl_stg_src.sql
-- Proyecto    : Analytics TMS - Sunshine Deliveries
-- Esquema     : STG_SRC
-- Propósito   : Tablas de staging crudo para TrackItWeb, Carta Porte, Flota,
--               Estatus Diario, CFDI Ingreso 4.0 y Liquidaciones de Gastos.
-- Autor/Fecha : Oracle DW Architect / 2026-11-22
-- Fuente      : docs/Arquitectura-dw-analytics-tms.docx (§2, §4, §6)
--
-- Compatibilidad Oracle SE2 (ver .bob/rules/02-licensing-oracle-guardrails.md):
--   * NO usar PARTITION BY en definición de tablas.
--   * NO usar COMPRESS FOR OLTP / ADVANCED.
--   * Tablas estándar en tablespace USERS.
--
-- Idempotencia: el script puede ejecutarse más de una vez sin error (captura ORA-00955).
-- =============================================================================

SET DEFINE OFF;
WHENEVER SQLERROR EXIT SQL.SQLCODE;

-- 1. Tabla: STG_SRC.STG_TRACKIT_DESPACHO (Cabecera de Viaje TrackItWeb)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_TRACKIT_DESPACHO (
        TALON_FOLIO             VARCHAR2(30)    NOT NULL,
        FECHA_DESPACHO          TIMESTAMP       NOT NULL,
        HORA_DESPACHO           VARCHAR2(8)     NOT NULL,
        CODIGO_ECO              VARCHAR2(20)    NOT NULL,
        CODIGO_REMOLQUE         VARCHAR2(20),
        CODIGO_OPERADOR         VARCHAR2(20)    NOT NULL,
        TAG_IAVE                VARCHAR2(30),
        CLIENTE_ORIGEN          VARCHAR2(100),
        CLIENTE_DESTINO         VARCHAR2(100),
        ODOMETRO_INICIAL        NUMBER(10,2),
        ODOMETRO_FINAL          NUMBER(10,2),
        KMS_CARGADO             NUMBER(10,2)    DEFAULT 0 NOT NULL,
        KMS_VACIO               NUMBER(10,2)    DEFAULT 0 NOT NULL,
        KMS_TOTAL               NUMBER(10,2)    DEFAULT 0 NOT NULL,
        BATERIA_INICIAL_PCT     NUMBER(5,2),
        BATERIA_FINAL_PCT       NUMBER(5,2),
        KWH_CONSUMO             NUMBER(10,2)    DEFAULT 0,
        RENDIMIENTO_KMS_KWH     NUMBER(8,4)     DEFAULT 0,
        PESO_BRUTO_KG           NUMBER(12,2)    DEFAULT 0,
        TOTAL_PARADAS           NUMBER(4)       DEFAULT 0,
        ESTATUS_DESPACHO        VARCHAR2(30)    NOT NULL,
        FECHA_CIERRE            TIMESTAMP,
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_TRACKIT_DESPACHO IS 'Staging: Cabecera operativa de despachos y viajes extraída de TrackItWeb.';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_DESPACHO.TALON_FOLIO IS 'Número o folio de talón de viaje TMS (ej. GRD340).';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_DESPACHO.KMS_TOTAL IS 'Kilómetros totales del viaje (Kms Cargado + Kms Vacío).';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_DESPACHO.BATCH_ID IS 'Identificador de lote de ingesta/simulación.';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_DESPACHO.INGESTED_AT IS 'Timestamp de inserción en la capa de staging.';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_DESPACHO.SOURCE_SYSTEM IS 'Sistema de origen (TRACKITWEB).';

-- 2. Tabla: STG_SRC.STG_TRACKIT_PARADAS (Bitácora de Paradas e Hitos)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_TRACKIT_PARADAS (
        TALON_FOLIO             VARCHAR2(30)    NOT NULL,
        NUMERO_SECUENCIA        NUMBER(4)       NOT NULL,
        CODIGO_UBICACION        VARCHAR2(30)    NOT NULL,
        NOMBRE_UBICACION        VARCHAR2(100),
        TIPO_EVENTO             VARCHAR2(50)    NOT NULL,
        FECHA_HORA_PROGRAMADA   TIMESTAMP,
        FECHA_HORA_LLEGADA_REAL TIMESTAMP,
        FECHA_HORA_SALIDA_REAL  TIMESTAMP,
        UNIDAD_EMBARQUE_UE      VARCHAR2(50),
        KMS_TRAMO               NUMBER(10,2)    DEFAULT 0,
        LAG_LLEGADA_MINUTOS     NUMBER(10,2)    DEFAULT 0,
        LAG_SALIDA_MINUTOS      NUMBER(10,2)    DEFAULT 0,
        TIEMPO_ESTADIA_MINUTOS  NUMBER(10,2)    DEFAULT 0,
        ESTATUS_PARADA          VARCHAR2(30)    NOT NULL,
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_TRACKIT_PARADAS IS 'Staging: Bitácora de eventos y paradas de la ruta en TrackItWeb.';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_PARADAS.NUMERO_SECUENCIA IS 'Orden correlativo del hito/parada dentro del viaje (1..N).';
COMMENT ON COLUMN STG_SRC.STG_TRACKIT_PARADAS.TIPO_EVENTO IS 'Evento operativo (INICIO VIAJE, RECOLECCION, CARGA, DESCARGA, FIN VIAJE).';

-- 3. Tabla: STG_SRC.STG_CARTA_PORTE_CABECERA (CFDI Traslado con Complemento Carta Porte)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_CARTA_PORTE_CABECERA (
        UUID_CCP                VARCHAR2(36)    NOT NULL,
        FOLIO_DOCUMENTO         VARCHAR2(30),
        SERIE                   VARCHAR2(10),
        FECHA_EMISION           TIMESTAMP       NOT NULL,
        NUMERO_TALON            VARCHAR2(30)    NOT NULL,
        RFC_REMITENTE           VARCHAR2(20)    NOT NULL,
        NOMBRE_REMITENTE        VARCHAR2(150),
        RFC_DESTINATARIO        VARCHAR2(20)    NOT NULL,
        NOMBRE_DESTINATARIO     VARCHAR2(150),
        CODIGO_ECO              VARCHAR2(20)    NOT NULL,
        PLACA_VEHICULO          VARCHAR2(20),
        CONFIGURACION_SAT       VARCHAR2(20),
        NUMERO_REMOLQUE         VARCHAR2(20),
        PLACA_REMOLQUE          VARCHAR2(20),
        RFC_OPERADOR            VARCHAR2(20),
        NOMBRE_OPERADOR         VARCHAR2(120),
        LICENCIA_OPERADOR       VARCHAR2(30),
        UBICACION_ORIGEN_CP     VARCHAR2(10),
        UBICACION_DESTINO_CP    VARCHAR2(10),
        DISTANCIA_DECLARADA_KM  NUMBER(10,2)    DEFAULT 0,
        PESO_BRUTO_TOTAL_KG     NUMBER(12,2)    DEFAULT 0,
        NUMERO_TOTAL_MERCANCIAS NUMBER(6)       DEFAULT 0,
        USO_CFDI                VARCHAR2(10),
        MONEDA                  VARCHAR2(10),
        POLIZA_RESP_CIVIL       VARCHAR2(50),
        ASEGURADORA_RESP_CIVIL  VARCHAR2(100),
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_CARTA_PORTE_CABECERA IS 'Staging: Cabecera de CFDI Traslado con Complemento Carta Porte 3.0/3.1.';
COMMENT ON COLUMN STG_SRC.STG_CARTA_PORTE_CABECERA.UUID_CCP IS 'Identificador universal fiscal del comprobante CCP.';

-- 4. Tabla: STG_SRC.STG_CARTA_PORTE_MERCANCIAS (Partidas de Mercancía SAT)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_CARTA_PORTE_MERCANCIAS (
        UUID_CCP                VARCHAR2(36)    NOT NULL,
        NUMERO_TALON            VARCHAR2(30)    NOT NULL,
        NUMERO_PARTIDA          NUMBER(6)       NOT NULL,
        CLAVE_PRODUCTO_SAT      VARCHAR2(20)    NOT NULL,
        DESCRIPCION_PRODUCTO_SAT VARCHAR2(250),
        CANTIDAD                NUMBER(12,2)    DEFAULT 1 NOT NULL,
        CLAVE_UNIDAD_SAT        VARCHAR2(20),
        UNIDAD_SAT              VARCHAR2(50),
        PESO_KG                 NUMBER(12,2)    DEFAULT 0 NOT NULL,
        MATERIAL_PELIGROSO_FLAG VARCHAR2(5)     DEFAULT ''0'',
        CLAVE_MATERIAL_PELIGROSO VARCHAR2(20),
        EMBALAJE_SAT            VARCHAR2(20),
        UNIDAD_EMBARQUE_UE      VARCHAR2(50),
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_CARTA_PORTE_MERCANCIAS IS 'Staging: Partidas de mercancías amparadas en el Complemento Carta Porte.';
COMMENT ON COLUMN STG_SRC.STG_CARTA_PORTE_MERCANCIAS.CLAVE_PRODUCTO_SAT IS 'Clave de producto según catálogo c_ClaveProdServCP del SAT.';

-- 5. Tabla: STG_SRC.STG_FLOTA_UNIDADES (Catálogo Maestro de Flota)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_FLOTA_UNIDADES (
        CODIGO_ECO              VARCHAR2(20)    NOT NULL,
        TIPO_UNIDAD             VARCHAR2(30)    NOT NULL,
        PLACA                   VARCHAR2(20),
        ANIO_MODELO             NUMBER(4),
        MARCA                   VARCHAR2(50),
        MODELO                  VARCHAR2(50),
        CONFIGURACION_SAT       VARCHAR2(20),
        TIPO_PERMISO_SCT        VARCHAR2(20),
        NUMERO_PERMISO_SCT      VARCHAR2(50),
        PESO_BRUTO_MAX_KG       NUMBER(12,2)    DEFAULT 0,
        CAPACIDAD_CARGA_KG      NUMBER(12,2)    DEFAULT 0,
        NUMERO_SERIE_VIN        VARCHAR2(50),
        NUMERO_MOTOR            VARCHAR2(50),
        NUMERO_POLIZA_SEGURO    VARCHAR2(50),
        ASEGURADORA             VARCHAR2(100),
        VIGENCIA_POLIZA         DATE,
        ESTATUS_INVENTARIO      VARCHAR2(30)    NOT NULL,
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_FLOTA_UNIDADES IS 'Staging: Inventario maestro de las 100 unidades y remolques de la flota.';

-- 6. Tabla: STG_SRC.STG_FLOTA_ESTATUS_DIARIO (Disponibilidad y Estatus Diario de Patio)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_FLOTA_ESTATUS_DIARIO (
        FECHA_CORTE             DATE            NOT NULL,
        CODIGO_ECO              VARCHAR2(20)    NOT NULL,
        ESTATUS_PATIO           VARCHAR2(30)    NOT NULL,
        NUMERO_TALON            VARCHAR2(30),
        UBICACION_PATIO         VARCHAR2(50),
        KMS_ODOMETRO_DIA        NUMBER(10,2)    DEFAULT 0,
        KWH_CONSUMO_DIA         NUMBER(10,2)    DEFAULT 0,
        OBSERVACIONES           VARCHAR2(250),
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_FLOTA_ESTATUS_DIARIO IS 'Staging: Estatus diario de disponibilidad en patio/ruta para las 100 unidades.';
COMMENT ON COLUMN STG_SRC.STG_FLOTA_ESTATUS_DIARIO.ESTATUS_PATIO IS 'Estatus: DISPONIBLE_CON_VIAJE, DISPONIBLE_SIN_VIAJE, EN_MANTENIMIENTO, INACTIVO.';

-- 7. Tabla: STG_SRC.STG_CFDI_INGRESO (Facturación Comercial de Flete 4.0)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_CFDI_INGRESO (
        UUID_INGRESO            VARCHAR2(36)    NOT NULL,
        FACTURA_ID              VARCHAR2(30)    NOT NULL,
        SERIE                   VARCHAR2(10),
        FECHA_FACTURA           TIMESTAMP       NOT NULL,
        NUMERO_TALON            VARCHAR2(30)    NOT NULL,
        RFC_EMISOR              VARCHAR2(20)    NOT NULL,
        RFC_RECEPTOR            VARCHAR2(20)    NOT NULL,
        RAZON_SOCIAL_RECEPTOR   VARCHAR2(150),
        USO_CFDI                VARCHAR2(10),
        REGIMEN_FISCAL_RECEPTOR VARCHAR2(20),
        MONEDA                  VARCHAR2(10)    DEFAULT ''MXN'' NOT NULL,
        TIPO_CAMBIO             NUMBER(10,4)    DEFAULT 1.0,
        IMPORTE_SUBTOTAL        NUMBER(14,2)    DEFAULT 0 NOT NULL,
        IMPORTE_DESCUENTO       NUMBER(14,2)    DEFAULT 0,
        IMPORTE_IVA_TRASLADADO  NUMBER(14,2)    DEFAULT 0,
        IMPORTE_IVA_RETENIDO    NUMBER(14,2)    DEFAULT 0,
        IMPORTE_TOTAL           NUMBER(14,2)    DEFAULT 0 NOT NULL,
        METODO_PAGO             VARCHAR2(10),
        FORMA_PAGO              VARCHAR2(10),
        ESTATUS_FACTURA         VARCHAR2(20)    NOT NULL,
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_CFDI_INGRESO IS 'Staging: Facturación comercial por flete (CFDI Ingreso 4.0).';

-- 8. Tabla: STG_SRC.STG_LIQUIDACIONES_GASTOS (Gastos y Liquidación de Viajes)
BEGIN
    EXECUTE IMMEDIATE '
    CREATE TABLE STG_SRC.STG_LIQUIDACIONES_GASTOS (
        FOLIO_LIQUIDACION       VARCHAR2(30)    NOT NULL,
        FECHA_LIQUIDACION       TIMESTAMP       NOT NULL,
        NUMERO_TALON            VARCHAR2(30)    NOT NULL,
        CODIGO_ECO              VARCHAR2(20)    NOT NULL,
        CODIGO_REMOLQUE         VARCHAR2(20),
        CODIGO_OPERADOR         VARCHAR2(20)    NOT NULL,
        TIPO_GASTO              VARCHAR2(30)    NOT NULL,
        SUBTIPO_GASTO           VARCHAR2(50),
        IMPORTE_GASTO           NUMBER(14,2)    DEFAULT 0 NOT NULL,
        REFERENCIA_COMPROBANTE  VARCHAR2(50),
        ESTATUS_LIQUIDACION     VARCHAR2(20)    NOT NULL,
        BATCH_ID                VARCHAR2(64)    NOT NULL,
        INGESTED_AT             TIMESTAMP       DEFAULT SYSTIMESTAMP NOT NULL,
        SOURCE_SYSTEM           VARCHAR2(30)    NOT NULL
    )';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN RAISE; END IF;
END;
/

COMMENT ON TABLE STG_SRC.STG_LIQUIDACIONES_GASTOS IS 'Staging: Gastos de viaje (casetas IAVE, pago a operadores, mantenimiento).';

-- 9. Asignación de Permisos por Rol (Mínimo Privilegio)
DECLARE
    TYPE t_tab IS TABLE OF VARCHAR2(50);
    v_tabs t_tab := t_tab(
        'STG_TRACKIT_DESPACHO',
        'STG_TRACKIT_PARADAS',
        'STG_CARTA_PORTE_CABECERA',
        'STG_CARTA_PORTE_MERCANCIAS',
        'STG_FLOTA_UNIDADES',
        'STG_FLOTA_ESTATUS_DIARIO',
        'STG_CFDI_INGRESO',
        'STG_LIQUIDACIONES_GASTOS'
    );
BEGIN
    FOR i IN 1..v_tabs.COUNT LOOP
        EXECUTE IMMEDIATE 'GRANT SELECT, INSERT, UPDATE, DELETE ON STG_SRC.' || v_tabs(i) || ' TO SIM_WRITER';
        EXECUTE IMMEDIATE 'GRANT SELECT, INSERT, UPDATE, DELETE ON STG_SRC.' || v_tabs(i) || ' TO ETL_RUNNER';
    END LOOP;
END;
/

-- =============================================================================
EXIT;
-- Fin del script: 02_ddl_stg_src.sql
-- =============================================================================