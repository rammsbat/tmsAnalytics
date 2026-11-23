-- =============================================================================
-- Script      : 06_etl_grants.sql
-- Proyecto    : Analytics TMS - Sunshine Deliveries
-- Esquema     : STG_SRC (ejecutar como SYSTEM/ADMIN conectado a PDB FREEPDB1)
-- Propósito   : Ajuste de mínimo privilegio de Fase 3 (decisión D5 del plan
--               docs/fase-3-sim-etl-plan.md): SIM_WRITER solo INSERT/UPDATE/SELECT
--               sobre STG_SRC. Se revoca DELETE de las 8 tablas de staging.
-- Autor/Fecha : Oracle DW Architect / 2026-11-23
-- Referencia  : .bob/rules/03-security-and-secrets.md (§3)
--
-- Compatibilidad Oracle SE2: solo DCL estándar.
--
-- Idempotencia: puede ejecutarse varias veces; captura ORA-01927 (el privilegio
-- ya no está otorgado / no fue otorgado por el revocador) y ORA-00942.
-- =============================================================================

SET DEFINE OFF;
SET VERIFY OFF;
SET SERVEROUTPUT ON;
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

-- 2. REVOKE DELETE para SIM_WRITER sobre las 8 tablas de STG_SRC (idempotente)
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
        BEGIN
            EXECUTE IMMEDIATE 'REVOKE DELETE ON STG_SRC.' || v_tabs(i) || ' FROM SIM_WRITER';
            DBMS_OUTPUT.PUT_LINE('REVOKE DELETE aplicado: STG_SRC.' || v_tabs(i));
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE = -1927 THEN
                    DBMS_OUTPUT.PUT_LINE('Sin cambios (ORA-01927, DELETE ya revocado): STG_SRC.' || v_tabs(i));
                ELSE
                    RAISE;
                END IF;
        END;
    END LOOP;
END;
/

-- =============================================================================
EXIT;
-- Fin del script: 06_etl_grants.sql
-- =============================================================================
