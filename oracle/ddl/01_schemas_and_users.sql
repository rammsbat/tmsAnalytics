-- =============================================================================
-- Script      : 01_schemas_and_users.sql
-- Proyecto    : Analytics TMS - Sunshine Deliveries
-- Esquema     : ADMIN / SYSTEM (PDB FREEPDB1)
-- Propósito   : Creación idempotente de 4 esquemas y 3 usuarios de mínimo privilegio
-- Autor/Fecha : Oracle DW Architect / 2026-11-22
-- Fuente      : docs/Arquitectura-dw-analytics-tms.docx (§4, §6)
--
-- Compatibilidad Oracle SE2 (ver .bob/rules/02-licensing-oracle-guardrails.md):
--   * Sin opciones licenciadas EE.
--   * Mínimo privilegio estricto por rol.
--
-- Idempotencia: el script puede ejecutarse más de una vez actualizando credenciales.
-- =============================================================================

SET VERIFY OFF;
SET ECHO OFF;
WHENEVER SQLERROR EXIT SQL.SQLCODE;

-- 1. Validación de Pluggable Database (FREEPDB1)
DECLARE
    v_con_name VARCHAR2(128);
BEGIN
    SELECT SYS_CONTEXT('USERENV', 'CON_NAME') INTO v_con_name FROM DUAL;
    IF UPPER(v_con_name) != 'FREEPDB1' THEN
        RAISE_APPLICATION_ERROR(-20001, 'ERROR: Este script debe ejecutarse conectado directamente a la PDB FREEPDB1. Conexión actual: ' || v_con_name);
    END IF;
END;
/

-- 2. Creación / Configuración idempotente de los 4 dueños de esquema
DECLARE
    PROCEDURE create_or_update_schema(p_user IN VARCHAR2) IS
        v_count NUMBER;
    BEGIN
        SELECT COUNT(*) INTO v_count FROM all_users WHERE username = UPPER(p_user);
        IF v_count = 0 THEN
            EXECUTE IMMEDIATE 'CREATE USER ' || UPPER(p_user) || ' NO AUTHENTICATION ACCOUNT LOCK DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP';
        ELSE
            EXECUTE IMMEDIATE 'ALTER USER ' || UPPER(p_user) || ' ACCOUNT LOCK';
        END IF;
        EXECUTE IMMEDIATE 'ALTER USER ' || UPPER(p_user) || ' QUOTA UNLIMITED ON USERS';
    END;
BEGIN
    create_or_update_schema('STG_SRC');
    create_or_update_schema('EDW_3FN');
    create_or_update_schema('DWH_MART');
    create_or_update_schema('BI_SEMANTIC');
END;
/

-- 3. Privilegios de Sistema para BI_SEMANTIC (soporte de Vistas, MV, Tablas contenedoras y Procedimientos)
GRANT CREATE VIEW TO BI_SEMANTIC;
GRANT CREATE MATERIALIZED VIEW TO BI_SEMANTIC;
GRANT CREATE TABLE TO BI_SEMANTIC;
GRANT CREATE PROCEDURE TO BI_SEMANTIC;

-- 4. Creación / Actualización idempotente de usuarios de aplicación con mínimo privilegio
-- &1 = Contraseña para BI_READER
-- &2 = Contraseña para SIM_WRITER
-- &3 = Contraseña para ETL_RUNNER

-- 4.1 BI_READER (Usuario de consulta para Apache Superset: solo SELECT en BI_SEMANTIC y DWH_MART)
DECLARE
    v_count NUMBER;
    v_pwd   VARCHAR2(256) := '&1';
BEGIN
    SELECT COUNT(*) INTO v_count FROM all_users WHERE username = 'BI_READER';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE USER BI_READER IDENTIFIED BY "' || v_pwd || '" DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP ACCOUNT UNLOCK';
    ELSE
        EXECUTE IMMEDIATE 'ALTER USER BI_READER IDENTIFIED BY "' || v_pwd || '" ACCOUNT UNLOCK';
    END IF;
END;
/
GRANT CREATE SESSION TO BI_READER;

-- 4.2 SIM_WRITER (Usuario del simulador de datos: solo DML sobre STG_SRC, sin RESOURCE ni cuota propia)
DECLARE
    v_count NUMBER;
    v_pwd   VARCHAR2(256) := '&2';
BEGIN
    SELECT COUNT(*) INTO v_count FROM all_users WHERE username = 'SIM_WRITER';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE USER SIM_WRITER IDENTIFIED BY "' || v_pwd || '" DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP ACCOUNT UNLOCK';
    ELSE
        EXECUTE IMMEDIATE 'ALTER USER SIM_WRITER IDENTIFIED BY "' || v_pwd || '" ACCOUNT UNLOCK';
    END IF;
END;
/
GRANT CREATE SESSION TO SIM_WRITER;

-- 4.3 ETL_RUNNER (Usuario de ejecución para dbt-oracle: gestión completa de transformaciones)
DECLARE
    v_count NUMBER;
    v_pwd   VARCHAR2(256) := '&3';
BEGIN
    SELECT COUNT(*) INTO v_count FROM all_users WHERE username = 'ETL_RUNNER';
    IF v_count = 0 THEN
        EXECUTE IMMEDIATE 'CREATE USER ETL_RUNNER IDENTIFIED BY "' || v_pwd || '" DEFAULT TABLESPACE USERS TEMPORARY TABLESPACE TEMP ACCOUNT UNLOCK';
    ELSE
        EXECUTE IMMEDIATE 'ALTER USER ETL_RUNNER IDENTIFIED BY "' || v_pwd || '" ACCOUNT UNLOCK';
    END IF;
    EXECUTE IMMEDIATE 'ALTER USER ETL_RUNNER QUOTA UNLIMITED ON USERS';
END;
/
GRANT CREATE SESSION, RESOURCE TO ETL_RUNNER;

-- =============================================================================
EXIT;
-- Fin del script: 01_schemas_and_users.sql
-- =============================================================================