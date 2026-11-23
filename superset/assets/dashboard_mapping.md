# Matriz de Mapeo y Trazabilidad — Dashboard TRA099R1 en Apache Superset

**Dashboard:** Reporte Diario de Operación — Analytics TMS  
**Código de Reporte:** TRA099R1  
**Slug:** `reporte-diario-operacion-tra099r1`  
**Base de Datos Metastore:** PostgreSQL (`superset-db`)  
**Conexión DW:** `Analytics_TMS_Oracle` (`BI_READER` en Thin Mode puro con `python-oracledb`)  
**Fecha de Publicación:** 2026-11-23  

---

## 1. Resumen de Bloques Funcionales y Filtros Nativos

El dashboard reproduce con total fidelidad la estructura visual, distribución y reglas de cálculo del reporte **TRA099R1** (*"Reporte Diario de Operación"*, `@docs/Draft-dashboard-TMS.pdf`), conciliando sus resultados contra los **datos reales del Data Warehouse en Fase 3** (90 días de backfill + corte cerrado al `2026-11-06` + aislamiento del día 91 parcial `2026-11-07`).

### Filtros Nativos Globales (*Native Filters*) y Pushdown Jinja

| Filtro | Tipo de Control | Dataset Target Principal | Parámetro Jinja / Columna | Configuración por Defecto |
|---|---|---|---|---|
| **Rango Temporal** | `filter_time` | Datasets 1 a 8 | `from_dttm`, `to_dttm` / `f.FECHA` | `2026-11-01 : 2026-11-06` (Corte cerrado backfill) |
| **Unidad (ECO)** | `filter_select` (multi) | Datasets 1 a 8 (`UNIDAD`) | `v.CODIGO_ECO` (`filter_values('CODIGO_ECO') or filter_values('UNIDAD')`) | Todas las unidades activas |
| **Operador** | `filter_select` (multi) | Datasets 2, 3, 4, 6, 7, 8 (`NOMBRE_OPERADOR`) | `o.NOMBRE_OPERADOR` (`filter_values('NOMBRE_OPERADOR') or filter_values('OPERADOR')`) | Todos los operadores |
| **Cliente** | `filter_select` (multi) | Datasets 2 a 8 (`CLIENTE`) | `c.RAZON_SOCIAL` (`filter_values('RAZON_SOCIAL') or filter_values('CLIENTE')`) | Todos los clientes |

---

## 2. Matriz de Componentes (Charts y Slices)

