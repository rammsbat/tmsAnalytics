# Plan de Ejecución — Fase 4: Capa Semántica, Virtual Datasets y Dashboards en Apache Superset

**Proyecto:** Analytics TMS — Sunshine Deliveries  
**Fase:** Fase 4 — Capa Semántica y Dashboards en Apache Superset (Días 12–15)  
**Modo Principal:** `bi-superset-dev`  
**Skill:** `superset-oracle-drillacross`  
**Conexión Objetivo:** `Analytics_TMS_Oracle` (`BI_READER` sobre esquemas `BI_SEMANTIC` y `DWH_MART`)  
**Fecha de Elaboración:** 2026-11-23  
**Estado General:** `[ ] pendiente de aprobación`  

---

## 1. Top-Level Overview

El objetivo de la **Fase 4** es construir, validar y empaquetar de forma reproducible la capa analítica y de visualización en **Apache Superset** (v4.1.1 con PostgreSQL 16 y caché Valkey 8). La plataforma consume exclusivamente la capa `BI_SEMANTIC` y `DWH_MART` de Oracle Database mediante el usuario de solo lectura `BI_READER`.

Esta fase materializa los **7 bloques funcionales** del reporte operativo TRA099R1 (*"Reporte Diario de Operación"*, `@docs/Draft-dashboard-TMS.pdf`) y su checklist técnica `@.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md`, adoptando el PDF como **especificación visual, de distribución y de fórmulas de cálculo**, y conciliando los resultados contra las **cifras reales persistidas en el DW en Fase 3** (90 días de backfill + corte cerrado al `2026-11-06` + aislamiento del día 91 parcial `2026-11-07`).

Pilares de la solución:
1. **Virtual Datasets con Jinja Templating y Drill-Across:** Consultas multi-hecho estructuradas como una CTE por hecho + `FULL OUTER JOIN` sobre dimensiones conformadas compartidas, prohibiendo uniones directas Fact↔Fact y evitando productos cartesianos (*fan traps*).
2. **Filter Pushdown en Oracle SE2:** Inyección de predicados dinámicos de tiempo (`from_dttm`, `to_dttm`) y dimensiones (`filter_values(...) | where_in`) dentro de **cada** CTE antes del join y agregación, optimizando el rendimiento en Oracle SE2 sin opciones de pago.
3. **Manejo de SCD Tipo 2 en Drill-Across:** Agregación por la llave natural `CODIGO_ECO` (cruzando internamente por `ID_VEHICULO` contra `VW_DIM_VEHICULO`) para que vehículos con múltiples versiones históricas (ej. `ECO15` con versión v1 y v2 tras el día 91) se consoliden en una única fila de reporte unificada.
4. **Manejo No Aditivo y Períodos:** Tratamiento no aditivo de `DISTANCIA_DECLARADA_KM` entre partidas de un mismo CCP y derivación explícita de métricas de *Día* (fecha de corte seleccionada) y *Mes* (mes acumulado a la fecha de corte).
5. **Reproducibilidad y Cero Secretos:** Exportación de assets versionables (SQLs Jinja, mapeo en `dashboard_mapping.md` y bundles YAML/JSON importables vía API/CLI sin credenciales), validación automatizada contra Oracle y auditoría Actor-Crítico con 0 hallazgos BLOCKER.

---

## 2. Sub-Tasks de Ejecución

### ST-0 — Pre-Vuelo y Verificación de Entorno de BI
**Intent:** Verificar la operatividad de los servicios del stack de BI (Superset App, Metastore PostgreSQL, Caché/Broker Valkey, Celery Worker/Beat) y la conectividad `BI_READER` en Thin Mode estricto hacia Oracle DW.

