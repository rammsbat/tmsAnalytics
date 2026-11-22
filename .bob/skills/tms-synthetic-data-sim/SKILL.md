---
name: tms-synthetic-data-sim
description: Implementa el simulador de datos sintéticos en Python para el sistema TMS (TrackItWeb, Carta Porte, Flota de 100 unidades, CFDI Ingreso 4.0 y Liquidaciones) con modos backfill e incremental.
---

# Workflow: Simulador de Datos Sintéticos TMS

## Reglas de Realismo Obligatorias
- Referenciar los ejemplos reales de `@docs/Draft-dashboard-TMS.pdf` y `@docs/Arquitectura-dw-analytics-tms.docx` (ej. Procter & Gamble, `ECO01`..`ECO100`, `CAJA05`, ubicaciones `IMESA`, `SMO`, `MERCURIO`, productos SAT `12161902` / `24112701`).
- Usar `templates/sim_rules_schema.yaml` como esquema de `simulator/config_rules.yaml`.

## Pasos de Ejecución
1. Definir `simulator/config_rules.yaml` con parámetros configurables:
   - `seed`: semilla determinista.
   - `fleet_size`: 100 unidades (porcentaje configurable con viaje ~56%, sin viaje ~40%, inactivas ~4%).
   - `date_range_backfill`: últimos 90 días (con preset opcional hasta `2026-11-06` para replicar el Draft Dashboard).
   - `pricing_model`: tarifa base + tarifa/km + recargos para CFDI Ingreso 4.0.
   - `cost_model`: peajes IAVE, pago por km/viaje a operador y costos de mantenimiento.
2. Implementar generadores modulares en `simulator/src/generators/`:
   - `fleet_master.py`: pobla catálogos base sin duplicados.
   - `trackit_ops.py`: genera despachos diarios, odómetros, consumo kWh (rendimiento objetivo 2.0–11.6 km/kWh), 4–12 paradas con retrasos gaussianos y eventos `FIN VIAJE`.
   - `carta_porte.py`: genera partidas de mercancía por viaje respetando el peso máximo vehicular.
   - `finance_erp.py`: emite CFDIs de Ingreso 4.0 y liquidaciones vinculadas por `NUMERO_TALON`.
3. Implementar `db_loader.py` usando `oracledb` en Thin Mode con `cursor.executemany()` en lotes de 5,000 filas y *bind variables*.
4. Implementar CLI `main.py` soportando:
   - `--mode backfill --days 90`
   - `--mode incremental --trips 5`
   - `--dry-run` (genera estadísticas de validación sin escribir en Oracle).
5. Agregar pruebas unitarias (`pytest`) verificando que no existan pesos negativos, fechas invertidas ni violaciones de integridad referencial.
