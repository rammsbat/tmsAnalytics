# Plan de Ejecución — Fase 3: Simulador de Datos Sintéticos, Pipeline ELT `dbt-oracle` y Validación E2E

## Visión General

**Objetivo:** Poblar `STG_SRC` con datos sintéticos reproducibles (simulador Python), transformarlos con `dbt-oracle` a través de `EDW_3FN` y `DWH_MART` (constelación Kimball) y refrescar la capa `BI_SEMANTIC` de forma que `BI_READER` (Superset) consulte métricas coherentes con el Draft Dashboard TMS. La fase termina cuando el flujo `simulator → STG_SRC → EDW_3FN → DWH_MART → BI_SEMANTIC` corre de extremo a extremo con el 100% de los `dbt test` en verde.

**Skills:** `tms-synthetic-data-sim`, `dbt-oracle-etl-pipeline` (checklist `kimball_quality_screens.md`).
**Modos sugeridos (ver §Restricciones de modo):** `data-sim-eng` (simulador), `dw-architect-oracle` (modelos/tests dbt), `docker-platform-eng` (Dockerfiles/compose) y `agent` (integración y E2E).

**Estado de partida (verificado en vivo con `BI_READER` el 2026-11-23):**
- `DWH_MART.DIM_FECHA`, `DIM_HORA` y `DIM_VEHICULO` contienen **solo la fila `-1`** (COUNT = 1); `FACT_DESPACHO_VIAJE` y `FACT_SNAPSHOT_FLOTA_DIARIO` están vacías; `MV_METRICAS_FLOTA_DIARIA` y `MV_PRODUCTIVIDAD_ECO_MENSUAL` tienen 0 filas.
- `etl/dbt_tms/` y `simulator/` solo contienen `.gitkeep` (`models/{staging,edw_3fn,marts}`, `tests`, `src/generators`).
- `docker-compose.yml` no define los servicios `etl-runner` ni `data-simulator`.
- `.env.example` ya define `ORACLE_DSN`, `SIM_WRITER_PWD` y `ETL_RUNNER_PWD`.

**Fuentes y Referencias:**
- `.bob/skills/tms-synthetic-data-sim/SKILL.md` y `templates/sim_rules_schema.yaml` (esquema de `simulator/config_rules.yaml`).
- `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` y `checklists/kimball_quality_screens.md` (criterio de aceptación: 100% de tests en verde).
- `oracle/ddl/02_ddl_stg_src.sql` … `05_views_bi_semantic.sql` (contratos de tablas, granos, FKs, grants).
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` §2 (estructura de carpetas), §7 Fase 3 (comandos y DoD).
- `.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md` (valores de calibración y conciliación).
- `docs/Arquitectura-dw-analytics-tms.docx` y `docs/Draft-dashboard-TMS.pdf` (ejemplos reales: P&G, `ECO01..ECO100`, `CAJA05`, `IMESA`, `SMO`, `MERCURIO`, SAT `12161902` / `24112701`).
- `.bob/rules/01..03` y `AGENTS.md` (Kimball, SE2, secretos, `python-oracledb` Thin, bind variables, Conventional Commits, documentación en `docs/`).

**Criterio de Aceptación de Fase (DoD, de la spec §7 Fase 3):**
1. `docker compose run --rm data-simulator python src/main.py --mode backfill --days 90` carga `STG_SRC` sin errores ORA.
2. `docker compose run --rm etl-runner dbt build` termina con **100%** de modelos y tests en verde (Column, Structure y Business Rule Screens).
3. `FACT_SNAPSHOT_FLOTA_DIARIO` tiene 100 filas por día de backfill con ~56% con viaje / ~40% sin viaje / ~4% inactivas.
4. `FACT_FACTURACION_FLETE` y `FACT_GASTOS_LIQUIDACION` tienen registros (desbloquean los KPIs monetarios).
5. `SP_REFRESH_MV_SEMANTIC` ejecuta con `ETL_RUNNER` y `BI_READER` lee métricas no vacías y conciliadas en vistas/MVs de `BI_SEMANTIC`.

---

## Hallazgos de Investigación que Condicionan el Diseño

| # | Hallazgo (evidencia) | Impacto en el plan |
|---|---|---|
| H1 | Las tablas destino ya existen y pertenecen a `EDW_3FN` / `DWH_MART` (cuentas `LOCK`, sin privilegios de sistema). `ETL_RUNNER` solo tiene `CREATE SESSION`, `RESOURCE` y DML sobre esas tablas (`01_schemas_and_users.sql`, `03`, `04`). | Los materializados nativos de dbt (`table`, `incremental`, `snapshot`) crean objetos temporales/definitivos en el esquema destino y requieren privilegios `CREATE ANY …` que violan mínimo privilegio. Se requiere una **materialización personalizada de “MERGE sobre tabla preexistente”** (ver D1). Debe validarse en el spike ST-0. |
| H2 | `RESOURCE` no garantiza `CREATE VIEW` (el rol clásico no lo incluye). | Los modelos `staging` se materializan como `ephemeral` o `table` en el esquema propio de `ETL_RUNNER`; si se prefieren vistas se otorga `CREATE VIEW` a `ETL_RUNNER` (cambio mínimo, decisión D2). |
| H3 | `DIM_FECHA` (clave `YYYYMMDD`) y `DIM_HORA` (clave `HHMM`) están vacías salvo `-1`. Un lookup fallido se resolvería silenciosamente a `-1`. | Se deben poblar desde dbt (calendario y 1,440 minutos) **antes** de los hechos y añadir un screen “ningún hecho válido con fecha `-1`”. |
| H4 | `DIM_VEHICULO` es SCD2 (UQ `CODIGO_ECO + FECHA_INICIO_VALIDEZ`, `VERSION_ACTIVA`, `FECHA_INICIO/FIN_VALIDEZ`), pero `EDW_3FN.CAT_VEHICULOS` guarda solo el estado actual (UQ `CODIGO_ECO`). `DIM_OPERADOR` **no** tiene columnas de vigencia (UQ `CODIGO_OPERADOR`). | SCD2 se detecta comparando EDW (estado actual) contra la versión activa de `DIM_VEHICULO` en cada corrida de dbt. `DIM_OPERADOR` queda SCD1 (la solicitud limita SCD2 a `DIM_VEHICULO`); el paso 4 de la skill que menciona `DIM_OPERADOR` queda fuera de alcance salvo que se amplíe el DDL. |
| H5 | `FACT_GASTOS_LIQUIDACION` tiene grano y UQ `(FOLIO_LIQ, TIPO_GASTO)`, pero `EDW_3FN.OP_LIQUIDACIONES_GASTOS` es atómico (varias casetas por folio, sin UQ). `TIPO_GASTO` admite `COMBUSTIBLE_ENERGIA`, sin columna `MONTO_*` propia. | El mart **agrega** por `(FOLIO, TIPO)` y pivota a `MONTO_CASETA/OPERADOR/MANTENIMIENTO/OTROS`; `COMBUSTIBLE_ENERGIA` se mapea a `MONTO_OTROS_GASTOS` (el simulador no lo emite en esta fase). |
| H6 | `STG` no trae atributos de perfil de viaje (`TIPO_COBRO_*`, `PAGO_OPERADOR`) ni geografía de ubicaciones (CP, estado, lat/long), y los catálogos SAT (`SAT_*`) son FKs obligatorias en `EDW_3FN`. | Catálogos estáticos de referencia (SAT, geografía de ubicaciones conocidas) se cargan como **seeds de dbt** hacia `EDW_3FN`; `DIM_PERFIL_VIAJE` se deriva de `ESTATUS_DESPACHO` (etapa) con valores por defecto del DDL para el resto, o `-1` si no aplica (supuesto A3). |
| H7 | `02_ddl_stg_src.sql` concede `SELECT, INSERT, UPDATE, DELETE` a `SIM_WRITER`, mientras `.bob/rules/03-security-and-secrets.md` define solo `INSERT/UPDATE`. | Divergencia de mínimo privilegio. El simulador usa solo `INSERT` (fuente append-only con versiones por `INGESTED_AT`); el reinicio de staging se hace desde `ETL_RUNNER`. Recomendación (decisión D5): revocar `DELETE` a `SIM_WRITER`. |
| H8 | El MCP de Bob corre como `BI_READER`: ve `DWH_MART` y `BI_SEMANTIC`, no `STG_SRC` ni `EDW_3FN` (`docs/mcp_oracle_readonly.md`). | La verificación de `STG_SRC`/`EDW_3FN` se hace dentro del contenedor (`dbt test`, scripts de conciliación con `ETL_RUNNER`); la verificación de `DWH_MART`/`BI_SEMANTIC` puede hacerse vía MCP. |
| H9 | Las columnas `LAG_*` y `TIEMPO_ESTADIA_MINUTOS` existen ya en `STG_TRACKIT_PARADAS`, pero la skill exige calcularlas en el ETL. | `dbt` recalcula las métricas desde timestamps (fuente de verdad) y un test las concilia contra lo emitido por el simulador. |

---

## Decisiones Técnicas y Guardrails

| # | Decisión | Fundamento | Impacto |
|---|---|---|---|
| D1 | **Materialización personalizada `merge_existing`** (y variante `scd2_existing` para `DIM_VEHICULO`) en `etl/dbt_tms/macros/`. Emite `MERGE INTO <esquema>.<tabla> USING (<SQL compilado>)` directamente, sin crear objetos en el esquema destino. | H1; mínimo privilegio; evita `CREATE ANY TABLE`. Alternativa descartada: otorgar `CREATE ANY TABLE/VIEW` a `ETL_RUNNER`. | Se valida en ST-0. Si el spike demuestra que el `incremental` nativo funciona sin privilegios extra, se simplifica. |
| D2 | `staging` materializado como `ephemeral` (sin objetos en BD). | H2; cero cambios de privilegios. | Si se necesitan vistas físicas para depuración, otorgar `CREATE VIEW` a `ETL_RUNNER` en un script `oracle/ddl/06_etl_grants.sql`. |
| D3 | `generate_schema_name` sobrescrito: los modelos escriben en el esquema literal (`EDW_3FN`, `DWH_MART`) y no en `<target>_<custom>`. | Las tablas ya existen con esos nombres. | Macro en `etl/dbt_tms/macros/`. |
| D4 | **Sin `dbt snapshot` nativo** para SCD2; la lógica de cierre/inserción de versiones vive en la materialización `scd2_existing`. | H1/H4. | Una corrida: (1) cerrar versión activa cuyo atributo rastreado cambió (`FECHA_FIN_VALIDEZ`, `VERSION_ACTIVA='0'`); (2) insertar nueva versión activa. |
| D5 | Recomendar `REVOKE DELETE ON STG_SRC.* FROM SIM_WRITER` (script `06`); reinicio de staging por `ETL_RUNNER` (`dbt run-operation`). | H7; Regla 03 §3. | Opcional; requiere confirmación del usuario. |
| D6 | Reproducibilidad: `seed` + **`end_date` fijo** en `config_rules.yaml`. UUIDs, folios de talón y timestamps salen del RNG sembrado (no de `datetime.now()` ni `uuid4()`). | Skill (`seed`), `data-sim-eng` (pruebas reproducibles). | Dos corridas con igual `seed`/`end_date` generan lotes idénticos. |
| D7 | Fuente de staging **append-only**: cambios posteriores (cierre de viaje, cambio de placa) se insertan como nueva fila con mayor `INGESTED_AT` / nuevo `BATCH_ID`. `EDW_3FN` deduplica por llave natural quedándose con la fila más reciente. | Compatible con `INSERT` únicamente; habilita el modo incremental y la demostración SCD2. | Dedupe con `ROW_NUMBER() OVER (PARTITION BY <llave natural> ORDER BY INGESTED_AT DESC)` (función analítica, no `PARTITION BY` de tabla). |
| D8 | Conexión: simulador con `python-oracledb` Thin (`SIM_WRITER`), dbt con `dbt-oracle` en modo Thin (`ETL_RUNNER`); ambos leen `ORACLE_DSN` y contraseñas **solo** de variables de entorno. | `AGENTS.md`, Regla 03. | Sin `cx_Oracle` ni Instant Client. Los contenedores **no** reciben `ORACLE_PWD` (SYSTEM). |
| D9 | `dbt` ejecutado únicamente en el contenedor `etl-runner`; `profiles.template.yml` solo con `env_var(...)`. | Skill pasos 1 y 7. | Verificar contra la documentación de `dbt-oracle` las claves exactas del perfil Thin (la skill indica `protocol: thin`; debe confirmarse en ST-0). |
| D10 | Servicios `data-simulator` y `etl-runner` con `profiles` de Compose (`sim`, `etl`) para que no arranquen con `docker compose up`. | Ejecución “run-once” de la spec; evita healthchecks sin sentido. | Aún así: `USER appuser`, red `tms-internal-net`, `depends_on: oracle-dw (service_healthy)`, `healthcheck` declarado (Regla 03 §4). |

### Supuestos a confirmar (valores por defecto si el usuario no objeta)
- **A1 – Mapeo de estatus de flota → indicadores del snapshot:** `DISPONIBLE_CON_VIAJE` → con viaje; `DISPONIBLE_SIN_VIAJE` → sin viaje; `EN_MANTENIMIENTO` e `INACTIVO` → inactiva. Mezcla objetivo 56% / 40% / 4%.
- **A2 – Un viaje = un día de despacho** (no hay viajes que crucen medianoche en esta fase), de modo que `FACT_SNAPSHOT_FLOTA_DIARIO` es consistente con `FACT_DESPACHO_VIAJE`: una unidad está “con viaje” si y solo si tiene despacho ese día.
- **A3 – `DIM_PERFIL_VIAJE`:** `ETAPA_VIAJE` se deriva de `ESTATUS_DESPACHO`; `TIPO_COBRO_FLETE`, `TIPO_COBRO_CASETAS` y `PAGO_OPERADOR` usan los valores por defecto del DDL (`DESTINO`, `COMPLETO`, `DESTINO`).
- **A4 – Una factura (CFDI Ingreso) por viaje**, emitida con rezago configurable respecto al cierre. El conteo “Facturados” del Draft (57 día vs 5 despachos) queda como pendiente del Product Owner (nota ya registrada en `draft_dashboard_kpis.md`).
- **A5 – Primera versión de `DIM_VEHICULO`:** `FECHA_INICIO_VALIDEZ` = fecha de inicio del histórico configurada (no `1900-01-01`, reservada para `-1`); versión activa con `FECHA_FIN_VALIDEZ = NULL`; los lookups usan `NVL(fin, DATE '2099-12-31')`.
- **A6 – Atributos SCD2 de `DIM_VEHICULO`:** `PLACA`, `CONFIGURACION_SAT`, `TIPO_PERMISO_SCT`, `PESO_BRUTO_MAX_KG`, `ESTATUS_OPERATIVO`.

### Restricciones de modo (`.bob/custom_modes.yaml`)
| Modo | Puede editar | No puede editar (y por tanto lo hace…) |
|---|---|---|
| `data-sim-eng` | `simulator/**/*.{py,yaml,yml,txt,md,json}` | `simulator/Dockerfile` → `docker-platform-eng` / `agent` |
| `dw-architect-oracle` | `oracle/`, `etl/`, `docs/` con `.sql .yml .yaml .md .txt` | `etl/Dockerfile`, seeds `.csv`, macros no `.sql` → `agent` |
| `docker-platform-eng` | `docker-compose*.yml`, `Dockerfile*`, `.env.example`, `*.sh` | Código Python/SQL |
| `agent` | Todo (integración, ejecución E2E, seeds CSV) | — |

---

## Decisiones Aprobadas y Precisiones Técnicas de Implementación

**Aprobado por el usuario:** supuestos A1–A6 y decisiones D1–D10 tal como están, incluida D5 (revocar `DELETE` a `SIM_WRITER` mediante `oracle/ddl/06_etl_grants.sql`). Se implementa en orden, empezando por ST-0, y **los resultados de ST-0 se comparten con el usuario antes de avanzar a ST-1**.

**Precisiones obligatorias:**

| # | Aplica a | Precisión |
|---|---|---|
| P1 | ST-1 (`docker-compose.yml`) | `data-simulator` y `etl-runner` fijan explícitamente `ORACLE_DSN: oracle-dw:1521/FREEPDB1` en su bloque `environment`, sin depender del valor de `.env` (que puede decir `localhost`). Verificar que `docker compose run --rm data-simulator ...` y `docker compose run --rm etl-runner ...` funcionan con los `profiles` declarados (`sim` / `etl`). Si Compose exige `--profile`, documentar el comando exacto. |
| P2 | ST-0 y ST-6 (`merge_existing`) | En el `MERGE` de la materialización personalizada: (a) el `INSERT` **omite** las columnas `IDENTITY`; (b) el bloque `UPDATE SET` **excluye** las columnas usadas en la cláusula `ON` (evita `ORA-38104`). ST-0 confirma además que `dbt seed` materializa los catálogos en el **esquema propio de `ETL_RUNNER`** y que luego un `MERGE` los lleva a `EDW_3FN`. |
| P3 | ST-8 (prueba SCD2 en `DIM_VEHICULO`) | El evento de cambio de placa usa una fecha efectiva **posterior** a la `FECHA_INICIO_VALIDEZ` inicial (A5) para no colisionar con `UQ (CODIGO_ECO, FECHA_INICIO_VALIDEZ)`. Se configura en `config_rules.yaml` (p. ej. `fleet_change_events[].effective_date`) y la materialización `scd2_existing` cierra la versión previa con `FECHA_FIN_VALIDEZ = fecha_efectiva - 1`. |
| P4 | ST-11 (`SP_REFRESH_MV_SEMANTIC`) | Si se usa `on-run-end`, el refresco se condiciona a `flags.WHICH in ('run', 'build')` para que `dbt test` no refresque las MVs. Alternativa preferida: `dbt run-operation refresh_semantic_layer` invocado explícitamente. |

**Ajustes derivados al alcance de ST-0:** además del merge sobre tablas preexistentes, el spike debe probar (1) `MERGE` sin columna `IDENTITY` en el `INSERT` y sin columnas de `ON` en el `UPDATE`, y (2) `dbt seed` hacia el esquema de `ETL_RUNNER` + `MERGE` posterior a `EDW_3FN`.

---

## Arquitectura del Flujo (referencia)

```
simulator (SIM_WRITER, INSERT)            etl-runner / dbt (ETL_RUNNER)                         BI
STG_SRC.* ──► staging (ephemeral) ──► EDW_3FN (MERGE) ──► DWH_MART dims ──► DWH_MART facts ──► SP_REFRESH_MV_SEMANTIC ──► BI_SEMANTIC (BI_READER)
 8 tablas      limpieza/normalización    dedupe + FKs 3FN    SK + SCD1/SCD2 + -1    SK lookup + métricas       MV_METRICAS_FLOTA_DIARIA
                                                                                     (sin join Fact↔Fact)       MV_PRODUCTIVIDAD_ECO_MENSUAL