**Expected Outcomes:**
- Servicios `superset-app`, `superset-worker`, `superset-beat`, `superset-db` y `superset-valkey` en estado *healthy* en Docker Compose.
- Conexión `Analytics_TMS_Oracle` registrada en el metastore con URI `oracle+cx_oracle://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1`. **Nota de Arquitectura:** En SQLAlchemy 1.4 (utilizado por Superset 4.1.1), el dialecto registrado es `oracle+cx_oracle`, el cual es interceptado y puenteado a `python-oracledb` puro mediante `sys.modules["cx_Oracle"] = oracledb` en `superset_config.py`. Se verificó en vivo que la conexión opera en **Thin Mode estricto** (`is_thin_mode() == True`, tipo `<class 'oracledb.Connection'>`).
- Parámetros analíticos verificados: `ENABLE_TEMPLATE_PROCESSING: True`, `allow_run_async: True`, `arraysize: 1000`.
- Consultas de verificación ejecutadas exitosamente con `BI_READER` sobre `BI_SEMANTIC.VW_DIM_FECHA`, `BI_SEMANTIC.MV_METRICAS_FLOTA_DIARIA` y `BI_SEMANTIC.MV_PRODUCTIVIDAD_ECO_MENSUAL`.

**Todo List:**
1. Validar el estado de salud de los servicios de Superset en Docker.
2. Confirmar que `superset_config.py` y `bootstrap.sh` operan en Thin Mode estricto con `python-oracledb`.
3. Probar la conectividad SQL desde Superset SQL Lab hacia Oracle usando `Analytics_TMS_Oracle`.

**Relevant Context:** `superset/superset_config.py`, `superset/bootstrap.sh`, `docker-compose.yml`, `oracle/ddl/05_views_bi_semantic.sql`.
**Status:** `[x] done` (Servicios healthy, Thin Mode oracledb verificado con is_thin_mode()==True, flags activos, consultas de prueba OK)

---

### ST-1 — Creación de Virtual Datasets Jinja con Patrón Drill-Across
**Intent:** Escribir y validar en `superset/assets/datasets/` las consultas SQL con Jinja templating para los 7 bloques del Draft Dashboard y análisis de rutas, aplicando Drill-Across estricto, consolidación SCD Tipo 2 por llave natural y nombres reales de columnas de `BI_SEMANTIC`.

**Expected Outcomes:**
- `superset/assets/datasets/ds_01_flota_diaria.sql`: Bloque 1 (Indicadores diarios de flota y dona: Unidades con viaje, sin viaje, inactivas, total y % disponibilidad sobre `MV_METRICAS_FLOTA_DIARIA` / `VW_FACT_SNAPSHOT_FLOTA_DIARIO`).
- `superset/assets/datasets/ds_02_operacion_dia_mes.sql`: Bloque 2 (Indicadores de Operación Día vs. Mes: Despachos, Cierres, Liq. Casetas, Liq. Operador, CFDI Traslado, Facturados. Derivación dinámica: el *Día* corresponde a `TRUNC(TO_DATE('{{ to_dttm }}', 'YYYY-MM-DD HH24:MI:SS'))` [o fecha de corte] y el *Mes* al rango `TRUNC(fecha, 'MM')` hasta la fecha de corte; unión vía `FULL OUTER JOIN` entre CTEs de hechos).
- `superset/assets/datasets/ds_03_generales_dia_mes.sql`: Bloque 3 (Indicadores Generales Día vs. Mes: Total Kms, Rendimiento Kms/kWh con `NULLIF`, Pago Casetas, Pago Operadores, Total Facturado $; misma lógica temporal Día/Mes que ds_02).
- `superset/assets/datasets/ds_04_top5_clientes.sql`: Bloque 4 (Ranking Top 5 Clientes por Despachos Día vs. Mes, cruzando `VW_FACT_DESPACHO_VIAJE` y `VW_DIM_CLIENTE` usando la columna real `RAZON_SOCIAL`).
- `superset/assets/datasets/ds_05_facturacion_top10_eco.sql`: Bloque 5 (Top 10 Facturación por Unidad ECO en el mes, agrupando por `v.CODIGO_ECO` y uniendo internamente `fac.ID_VEHICULO = v.ID_VEHICULO` para unificar versiones SCD2 de `DIM_VEHICULO`).
- `superset/assets/datasets/ds_06_productividad_unidades.sql`: Bloque 6 (Matriz mensual de productividad por Unidad ECO: Despachos, Cerrados, Kms Cargado, Kms Vacío, Kms Total, Facturación, Costo/Km [Fact/Km], Rendimiento Kms/kWh, Operador, Mantenimiento, Otros Gastos, Total Costo; CTEs de 4 hechos agregadas por `CODIGO_ECO` [SCD2 unified] + `FULL OUTER JOIN`, con cálculo no aditivo de `DISTANCIA_DECLARADA_KM`).
- `superset/assets/datasets/ds_07_productividad_operadores.sql`: Bloque 7 (Matriz mensual de productividad por Operador: Despachos, Cerrados, Kms Cargado/Vacío/Total, Facturación, Costo/Km, Rendimiento Kms/kWh, Costos; CTEs agregadas por `o.CODIGO_OPERADOR` / `o.NOMBRE_OPERADOR` + `FULL OUTER JOIN`).
- `superset/assets/datasets/ds_08_analisis_rutas_origen_destino.sql`: Dataset para análisis de corredores utilizando las vistas de rol `VW_DIM_UBICACION_ORIGEN`, `VW_DIM_UBICACION_DESTINO` y `VW_DIM_UBICACION_PARADA`.