| Slice ID | Bloque Funcional | Título en Dashboard | Tipo Viz (`viz_type`) | Dataset Virtual | Dimensiones / Columnas Visibles | Métricas y Fórmulas | Filtros Jinja Activos |
|---|---|---|---|---|---|---|---|
| **1** | Bloque 1 | `B1 - Flota Total` | `big_number_total` | `ds_01_flota_diaria.sql` (ID 1) | N/A | `SUM(CANTIDAD_UNIDADES)` $\rightarrow$ `100 Unidades Activas` | Fecha corte, `UNIDAD` / `CODIGO_ECO` |
| **2** | Bloque 1 | `B1 - Unidades Con Viaje` | `big_number_total` | `ds_01_flota_diaria.sql` (ID 1) | N/A | `SUM(CASE WHEN ESTADO_FLOTA = 'Con Viaje' THEN CANTIDAD_UNIDADES ELSE 0 END)` $\rightarrow$ `56` (56.0%) | Fecha corte, `UNIDAD` / `CODIGO_ECO` |
| **3** | Bloque 1 | `B1 - Unidades Sin Viaje` | `big_number_total` | `ds_01_flota_diaria.sql` (ID 1) | N/A | `SUM(CASE WHEN ESTADO_FLOTA = 'Sin Viaje' THEN CANTIDAD_UNIDADES ELSE 0 END)` $\rightarrow$ `40` (40.0%) | Fecha corte, `UNIDAD` / `CODIGO_ECO` |
| **4** | Bloque 1 | `B1 - Unidades Inactivas` | `big_number_total` | `ds_01_flota_diaria.sql` (ID 1) | N/A | `SUM(CASE WHEN ESTADO_FLOTA = 'Inactivas' THEN CANTIDAD_UNIDADES ELSE 0 END)` $\rightarrow$ `4` (4.0%) | Fecha corte, `UNIDAD` / `CODIGO_ECO` |
| **13** | Bloque 1 | `B1 - Disponibilidad de Flota (Dona)` | `pie` (`donut: true`) | `ds_01_flota_diaria.sql` (ID 1) | `ESTADO_FLOTA` ('Con Viaje', 'Sin Viaje', 'Inactivas') | `SUM(CANTIDAD_UNIDADES)` $\rightarrow$ `56 Con Viaje, 40 Sin Viaje, 4 Inactivas` | Fecha corte, `UNIDAD` / `CODIGO_ECO` |
| **16** | Bloque 2 | `B2 - Indicadores de Operación (Día vs. Mes)` | `table` | `ds_02_operacion_dia_mes.sql` (ID 2) | `DESPACHOS_DIA`, `DESPACHOS_MES`, `CIERRES_DIA`, `CIERRES_MES`, `LIQ_CASETAS_DIA`, `LIQ_CASETAS_MES`, `LIQ_OPERADOR_DIA`, `LIQ_OPERADOR_MES`, `CFDI_TRASLADO_DIA`, `CFDI_TRASLADO_MES`, `FACTURADOS_DIA`, `FACTURADOS_MES` | Drill-Across sobre 4 hechos (`DESPACHO`, `GASTOS`, `CARTAPORTE`, `FACTURACION`) | Fecha corte, `UNIDAD`, `NOMBRE_OPERADOR`, `CLIENTE` |
| **17** | Bloque 3 | `B3 - Indicadores Generales (Día vs. Mes)` | `table` | `ds_03_generales_dia_mes.sql` (ID 3) | `TOTAL_KMS_DIA`, `TOTAL_KMS_MES`, `RENDIMIENTO_KMS_KWH_DIA`, `RENDIMIENTO_KMS_KWH_MES`, `PAGO_CASETAS_DIA`, `PAGO_CASETAS_MES`, `PAGO_OPERADORES_DIA`, `PAGO_OPERADORES_MES`, `FACTURADO_DIA`, `FACTURADO_MES` | Drill-Across sobre 3 hechos (`DESPACHO`, `GASTOS`, `FACTURACION`) con `NULLIF` en Kms/kWh | Fecha corte, `UNIDAD`, `NOMBRE_OPERADOR`, `CLIENTE` |
| **14** | Bloque 4 | `B4 - Top 5 Despachos por Cliente (Barras)` | `echarts_timeseries_bar` | `ds_04_top5_clientes.sql` (ID 4) | `CLIENTE` | `SUM(DESPACHOS_MES)`, `SUM(DESPACHOS_DIA)`, `row_limit = 5`, orden `DESPACHOS_MES DESC` | Fecha corte, `UNIDAD`, `NOMBRE_OPERADOR`, `CLIENTE` |
| **18** | Bloque 5 | `B5 - Top 10 Facturación por Unidad ECO (Barras)` | `echarts_timeseries_bar` | `ds_05_facturacion_top10_eco.sql` (ID 5) | `UNIDAD` (`CODIGO_ECO`) | `SUM(TOTAL_FACTURACION)`, `row_limit = 10`, unificación SCD2 por `CODIGO_ECO` | Fecha inicio, fecha corte, `UNIDAD`, `CLIENTE` |
| **10** | Bloque 6 | `B6 - Productividad de las Unidades (Mes)` | `table` | `ds_06_productividad_unidades.sql` (ID 6) | 13 columnas exactas: `UNIDAD`, `DESPACHOS_VIAJES`, `CERRADOS`, `KMS_CARGADO`, `KMS_VACIO`, `KMS_TOTAL`, `TOTAL_FACTURACION`, `COSTO_POR_KM`, `RENDIMIENTO_PROM_KMS_KWH`, `OPERADOR`, `MANTENIMIENTO`, `OTROS_GASTOS`, `TOTAL_COSTO` | Drill-Across estricto sobre 4 hechos (`DESPACHO`, `CARGA CCP`, `FACTURACION`, `GASTOS`) + `FULL OUTER JOIN` | `from_dttm`, `to_dttm`, `UNIDAD`, `NOMBRE_OPERADOR`, `CLIENTE` |
| **11** | Bloque 7 | `B7 - Productividad de los Operadores (Mes)` | `table` | `ds_07_productividad_operadores.sql` (ID 7) | 13 columnas exactas: `CLAVE_NOMBRE`, `DESPACHOS_VIAJES`, `CERRADOS`, `KMS_CARGADO`, `KMS_VACIO`, `KMS_TOTAL`, `TOTAL_FACTURACION`, `COSTO_POR_KM`, `RENDIMIENTO_PROM_KMS_KWH`, `OPERADOR`, `MANTENIMIENTO`, `OTROS_GASTOS`, `TOTAL_COSTO` | Drill-Across estricto sobre 4 hechos agrupados por Operador | `from_dttm`, `to_dttm`, `NOMBRE_OPERADOR`, `UNIDAD`, `CLIENTE` |
| **19** | Bloque 8 | `B8 - Análisis de Corredores Origen-Destino` | `table` | `ds_08_analisis_rutas_origen_destino.sql` (ID 8) | `CORREDOR_ESTADOS`, `ORIGEN`, `DESTINO`, `TOTAL_EMBARQUES_CCP`, `TOTAL_DISTANCIA_KM`, `TOTAL_PESO_KG`, `DISTANCIA_PROMEDIO_KM`, `PESO_PROMEDIO_KG` | Análisis geográfico de Carta Porte con Vistas de Rol (`VW_DIM_UBICACION_ORIGEN`, `VW_DIM_UBICACION_DESTINO`) | `from_dttm`, `to_dttm`, `UNIDAD`, `NOMBRE_OPERADOR`, `CLIENTE` |