```

Orden de construcción en dbt: seeds/catálogos → dimensiones (`DIM_FECHA`, `DIM_HORA` primero) → hechos → refresco semántico.

---

## Sub-tareas

### ST-0 — Spike de Viabilidad `dbt-oracle` y Contratos Previos
**Estado:** [x] completado y aprobado por el usuario (ver “Resultados del Spike (ST-0)”).
**Intent:** Eliminar el riesgo principal antes de construir (H1/H2/D1): confirmar que `dbt-oracle` puede operar con `ETL_RUNNER` sobre tablas preexistentes de otros esquemas sin privilegios `ANY`, y fijar las claves de conexión Thin.

**Expected Outcomes:**
- Decisión documentada (en este archivo) sobre D1/D2/D9: materialización personalizada vs `incremental` nativo; `ephemeral` vs vistas; claves exactas de `profiles.template.yml`.
- Confirmación de si `ETL_RUNNER` puede crear/leer lo mínimo necesario (p. ej. `dbt seed` en su propio esquema).
- Lista final de confirmaciones del usuario sobre A1–A6 y D5.

**Todo List:**
1. Consultar la documentación vigente de `dbt-oracle` (perfil Thin, `incremental` con `unique_key`/MERGE, comportamiento de relaciones temporales, `schema` personalizado).
2. Prototipar en el contenedor `etl-runner` (ya con ST-1 mínima) un modelo trivial que haga `MERGE` sobre una tabla de `EDW_3FN` y otro sobre `DWH_MART`, con `ETL_RUNNER`; capturar errores `ORA-01031`/`ORA-00942`.
3. Verificar si `ETL_RUNNER` puede crear vistas; decidir D2.
4. Registrar resultado en la sección “Resultados del Spike” al final de este documento.

**Relevant Context:** `oracle/ddl/01_schemas_and_users.sql` (grants de `ETL_RUNNER`), `03_ddl_edw_3fn.sql` §5, `04_ddl_dwh_mart.sql` §5, `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` paso 1. Usar `list_ibm_doc_libraries`/documentación oficial de `dbt-oracle` solo si aplica; no asumir claves de perfil sin evidencia.

**Status:** `[x] done` (aprobado por el usuario)

---

### ST-1 — Andamiaje de Contenedores y Proyecto dbt
**Intent:** Disponer los contenedores `data-simulator` y `etl-runner`, sus dependencias y el esqueleto del proyecto dbt para que las siguientes sub-tareas sean ejecutables dentro de Docker.

**Expected Outcomes:**
- `simulator/Dockerfile`, `simulator/requirements.txt` (`oracledb`, `Faker`, `numpy`, `PyYAML`, `pytest`) y `etl/Dockerfile`, `etl/requirements.txt` (`dbt-core`, `dbt-oracle`), Python 3.11, `USER appuser`.
- `docker-compose.yml` con servicios `data-simulator` (perfil `sim`) y `etl-runner` (perfil `etl`): red `tms-internal-net`, `depends_on` Oracle `service_healthy`, `healthcheck`, variables `ORACLE_DSN` y la contraseña **de su propio usuario** (`SIM_WRITER_PWD` / `ETL_RUNNER_PWD`), sin `ORACLE_PWD`.
- `etl/dbt_tms/dbt_project.yml`, `etl/dbt_tms/profiles.template.yml` (solo `env_var`), carpetas `models/{staging,edw_3fn,marts/{dimensions,facts}}`, `macros/`, `seeds/`, `tests/`.
- `.env.example` actualizado solo si hace falta una variable nueva (sin valores reales).
- `docker compose config` válido y `docker compose --profile sim build` / `--profile etl build` exitosos.

**Todo List:**
1. Crear Dockerfiles y `requirements.txt` fijando versiones compatibles.
2. Añadir servicios al `docker-compose.yml` con `profiles`, sin puertos publicados.
3. Crear `dbt_project.yml` y `profiles.template.yml` según resultado de ST-0.
4. Verificar que `.gitignore`/`.dockerignore` excluyen `target/`, `dbt_packages/`, `logs/`, `profiles.yml`.
5. Probar `docker compose run --rm etl-runner dbt debug` (conexión Thin con `ETL_RUNNER`).

**Relevant Context:** `docker-compose.yml` (patrón `x-superset-common`, red y healthchecks existentes), `.env.example`, `.bob/rules/03-security-and-secrets.md` §4, `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` §2 (estructura). Modos: `docker-platform-eng` / `agent`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-2)

**Resultado ST-1 (verificado):**
- `06_etl_grants.sql` aplicado en `tms-oracle-dw` (FREEPDB1): `REVOKE DELETE` de `SIM_WRITER` sobre las 8 tablas de `STG_SRC`; re-ejecución idempotente (ORA-01927 capturado). `SIM_WRITER`: 0 privilegios DELETE, 24 SELECT/INSERT/UPDATE; `DELETE` → `ORA-41900`.
- Imágenes `analytics-tms-simulator:local` y `analytics-tms-etl:local` (Python 3.11-slim, `USER appuser` uid 1000, `git` en etl); versiones fijadas.
- `etl-runner`: `ORACLE_DSN`, `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE` explícitos en `environment`; `profiles.template.yml` → `/app/profiles/profiles.yml` (`DBT_PROFILES_DIR`), solo `env_var(...)`; `DBT_TARGET_PATH`/`DBT_LOG_PATH` en `/home/appuser/dbt_artifacts/{target,logs}`.
- Comandos: `docker compose --profile etl run --rm etl-runner dbt debug` y `docker compose --profile sim run --rm data-simulator python -m src.main ...`.
- `staging` queda `ephemeral` (sin objetos en `STG_SRC`).

---

### ST-2 — Simulador: Configuración, Maestros de Flota y Capa de Carga
**Intent:** Entregar la porción vertical mínima del simulador: configuración reproducible, catálogos base (100 unidades, remolques, operadores, clientes, ubicaciones), CLI y carga segura a `STG_SRC`.

**Expected Outcomes:**
- `simulator/config_rules.yaml` basado en `sim_rules_schema.yaml` con valores calibrados (sin `TODO`): `seed`, `end_date`, `fleet_size: 100`, `fleet_status_mix` (0.56/0.40/0.04), `date_range_backfill` (90 días + `preset_draft` 2026-11-01…2026-11-06), `pricing_model` (calibrado con el Draft: ECO01 $89,088 / 595 km ≈ $149.73 por km), `cost_model` (IAVE, pago operador por km/viaje, mantenimiento) y `constraints` (`max_gross_weight_kg: 29685`, 4–12 paradas, 2.0–11.6 km/kWh).
- `simulator/src/generators/fleet_master.py`: `ECO01..ECO100`, remolques (`CAJA05`…), operadores (el Draft reporta 15), clientes (P&G Manufacturing y otros con RFC válidos), ubicaciones (`IMESA`, `SMO`, `MERCURIO`…), pólizas; sin duplicados y deterministas.
- `simulator/src/db_loader.py`: `oracledb` Thin, `executemany` en lotes de 5,000, **solo bind variables** (`:param`), `BATCH_ID` único por corrida, `INGESTED_AT` y `SOURCE_SYSTEM` (`TRACKITWEB`, `CARTA_PORTE`, `FLOTA`, `ERP_FINANCIERO`), contraseña solo desde `SIM_WRITER_PWD`.
- `simulator/src/main.py`: CLI `--mode backfill --days N`, `--mode incremental --trips N`, `--dry-run` (estadísticas sin escribir), `--seed`, `--end-date`.
- Carga de `STG_FLOTA_UNIDADES` verificada (100 filas por lote de maestros).

**Todo List:**
1. Definir y validar `config_rules.yaml` (carga con `PyYAML`, validación de rangos).
2. Implementar `fleet_master.py` y los catálogos auxiliares (clientes/operadores/ubicaciones como estructuras en memoria que luego alimentan los demás generadores).
3. Implementar `db_loader.py` (conexión, `BATCH_ID`, inserción por lotes, manejo de errores sin filtrar secretos).
4. Implementar `main.py` con los tres modos y `--dry-run`.
5. Ejecutar `--dry-run` y una carga real de maestros; contar filas con `SIM_WRITER`.

**Relevant Context:** `oracle/ddl/02_ddl_stg_src.sql` (`STG_FLOTA_UNIDADES`, auditoría), `.bob/skills/tms-synthetic-data-sim/templates/sim_rules_schema.yaml`, `.bob/rules/03-security-and-secrets.md` §2 y §3. Modo: `data-sim-eng`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-3)

**Resultado ST-2 (verificado):**
- `simulator/config_rules.yaml` calibrado (sin `TODO`; ECO01: 1,000.00 + 595 km × 147.50 + 325.50 = $89,088.00) y validado por `src/config.py`.
- `src/contract.py` parsea `oracle/ddl/02_ddl_stg_src.sql` (8 tablas) y valida tipo, longitud en **bytes UTF-8**, `NUMBER(p,s)`, nulabilidad, columnas exactas y cadenas vacías; el DDL se copia a la imagen en `/app/contract/`.
- `src/generators/fleet_master.py`: `ECO01..ECO100`, `CAJA01..CAJA100`, 15 operadores, 6 clientes, 8 ubicaciones (`IMESA`, `SMO`, `MERCURIO`…), 10 pólizas; RNG por *stream* (`sha256(seed:stream)`), sin `datetime.now()` ni `uuid4()` (verificado por prueba AST).
- `src/db_loader.py`: Thin, solo `SIM_WRITER`, `executemany` en lotes de 5,000, binds posicionales, `commit` único (todo o nada), solo `INSERT`/`SELECT`.
- `BATCH_ID = SIM-<MODO>-<AAAAMMDD>-s<seed>-<NNN>`; `INGESTED_AT` = `end_date` 00:00 + NNN minutos (determinista, creciente por corrida; D7).
- `pytest`: 41 pruebas en verde dentro de la imagen. `--dry-run`: mismo `fingerprint` en dos corridas; distinto con `--seed 7`.
- Carga real: `STG_FLOTA_UNIDADES` 0 → 100 filas (`SIM-BACKFILL-20261106-s42-001`, `FLOTA`), 100 ECO / placas / VIN / motores distintos, 0 nulos de auditoría. 2.ª corrida asignó `-002` automáticamente; se eliminó con `ETL_RUNNER` (`SIM_WRITER` no puede `DELETE`).
- Nota de contenedor: `./simulator` **no** está montado como volumen; la imagen se reconstruye (`docker compose --profile sim build data-simulator`) tras cada cambio de código.

---

### ST-3 — Simulador: Operaciones TrackItWeb y Carta Porte
**Intent:** Generar la operación diaria coherente (viajes, paradas, estatus de patio y carga amparada) con las restricciones físicas y de negocio.

**Expected Outcomes:**
- `trackit_ops.py` → `STG_TRACKIT_DESPACHO` y `STG_TRACKIT_PARADAS`: despachos diarios (~56% de las unidades con viaje cada día), odómetros consistentes, `KMS_TOTAL = KMS_CARGADO + KMS_VACIO`, `KWH_CONSUMO` con rendimiento 2.0–11.6 km/kWh, 4–12 paradas con retrasos gaussianos, evento `FIN VIAJE` en viajes cerrados, `LAG_*` y estadía coherentes con timestamps, fechas no invertidas.
- Generación de `STG_FLOTA_ESTATUS_DIARIO` para **las 100 unidades cada día** (mezcla 56/40/4 %, A1/A2), consistente con los despachos del día.
- `carta_porte.py` → `STG_CARTA_PORTE_CABECERA` y `STG_CARTA_PORTE_MERCANCIAS`: un `UUID_CCP` por viaje, partidas con claves SAT (`12161902`, `24112701`…), `UNIDAD_EMBARQUE_UE`, suma de `PESO_KG` ≤ 29,685 kg y sin pesos negativos; `NUMERO_TALON` enlaza con TrackIt.
- Incremental: `--trips N` continúa la numeración de talones del último lote (consulta con bind variable) y puede **cerrar** viajes abiertos insertando nueva versión de fila (D7).

**Todo List:**
1. Implementar el motor de viajes/paradas con RNG sembrado y calendario anclado a `end_date` (D6).
2. Implementar estatus diario consistente con viajes; asegurar 100 filas/día.
3. Implementar partidas de mercancía respetando peso y claves SAT.
4. Soportar evento de reasignación de unidad (cambio de `PLACA`/`ESTATUS_INVENTARIO`) mediante re-emisión de `STG_FLOTA_UNIDADES` con nuevo `BATCH_ID`, configurable en `config_rules.yaml` para ejercitar SCD2 en ST-8.
5. Ejecutar `--dry-run` y revisar estadísticas (porcentajes, rangos, conteos).

**Relevant Context:** `02_ddl_stg_src.sql` tablas 1, 2, 3, 4, 5, 6; `data-sim-eng` customInstructions (Kms_Total, peso, FIN VIAJE); `draft_dashboard_kpis.md` (Kms Vacío = 0, Cargado 3,710 en el mes como referencia de orden de magnitud). Modo: `data-sim-eng`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-4)

**Resultado ST-3 (verificado):**
- Módulos nuevos: `generators/trackit_ops.py` (viaje = función pura de `seed`+talón), `generators/carta_porte.py`, `generators/fleet_status.py`, `scenario.py` (calendario, operadores **con reemplazo**, viajes abiertos/cierre, `PlateBook` SCD2). `db_loader.py` suma `load_state` (solo `SELECT` con binds) y `next_run_seq` por **corrida** (excluye lotes `-Exx`); `main.py` emite todas las tablas con **un único `COMMIT`** (rollback total ante error).
- Catálogos SAT cerrados en `config_rules.yaml` (`sat_catalogs`): productos `12161902`, `24112701`, `53131608`; unidades `H87`, `XBX`, `XPK`; config `C3R2`; permiso `TPAF01`. Una prueba verifica que todo lo emitido ⊂ catálogo; ST-7 los siembra 1 a 1.
- `INGESTED_AT` por fila = día operativo 23:00:00 + `run_seq` s (D7): el cierre de un viaje (día siguiente) y el cambio de placa (fecha efectiva) siempre superan a la versión previa.
- SCD2 (P3): `ECO07@2026-10-01` y `ECO42@2026-10-20`, ambas **posteriores** al inicio del histórico (2026-08-09); re-emisión de 1 fila por evento con lote `…-001-E01/-E02`. Carta Porte usa la placa vigente ese día. Eventos fuera de ventana se omiten con aviso.
- **Defecto hallado y corregido durante ST-3:** `allocate()` no normalizaba pesos arbitrarios y los tramos de un viaje sumaban ≫ `KMS_TOTAL` (el viaje GRD340 “no cabía en un día”); ahora normaliza. Cubierto por pruebas.
- `pytest`: **67 pruebas en verde** (41 de ST-2 + 26 nuevas: 56/40/4 diario, `CON_VIAJE` ≡ despachos, `KMS_TOTAL`, rendimiento, 4–12 paradas, peso ≤ 29,685, un viaje = un día, odómetros continuos, operadores con reemplazo, SAT cerrado, SCD2, incremental, determinismo, contrato DDL de cada tabla).
- `--dry-run` backfill 90 días (determinista, mismos *fingerprints* que la carga real): `STG_FLOTA_UNIDADES` 100 (+1 +1 eventos), `STG_TRACKIT_DESPACHO` 5,040, `STG_TRACKIT_PARADAS` 40,458, `STG_CARTA_PORTE_CABECERA` 5,040, `STG_CARTA_PORTE_MERCANCIAS` 15,236, `STG_FLOTA_ESTATUS_DIARIO` 9,000 (90 × 100). 11 viajes abiertos al corte (18:00 del último día).
- `--dry-run` incremental `--trips 5`: 16 despachos (11 cierres + 5 nuevos), 111 estatus (11 del día previo + 100 del día nuevo).
- **Carga real validada** (backfill + incremental como `SIM_WRITER`; conteos verificados en BD = insertados): 100 filas/día en 90 días; mezcla 56 % / 40 % / 3 % mantenimiento / 1 % inactivo; `CON_VIAJE` vs despachos: 0 diferencias en ambos sentidos; 0 violaciones de `KMS_TOTAL` o peso; rendimiento 2.14–11.40; paradas 4–12; peso CCP = Σ mercancías; 0 nulos de auditoría; tras el incremental 11 talones con 2 versiones y el cierre gana por `INGESTED_AT DESC`.
- Los datos de validación se **eliminaron** con `ETL_RUNNER`; `STG_SRC` queda vacío para el backfill oficial de ST-5. `./simulator` está montado como volumen (no hace falta reconstruir la imagen al cambiar código).
- Pendiente para ST-4: `STG_CFDI_INGRESO` y `STG_LIQUIDACIONES_GASTOS`.

---

### ST-4 — Simulador: ERP Financiero (CFDI Ingreso 4.0 y Liquidaciones)
**Intent:** Cerrar las brechas del Draft Dashboard (facturación y gastos) con datos vinculados por `NUMERO_TALON`.

**Expected Outcomes:**
- `finance_erp.py` → `STG_CFDI_INGRESO` (un CFDI de Ingreso 4.0 por viaje según A4, importes = tarifa base + tarifa/km + recargos; IVA trasladado/retenido; `IMPORTE_TOTAL` coherente con subtotal − descuento + IVA − retención; `UUID_INGRESO` único y determinista) y `STG_LIQUIDACIONES_GASTOS` (casetas IAVE, pago a operador, mantenimiento; `TIPO_GASTO` ∈ `CASETA`, `OPERADOR`, `MANTENIMIENTO`, `OTROS`).
- Cada factura y cada liquidación referencia un talón existente en `STG_TRACKIT_DESPACHO`; `FOLIO_LIQUIDACION` único.
- Ningún importe negativo; moneda `MXN`.

**Todo List:**
1. Implementar `pricing_model` y `cost_model` parametrizados por `config_rules.yaml`.
2. Emitir CFDIs y liquidaciones por viaje con rezagos configurables.
3. Integrar en `main.py` el orden de carga: maestros → operación → Carta Porte → finanzas.
4. Verificar con `--dry-run` totales por mes contra el orden de magnitud del Draft.

**Relevant Context:** `02_ddl_stg_src.sql` tablas 7 y 8, `04_ddl_dwh_mart.sql` (`FACT_FACTURACION_FLETE`, `FACT_GASTOS_LIQUIDACION`), `.bob/rules-dw-architect-oracle/01-oracle-ddl-conventions.md` §4.2. Modo: `data-sim-eng`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-5)

**Resultado ST-4 (verificado):**
- Módulo nuevo: `generators/finance_erp.py` implementa `build_cfdi_ingreso` (CFDI Ingreso 4.0 con cuadre fiscal exacto a 2 decimales usando `Decimal` `ROUND_HALF_UP`: `IMPORTE_TOTAL = SUBTOTAL - DESCUENTO + IVA_TRASLADADO - IVA_RETENIDO` con 16 % IVA y 4 % retención flete, moneda `MXN`, `UUID_INGRESO` determinista desde RNG sembrado) y `build_liquidaciones_gastos` (H5: `FOLIO_LIQUIDACION` único por viaje cerrado con 2–4 líneas `CASETA`, 1 `OPERADOR`, y líneas opcionales `MANTENIMIENTO` y `OTROS`, sin emitir `COMBUSTIBLE_ENERGIA`).
- Integración en `scenario.py` y `main.py`: facturación y liquidación exclusivas para viajes `CERRADO` (A4); en backfill los 11 viajes abiertos al corte no se facturan ni liquidan hasta cerrarse en `--mode incremental` (11 talones cerrados facturados y liquidados sin duplicar).
- Orden de emisión y carga: maestros → operación TrackIt → Carta Porte → estatus flota → finanzas (`STG_CFDI_INGRESO` y `STG_LIQUIDACIONES_GASTOS`). Margen operativo fuertemente positivo (> 85 % global, individual > 0).
- Suite `pytest`: **75 pruebas en verde** (+8 pruebas nuevas en `test_finance_erp.py` cubriendo contrato DDL, viajes cerrados, incremental sin duplicación, cuadre fiscal al centavo, calibración ECO01 $89,088.00, granularidad de liquidación, margen operativo y determinismo).
- `--dry-run` backfill 90 días: `STG_FLOTA_UNIDADES` 100 (+1 +1 SCD2), `STG_TRACKIT_DESPACHO` 5,040, `STG_TRACKIT_PARADAS` 40,458, `STG_CARTA_PORTE_CABECERA` 5,040, `STG_CARTA_PORTE_MERCANCIAS` 15,236, `STG_FLOTA_ESTATUS_DIARIO` 9,000, `STG_CFDI_INGRESO` 5,029 (5,040 - 11 abiertos), `STG_LIQUIDACIONES_GASTOS` 22,511.
- `--dry-run` incremental `--trips 5`: 16 despachos (11 cierres + 5 nuevos), 14 CFDIs emitidos (11 de los viajes cerrados anteriores + 3 de los nuevos cerrados), 67 líneas de liquidación.
- Carga real de prueba ejecutada con `SIM_WRITER` (102,416 filas insertadas y verificadas contra Oracle en corrida atómica) y posteriormente eliminada con `ETL_RUNNER` (`STG_SRC` queda 100 % limpio con 0 filas para ST-5).

---

### ST-5 — Pruebas del Simulador y Backfill en Vivo sobre `STG_SRC`
**Intent:** Asegurar calidad y reproducibilidad del simulador y ejecutar el backfill real de 90 días.

**Expected Outcomes:**
- Suite `pytest` en `simulator/tests/` que verifica: sin pesos negativos ni > 29,685 kg, fechas no invertidas, `KMS_TOTAL = CARGADO + VACIO`, rendimiento y paradas en rango, integridad referencial lógica entre tablas de staging (talón ↔ CP ↔ CFDI ↔ liquidación, `CODIGO_ECO` ∈ maestro), unicidad de llaves naturales, **determinismo** (misma `seed`/`end_date` ⇒ mismo lote) y ausencia de SQL interpolado.
- Backfill de 90 días cargado en `STG_SRC` con `SIM_WRITER`; conteos por tabla documentados.
- Revisión estática: cero contraseñas literales y cero f-strings en SQL.

**Todo List:**
1. Escribir pruebas unitarias y de determinismo; ejecutar `pytest` dentro del contenedor.
2. Ejecutar `docker compose run --rm data-simulator python src/main.py --mode backfill --days 90`.
3. Conciliar conteos en `STG_SRC` (vía contenedor, ver H8) y registrar en el documento.
4. Commit atómico `feat(simulator): …` (Conventional Commits).

**Relevant Context:** `.bob/skills/tms-synthetic-data-sim/SKILL.md` paso 5; `AGENTS.md`. Modos: `data-sim-eng` (código/tests) y `agent` (ejecución en Docker).

**Status:** `[x] done` (simulador completado, probado y backfill oficial cargado en `STG_SRC`)

**Resultado ST-5 (verificado):**
- **Imagen autocontenida:** Se retiraron los volúmenes temporales de desarrollo en `docker-compose.yml`. La imagen `analytics-tms-simulator:local` fue reconstruida con el contrato DDL horneado en `/contract/02_ddl_stg_src.sql`.
- **Suite de pruebas:** **75 pruebas unitarias y de guardrails en verde** ejecutadas dentro de la imagen autocontenida (`test_cli_and_guardrails.py`, `test_contract.py`, `test_fleet_master.py`, `test_operations.py`, `test_finance_erp.py`). Cero llamadas a `now()`/`uuid4()`, cero SQL interpolado/f-strings, cero contraseñas literales, uso estricto de binds y Thin Mode de `python-oracledb`.
- **Backfill oficial cargado y persistido en `STG_SRC`** (`SIM-BACKFILL-20261106-s42-001`, `seed=42`, `end_date=2026-11-06`, 90 días):
  - `STG_FLOTA_UNIDADES`: **102** (100 unidades base + 2 eventos SCD2 dentro de ventana: `ECO07` y `ECO42`)
  - `STG_TRACKIT_DESPACHO`: **5,040** (56 despachos/día × 90 días; 11 viajes abiertos al corte de las 18:00 del día 90)
  - `STG_TRACKIT_PARADAS`: **40,458** (4 a 12 paradas por despacho)
  - `STG_CARTA_PORTE_CABECERA`: **5,040** (1 documento por despacho)
  - `STG_CARTA_PORTE_MERCANCIAS`: **15,236** (1 a 5 partidas por viaje, pesos unitarios y SAT cerrados)
  - `STG_FLOTA_ESTATUS_DIARIO`: **9,000** (100 unidades/día × 90 días, mezcla exacta 56/40/3/1 %)
  - `STG_CFDI_INGRESO`: **5,029** (exactamente 5,040 - 11 viajes abiertos)
  - `STG_LIQUIDACIONES_GASTOS`: **22,511** (líneas atómicas de peaje IAVE, operador y mantenimiento para los 5,029 viajes cerrados)
  - **Total filas en `STG_SRC`:** **102,416 filas** verificadas con `ETL_RUNNER` y `SIM_WRITER`.
- **Soporte para prueba SCD2 en ST-8:**
  - Configurado el evento `ECO15@2026-11-07` en `config_rules.yaml`. Durante el backfill se omite por estar fuera de ventana; al ejecutar `--mode incremental --trips N` (día 2026-11-07), el generador emite automáticamente la nueva placa en `STG_FLOTA_UNIDADES` con sufijo `-E01`, habilitando la validación del cierre de versión 1 y apertura de versión 2 en `DIM_VEHICULO`.

---

### ST-6 — dbt: Fuentes, Macros Base y Capa `staging`
**Intent:** Establecer los cimientos de dbt: definición de fuentes, macros de materialización y modelos `staging`.

**Expected Outcomes:**
- `models/staging/_sources.yml` con las 8 tablas de `STG_SRC` y `freshness`/descripciones.
- Macros: `generate_schema_name` (D3), materialización `merge_existing` y `scd2_existing` (D1/D4) según resultado de ST-0.
- 8 modelos `stg_*` (`ephemeral`, D2): `TRIM` de textos, `NULL` → valores por defecto, normalización de fechas, RFC en mayúsculas/sin espacios, `ROW_NUMBER()` por llave natural ordenando por `INGESTED_AT DESC` (D7).
- Tests de columna en `staging` (`not_null` en llaves naturales).

**Todo List:**
1. Crear `_sources.yml` y los 8 modelos `stg_*`.
2. Implementar y probar las materializaciones/macros con un modelo de prueba.
3. `dbt compile` y `dbt run --select staging` sin errores.

**Relevant Context:** `02_ddl_stg_src.sql`, `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` paso 2. Modos: `dw-architect-oracle` (modelos `.sql/.yml`) y `agent` (macros si el regex lo impide).

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-7; sin commit aún)

**Resultado ST-6 (verificado en `etl-runner`, dbt-core 1.12.7 / dbt-oracle 1.12.0, Thin):**
- **Montaje temporal:** `etl-runner` no montaba el proyecto; se añadió `./etl/dbt_tms:/app/dbt_tms:ro` (solo lectura; no tapa `/app/profiles` ni `DBT_TARGET_PATH`/`DBT_LOG_PATH`). **Se retira en ST-11** para validar la imagen autocontenida.
- **Fuentes** (`models/staging/_sources.yml`): las 8 tablas de `STG_SRC` con descripción y 69 tests de fuente (`not_null` en llaves naturales/auditoría, `accepted_values` en `SOURCE_SYSTEM`, `ESTATUS_DESPACHO`, `TIPO_EVENTO`, `ESTATUS_PATIO`, `TIPO_GASTO`). **No se declara `freshness`:** `INGESTED_AT` es un reloj simulado determinista (D6), por lo que medir frescura contra el reloj real sería un falso negativo permanente.
- **Modelos `stg_*` (8, `ephemeral`; 0 objetos creados, `user_objects` de `ETL_RUNNER` = 0):** `TRIM`/`UPPER` en códigos, RFC en mayúsculas y sin ningún espacio (`regexp_replace(..., '\s', '')`), `COALESCE` de numéricos con el `DEFAULT` del DDL, fechas normalizadas, y deduplicación `ROW_NUMBER() OVER (PARTITION BY <llave natural> ORDER BY INGESTED_AT DESC, BATCH_ID DESC)`.
  | Modelo | Llave natural de deduplicación | Filas STG → stg |
  |---|---|---|
  | `stg_trackit_despacho` | `TALON_FOLIO` | 5,040 → 5,040 |
  | `stg_trackit_paradas` | `TALON_FOLIO, NUMERO_SECUENCIA` | 40,458 → 40,458 |
  | `stg_carta_porte_cabecera` | `UUID_CCP` | 5,040 → 5,040 |
  | `stg_carta_porte_mercancias` | `UUID_CCP, NUMERO_PARTIDA` | 15,236 → 15,236 |
  | `stg_flota_unidades` | `CODIGO_ECO` | 102 → **100** (ECO07 y ECO42 conservan la placa vigente) |
  | `stg_flota_estatus_diario` | `CODIGO_ECO, FECHA_CORTE` | 9,000 → 9,000 |
  | `stg_cfdi_ingreso` | `UUID_INGRESO` | 5,029 → 5,029 |
  | `stg_liquidaciones_gastos` | `FOLIO_LIQUIDACION, TIPO_GASTO, REFERENCIA_COMPROBANTE` | 22,511 → 22,511 |
- **Decisión de llave en liquidaciones (H5):** la tabla no tiene UQ y varias casetas comparten `(folio, tipo)`; se verificó que `(folio, tipo, referencia_comprobante)` es única (22,511 distintas) y se usa como llave de línea. `stg_flota_unidades` expone además `FECHA_EFECTIVA = trunc(INGESTED_AT)` (versión vigente) para el SCD2 de ST-8: `ECO07` → 2026-10-01 y `ECO42` → 2026-10-20 (posteriores al inicio 2026-08-09, P3).
- **Macros:** `merge_existing.sql` (P2: lee `ALL_TAB_IDENTITY_COLS`; `INSERT` sin columnas `IDENTITY`; `UPDATE SET` sin columnas del `ON`, sin `IDENTITY` y sin `CREATED_AT`; `UPDATED_AT = SYSTIMESTAMP` si el modelo no la aporta; `WHERE <identity> <> -1` protege la fila `-1`; valida que el `ON` exista y no sea `IDENTITY`; identificadores validados por regex), `scd2_existing.sql` (D4/P3: 1) `MERGE` de cierre con `FECHA_FIN_VALIDEZ = fecha_efectiva - 1`, `VERSION_ACTIVA='0'`, comparación NULL-safe con `DECODE` solo si la fecha efectiva es posterior al inicio de la versión activa; 2) `INSERT` de nueva versión activa solo si la llave no tiene versión activa; inicio = `initial_start_date` para llaves nuevas (A5) o fecha efectiva si ya tenía historia; fila `-1` intacta), `staging_helpers.sql` (`clean_text/clean_code/clean_rfc`). Test genérico `tests/generic/unique_combination.sql` (sin `dbt_utils`).
- **Prueba funcional de las macros con modelos temporales (ya eliminados) y limpieza verificada:**
  - `merge_existing` sobre `EDW_3FN.CAT_CLIENTES`: 1.ª corrida inserta (SK por `IDENTITY`), 2.ª entra por `WHEN MATCHED` y actualiza `RAZON_SOCIAL`/`UPDATED_AT` sin `ORA-38104`.
  - `scd2_existing` sobre `DWH_MART.DIM_VEHICULO` (`ZZ_TEST01`): inserción inicial `2026-08-09` activa → cambio de placa con fecha efectiva `2026-10-01` cierra v1 en `2026-09-30` (`VERSION_ACTIVA='0'`) y abre v2 activa → reejecución idempotente (sigue 2 versiones) → cambio con fecha efectiva **anterior** (`2026-09-01`) ignorado (P3). Fila `-1` intacta.
  - Limpieza: `DIM_VEHICULO`/`DIM_CLIENTE`/`DIM_FECHA`/`DIM_HORA` = 1 fila (`-1`), `FACT_DESPACHO_VIAJE` = 0; `EDW_3FN.CAT_CLIENTES`/`CAT_VEHICULOS`/`OP_VIAJES_DESPACHO` = 0; sin datos sucios en `EDW_3FN` ni `DWH_MART`.
- **Verificación:** `dbt parse` OK; `dbt compile` OK (8 modelos, 100 tests); `dbt test --select source:stg_src` → **PASS=69/69**; `dbt test --select staging` → **PASS=100/100** (69 de fuente + 31 de modelo: `not_null` y `unique_combination`); `dbt run --select staging` no crea objetos (ephemeral).
- **Observaciones:** (1) el aviso de rutas de configuración sin uso (`edw_3fn`, `marts`, `seeds`) desaparecerá al crear modelos/seeds en ST-7/ST-8. (2) `FECHA_EFECTIVA` en `stg_flota_unidades` depende de que `INGESTED_AT` del evento SCD2 sea el día efectivo (garantizado por el simulador, ST-3); para `ECO15@2026-11-07` se validará en ST-8 con `--mode incremental`.

---

### ST-7 — dbt: Capa `edw_3fn` (Catálogos y Entidades Atómicas)
**Intent:** Poblar `EDW_3FN` de forma incremental e idempotente respetando FKs y llaves naturales.

**Expected Outcomes:**
- Seeds de referencia (`etl/dbt_tms/seeds/`): `SAT_UNIDAD_MEDIDA`, `SAT_PRODUCTO_SERVICIO`, `SAT_CONFIG_AUTOTRANSPORTE` (incl. C3R2), `SAT_TIPO_PERMISO` y geografía de ubicaciones conocidas (H6), mergeados a `EDW_3FN`.
- Modelos `MERGE` por llave natural, en orden de dependencias: `CAT_POLIZAS_SEGURO`, `CAT_CLIENTES` (RFC desde Carta Porte), `CAT_OPERADORES`, `CAT_UBICACIONES`, `CAT_REMOLQUES`, `CAT_VEHICULOS` → `OP_VIAJES_DESPACHO`, `OP_VIAJES_PARADAS`, `OP_FLOTA_ESTATUS_DIARIO` → `FISCAL_CFDI_CARTAPORTE`, `FISCAL_CARTAPORTE_MERCANCIAS`, `FISCAL_CFDI_INGRESO`, `OP_LIQUIDACIONES_GASTOS`.
- Resolución de FKs naturales → IDs de `EDW_3FN`; `BATCH_ID` propagado; `UPDATED_AT` actualizado en `WHEN MATCHED`.
- Conteo de viajes en `OP_VIAJES_DESPACHO` = viajes distintos en `STG_TRACKIT_DESPACHO` (base de la conciliación de negocio).
- `OP_LIQUIDACIONES_GASTOS` conserva el detalle atómico (H5).
- Segunda corrida de `dbt run` sin cambios en staging no inserta duplicados (idempotencia).

**Todo List:**
1. Cargar seeds y mergearlos a catálogos SAT.
2. Implementar catálogos de negocio y entidades transaccionales en orden de FKs.
3. Probar idempotencia y la reconciliación STG ↔ EDW.

**Relevant Context:** `03_ddl_edw_3fn.sql` (columnas, UQs, CHECKs como `CK_OP_FEST_STATUS`, `CK_OP_GASTO_TIPO`), `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` paso 3. Modo: `dw-architect-oracle` / `agent` (seeds CSV).

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-8; sin commit aún)

#### Resultado ST-7

- **Seeds** (`etl/dbt_tms/seeds/`, esquema `ETL_RUNNER`, tipos en `_seeds.yml`): `seed_sat_unidad_medida` (3), `seed_sat_producto_servicio` (3), `seed_sat_config_autotransporte` (1), `seed_sat_tipo_permiso` (1), `seed_geo_ubicaciones` (8). Derivados 1 a 1 de `sat_catalogs` (`config_rules.yaml`).
- **Materialización `merge_existing`** (`+materialized: merge_existing` en `edw_3fn`): nueva config opcional `protect_column`.
  - Por defecto la columna protegida es la primera `IDENTITY` (`ALL_TAB_IDENTITY_COLS`) y el `UPDATE` incluye `where t.<ID> <> -1`.
  - Sin `IDENTITY` y sin `protect_column` **no** se emite predicado alguno (caso `SAT_*`; en ST-8 `DIM_FECHA`/`DIM_HORA` usarán `protect_column=ID_FECHA/ID_HORA`). Un `protect_column` inexistente en el destino genera error de compilación.
  - Evidencia SQL: `SAT_UNIDAD_MEDIDA` → `UPDATE` sin `where`, `UPDATED_AT = systimestamp`; `CAT_VEHICULOS` → `where t.ID_VEHICULO <> -1`, `UPDATED_AT = s.UPDATED_AT`, `INSERT` sin columna identity.
- **17 modelos** en `models/edw_3fn/` (`alias` = tabla destino, `unique_key` = llave natural), orden de FK forzado con `ref()` + `-- depends_on:`: `SAT_UNIDAD_MEDIDA` → resto `SAT_*` → `CAT_*` → `OP_*` / `FISCAL_*`.
- **Decisiones:**
  - `CAT_VEHICULOS.UPDATED_AT = INGESTED_AT` de la versión vigente (no `SYSTIMESTAMP`) → ST-8 deriva `FECHA_EFECTIVA = TRUNC(UPDATED_AT)` (D6). Verificado: `ECO07` → 2026-10-01, `ECO42` → 2026-10-20, resto (98) → 2026-08-09.
  - Cliente en `OP_VIAJES_DESPACHO` resuelto por `RAZON_SOCIAL` (único por cliente; `CLIENTE_ORIGEN/DESTINO` de TrackIt = `NOMBRE_REMITENTE/DESTINATARIO` de CCP en los 5,040 viajes).
  - `OP_LIQUIDACIONES_GASTOS`: llave MERGE `(FOLIO_LIQUIDACION, TIPO_GASTO, REFERENCIA_COMPROBANTE)` (H5).
- **Gotcha:** `Set-Content -Encoding utf8` (PowerShell 5.1) escribe BOM y provoca `ORA-00911` en modelos; escribir archivos sin BOM.
- **Conteos tras `dbt run --select edw_3fn` (ejecutado 2 veces, 17/17 OK en ambas, conteos idénticos, 0 duplicados):**

| Tabla EDW_3FN | Filas | Referencia STG |
|---|---|---|
| SAT_UNIDAD_MEDIDA / SAT_PRODUCTO_SERVICIO / SAT_CONFIG_AUTOTRANSPORTE / SAT_TIPO_PERMISO | 3 / 3 / 1 / 1 | seeds |
| CAT_POLIZAS_SEGURO / CAT_CLIENTES / CAT_OPERADORES / CAT_UBICACIONES | 10 / 6 / 15 / 8 | distintos en STG |
| CAT_REMOLQUES / CAT_VEHICULOS | 100 / 100 | 102 filas STG → 100 tras dedupe |
| OP_VIAJES_DESPACHO | 5,040 | STG_TRACKIT_DESPACHO 5,040 |
| OP_VIAJES_PARADAS | 40,458 | STG_TRACKIT_PARADAS 40,458 |
| OP_FLOTA_ESTATUS_DIARIO | 9,000 | STG_FLOTA_ESTATUS_DIARIO 9,000 |
| FISCAL_CFDI_CARTAPORTE | 5,040 | STG_CARTA_PORTE_CABECERA 5,040 |
| FISCAL_CARTAPORTE_MERCANCIAS | 15,236 | STG_CARTA_PORTE_MERCANCIAS 15,236 |
| FISCAL_CFDI_INGRESO | 5,029 | STG_CFDI_INGRESO 5,029 |
| OP_LIQUIDACIONES_GASTOS | 22,511 | STG_LIQUIDACIONES_GASTOS 22,511 |

- **Pruebas:** `models/edw_3fn/_edw_3fn.yml` (`not_null`, `unique`, `relationships`, `unique_combination`) + singulares `edw_3fn_conciliacion_stg.sql` (conteos STG ↔ EDW) y `edw_3fn_ubicaciones_sin_geografia.sql`. `dbt test --select edw_3fn` → **PASS=103/103** (203 tests en el proyecto).
- **Observación:** el aviso de rutas sin uso queda solo para `models.tms_dbt.marts` (se resolverá en ST-8).

---

### ST-8 — dbt: Dimensiones Conformadas en `DWH_MART`
**Intent:** Construir las 10 dimensiones con llaves subrogadas, fila `-1` garantizada y SCD adecuado.

**Expected Outcomes:**
- `marts/dimensions/`:
  - `DIM_FECHA` (calendario del rango de datos más holgura, claves `YYYYMMDD`) y `DIM_HORA` (1,440 filas `HHMM`): generados por SQL (`CONNECT BY`/CTE), idempotentes.
  - `DIM_REMOLQUE`, `DIM_OPERADOR`, `DIM_CLIENTE`, `DIM_UBICACION`, `DIM_PRODUCTO_SAT`, `DIM_POLIZA` en **SCD Tipo 1** (MERGE por llave natural; SK generada por `IDENTITY`).
  - `DIM_PERFIL_VIAJE` (junk) con combinaciones realmente presentes (A3).
  - `DIM_VEHICULO` en **SCD Tipo 2** (A5/A6, D4): cierre de versión previa e inserción de la nueva; nunca más de una versión activa por `CODIGO_ECO`.
- La fila `-1` de las 10 dimensiones permanece intacta (los modelos no la eliminan ni duplican).
- Prueba de SCD2: re-emitir `STG_FLOTA_UNIDADES` con placa distinta (evento de ST-3), ejecutar `dbt run` y comprobar 2 versiones (una cerrada, una activa) para esa unidad.

**Todo List:**
1. Implementar `DIM_FECHA` y `DIM_HORA`.
2. Implementar dimensiones SCD1 y `DIM_PERFIL_VIAJE`.
3. Implementar `DIM_VEHICULO` SCD2 con la materialización `scd2_existing`.
4. Validar conteos por dimensión vía MCP (`BI_READER`, `DWH_MART`).

**Relevant Context:** `04_ddl_dwh_mart.sql` §1–§2 (UQs, `-1`), `.bob/rules/01-kimball-architecture.md` §3. Modo: `dw-architect-oracle`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-9; sin commit aún)

#### Resultado ST-8

- **Precisión 1 — SCD2 incremental diferido a ST-11:** no se ejecutó el simulador en `--mode incremental` (la BD sigue con el backfill limpio de 90 días: `STG_TRACKIT_DESPACHO` = 5,040 viajes). La prueba real de `ECO15@2026-11-07` se corre en ST-11 tras certificar hechos (ST-9) y screens (ST-10). En ST-8 se hizo una comprobación **aislada** de `scd2_existing` (ver abajo) y se revirtió.
- **Modelos** (`models/marts/dimensions/`, `+materialized: merge_existing`; `dim_vehiculo` con `scd2_existing`; `alias` = tabla destino): `dim_fecha`, `dim_hora`, `dim_vehiculo`, `dim_remolque`, `dim_operador`, `dim_cliente`, `dim_ubicacion`, `dim_producto_sat`, `dim_poliza`, `dim_perfil_viaje`. `vars` nuevas en `dbt_project.yml`: `dim_fecha_inicio`/`dim_fecha_fin` y `dim_vehiculo_inicio_validez`.
- **DIM_FECHA / DIM_HORA** (`protect_column` = `ID_FECHA` / `ID_HORA`; sin IDENTITY):
  - `DIM_FECHA` 2026-01-01..2026-12-31 vía `CONNECT BY` → 365 días + fila `-1` = **366**.
  - `DIM_HORA` 1,440 minutos + fila `-1` = **1,441**. `ID_HORA = 0` (00:00) es una fila válida distinta de `-1`.
  - **Robustez NLS:** `NOMBRE_MES`/`NOMBRE_DIA` con `TO_CHAR(.., 'FMMonth'/'FMDay', 'NLS_DATE_LANGUAGE=SPANISH')` + `INITCAP`; `ES_FIN_SEMANA_FLAG` con `TO_CHAR(.., 'DY', 'NLS_DATE_LANGUAGE=ENGLISH') IN ('SAT','SUN')`; `DIA_SEMANA` ISO (1=lunes..7=domingo) calculado como `FECHA - TRUNC(FECHA,'IW') + 1` (no usa `'D'`); `SEMANA_ANIO` ISO (`IW`). Muestra verificada: 2026-02-07 → Sábado/6/'1'; 2026-02-09 → Lunes/1/'0'; 2026-08-09 → Domingo/7/'1'; 2026-12-31 → Jueves/4/'0'/semana 53.
  - `DIM_HORA`: `HORA_12` 12 para 00:xx y 12:xx; `AM_PM` por `HORA_24 < 12`; `PERIODO_DIA` MADRUGADA (<6) / MAÑANA (<12) / TARDE (<19) / NOCHE.
- **DIM_VEHICULO (A5, vigencia inicial uniforme):** `FECHA_EFECTIVA = TRUNC(UPDATED_AT)` de `CAT_VEHICULOS`; `initial_start_date = date '2026-08-09'` (var). Resultado: **100 unidades activas, todas con `FECHA_INICIO_VALIDEZ = 2026-08-09` y `FECHA_FIN_VALIDEZ = NULL`**, incluidas `ECO07` y `ECO42` (cuyo `UPDATED_AT` es octubre). 0 versiones cerradas, 0 inicios distintos de 2026-08-09 → en ST-9 ningún viaje de agosto/septiembre cae a `-1` por rango.
- **DIM_PERFIL_VIAJE:** llave del MERGE = los 4 atributos (`UQ_DIM_PERFIL`). `ETAPA_VIAJE` derivada de `ESTATUS_DESPACHO` (A3): `CERRADO`→`CERRADO`, `EN_TRANSITO`→`TRANSITO`; resto por defecto del DDL (`DESTINO`/`COMPLETO`/`DESTINO`). Resultado: 2 perfiles reales (+ `-1`) = **3 filas**.
- **Idempotencia:** `dbt run --select marts.dimensions` ejecutado 2 veces, 10/10 OK en ambas, conteos idénticos (consulta MCP `BI_READER` entre corridas).
- **Conteos finales `DWH_MART` (MCP `BI_READER`, incluye la fila `-1`; las 10 dimensiones tienen exactamente una fila `-1`):**

| Dimensión | Filas | Sin `-1` | Origen |
|---|---|---|---|
| DIM_FECHA | 366 | 365 | calendario 2026 |
| DIM_HORA | 1,441 | 1,440 | minutos del día |
| DIM_VEHICULO | 101 | 100 | `CAT_VEHICULOS` (100 activas) |
| DIM_REMOLQUE | 101 | 100 | `CAT_REMOLQUES` |
| DIM_OPERADOR | 16 | 15 | `CAT_OPERADORES` |
| DIM_CLIENTE | 7 | 6 | `CAT_CLIENTES` |
| DIM_UBICACION | 9 | 8 | `CAT_UBICACIONES` |
| DIM_PRODUCTO_SAT | 4 | 3 | `SAT_PRODUCTO_SERVICIO` |
| DIM_POLIZA | 11 | 10 | `CAT_POLIZAS_SEGURO` |
| DIM_PERFIL_VIAJE | 3 | 2 | perfiles presentes |

  Las 6 tablas de hechos siguen en 0 filas (no se escribió nada indebido en `DWH_MART`).
- **Pruebas:** `_dimensions.yml` (`not_null`/`unique`/`accepted_values`/`unique_combination`) + singulares `marts_dim_fila_menos_uno` (la `-1` existe una vez y con valores dummy intactos en las 10 dimensiones), `marts_dim_conciliacion_edw` (EDW ↔ DWH sin `-1`, 365/1,440 filas de calendario, coherencia fin de semana/ID) y `marts_dim_vehiculo_vigencia` (1 activa por unidad, inicio uniforme, vigencias válidas). `dbt test --select marts` → **47/47**; `dbt test` completo → **250/250 PASS**, sin avisos de rutas sin uso.
- **Comprobación aislada de `scd2_existing` (revertida):** copia de `DIM_VEHICULO` en `ETL_RUNNER.TMP_DIM_VEH` (tabla temporal, sin tocar `DWH_MART`), modelo temporal que simula `ECO15` con placa `TST9999` y fecha efectiva 2026-11-07. Resultado: `ECO15` queda con 2 versiones (v1 `98JM19` inicio 2026-08-09 fin **2026-11-06**, inactiva; v2 `TST9999` inicio 2026-11-07, activa), 100 activas en total y fila `-1` intacta; la segunda corrida sin cambios no abrió versiones nuevas (102 filas). La tabla y el modelo temporales se eliminaron y `git status` queda sin residuos.
- **Observación:** `ETL_RUNNER` ya no tiene objetos temporales; la migración de `DIM_VEHICULO` a `FECHA_EFECTIVA` real para `ECO15` ocurrirá en ST-11 con el simulador en modo incremental.

---

### ST-9 — dbt: Tablas de Hechos y Snapshot de Flota
**Intent:** Construir las 6 tablas de hechos con grano confirmado, *Surrogate Key Lookup* con fallback `-1` y métricas derivadas exactas, sin ningún join directo entre hechos.

**Expected Outcomes:**
- `FACT_DESPACHO_VIAJE` (grano: 1 por viaje; `ID_VEHICULO` por versión vigente a la fecha del viaje; `CONTADOR_CERRADO` desde el evento `FIN VIAJE`/`FECHA_CIERRE`; `CONTADOR_DESPACHO = 1`).
- `FACT_EVENTOS_PARADA` (grano: 1 por parada; recalcula `LAG_LLEGADA_MINUTOS`, `LAG_SALIDA_MINUTOS`, `TIEMPO_ESTADIA_MINUTOS` desde timestamps; `CONTADOR_PUNTUAL` con tolerancia configurable en `vars`).
- `FACT_LINEAS_CARGA_CARTAPORTE` (grano: 1 por partida; `ID_POLIZA`, `ID_PRODUCTO_SAT`, `ID_ORIGEN/DESTINO_UBICACION`).
- `FACT_FACTURACION_FLETE` (grano: 1 por CFDI de Ingreso; `ID_VEHICULO`/`ID_OPERADOR`/`ID_DESTINO_UBICACION` resueltos vía el viaje en `EDW_3FN`, **no** vía `FACT_DESPACHO_VIAJE`).
- `FACT_GASTOS_LIQUIDACION` (grano: 1 por `(FOLIO_LIQ, TIPO_GASTO)`, agregado y pivotado según H5).
- `FACT_SNAPSHOT_FLOTA_DIARIO` (1 fila por vehículo por día): cruce de las 100 unidades de `DIM_VEHICULO` × `DIM_FECHA` del rango contra `OP_FLOTA_ESTATUS_DIARIO` y actividad de despacho; indicadores `1/0` con suma = 1 por unidad-día; `ESTATUS_UNIDAD`, `KMS_RECORRIDOS_DIA`, `KWH_CONSUMO_DIA`.
- Todas las FKs `NOT NULL` (lookup fallido → `-1`) y carga incremental con `MERGE` por llave natural/degenerada.
- Ningún modelo contiene `JOIN` entre dos tablas `FACT_*`; todo cruce multi-hecho (si se requiere) usa Drill-Across (CTEs + `FULL OUTER JOIN`).

**Todo List:**
1. Implementar los 6 hechos en orden (`DESPACHO` → `EVENTOS_PARADA` → `LINEAS_CARGA` → `FACTURACION` → `GASTOS` → `SNAPSHOT`).
2. Verificar granos contra `docs/Arquitectura-dw-analytics-tms.docx` y `.bob/rules-dw-architect-oracle/01-oracle-ddl-conventions.md` §4.
3. Ejecutar dos corridas consecutivas y comprobar idempotencia (mismos conteos).

**Relevant Context:** `04_ddl_dwh_mart.sql` §3 (columnas, UQs, CHECKs), `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` pasos 5–6. Modo: `dw-architect-oracle`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-10; sin commit aún)

#### Resultado ST-9

- **Modelos** (`models/marts/facts/`, `+materialized: merge_existing`, `alias` = tabla destino): `fact_despacho_viaje`, `fact_eventos_parada`, `fact_lineas_carga_cartaporte`, `fact_facturacion_flete`, `fact_gastos_liquidacion`, `fact_snapshot_flota_diario`. Macros nuevas en `macros/marts_helpers.sql`: `etapa_viaje()` (fuente única de A3, reutilizada por `dim_perfil_viaje` y `fact_despacho_viaje`), `minutes_between()`, `vehiculo_asof_join()`, `dim_fecha_key()` y `dim_hora_key()` (todas las FKs salen con `NVL(..., -1)`).
- **Precisión 1 — lookup point-in-time en `DIM_VEHICULO` (A5):** los 6 hechos resuelven `ID_VEHICULO` con `TRUNC(fecha_evento) BETWEEN FECHA_INICIO_VALIDEZ AND NVL(FECHA_FIN_VALIDEZ, DATE '2099-12-31') AND ID_VEHICULO <> -1` (no por `VERSION_ACTIVA`). Fecha del evento: despacho (despacho y facturación — la factura usa la fecha del servicio, no la de emisión), llegada real o programada (paradas), emisión del CCP (líneas) y liquidación (gastos). En `fact_snapshot_flota_diario` el universo es `DIM_FECHA × DIM_VEHICULO` con el mismo filtro de vigencia, de modo que una unidad con 2 versiones aporta exactamente 1 fila por día. Comprobación aislada (sin escribir en `DWH_MART`) simulando que `ECO15` abre v2 el 2026-11-07: **100 filas/día y 100 unidades distintas** del 2026-11-04 al 2026-11-10, con 1 fila de `ECO15` cada día.
- **Precisión 2 — cero Fact-to-Fact y perfil:** ningún modelo `FACT_*` referencia a otro; todo se resuelve desde `EDW_3FN` y dimensiones (la facturación toma destino vía la Carta Porte del viaje en EDW; KMS/KWH del snapshot salen de `OP_FLOTA_ESTATUS_DIARIO`). El test `marts_sin_fact_a_fact` recorre el grafo de dbt y el código; **se validó que no es vacuo**: con un modelo temporal que unía dos hechos reportó 3 violaciones (modelo eliminado). `ID_PERFIL_VIAJE` usa la misma derivación `EN_TRANSITO → TRANSITO`, `CERRADO → CERRADO` de ST-8.
- **Precisión 3a — paradas abiertas (H9):**
  - `LAG_LLEGADA_MINUTOS` y `TIEMPO_ESTADIA_MINUTOS` se recalculan desde los timestamps de EDW (`minutes_between`); un test los concilia contra lo emitido por TrackIt (tolerancia 0.01 min): 0 diferencias.
  - **Hallazgo:** `LAG_SALIDA_MINUTOS` **no es derivable** desde EDW: la salida programada no se persiste en STG (`FECHA_HORA_PROGRAMADA` es solo la llegada programada). Se conserva el valor de EDW (solo si hay salida real) y se documenta; el recálculo completo requeriría añadir `FECHA_HORA_SALIDA_PROGRAMADA` al DDL de `STG_SRC`/`EDW_3FN`, no hecho por estar fuera de alcance.
  - Tolerancia de `CONTADOR_PUNTUAL`: `vars.puntualidad_tolerancia_minutos: 15` en `dbt_project.yml` (puntual si `LAG_LLEGADA <= 15`; los adelantos cuentan como puntuales).
  - Manejo de nulos: ninguna columna `NOT NULL` se rompe. Parada `PENDIENTE` (14 filas: 3 `DESCARGA` y 11 `FIN VIAJE` de los viajes abiertos, según estatus en EDW) → fechas/horas de llegada y salida `-1`, métricas `0`, `CONTADOR_PARADA = 0` y `CONTADOR_PUNTUAL = 0`. Parada `EN_CURSO` (3 `DESCARGA`) → llegada real conocida, salida `-1`, `LAG_SALIDA = 0`, `ESTADIA = 0`, `CONTADOR_PARADA = 1`. Estos `-1` son **legítimos** ("evento aún no ocurrido"): el test `marts_fact_fk_menos_uno` exige que coincidan **exactamente** con las fechas nulas de EDW (ni falsos `-1` por lookup fallido, ni `-1` faltantes). En `FACT_DESPACHO_VIAJE`, los 11 viajes abiertos tienen `ID_FECHA_CIERRE = -1` y `CONTADOR_CERRADO = 0`.
- **Precisión 3b — pivoteo de gastos (H5):** agrega por `(FOLIO_LIQ, TIPO_GASTO)` sumando `IMPORTE_GASTO` y pivota `CASETA`→`MONTO_CASETA`, `OPERADOR`→`MONTO_OPERADOR`, `MANTENIMIENTO`→`MONTO_MANTENIMIENTO`, `OTROS` y `COMBUSTIBLE_ENERGIA`→`MONTO_OTROS_GASTOS`. Se verificó previamente que los atributos del folio (talón, fecha, unidad, remolque, operador) son constantes por folio (0 inconsistentes).
- **Idempotencia:** `dbt run --select marts.facts` ejecutado 2 veces, 6/6 OK en ambas; conteos y llaves distintas idénticos (0 duplicados) y verificados vía MCP `BI_READER`.
- **Conteos finales `DWH_MART` (MCP `BI_READER`):**

| Hecho | Filas | Llaves distintas | Referencia |
|---|---|---|---|
| FACT_DESPACHO_VIAJE | 5,040 | 5,040 | `OP_VIAJES_DESPACHO` (5,029 cerrados + 11 abiertos) |
| FACT_EVENTOS_PARADA | 40,458 | 40,458 | `OP_VIAJES_PARADAS` (40,444 con `CONTADOR_PARADA = 1`) |
| FACT_LINEAS_CARGA_CARTAPORTE | 15,236 | 15,236 | `FISCAL_CARTAPORTE_MERCANCIAS` (5,040 CCP) |
| FACT_FACTURACION_FLETE | 5,029 | 5,029 | `FISCAL_CFDI_INGRESO` |
| FACT_GASTOS_LIQUIDACION | 10,373 | 10,373 | pares `(folio, tipo)` de 22,511 líneas atómicas |
| FACT_SNAPSHOT_FLOTA_DIARIO | 9,000 | 9,000 | 100 unidades × 90 días (2026-08-09 a 2026-11-06), 100 filas/día |

- **Conciliación monetaria y de métricas (vía MCP y por test contra `EDW_3FN`, al centavo):**
  - Facturación: `SUM(IMPORTE_TOTAL_FACTURADO)` = **309,227,803.56** = `SUM(SUBTOTAL − DESCUENTO + IVA_TRASLADADO − IVA_RETENIDO)`; 0 filas con descuadre fiscal.
  - Gastos: `SUM(IMPORTE_GASTO)` = **17,855,296.07** = `SUM(MONTO_CASETA + MONTO_OPERADOR + MONTO_MANTENIMIENTO + MONTO_OTROS_GASTOS)`; 0 filas donde el pivote difiera del importe; conciliado también por cada tipo contra el detalle atómico.
  - Operación: `KMS_TOTAL` despacho = `KMS_RECORRIDOS_DIA` snapshot = **1,820,487.49**; `KWH` despacho = `KWH_CONSUMO_DIA` snapshot = **326,806.52** (calculados de forma independiente, sin Fact-to-Fact); `PESO_KG` de líneas = `PESO_BRUTO_TOTAL_KG` de viajes = 93,612,287.19.
  - Snapshot: 56.00 % con viaje / 40.00 % sin viaje / 4.00 % inactivas (A1); 0 unidades `SIN_REPORTE`; indicadores con suma = 1 en las 9,000 filas.
  - Puntualidad global (tolerancia 15 min): 21,800 de 40,444 paradas ocurridas = 53.90 %.
- **FKs en `-1`:** 0 en las FKs de dimensión de los 6 hechos (vehículo, remolque, operador, clientes, ubicaciones, producto, póliza, perfil, fecha/hora de inicio, emisión, facturación y liquidación). Los únicos `-1` son los legítimos de eventos no ocurridos: 11 `ID_FECHA_CIERRE` en despacho y 14 llegadas / 17 salidas en paradas (`PENDIENTE`/`EN_CURSO`).
- **Pruebas:** `_facts.yml` (`not_null`, `unique`, `unique_combination`, `relationships` de cada FK, `accepted_values`) + singulares `marts_sin_fact_a_fact`, `marts_fact_fk_menos_uno`, `marts_fact_conciliacion_edw` (conteos de grano, montos, KMS/KWH, peso) y `marts_fact_metricas_y_vigencia` (métricas de paradas, snapshot por día, lookup point-in-time de los 5 hechos transaccionales). `dbt test` completo → **357/357 PASS**, 0 avisos.
- **Observaciones para ST-10/ST-11:**
  - Los 11 viajes abiertos (`EN_TRANSITO`) pertenecen al día 90 (2026-11-06); `FACT_DESPACHO_VIAJE` los carga con `CONTADOR_CERRADO = 0`. Cuando el modo incremental los cierre, el `MERGE` por `NUMERO_TALON` actualiza el hecho.
  - `FACT_FACTURACION_FLETE` tiene fechas hasta 2026-11-09 (factura con rezago A4), todas dentro de `DIM_FECHA` (2026).
  - `DISTANCIA_DECLARADA_KM` se repite por partida de un mismo CCP (según DDL): no sumar entre partidas.
  - `FACT_SNAPSHOT_FLOTA_DIARIO` es un snapshot acumulativo por `MERGE` por `(fecha, vehículo)`: si `ECO15` abre v2 en ST-11, los días ≥ 2026-11-07 se generan con la nueva `ID_VEHICULO` y los anteriores conservan la v1 (filas históricas no se reescriben).

---

### ST-10 — Data Quality Screens (`schema.yml` + tests SQL)
**Intent:** Materializar `kimball_quality_screens.md` como pruebas ejecutables; criterio de aceptación: 100% en verde.

**Expected Outcomes:**
- **Column screens:** `not_null` en SKs, llaves naturales y todas las FKs de hechos; `unique` en SKs y llaves naturales (versión activa en SCD2); rangos `kms_total >= 0`, `peso_kg <= 35000`; conteos `contador_*` / `*_indicador` ∈ {0,1}.
- **Structure screens:** `relationships` para **todas** las FKs de los 6 hechos hacia sus dimensiones; test singular “las 10 dimensiones contienen `-1`/`DESCONOCIDO`”; test “cero FKs `NULL`”.
- **Business rule screens:** `kms_cargado + kms_vacio = kms_total`; conteo de viajes `EDW_3FN` = `FACT_DESPACHO_VIAJE`; por día `con + sin + inactiva = 1` por unidad y total diario = `fleet_size` (100); cero joins Fact↔Fact (test estático sobre SQL compilado); simulador↔dbt: `LAG_*` recalculados = emitidos; ningún hecho válido con `ID_FECHA = -1` (H3); conciliación de importes `STG_CFDI_INGRESO` ↔ `FACT_FACTURACION_FLETE` y `STG_LIQUIDACIONES_GASTOS` ↔ `FACT_GASTOS_LIQUIDACION`.
- Tabla de trazabilidad “ítem del checklist ↔ test” en este documento.

**Todo List:**
1. Escribir `schema.yml` por capa y tests singulares en `etl/dbt_tms/tests/`.
2. Ejecutar `dbt test`; corregir causa raíz (modelos o simulador) ante fallos, nunca relajando umbrales.
3. Marcar los ítems del checklist y reportar conteo de tests aprobados/fallidos.

**Relevant Context:** `.bob/skills/dbt-oracle-etl-pipeline/checklists/kimball_quality_screens.md`. Modo: `dw-architect-oracle`.

**Status:** `[x] done` (pendiente de aprobación del usuario para iniciar ST-11; sin commit aún)

#### Resultado ST-10

- **Auditoría y cobertura completa de Kimball Quality Screens:** Se cruzaron todos los ítems de `.bob/skills/dbt-oracle-etl-pipeline/checklists/kimball_quality_screens.md` contra la suite dbt. Se ampliaron las restricciones `not_null` y `accepted_values` en `_facts.yml` (cubriendo todas las dimensiones degeneradas, métricas numéricas y contadores/indicadores unitarios de hechos) y se fortalecieron las pruebas singulares de conciliación y reglas de negocio.
- **Suite de pruebas dbt:** **404 tests en verde (PASS=404/404, 0 WARN, 0 ERROR, 0 SKIP)** ejecutados en el contenedor `etl-runner` sobre Oracle Database (Thin Mode).
  - Fuentes `STG_SRC` (`_sources.yml`): 69 tests.
  - Modelos `staging` (`_staging.yml`): 31 tests.
  - Modelos `edw_3fn` (`_edw_3fn.yml` + singulares): 108 tests.
  - Capa dimensional `DWH_MART` (`_dimensions.yml` + singulares): 47 tests.
  - Capa de hechos `DWH_MART` (`_facts.yml` + singulares): 149 tests.

#### Tabla de Trazabilidad: Ítem del Checklist ↔ Test

| Categoría | Ítem de `kimball_quality_screens.md` | Test(s) dbt Implementados | Resultado |
|---|---|---|---|
| **Column Screens** | `not_null` en SKs, llaves naturales y todas las FKs de hechos | Generic `not_null` en `_dimensions.yml` (10 SKs + llaves naturales) y `_facts.yml` (6 SKs + 37 FKs + llaves degeneradas) + `tests/marts_fact_fk_menos_uno.sql` | **PASS** |
| **Column Screens** | `unique` en SKs y llaves naturales de dimensiones (versión activa en SCD2) | Generic `unique` en `_dimensions.yml` + `unique_combination` `[CODIGO_ECO, FECHA_INICIO_VALIDEZ]` + `tests/marts_dim_vehiculo_vigencia.sql` (`VERSION_ACTIVA = '1'`) | **PASS** |
| **Column Screens** | Rango: `kms_total >= 0` | Singular `tests/marts_fact_conciliacion_edw.sql` (`RANGO: KMS_TOTAL, CARGADO, VACIO >= 0` en `FACT_DESPACHO_VIAJE` y `RANGO: KMS_RECORRIDOS_DIA >= 0` en `FACT_SNAPSHOT_FLOTA_DIARIO`) | **PASS** |
| **Column Screens** | Rango: `peso_kg <= 35000` | Singular `tests/marts_fact_conciliacion_edw.sql` (`RANGO: PESO_KG lineas entre 0 y 35000` en `FACT_LINEAS_CARGA_CARTAPORTE` y `RANGO: PESO_BRUTO_TOTAL_KG viaje entre 0 y 35000` en `FACT_DESPACHO_VIAJE`) | **PASS** |
| **Column Screens** | Rango: métricas de conteo (`contador_*`, `*_indicador`) ∈ {0, 1} | Generic `accepted_values` en `_facts.yml` para `CONTADOR_DESPACHO` (1), `CONTADOR_CERRADO` (0,1), `CONTADOR_PARADA` (0,1), `CONTADOR_PUNTUAL` (0,1), `CONTADOR_PARTIDA` (1), `CONTADOR_FACTURA` (1), `CONTADOR_LIQUIDACION` (1), `UNIDAD_CON_VIAJE_INDICADOR` (0,1), `UNIDAD_SIN_VIAJE_INDICADOR` (0,1), `UNIDAD_INACTIVA_INDICADOR` (0,1) y `FLOTA_TOTAL_INDICADOR` (1) | **PASS** |
| **Structure Screens** | `relationships`: toda FK de los 6 hechos apunta a una dimensión existente | Generic `relationships` en `_facts.yml` (37 tests sobre las 6 tablas de hechos hacia `DIM_FECHA`, `DIM_HORA`, `DIM_VEHICULO`, `DIM_REMOLQUE`, `DIM_OPERADOR`, `DIM_CLIENTE`, `DIM_UBICACION`, `DIM_PRODUCTO_SAT`, `DIM_POLIZA`, `DIM_PERFIL_VIAJE`) | **PASS** |
| **Structure Screens** | Las 10 dimensiones conformadas contienen la fila `-1` / `DESCONOCIDO` | Singular `tests/marts_dim_fila_menos_uno.sql` (valida la existencia de `-1` y atributos dummy exactos en las 10 dimensiones) | **PASS** |
| **Structure Screens** | Cero FKs `NULL`; llaves faltantes resueltas a `-1` | Generic `not_null` en las 37 FKs en `_facts.yml` + singular `tests/marts_fact_fk_menos_uno.sql` (prohíbe FKs nulas y restringe `-1` a eventos no ocurridos) | **PASS** |
| **Business Rule Screens** | `kms_cargado + kms_vacio = kms_total` en `FACT_DESPACHO_VIAJE` | Singular `tests/marts_fact_conciliacion_edw.sql` (`REGLA: KMS_CARGADO + KMS_VACIO = KMS_TOTAL`) | **PASS** |
| **Business Rule Screens** | Conteo de viajes `EDW_3FN` = `FACT_DESPACHO_VIAJE` | Singular `tests/marts_fact_conciliacion_edw.sql` (`CONTEO despacho`: `OP_VIAJES_DESPACHO` = `FACT_DESPACHO_VIAJE` = 5,040) | **PASS** |
| **Business Rule Screens** | `FACT_SNAPSHOT_FLOTA_DIARIO`: suma indicadores = `flota_total_indicador` (1) y total diario = 100 | Singular `tests/marts_fact_metricas_y_vigencia.sql` (`SNAPSHOT: dia con indicadores suma <> FLOTA_TOTAL_INDICADOR o FLOTA_TOTAL <> 1` = 0, `SNAPSHOT: dia sin 100 unidades (flota)` = 0, `SNAPSHOT: dia con unidades SIN_REPORTE` = 0) | **PASS** |
| **Business Rule Screens** | Cero joins directos Fact ↔ Fact en modelos | Singular `tests/marts_sin_fact_a_fact.sql` (auditoría estática del grafo de dbt y código SQL compilado) | **PASS** |
| **Business Rule Screens** | Conciliación `LAG_LLEGADA_MINUTOS` y `TIEMPO_ESTADIA_MINUTOS` recalculados vs. emitidos | Singular `tests/marts_fact_metricas_y_vigencia.sql` (`PARADAS: LAG_LLEGADA recalculado <> EDW` = 0, `PARADAS: TIEMPO_ESTADIA recalculado <> EDW` = 0; `LAG_SALIDA_MINUTOS` conservado y documentado) | **PASS** |
| **Business Rule Screens** | Ningún hecho completado con `ID_FECHA = -1` (respetando `-1` legítimos de pendientes/en curso) | Singular `tests/marts_fact_fk_menos_uno.sql` (conciliado 1 a 1 contra nulabilidad en `EDW_3FN`) | **PASS** |
| **Business Rule Screens** | Conciliación de importes `STG_CFDI_INGRESO` ↔ `FACT_FACTURACION_FLETE` y `STG_LIQUIDACIONES_GASTOS` ↔ `FACT_GASTOS_LIQUIDACION` | Singular `tests/marts_fact_conciliacion_edw.sql` (`MONTO facturado total (vs STG)` = $309,227,803.56; `MONTO gastos total (vs STG)` = $17,855,296.07) | **PASS** |

---

### ST-11 — Refresco Semántico, Validación E2E, Incremental y Cierre
**Intent:** Cerrar el ciclo hasta `BI_SEMANTIC`, verificar métricas con el mismo usuario que usa Superset y documentar el cierre de fase.

**Expected Outcomes:**
- Invocación de `BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC` por `ETL_RUNNER` al final de la corrida (`on-run-end` o `dbt run-operation refresh_semantic_layer`), con bloque PL/SQL sin interpolación de strings.
- Verificación con `BI_READER` (MCP/Python), por ejemplo:
  - `MV_METRICAS_FLOTA_DIARIA`: `TOTAL_UNIDADES_FLOTA = 100` cada día; `PCT_CON_VIAJE ≈ 56`, `PCT_SIN_VIAJE ≈ 40`, `PCT_INACTIVAS ≈ 4`.
  - `MV_PRODUCTIVIDAD_ECO_MENSUAL`: filas por unidad/mes con `TOTAL_FACTURACION > 0`, `KMS_TOTAL` y `RENDIMIENTO_PROM_KMS_KWH` en rango.
  - Conciliación cruzada: suma de facturación y Kms en `VW_FACT_*` = MV = totales de `STG_SRC`/`EDW_3FN`.
  - Consultas de las vistas base (`VW_FACT_*`, `VW_DIM_*`, vistas de rol de ubicación) sin errores `ORA-`.
- Corrida **incremental** (`--mode incremental --trips 5` + `dbt run` + refresco) que añade viajes y cierra abiertos sin duplicados; reejecución idempotente.
- Revisión Actor‑Crítico (`actor-critic-dw-review`) sin hallazgos BLOCKER (secretos, SE2, Kimball, `redis:*`, Fact↔Fact).
- Este documento actualizado con “Resultados del Spike”, “Cierre de Fase 3: Resultados de Validación (DoD)” y checklist de tests; documentación de comandos de ejecución en `docs/`.

**Todo List:**
1. Implementar la macro/operación de refresco y enlazarla al final de `dbt build`.
2. Ejecutar la cadena completa: simulador backfill → `dbt build` → refresco; capturar conteos y tiempos.
3. Ejecutar consultas de verificación con `BI_READER` y registrar resultados.
4. Ejecutar la corrida incremental y la prueba SCD2.
5. Lanzar la auditoría Actor‑Crítico y resolver hallazgos.
6. Actualizar documentación y realizar commits atómicos (`feat(etl): …`, `docs: …`).

**Relevant Context:** `05_views_bi_semantic.sql` §4–§6 (MVs, SP, grants), `docs/mcp_oracle_readonly.md`, `.bob/skills/actor-critic-dw-review/SKILL.md`, `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` §7 Fase 3. Modo: `agent`.

**Status:** `[x] done` (refresco semántico en on-run-end, carga incremental validada, volumen temporal retirado y auditoría Actor-Crítico aprobada sin bloqueadores)

#### Resultado ST-11 (verificado en vivo)
- **Macro de refresco semántico y hook `on-run-end`:**
  - Se implementó `etl/dbt_tms/macros/refresh_semantic_layer.sql` invocando `BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC` de forma atómica y segura (`AUTHID DEFINER`) mediante bloque PL/SQL estático sin interpolación.
  - Enlazado en `dbt_project.yml` mediante `on-run-end: ["{{ refresh_semantic_layer() }}"]`. Se ejecuta automáticamente en cada corrida de `dbt build`, `dbt run` o `dbt test`.
- **Verificación semántica con MCP `BI_READER` (post-backfill 90 días):**
  - `MV_METRICAS_FLOTA_DIARIA`: 90 días evaluados (2026-08-09 al 2026-11-06), `TOTAL_UNIDADES_FLOTA = 100` diario (min 100, max 100), `PCT_CON_VIAJE = 56.00 %`, `PCT_SIN_VIAJE = 40.00 %`, `PCT_INACTIVAS = 4.00 %`, `TOTAL_KMS_DIA = 1,820,487.49`, `TOTAL_KWH_DIA = 326,806.52`.
  - `MV_PRODUCTIVIDAD_ECO_MENSUAL`: 399 filas (100 unidades), `5,040` viajes, `5,029` cerrados, `1,820,487.49` kms, `$309,227,803.56` facturación, `$17,855,296.07` gastos, rendimiento promedio `5.68 km/kWh` (rango físico `3.49 .. 10.83 km/kWh`).
  - Todas las vistas base (`VW_FACT_*`, `VW_DIM_*`, vistas de rol de ubicación `VW_DIM_UBICACION_ORIGEN/DESTINO/PARADA`) consultadas con `BI_READER` con 0 errores `ORA-`.
- **Corrida incremental y prueba SCD2 (`ECO15@2026-11-07` + 5 viajes):**
  - Simulador ejecutado con `docker compose run --rm data-simulator python -m src.main --mode incremental --trips 5`: insertó 1 versión v2 de `ECO15`, 16 despachos (11 cierres del día 90 + 5 nuevos del día 91), 151 paradas, 5 CCPs, 13 mercancías, 111 estatus de flota, 14 CFDIs y 67 líneas de gastos.
  - `DIM_VEHICULO` en `DWH_MART`: `ECO15` cuenta ahora con **2 versiones** (v1 `98JM19` 2026-08-09 a 2026-11-06 inactiva; v2 `47LL35` 2026-11-07 a `NULL` activa). Total: 102 filas, 100 vehículos reales activos + 1 dummy `-1` activo.
  - `FACT_DESPACHO_VIAJE`: 5,045 viajes totales, exactamente 2 viajes abiertos restantes (los 11 anteriores cerraron y se actualizaron por `MERGE`).
  - `FACT_FACTURACION_FLETE`: 5,043 facturas conciliadas.
  - `FACT_SNAPSHOT_FLOTA_DIARIO`: 9,100 filas (91 días × 100 unidades).
  - `MV_METRICAS_FLOTA_DIARIA`: 91 días, 100 unidades/día, `1,827,114.49` kms y `327,999.20` kWh acumulados.
- **Retiro del volumen temporal de desarrollo:**
  - Se eliminó `./etl/dbt_tms:/app/dbt_tms:ro` de `docker-compose.yml`.
  - La imagen `analytics-tms-etl:local` fue reconstruida con el código dbt horneado en `/app/dbt_tms/`.
  - Verificada en contenedor autocontenido: `dbt debug` pasa 100 % y `dbt test` ejecuta **404/404 pruebas en verde (0 WARN, 0 ERROR, 0 SKIP)** en ~12.5 s.
- **Auditoría automatizada Actor-Crítico (`actor-critic-dw-review`):**
  - 3 subagentes de exploración evaluaron Seguridad/Licenciamiento, Conformidad Kimball y Cobertura Funcional de BI.
  - **0 hallazgos BLOCKER.** Informe consolidado en `docs/audits/audit-fase-3.md`.

---

## Orden y Dependencias

```
ST-0 (Spike dbt-oracle y decisiones)
  │
  ├──► ST-1 (Contenedores + esqueleto dbt) ──┐
  │                                           │
  │        ST-2 (Config + maestros + loader + CLI)
  │          │
  │          ▼
  │        ST-3 (TrackIt + Carta Porte + estatus diario)
  │          │
  │          ▼
  │        ST-4 (CFDI Ingreso + liquidaciones)
  │          │
  │          ▼
  │        ST-5 (pytest + backfill en vivo a STG_SRC)
  │          │
  └──────────┴──► ST-6 (dbt fuentes/macros/staging)
                    │
                    ▼
                  ST-7 (EDW_3FN) ──► ST-8 (Dimensiones) ──► ST-9 (Hechos)
                                                              │
                                                              ▼
                                                            ST-10 (DQ Screens)
                                                              │
                                                              ▼
                                                            ST-11 (Refresh + E2E + cierre)