**Todo List:**
1. Crear cada archivo `.sql` en `superset/assets/datasets/` con CTEs independientes por tabla de hechos.
2. Inyectar macros Jinja con manejo seguro de filtros vacíos:
   - Filtros de fecha: `{% if from_dttm %} AND f.FECHA >= TO_DATE('{{ from_dttm }}', 'YYYY-MM-DD HH24:MI:SS') {% endif %}` y `{% if to_dttm %} AND f.FECHA <= TO_DATE('{{ to_dttm }}', 'YYYY-MM-DD HH24:MI:SS') {% endif %}`.
   - Filtros dimensionales: `{% if filter_values('CODIGO_ECO') %} AND v.CODIGO_ECO IN ({{ filter_values('CODIGO_ECO') | where_in }}) {% endif %}` (y análogo para cliente y operador).
3. Asegurar agregación por llave natural (`CODIGO_ECO`, `CODIGO_OPERADOR`, `RAZON_SOCIAL`) para resolver SCD2 en dimensiones.
4. Aplicar `NULLIF(denominador, 0)` en todas las divisiones de ratio y rendimiento.

**Relevant Context:** `.bob/rules-bi-superset-dev/01-drillacross-jinja-standards.md`, `.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md`, `oracle/ddl/05_views_bi_semantic.sql`.
**Status:** `[x] done` (8 Virtual Datasets creados en superset/assets/datasets/, registrados en Superset Metastore y probados al 100% con y sin filtros)

---

### ST-2 — Validación de Filter Pushdown y Compatibilidad Oracle SE2
**Intent:** Verificar mediante planes de ejecución (`EXPLAIN PLAN`) ejecutados en sesión estándar de `BI_READER` (fuera del MCP de solo lectura) que los predicados dinámicos de Jinja se empujan eficazmente dentro de cada subconsulta en Oracle SE2.

**Expected Outcomes:**
- Planes de ejecución (`DBMS_XPLAN.DISPLAY`) ejecutados mediante script Python/oracledb desde `superset-app` o `oracle-dw` confirmando que los filtros de rango de fechas y dimensiones se aplican en las ramas de acceso a tablas antes de agregaciones y `FULL OUTER JOIN`.
- Verificación estricta de compatibilidad SE2: cero cláusulas `PARTITION BY`, cero `COMPRESS FOR OLTP`, cero `ENABLE QUERY REWRITE`.
- Verificación de uso de índices B-Tree estándar de `DWH_MART` (`oracle/ddl/04_ddl_dwh_mart.sql`).
- Tiempos de respuesta de cada Virtual Dataset $< 1.5$ segundos con caché fría y $< 300$ ms con caché Valkey.

**Todo List:**
1. Diseñar script de verificación de planes de ejecución (`tools/verify_explain_plans.py`) que conecte con `BI_READER` vía `python-oracledb` estándar (no MCP) y genere `EXPLAIN PLAN FOR <dataset_sql>` + `SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY())`.
2. Validar que no existen productos cartesianos (`MERGE JOIN CARTESIAN`) en las uniones de CTEs.
3. Confirmar que los predicados de fecha se empujan a los filtros de partición/rango de fechas en cada CTE.

