# Checklist: Kimball Data Quality Screens (dbt test)

Fuente: `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` paso 6. Criterio de aceptación de Fase 3: 100% de los tests en verde.

## 1. Column screens
- [ ] `not_null` en llaves subrogadas, llaves naturales y todas las FK de hechos.
- [ ] `unique` en llaves subrogadas y llaves naturales de dimensiones (por versión vigente en SCD Tipo 2).
- [ ] Rango: `kms_total >= 0`.
- [ ] Rango: `peso_kg <= 35000` (límite de verificación de la spec; el simulador usa un máximo de 29,685 kg por unidad C3R2).
- [ ] Rango: métricas de conteo (`contador_*`, `*_indicador`) solo con valores `0` o `1`.

## 2. Structure screens
- [ ] `relationships`: toda FK de cada tabla de hechos apunta a una dimensión existente.
  - [ ] `FACT_DESPACHO_VIAJE`
  - [ ] `FACT_EVENTOS_PARADA`
  - [ ] `FACT_LINEAS_CARGA_CARTAPORTE`
  - [ ] `FACT_FACTURACION_FLETE`
  - [ ] `FACT_GASTOS_LIQUIDACION`
  - [ ] `FACT_SNAPSHOT_FLOTA_DIARIO`
- [ ] Cada una de las 10 dimensiones conformadas contiene la fila `-1` / `DESCONOCIDO`.
- [ ] Ninguna FK de un hecho es `NULL`; las llaves faltantes se resuelven a `-1`.

## 3. Business rule screens
- [ ] `kms_cargado + kms_vacio = kms_total` en `FACT_DESPACHO_VIAJE`.
- [ ] Conciliación: conteo de viajes en `EDW_3FN` = conteo en `FACT_DESPACHO_VIAJE`.
- [ ] `FACT_SNAPSHOT_FLOTA_DIARIO`: por día, `unidad_con_viaje_indicador + unidad_sin_viaje_indicador + unidad_inactiva_indicador = flota_total_indicador` por unidad, y el total diario iguala `fleet_size`.
- [ ] Ningún join directo entre tablas de hechos en modelos o vistas (ver `.bob/rules/01-kimball-architecture.md`).

## 4. Ejecución
- [ ] `dbt run` y `dbt test` ejecutados en el contenedor `etl-runner`.
- [ ] Resultados reportados con conteo de tests aprobados y fallidos.
