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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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

**Status:** `[ ] pending`

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
_Pendiente. Se completará en ST-11 con: conteos por capa, resultado de `dbt build`/`dbt test` (aprobados/fallidos), porcentajes del snapshot, verificación con `BI_READER` y hallazgos de la auditoría Actor‑Crítico._