**Relevant Context:** `.bob/rules/02-licensing-oracle-guardrails.md`, `oracle/ddl/04_ddl_dwh_mart.sql`, `oracle/ddl/05_views_bi_semantic.sql`.
**Status:** `[x] done` (16 planes evaluados con EXPLAIN PLAN + DBMS_XPLAN en BI_READER: 0 cartesianos en hechos, filter pushdown verificado en CTEs, latencia promedio en frío 45.8 ms y sanity check 98 vs 99 unidades validado)

---

### ST-3 — Construcción y Maquetación del Dashboard "Reporte Diario de Operación"
**Intent:** Ensamblar y maquetar el Dashboard en Apache Superset reproduciendo la distribución visual del Draft Dashboard, configurando filtros nativos y trazabilidad 1:1.

**Expected Outcomes:**
- Dashboard titulado **"Reporte Diario de Operación — Analytics TMS"** (código TRA099R1) conteniendo los 7 bloques:
  - **Bloque 1:** Indicadores Diarios de Flota (KPIs de Total, Con Viaje, Sin Viaje, Inactivas + Gráfica de Dona de disponibilidad).
  - **Bloque 2:** Grid de KPIs de Operación (Día vs. Mes: Despachos, Cierres, Liq. Casetas, Liq. Operador, CFDI Traslado, Facturados).
  - **Bloque 3:** Grid de KPIs Generales (Día vs. Mes: Total Kms, Rendimiento Kms/kWh, Pago Casetas, Pago Operadores, Facturado $).
  - **Bloque 4:** Gráfica de Barras / Tabla Top 5 Despachos por Cliente (Día vs. Mes) usando `RAZON_SOCIAL`.
  - **Bloque 5:** Gráfica de Barras Top 10 Facturación por Unidad ECO (consolidada por `CODIGO_ECO`).
  - **Bloque 6:** Tabla detallada de Productividad de las Unidades (13 columnas exactas según `draft_dashboard_kpis.md`).
  - **Bloque 7:** Tabla detallada de Productividad de los Operadores (13 columnas exactas por Operador).
- Filtros nativos globales (*Native Filters*):
  - Rango Temporal con fecha de corte por defecto `2026-11-06` (Día de corte cerrado del backfill) y selector mensual (`2026-11-01` a `2026-11-06`).
  - Filtro por Unidad (`CODIGO_ECO`).
  - Filtro por Operador (`NOMBRE_OPERADOR`).
  - Filtro por Cliente (`RAZON_SOCIAL`).
- Manejo visual del día 91 parcial (`2026-11-07`): el dashboard muestra por defecto el período cerrado al `2026-11-06`, permitiendo seleccionar `2026-11-07` de forma explícita sin distorsionar los totales consolidados.
- Documento de trazabilidad: `superset/assets/dashboard_mapping.md`.

**Todo List:**
1. Crear cada Chart en Superset asociado a su Virtual Dataset correspondiente.
2. Ensamblar el layout del Dashboard organizando los 7 bloques.
3. Configurar filtros nativos y sus alcances (*filter scopes*).
4. Redactar `superset/assets/dashboard_mapping.md` mapeando Chart ID, Dataset, Parámetros Jinja, Filtros y Métricas.

**Relevant Context:** `docs/Draft-dashboard-TMS.pdf`, `.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md`.  
**Status:** `[ ] pending`

---

### ST-4 — Exportación Reproducible y Versionado de Assets
**Intent:** Implementar un mecanismo automatizado y reproducible para exportar e importar los assets de Superset (Dashboards, Charts, Datasets) mediante bundles YAML/JSON libres de contraseñas y secretos, garantizando que una re-importación no sobreescriba ni rompa las credenciales de `Analytics_TMS_Oracle`.

**Expected Outcomes:**
- Exportación estructurada en `superset/assets/` de los assets generados (bundle ZIP/YAML exportado vía CLI de Superset o REST API `/api/v1/assets/export`).
- Sanitización estricta: los metadatos exportados de la base de datos `Analytics_TMS_Oracle` NO contienen contraseñas en texto claro (referencian variables de entorno o mantienen la configuración segura del metastore).
- Script reproducible de importación/restauración (`tools/import_superset_assets.py` o comando CLI) que permite recrear el dashboard y datasets desde cero en cualquier entorno nuevo sin intervención manual.