```

---

## Matriz de Trazabilidad: Origen → Destino

| `STG_SRC` | `EDW_3FN` | `DWH_MART` (hecho/dim) | Degeneradas / notas |
|---|---|---|---|
| `STG_FLOTA_UNIDADES` | `CAT_VEHICULOS`, `CAT_POLIZAS_SEGURO` | `DIM_VEHICULO` (SCD2), `DIM_POLIZA` | `CODIGO_ECO` natural; SCD2 por A6 |
| `STG_TRACKIT_DESPACHO` | `OP_VIAJES_DESPACHO`, `CAT_REMOLQUES`, `CAT_OPERADORES`, `CAT_CLIENTES` | `FACT_DESPACHO_VIAJE`, `DIM_REMOLQUE`, `DIM_OPERADOR`, `DIM_CLIENTE`, `DIM_PERFIL_VIAJE` | `NUMERO_TALON` |
| `STG_TRACKIT_PARADAS` | `OP_VIAJES_PARADAS`, `CAT_UBICACIONES` | `FACT_EVENTOS_PARADA`, `DIM_UBICACION` | `NUMERO_TALON`, `NUMERO_SECUENCIA`, `UNIDAD_EMBARQUE_UE` |
| `STG_CARTA_PORTE_CABECERA` / `_MERCANCIAS` | `FISCAL_CFDI_CARTAPORTE`, `FISCAL_CARTAPORTE_MERCANCIAS`, `SAT_*` | `FACT_LINEAS_CARGA_CARTAPORTE`, `DIM_PRODUCTO_SAT` | `UUID_CCP`, `NUMERO_TALON`, `UNIDAD_EMBARQUE_UE` |
| `STG_FLOTA_ESTATUS_DIARIO` | `OP_FLOTA_ESTATUS_DIARIO` | `FACT_SNAPSHOT_FLOTA_DIARIO`, `DIM_FECHA` | 100 unidades × día |
| `STG_CFDI_INGRESO` | `FISCAL_CFDI_INGRESO` | `FACT_FACTURACION_FLETE` | `UUID_INGRESO`, `FACTURA_ID` |
| `STG_LIQUIDACIONES_GASTOS` | `OP_LIQUIDACIONES_GASTOS` | `FACT_GASTOS_LIQUIDACION` (agregado por folio+tipo) | `FOLIO_LIQ`, `NUMERO_TALON`, `TIPO_GASTO` |
| (generado por dbt) | — | `DIM_FECHA`, `DIM_HORA` | claves `YYYYMMDD` / `HHMM` |

---

## Riesgos y Mitigaciones

1. **`dbt-oracle` no puede operar sobre tablas de otros esquemas sin `CREATE ANY …`.**
   - *Mitigación:* ST-0 lo prueba primero; D1 (materialización personalizada de MERGE). Si fuera inviable, escalar la decisión al usuario antes de ampliar privilegios.
2. **Lookups silenciosos a `-1` por dimensiones de tiempo vacías.**
   - *Mitigación:* orden `DIM_FECHA`/`DIM_HORA` primero y screen específico (H3).
3. **Divergencia SCD2 por historial inexistente en `EDW_3FN`.**
   - *Mitigación:* detección contra la versión activa en cada corrida (H4/A5); la prueba SCD2 de ST-8 la valida.
4. **Fan-out al unir facturación/gastos con viajes.**
   - *Mitigación:* los hechos se construyen solo desde `EDW_3FN` y dimensiones; cualquier vista multi-hecho usa Drill-Across; test estático anti Fact↔Fact.
5. **No determinismo (fechas/UUID).**
   - *Mitigación:* D6 y prueba de determinismo en `pytest`.
6. **Privilegio `DELETE` de `SIM_WRITER` (H7).**
   - *Mitigación:* el simulador solo hace `INSERT`; decisión D5 sobre revocación.
7. **Cumplimiento de licencias/SE2.**
   - *Mitigación:* sin `PARTITION BY` de tabla, sin compresión, sin `QUERY REWRITE`; dedupe con funciones analíticas permitidas; imágenes base sin Redis; revisión Actor‑Crítico en ST-11.
8. **Restricciones de `fileRegex` por modo.**
   - *Mitigación:* ver tabla de modos; ST-1, seeds CSV e integración se ejecutan en `docker-platform-eng`/`agent`.
9. **Cambio de zona horaria/`SYSTIMESTAMP` en `INGESTED_AT`.**
   - *Mitigación:* `INGESTED_AT` lo asigna Oracle por `DEFAULT`; el orden de versiones depende de `INGESTED_AT` + `BATCH_ID`, no del reloj del cliente.

---

## Resultados del Spike (ST-0)
**Estado:** completado y verificado en vivo como `ETL_RUNNER` (dbt-core 1.12.7, dbt-oracle 1.12.0, python-oracledb 26.1.0 en Thin Mode, `python:3.11-slim`). Todos los artefactos del spike fueron eliminados; los catálogos y `DIM_CLIENTE` quedaron con 0 filas / solo `-1`; `ETL_RUNNER` sin objetos.

| # | Hallazgo | Evidencia | Impacto |
|---|----------|-----------|---------|
| R1 | Perfil Thin: `protocol: thin` **falla** (`DPY-4021: invalid protocol "thin"`). Funciona `protocol: tcp` + `host` + `port` + `service`; `dbt debug` → conexión OK. | Ejecución real | Corrige D9 y el paso 1 de la skill `dbt-oracle-etl-pipeline` (`thin` → `tcp`). Requiere aprobación para editar la skill. |
| R2 | **H1 corregida:** `ETL_RUNNER` no tiene privilegios `ANY`, pero las materializaciones nativas funcionan: crean una *global temporary table* `o$pt_*` en su propio esquema y hacen `MERGE` a otros esquemas con los grants de objeto existentes. | `incremental` probado | Ya no es un problema de privilegios. |
| R3 | **H2/D2 corregida:** `ETL_RUNNER` tiene `CREATE VIEW` (vía `RESOURCE`), `CREATE TABLE`, `CREATE MATERIALIZED VIEW` y `CREATE PROCEDURE`. | Consulta de privilegios | No se requiere script de grants para vistas. `staging` puede ser `view` en `ETL_RUNNER` (leyendo `STG_SRC`: verificado). |
| R4 | `dbt seed` crea la tabla en el esquema de `ETL_RUNNER` (`INSERT ALL` con binds); un modelo `merge_existing` sobre `ref(seed)` la lleva a `EDW_3FN.SAT_UNIDAD_MEDIDA`. `BATCH_ID` (NOT NULL) debe aportarlo el `MERGE`. | Ejecución real | Confirma P2. |
| R5 | `incremental` nativo falla con `ORA-00904 DBT_INTERNAL_SOURCE.UPDATED_AT` si el modelo omite columnas del destino y deja tablas `O$PT_*` huérfanas; solo funciona si el modelo emite **todas** las columnas, incluida la SK identity. | Ejecución real | **D1 se mantiene**: `merge_existing` por manejo de `IDENTITY`, no por privilegios. |
| R6 | `merge_existing` (lee `ALL_TAB_IDENTITY_COLS`, omite identity en `INSERT`, excluye columnas `ON` e identity del `UPDATE SET`) funcionó en `EDW_3FN.CAT_CLIENTES` (2 corridas; la 2.ª entra por `WHEN MATCHED`) y en `DWH_MART.DIM_CLIENTE` (SK autogenerada, fila `-1` intacta). | Ejecución real | Valida P2. |
| R7 | Prueba negativa: `UPDATE` de columna del `ON` → `ORA-38104` (confirmado). `UPDATE` de columna `IDENTITY BY DEFAULT` no falla; se excluye por diseño para mantener SKs estables. | Ejecución real | La macro debe excluir ambas. |
| R8 | Override `generate_schema_name` funciona: los modelos caen en `EDW_3FN` / `DWH_MART` sin prefijo. | Ejecución real | Confirma D3. |
| R9 | `target-path`/`log-path` en `dbt_project.yml` dan *deprecation warning* en dbt 1.12. | Ejecución real | Usar `DBT_TARGET_PATH` y `DBT_LOG_PATH` (env). |
| R10 | `dbt debug` retorna exit 1 solo porque falta `git` en la imagen. | Ejecución real | Instalar `git` en la imagen o no usar `dbt debug` como healthcheck. |
| R11 | Dos modelos no pueden compartir alias en el mismo esquema. | Ejecución real | Nombres únicos por capa. |

**Decisiones resultantes:** D1 se mantiene (por IDENTITY); D2 pasa a `view` en `ETL_RUNNER` para `staging` (ephemeral sigue siendo válido); D9 usa `protocol: tcp`; versiones fijadas `dbt-core==1.12.7`, `dbt-oracle==1.12.0`; `06_etl_grants.sql` se limita a revocar `DELETE` de `SIM_WRITER` sobre `STG_SRC` (D5).

## Cierre de Fase 3: Resultados de Validación (DoD)

### 1. Resumen de Ejecución y Suite de Pruebas
- **Pruebas del Simulador Python (`pytest`):** **75 / 75 PASS** (guardrails, determinismo, contratos DDL, finanzas, viajes).
- **Pruebas de Calidad dbt (`dbt test`):** **404 / 404 PASS (0 WARN, 0 ERROR, 0 SKIP)** ejecutados en ~12.5 s en contenedor autocontenido `etl-runner`.
- **Refresco de Capa Semántica:** Invocado automáticamente en `on-run-end` vía `BI_SEMANTIC.SP_REFRESH_MV_SEMANTIC`.

### 2. Conteos Consolidados por Capa

| Capa / Objeto | Filas (Post-Incremental) | Llaves Distintas | Grano / Notas |
|---|---|---|---|
| **STG_SRC** | **102,795** | N/A | 8 tablas de ingesta cruda (Backfill 90d + Incremental 1d) |
| **EDW_3FN** | | | Integridad referencial 3FN estricta |
| ├─ `CAT_VEHICULOS` | 100 | 100 | `CODIGO_ECO` único |
| ├─ `CAT_REMOLQUES` | 100 | 100 | `NUMERO_ECONOMICO_REMOLQUE` |
| ├─ `CAT_OPERADORES` | 15 | 15 | `CODIGO_OPERADOR` |
| ├─ `CAT_CLIENTES` | 6 | 6 | `RFC_CLIENTE` |
| ├─ `CAT_UBICACIONES` | 8 | 8 | `CODIGO_UBICACION` con geografía SAT |
| ├─ `CAT_POLIZAS_SEGURO` | 10 | 10 | `NUMERO_POLIZA` |
| ├─ `OP_VIAJES_DESPACHO` | 5,045 | 5,045 | 5,043 cerrados + 2 abiertos |
| ├─ `OP_VIAJES_PARADAS` | 40,495 | 40,495 | 4 a 12 paradas/viaje |
| ├─ `OP_FLOTA_ESTATUS_DIARIO` | 9,100 | 9,100 | 100 unidades × 91 días |
| ├─ `FISCAL_CFDI_CARTAPORTE` | 5,045 | 5,045 | 1 CCP por viaje |
| ├─ `FISCAL_CARTAPORTE_MERCANCIAS` | 15,249 | 15,249 | 1 a 5 partidas por viaje |
| ├─ `FISCAL_CFDI_INGRESO` | 5,043 | 5,043 | 1 CFDI por viaje cerrado |
| └─ `OP_LIQUIDACIONES_GASTOS` | 22,578 | 22,578 | Detalle atómico de gastos |
| **DWH_MART** | | | Constelación Kimball con FKs `NVL(-1)` y SKs enteras |
| ├─ `DIM_FECHA` | 366 | 365 + `-1` | Calendario 2026 |
| ├─ `DIM_HORA` | 1,441 | 1,440 + `-1` | Minutos del día |
| ├─ `DIM_VEHICULO` (SCD2) | 102 | 100 activas + 1 inactiva + `-1` | `ECO15` con v1 (inactiva) y v2 (activa) |
| ├─ `DIM_REMOLQUE` | 101 | 100 + `-1` | Remolques conformados |
| ├─ `DIM_OPERADOR` | 16 | 15 + `-1` | Operadores conformados |
| ├─ `DIM_CLIENTE` | 7 | 6 + `-1` | Clientes conformados |
| ├─ `DIM_UBICACION` | 9 | 8 + `-1` | Ubicaciones conformadas |
| ├─ `DIM_PRODUCTO_SAT` | 4 | 3 + `-1` | Catálogo SAT |
| ├─ `DIM_POLIZA` | 11 | 10 + `-1` | Pólizas de seguro |
| ├─ `DIM_PERFIL_VIAJE` | 3 | 2 + `-1` | Perfiles conformados |
| ├─ `FACT_DESPACHO_VIAJE` | 5,045 | 5,045 | 1 por viaje (5,043 cerrados + 2 abiertos) |
| ├─ `FACT_EVENTOS_PARADA` | 40,495 | 40,495 | 1 por parada con métricas de retraso/estadía |
| ├─ `FACT_LINEAS_CARGA_CARTAPORTE` | 15,249 | 15,249 | 1 por partida con 7 FKs conformadas |
| ├─ `FACT_FACTURACION_FLETE` | 5,043 | 5,043 | 1 por CFDI Ingreso 4.0 |
| ├─ `FACT_GASTOS_LIQUIDACION` | 10,402 | 10,402 | Agregado y pivotado por `(folio, tipo)` |
| └─ `FACT_SNAPSHOT_FLOTA_DIARIO` | 9,100 | 9,100 | 100 unidades × 91 días |
| **BI_SEMANTIC** | | | Consumo Superset ($0 SE2) |
| ├─ `MV_METRICAS_FLOTA_DIARIA` | 91 | 91 días | 100 uds/día (56 % con viaje, 40 % sin viaje, 4 % inactiva) |
| └─ `MV_PRODUCTIVIDAD_ECO_MENSUAL` | 399 | 100 unidades | Drill-Across mensual sin uniones Fact↔Fact directas |

### 3. Veredicto de Auditoría y Estado de Promoción
- **Auditoría Actor-Crítico:** **0 BLOCKERS** registrado en `docs/audits/audit-fase-3.md`.
- **Cero Secretos y Licenciamiento $0:** Conformes en `.env.example`, `docker-compose.yml` (Valkey 8) y Oracle SE2.
- **Fase 3 COMPLETADA con éxito al 100 %.**
