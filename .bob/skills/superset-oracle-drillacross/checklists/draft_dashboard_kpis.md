# Checklist: KPIs del Draft Dashboard TMS

Fuente: `docs/Draft-dashboard-TMS.pdf` (reporte TRA099R1, "Reporte Diario de Operación", Sunshine Deliveries). Periodo: 01/11/2026 – 06/11/2026. Fecha del reporte: 06/11/2026.

Los nombres de bloque siguen el PDF. La fuente de hecho de cada KPI es una **propuesta** a validar en Fase 2/4; la spec no la fija KPI por KPI.

## Notas de interpretación
- **Flota (D4):** el PDF muestra 9 unidades (5 con viaje = 56%, 4 sin viaje = 44%, 0 inactivas). La spec y el docx usan 100 unidades con los mismos porcentajes. `fleet_size: 100` es decisión de la spec, no del Draft.
- **Columna "Costo/Km.":** en el PDF es Facturación ÷ Kms (ej. $89,088 ÷ 595 = $149.7277 para ECO01), no un costo. Los costos reales (Operador, Mantenimiento, Otros Gastos, Total Costo) están en $0.00 en todo el reporte.
- **Orden de columnas en las tablas de productividad:** el texto extraído del PDF es ambiguo. Por las sumas del total, la primera columna numérica suma 22 (= Despachos del mes) y la segunda suma 17 (= Cierres del mes). **Verificar visualmente contra el PDF antes de fijar los nombres de columna del dataset.**

## 1. Indicadores Diarios de Flota — `FACT_SNAPSHOT_FLOTA_DIARIO`
| KPI | Total | % | Hecho |
| :--- | :--- | :--- | :--- |
| Unidades C/Viaje | 5 | 56 | `FACT_SNAPSHOT_FLOTA_DIARIO` |
| Unidades S/Viaje | 4 | 44 | `FACT_SNAPSHOT_FLOTA_DIARIO` |
| Unidades Inactivas | 0 | 0 | `FACT_SNAPSHOT_FLOTA_DIARIO` |
| Total de Unidades | 9 | 100 | `FACT_SNAPSHOT_FLOTA_DIARIO` |
- [ ] KPIs de flota
- [ ] Gráfica de indicadores de flota (dona)

## 2. Indicadores de Operación (Día / Mes)
| KPI | Día | Mes | Hecho propuesto |
| :--- | :--- | :--- | :--- |
| Despachos | 5 | 22 | `FACT_DESPACHO_VIAJE` |
| Cierres | 1 | 17 | `FACT_DESPACHO_VIAJE` (`contador_cerrado`) |
| Liq. Casetas | 0 | 0 | `FACT_GASTOS_LIQUIDACION` |
| Liq. Operador | 0 | 0 | `FACT_GASTOS_LIQUIDACION` |
| CFDI de Traslado | 5 | 43 | `FACT_LINEAS_CARGA_CARTAPORTE` |
| Facturados | 57 | 63 | `FACT_FACTURACION_FLETE` |
- [ ] Los 6 KPIs
- Nota: "Facturados" (57 día / 63 mes) supera a los despachos (5 / 22). Es un conteo de facturas, no de viajes; confirmar con el Product Owner qué cuenta exactamente.

## 3. Indicadores Generales (Día / Mes)
| KPI | Día | Mes | Hecho propuesto |
| :--- | :--- | :--- | :--- |
| Total Kms. | 19 | 3,710 | `FACT_DESPACHO_VIAJE` |
| Rendimiento Kms/kWh | 1.46 | 6.35 | `FACT_DESPACHO_VIAJE` (kms ÷ kWh) |
| Pago Casetas | $0.00 | $0.00 | `FACT_GASTOS_LIQUIDACION` |
| Pago Operadores | $0.00 | $0.00 | `FACT_GASTOS_LIQUIDACION` |
| Facturado | $448,224.00 | $492,768.00 | `FACT_FACTURACION_FLETE` |
- [ ] Los 5 KPIs

## 4. Top 5 — Despachos / Cliente (Día / Mes)
| Cliente | Día | Mes |
| :--- | :--- | :--- |
| PROCTER & GAMBLE MANUFACTURING | 5 | 22 |
- [ ] Top 5 por cliente (`FACT_DESPACHO_VIAJE` + `DIM_CLIENTE`)

## 5. Gráfica Facturación por Unidad (Top 10)
- [ ] Facturación del mes por unidad (`FACT_FACTURACION_FLETE` + `DIM_VEHICULO`). Referencia: ECO02 = $133,632.00.

## 6. Productividad de las Unidades (Mes) — Drill-Across
Unidades con datos en el PDF: ECO01 a ECO06 (6 unidades).
| Unidad | Facturación | Rend. Kms/kWh | Kms Total |
| :--- | :--- | :--- | :--- |
| ECO01 | $89,088.00 | 2.86 | 595 |
| ECO02 | $133,632.00 | 5.25 | 868 |
| ECO03 | $0.00 | 0 | 0 |
| ECO04 | $98,368.00 | 8.21 | 1,512 |
| ECO05 | $90,016.00 | 5.04 | 394 |
| ECO06 | $81,664.00 | 5.86 | 341 |
| **Total** | **$492,768.00** | **6.35** | **3,710** |
- Columnas del reporte: Despachos, Cerrados, Kms (Total, Vacío, Cargado), Facturación, Rendimiento, Facturación/Km, Operador, Mantenimiento, Otros Gastos, Total Costo.
- Hechos combinados por CTE: `FACT_DESPACHO_VIAJE`, `FACT_LINEAS_CARGA_CARTAPORTE`, `FACT_FACTURACION_FLETE`, `FACT_GASTOS_LIQUIDACION`.
- [ ] Tabla con `FULL OUTER JOIN` entre CTE, sin joins directos entre hechos
- [ ] Conciliación: total facturación = $492,768.00; total Kms = 3,710 (Vacío 0, Cargado 3,710)

## 7. Productividad de los Operadores (Mes) — Drill-Across
Operadores con datos en el PDF: 15 (total de operadores = 15). Mismas columnas que el bloque 6, por operador (clave y nombre).
- [ ] Tabla con `FULL OUTER JOIN` entre CTE
- [ ] Conciliación: total facturación = $492,768.00; total Kms = 3,710

## Cobertura global
- [ ] 7/7 bloques renderizan sin errores ni productos cartesianos.
- [ ] El filtro de fecha empuja el predicado `WHERE` a cada CTE (verificar con `EXPLAIN PLAN`).