**Todo List:**
1. Ejecutar la exportación de assets desde Superset CLI / API hacia `superset/assets/`.
2. Validar que la exportación contenga los metadatos de los 7 bloques, datasets y filtros nativos.
3. Auditar los archivos generados para confirmar Cero Secretos (Regla 03).
4. Probar la re-importación en frío para verificar idempotencia y conservación de credenciales.

**Relevant Context:** `.bob/rules/03-security-and-secrets.md`, `superset/bootstrap.sh`.  
**Status:** `[ ] pending`

---

### ST-5 — Suite de Conciliación de KPIs Automatizada contra Oracle DW
**Intent:** Implementar y ejecutar un script de pruebas automatizadas en Python que ejecute las consultas de los datasets de Superset contra `BI_SEMANTIC` y `DWH_MART` vía `BI_READER`, conciliando los resultados contra las cifras reales persistidas en Fase 3.

**Expected Outcomes:**
- Script de validación automatizada `tests/test_superset_kpi_reconciliation.py`.
- Conciliaciones cuantitativas aprobadas contra los datos reales de Fase 3:
  1. **Corte Diario (2026-11-06):**
     - Flota total: 100 unidades (56 con viaje = 56.00 %, 40 sin viaje = 40.00 %, 4 inactivas = 4.00 %).
     - Despachos del día: 56 viajes cerrados.
     - Kms del día: ~20,993.45 km.
     - Facturación del día: concilia exactamente contra la suma de CFDIs de ingreso con fecha de emisión del día.
  2. **Mes Cerrado (2026-11-01 a 2026-11-06):**
     - Despachos del mes: suma exacta de viajes en `VW_FACT_DESPACHO_VIAJE` para los 6 días de noviembre.
     - Facturación acumulada del mes: suma de `VW_FACT_FACTURACION_FLETE` en el período.
     - Gastos del mes: suma de `VW_FACT_GASTOS_LIQUIDACION` (operador, casetas, mantenimiento, otros).
     - Kms y Rendimiento: Kms totales del mes y Kms/kWh con `NULLIF` coinciden con `MV_PRODUCTIVIDAD_ECO_MENSUAL`.
  3. **Acumulado 90 Días de Backfill:**
     - Facturación total: **$309,227,803.56**.
     - Gastos totales: **$17,855,296.07**.
     - Kms totales: **1,820,487.49** km.
     - Consumo total: **326,806.52** kWh.
     - Rendimiento global: **5.68** km/kWh (3.49 .. 10.83 km/kWh).
  4. **Aislamiento del Día 91 Incremental (2026-11-07):**
     - Al seleccionar el día 91: 5 viajes nuevos, 100 unidades (5 con viaje, 91 sin viaje, 4 inactivas), 2 viajes abiertos restantes (`CONTADOR_CERRADO = 0`), `ECO15` consolidado en una sola fila con métricas sumadas de ambas placas.
- 100% de aserciones de conciliación aprobadas (PASS).

**Todo List:**
1. Desarrollar `tests/test_superset_kpi_reconciliation.py` ejecutando las queries de `superset/assets/datasets/` vía `python-oracledb`.
2. Validar cada KPI contra las tablas base y vistas materializadas de `BI_SEMANTIC`.
3. Documentar los resultados numéricos en el reporte final de cierre.

**Relevant Context:** `oracle/ddl/05_views_bi_semantic.sql`, `docs/fase-3-sim-etl-plan.md` (sección DoD y resultados de validación).  
**Status:** `[ ] pending`

---

### ST-6 — Auditoría Actor-Crítico de Fase 4 y Cierre de Entregables
**Intent:** Ejecutar una auditoría formal automatizada utilizando el skill `actor-critic-dw-review` y subagentes de exploración para certificar la calidad, seguridad y completitud de la Fase 4 antes de la promoción.

