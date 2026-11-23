-- =============================================================================
-- Macro      : refresh_semantic_layer.sql
-- Propósito  : Invoca el procedimiento AUTHID DEFINER BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC
--              desde ETL_RUNNER para refrescar de forma atómica y completa las
--              Vistas Materializadas SE2 de la capa semántica.
--              Se ejecuta únicamente durante 'dbt run' o 'dbt build' (no en 'dbt test').
-- =============================================================================

{% macro refresh_semantic_layer() %}
    {% if flags.WHICH in ('run', 'build') %}
        {% set refresh_sql %}
            BEGIN
                BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC;
            END;
        {% endset %}
        {% do log("Refrescando Vistas Materializadas en BI_SEMANTIC...", info=true) %}
        {% do run_query(refresh_sql) %}
        {% do log("Refresco de BI_SEMANTIC completado exitosamente.", info=true) %}
    {% endif %}
{% endmacro %}
