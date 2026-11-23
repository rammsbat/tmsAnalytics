---
name: dbt-oracle-etl-pipeline
description: Construye y prueba modelos dbt-oracle para transformar datos desde STG_SRC hacia EDW_3FN y DWH_MART, incluyendo llaves subrogadas, SCD Tipo 1/2, snapshot diario de flota y Data Quality Screens.
---

# Workflow: Pipeline ELT en dbt-oracle

## Entradas Requeridas
- Usar `checklists/kimball_quality_screens.md` como lista de verificación de los Data Quality Screens.

## Pasos de Ejecución
1. Configurar `etl/dbt_tms/dbt_project.yml` y `etl/dbt_tms/profiles.template.yml` usando `type: oracle`, `protocol: tcp` (modo Thin; `thin` no es un valor válido: `DPY-4021`) con `host`/`port`/`service` y variables de entorno (`env_var`).
2. Construir modelos `staging/` (limpieza de nulos, trim de textos, normalización de fechas/RFCs).
3. Construir modelos `edw_3fn/` (deduplicación incremental por `MERGE` usando llaves naturales).
4. Construir modelos `marts/dimensions/`:
   - Implementar mapeo de llaves naturales a llaves subrogadas.
   - Manejar SCD Tipo 1 en catálogos estáticos y SCD Tipo 2 en `DIM_VEHICULO` / `DIM_OPERADOR` cuando cambien asignaciones clave.
5. Construir modelos `marts/facts/`:
   - Realizar *Surrogate Key Lookup* resolviendo llaves faltantes hacia `-1`.
   - Calcular métricas derivadas exactas: `LAG_LLEGADA_MINUTOS`, `LAG_SALIDA_MINUTOS`, `TIEMPO_ESTADIA_MINUTOS`, `CONTADOR_CERRADO`.
   - Implementar `FACT_SNAPSHOT_FLOTA_DIARIO` cruzando las 100 unidades maestras contra actividad diaria para obtener indicadores `1/0` de *Con Viaje*, *Sin Viaje* e *Inactiva*.
6. Implementar **Data Quality Screens** (`schema.yml` + tests SQL):
   - *Column screens:* `not_null`, `unique`, rangos válidos (`kms_total >= 0`, `peso_kg <= 35000`).
   - *Structure screens:* `relationships` entre todas las FKs de Facts y sus Dimensiones.
   - *Business rule screens:* `kms_cargado + kms_vacio = kms_total` y conciliación de conteo de viajes entre `EDW_3FN` y `FACT_DESPACHO_VIAJE`.
7. Ejecutar `dbt run` y `dbt test` dentro del contenedor `etl-runner` y reportar resultados.