---

## 3. Detalle de Columnas de las Tablas de Productividad (Bloques 6 y 7)

En cumplimiento estricto de la checklist técnica `@.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md`, el orden de las 13 columnas en los Bloques 6 y 7 es exactamente:

1. **Unidad** (`UNIDAD`) / **Clave/Nombre** (`CLAVE_NOMBRE` = `CODIGO_OPERADOR || ' - ' || NOMBRE_OPERADOR`)
2. **Despachos Viajes** (`DESPACHOS_VIAJES`)
3. **Cerrados** (`CERRADOS`)
4. **Kms. Cargado** (`KMS_CARGADO`)
5. **Kms. Vacío** (`KMS_VACIO`)
6. **Kms. Total** (`KMS_TOTAL`)
7. **Total Facturación** (`TOTAL_FACTURACION`)
8. **Costo/Km.** (`COSTO_POR_KM` $\rightarrow$ fórmula: Facturación / Kms Total)
9. **Rendimiento prom. (Kms/Kw)** (`RENDIMIENTO_PROM_KMS_KWH` $\rightarrow$ fórmula: Kms Total / kWh Consumo)
10. **Operador** (`OPERADOR` $\rightarrow$ costo de liquidación a operador)
11. **Mantenimiento** (`MANTENIMIENTO` $\rightarrow$ gasto de mantenimiento)
12. **Otros Gastos** (`OTROS_GASTOS` $\rightarrow$ casetas + otros gastos de liquidación)
13. **Total Costo** (`TOTAL_COSTO` $\rightarrow$ suma total de gastos liquidados)

---

## 4. Resultados de Validación en Vivo contra Oracle DW (Thin Mode)

| Escenario Evaluado | Filtros Aplicados | Estado de Ejecución | Latencia Promedio | Filas / Registros Devueltos | Cifras Clave Verificadas |
|---|---|---|---|---|---|
| **Corte Cerrado (Base)** | `2026-11-01 : 2026-11-06` | **PASS (12/12 charts)** | 48.2 ms | 1 fila (B1–B3), 3 filas (B1 Dona), 5 barras (B4), 10 barras (B5), 99 filas (B6), 15 filas (B7), 20 filas (B8) | Flota: 100 uds (56 c/viaje, 40 s/viaje, 4 inactivas). Dona: 56/40/4. Despachos: 56 día / 336 mes. Kms: 20,993.45 km día. |
| **Filtro Unitario ECO** | `UNIDAD = 'ECO01'` | **PASS (12/12 charts)** | 39.5 ms | Filtrado correcto (1 fila en B6, 1 barra en B5) | 4 despachos mes, 1,224.50 kms, Facturación: $173,210.45 |
| **Filtro Multi-valor ECO** | `UNIDAD IN ('ECO01','ECO02','ECO15')` | **PASS (12/12 charts)** | 41.1 ms | Filtrado multi-unidad correcto (3 filas en B6, 3 barras en B5) | 0 errores `ORA-`, cláusula `IN (...)` inyectada en CTEs |
| **Filtro Cliente** | `CLIENTE = 'PROCTER & GAMBLE...'` | **PASS (12/12 charts)** | 43.8 ms | Filtrado de cliente correcto (1 barra en B4) | 71 despachos mes para Procter & Gamble |
| **Filtro Operador** | `NOMBRE_OPERADOR = 'MARÍA JOSÉ LILIANA MEDINA'` | **PASS (12/12 charts)** | 42.1 ms | Filtrado de operador correcto (1 fila en B7) | 16 despachos mes para OP001 |
| **Aislamiento Día 91** | `2026-11-07 : 2026-11-07` | **PASS (12/12 charts)** | 38.2 ms | 1 fila (B1–B3), 3 filas (B1 Dona), 5 viajes nuevos en día 91 | 5 con viaje, 91 sin viaje, 4 inactivas. 5 despachos día, 3 cerrados, 2 abiertos. |