**Expected Outcomes:**
- Informe de auditoría `docs/audits/audit-fase-4.md` con **0 hallazgos BLOCKER y 0 hallazgos HIGH**.
- Verificación de 4 dimensiones críticas:
  1. **Seguridad y Cero Secretos:** Cero contraseñas en código o assets exportados.
  2. **Licenciamiento $0:** Exclusividad de Valkey (sin `redis:*`), compatibilidad Oracle SE2.
  3. **Conformidad Kimball:** Cero joins directos Fact↔Fact en datasets de Superset; Drill-Across estricto con `FULL OUTER JOIN`.
  4. **Cobertura Funcional de BI:** Los 7 bloques del Draft Dashboard renderizan y concilian métricas.
- Actualización de este documento con el estado final `[x] done` en todos los sub-tasks.

**Todo List:**
1. Lanzar los subagentes de auditoría Actor-Crítico para revisar código, SQLs Jinja y assets exportados.
2. Subsanar cualquier observación o advertencia detectada.
3. Redactar y versionar `docs/audits/audit-fase-4.md`.
4. Realizar commits atómicos en Git (`feat(bi): ...`, `docs: ...`).

**Relevant Context:** `.bob/skills/actor-critic-dw-review/SKILL.md`, `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` §7 Fase 4.  
**Status:** `[ ] pending`

---

## 3. Matriz de Trazabilidad: Bloques del Draft Dashboard ↔ Datasets ↔ Métricas Reales

| Bloque Draft | Nombre en Dashboard | Dataset Virtual (`superset/assets/datasets/`) | Fuentes Base en `BI_SEMANTIC` | Métricas y Fórmulas (según Draft PDF) | Conciliación Objetivo (Datos Reales Fase 3) |
|---|---|---|---|---|---|
| **Bloque 1** | Indicadores Diarios de Flota | `ds_01_flota_diaria.sql` | `MV_METRICAS_FLOTA_DIARIA` / `VW_FACT_SNAPSHOT_FLOTA_DIARIO` | Unidades C/Viaje, S/Viaje, Inactivas, Total, % Disponibilidad | **Día 2026-11-06:** 100 unidades (56 con viaje = 56.00%, 40 sin viaje = 40.00%, 4 inactivas = 4.00%). **Día 2026-11-07:** 100 unidades (5 con viaje, 91 sin viaje, 4 inactivas). |
| **Bloque 2** | Indicadores de Operación (Día / Mes) | `ds_02_operacion_dia_mes.sql` | `VW_FACT_DESPACHO_VIAJE`, `VW_FACT_GASTOS_LIQUIDACION`, `VW_FACT_LINEAS_CARGA_CARTAPORTE`, `VW_FACT_FACTURACION_FLETE` | Despachos, Cierres, Liq. Casetas, Liq. Operador, CFDI Traslado, Facturados | **Día 2026-11-06:** 56 despachos cerrados, 56 CFDIs ingreso. **Mes (01..06 Nov):** suma exacta de viajes cerrados y CFDIs del período en `DWH_MART`. |
| **Bloque 3** | Indicadores Generales (Día / Mes) | `ds_03_generales_dia_mes.sql` | `VW_FACT_DESPACHO_VIAJE`, `VW_FACT_GASTOS_LIQUIDACION`, `VW_FACT_FACTURACION_FLETE` | Total Kms, Rendimiento Kms/kWh (`NULLIF`), Pago Casetas ($), Pago Operadores ($), Facturado ($) | **Día 2026-11-06:** ~20,993.45 Kms, rendimiento ~4.95 km/kWh. **Mes (01..06 Nov):** suma acumulada de kms, kwh, facturación y gastos reales del mes en `BI_SEMANTIC`. |
| **Bloque 4** | Top 5 — Despachos / Cliente | `ds_04_top5_clientes.sql` | `VW_FACT_DESPACHO_VIAJE`, `VW_DIM_CLIENTE` | Ranking clientes por volumen de despachos (Día vs. Mes) usando `RAZON_SOCIAL` | Top 5 clientes reales del DW agrupados por `c.RAZON_SOCIAL` para el día 2026-11-06 y el mes acumulado. |
| **Bloque 5** | Facturación por Unidad (Top 10) | `ds_05_facturacion_top10_eco.sql` | `VW_FACT_FACTURACION_FLETE`, `VW_DIM_VEHICULO` | Facturación mensual acumulada por vehículo consolidando SCD2 por `CODIGO_ECO` | Top 10 vehículos con mayor facturación en el mes; `ECO15` unificado en una sola barra si abarca el día 91. |
| **Bloque 6** | Productividad de las Unidades (Mes) | `ds_06_productividad_unidades.sql` | `VW_FACT_DESPACHO_VIAJE`, `VW_FACT_LINEAS_CARGA_CARTAPORTE`, `VW_FACT_FACTURACION_FLETE`, `VW_FACT_GASTOS_LIQUIDACION`, `VW_DIM_VEHICULO` | 13 columnas: Unidad, Despachos, Cerrados, Kms Cargado, Kms Vacío, Kms Total, Facturación, Fact/Km, Rendimiento Kms/kWh, Costos (Operador, Mant., Otros, Total) | Consolidación por `CODIGO_ECO` de los 100 vehículos activos; suma de Facturación = `$309.2M` (90 días) o total mensual exacto; Kms = `1.82M` km (90 días); `DISTANCIA_DECLARADA_KM` no aditivo por CCP. |
| **Bloque 7** | Productividad de los Operadores (Mes) | `ds_07_productividad_operadores.sql` | `VW_FACT_DESPACHO_VIAJE`, `VW_FACT_LINEAS_CARGA_CARTAPORTE`, `VW_FACT_FACTURACION_FLETE`, `VW_FACT_GASTOS_LIQUIDACION`, `VW_DIM_OPERADOR` | 13 columnas por Operador: Clave/Nombre (`NOMBRE_OPERADOR`), Despachos, Cerrados, Kms Cargado/Vacío/Total, Facturación, Fact/Km, Rendimiento Kms/kWh, Costos | Consolidación por operador sobre `VW_DIM_OPERADOR`; totales de facturación, kms y costos concilian con Bloque 6 al centavo. |

