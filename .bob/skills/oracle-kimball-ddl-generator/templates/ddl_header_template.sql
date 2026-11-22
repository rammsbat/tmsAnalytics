-- =============================================================================
-- Script      : <NN_nombre_del_script>.sql
-- Proyecto    : Analytics TMS - Sunshine Deliveries
-- Esquema     : <STG_SRC | EDW_3FN | DWH_MART | BI_SEMANTIC>
-- Propósito   : <descripción breve de los objetos que crea este script>
-- Autor/Fecha : <autor> / <AAAA-MM-DD>
-- Fuente      : docs/Arquitectura-dw-analytics-tms.docx (sección <N>)
--
-- Compatibilidad Oracle SE2 (ver .bob/rules/02-licensing-oracle-guardrails.md):
--   * NO usar PARTITION BY en definición de tablas (Partitioning es opción de pago).
--   * NO usar COMPRESS FOR OLTP / ADVANCED (Advanced Compression es opción de pago).
--   * NO usar ENABLE QUERY REWRITE en vistas materializadas (requiere EE).
--   * Solo índices B-Tree estándar y estadísticas con DBMS_STATS.
--
-- Idempotencia: el script debe poder ejecutarse más de una vez sin error.
-- =============================================================================

-- Patrón idempotente para crear un objeto solo si no existe (ORA-00955 = nombre en uso).
-- Reemplazar <CREATE_STATEMENT> por el DDL real.
BEGIN
    EXECUTE IMMEDIATE '<CREATE_STATEMENT>';
EXCEPTION
    WHEN OTHERS THEN
        IF SQLCODE != -955 THEN
            RAISE;
        END IF;
END;
/

-- Documentación del catálogo (obligatoria en toda tabla y columna):
-- COMMENT ON TABLE  <ESQUEMA>.<TABLA>          IS '<descripción y grano>';
-- COMMENT ON COLUMN <ESQUEMA>.<TABLA>.<COLUMNA> IS '<descripción>';

-- Dimensiones: incluir la fila dummy para integridad referencial.
-- INSERT ... (<SK>, ..., 'DESCONOCIDO') con <SK> = -1, solo si no existe.