---

## 4. Criterios de Aceptación (Definition of Done - DoD de Fase 4)

1. **Cobertura Visual Completa:** Los 7 bloques del *Draft Dashboard TMS* renderizan en Apache Superset sin errores de visualización ni productos cartesianos.
2. **Filter Pushdown Jinja Verificado en Oracle SE2:** Los filtros de fecha y dimensiones se inyectan en cada CTE individual antes del `FULL OUTER JOIN`, verificado mediante `EXPLAIN PLAN` + `DBMS_XPLAN.DISPLAY` ejecutado en sesión estándar `BI_READER`.
3. **Conformidad Kimball y Licenciamiento:** Cero joins directos Fact↔Fact en las consultas analíticas; cero opciones de pago de Oracle EE (sin particiones, sin query rewrite); uso exclusivo de Valkey 8 (`valkey/valkey:8-alpine`).
4. **Conciliación Numérica contra Totales Reales de Fase 3:**
   - Corte diario `2026-11-06`: 100 unidades (56% con viaje, 40% sin viaje, 4% inactivas), 56 viajes cerrados, 56 facturas.
   - Mes cerrado `2026-11-01` a `2026-11-06`: viajes, kms, kwh, facturación y gastos concilian al 100% contra `DWH_MART` / `BI_SEMANTIC`.
   - Acumulado 90 días: Facturación `$309,227,803.56`, Gastos `$17,855,296.07`, Kms `1,820,487.49`, Rendimiento `5.68 km/kWh`.
   - Aislamiento del día 91 parcial (`2026-11-07`): 5 viajes nuevos, `ECO15` unificado en una sola fila/barra sin duplicidad por SCD2.
5. **Rendimiento:** Tiempo de respuesta p95 del dashboard $< 3$ segundos con la caché Valkey activa.
6. **Entregables Versionados:**
   - Datasets SQL Jinja en `superset/assets/datasets/`.
   - Matriz de trazabilidad en `superset/assets/dashboard_mapping.md`.
   - Exportación limpia de assets (Dashboard/Charts YAML/JSON) en `superset/assets/` sin secretos ni contraseñas.
   - Script de conciliación automatizado (`tests/test_superset_kpi_reconciliation.py`).
   - Reporte de auditoría `docs/audits/audit-fase-4.md` con 0 hallazgos BLOCKER.
