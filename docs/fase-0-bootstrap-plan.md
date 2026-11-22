# Plan de Ejecución — Fase 0: Bootstrap del Workspace Analytics TMS

## Visión general

**Objetivo:** dejar el workspace listo para que IBM Bob reconozca el gobierno del proyecto: estructura de carpetas, `AGENTS.md`, 3 reglas globales, 2 reglas por modo, 5 Custom Modes y 6 Skills. No se implementa Docker, DDL, ETL, simulador ni Superset; eso corresponde a las Fases 1 a 5.

**Fuentes (leídas completas):**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` (hoy `especificaci_n_sdlc_en_ibm_bob_plataforma_analytics_tms.md`). Es la fuente principal. Los §3, §4 y §5 traen el contenido de reglas, modos y skills casi listo para copiar.
- `docs/Arquitectura-dw-analytics-tms.docx`. Aporta los grains de 4 tablas de hechos (§6.1), las dimensiones y degeneradas de los procesos 5 y 6 (Matriz de Bus, §4) y el patrón Drill-Across. Se usa para las 2 reglas por modo y para las plantillas.
- `docs/Draft-dashboard-TMS.pdf` (hoy `Draft dashboard TMS.pdf`). Aporta los bloques visuales del reporte TRA099R1. Se usa para `draft_dashboard_kpis.md`.

**Alcance acordado (intermedio):**
- Incluye: carpetas, `AGENTS.md`, 3 reglas globales, 2 reglas por modo, `custom_modes.yaml` (5 modos), 6 `SKILL.md`, 4 plantillas/checklists de skills, `.env.example`, `.gitignore`, `.bobignore`.
- Excluye: `.bob/mcp.json` (requiere SQLcl y credenciales que aún no existen), `docs/gap-analysis-tracking.md` (la spec no define su contenido), `docker-compose.yml` y todo contenido de Fases 1 a 5.
- Los 2 archivos de `docs/` se renombran a los nombres canónicos de la spec.

**Enfoque:** cada sub-tarea es independiente y revisable. El contenido se toma de la spec (§3 a §5) y solo se corrige donde la spec es inconsistente (ver "Decisiones propuestas").

## Decisiones propuestas (hallazgos de la lectura cruzada)

Son inconsistencias entre los 3 documentos. Se proponen estas resoluciones y se aplican al implementar, salvo que indiques otra cosa.

| # | Hallazgo | Evidencia | Resolución propuesta |
|---|---|---|---|
| D1 | `sdlc-auditor-critic` no tiene grupo `execute`, pero la skill `actor-critic-dw-review` paso 1 usa `git status` / `git diff`. | Spec §4.2 vs §5.6 | Mantener el modo de solo lectura (sin `execute`). Reescribir el paso 1 de la skill: identificar archivos con `list_files`/`glob`/`grep`, o recibir la lista de cambios del humano. |
| D2 | `bi-superset-dev` solo puede editar `superset/assets/`, `superset_config.py` y `README.md`, pero la skill `superset-oracle-drillacross` paso 2 configura `superset/bootstrap.sh`. Ese archivo solo lo edita `docker-platform-eng`. | Spec §4.2 vs §5.5 | El paso 2 de la skill pasa a ser coordinación: pedir a `docker-platform-eng` el registro de la conexión `Analytics_TMS_Oracle`. No se amplía el `fileRegex` de `bi-superset-dev`. |
| D3 | La regla 01 prohíbe joins entre 5 facts, pero el DDL de §5.2 crea 6: añade `FACT_GASTOS_LIQUIDACION`. El docx documenta solo 4 facts y marca `FACT_FACTURACION_FLETE` como "fuente requerida". | Spec §3.2 vs §5.2; docx §6.1 | Incluir `FACT_GASTOS_LIQUIDACION` en la lista de la regla 01. Si no, el auditor no detectaría joins que la involucren. |
| D4 | El PDF muestra 9 unidades en la flota (5 con viaje = 56%, 4 sin viaje = 44%). La spec y el docx hablan de 100 unidades con 56% / 44%. | PDF "Indicadores diarios de flota" vs spec §1, §5.4; docx §6.1.D | Fase 0 no cambia nada. Dejar una nota en `draft_dashboard_kpis.md` y en `sim_rules_schema.yaml`: los porcentajes del Draft provienen de una muestra de 9 unidades y `fleet_size: 100` es decisión de la spec. |
| D5 | La spec numera y nombra los bloques del dashboard distinto del PDF. En la spec, "Indicadores Generales" contiene Despachos y Cierres. En el PDF, Despachos, Cierres, Liq. Casetas, Liq. Operador, CFDI de Traslado y Facturados están en "Indicadores de Operación", y Total Kms, Rendimiento, Pago Casetas, Pago Operadores y Facturado en "Indicadores Generales". | Spec §5.5 vs PDF | Los nombres de bloque en `draft_dashboard_kpis.md` y en la skill siguen el PDF. |
| D6 | `dw-architect-oracle` no puede editar `etl/dbt_tms/profiles.yml.template` (el regex exige extensiones `sql\|yml\|yaml\|md\|txt`). | Spec §4.2 | **Aprobado con ajuste:** se resuelve en Fase 0 estandarizando el nombre a `etl/dbt_tms/profiles.template.yml`. Conserva sintaxis YAML y cumple el `fileRegex` actual sin tocar `custom_modes.yaml`. Alternativa de respaldo, solo si el renombrado se descarta: añadir `template` a las extensiones del `fileRegex` en ST-5. El nuevo nombre se usa en el paso 1 de la skill `dbt-oracle-etl-pipeline` (ST-6) y en la comprobación del árbol (ST-8). |
| D7 | La regla 02 prohíbe Redis, pero `superset_config.py` usa el esquema `redis://` para hablar con Valkey. Es el protocolo, no la imagen. | Spec §3.3 vs §5.5 | Añadir una aclaración de una línea en la regla 02: el esquema `redis://` es válido; lo prohibido son imágenes `redis:*`. Así el auditor no genera falsos BLOCKER. |
| D8 | La spec define la raíz como `analytics-tms-platform/`. El workspace real es `c:\work\TMS Analytics`. | Spec §2 | La estructura se crea directamente en la raíz del workspace, sin carpeta anidada. |
| D9 | El `office_read` de este análisis generó `.bob/tmp/office-dumps/`. | Workspace | Borrarlo y añadir `.bob/tmp/` a `.gitignore` y `.bobignore`. |

## Sub-tareas

### ST-1 — Normalizar `docs/` y crear el árbol de carpetas
**Intent:** dejar el repositorio con las rutas exactas que las reglas, modos y skills referencian.
**Expected Outcomes:**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` y `docs/Draft-dashboard-TMS.pdf` existen. Los nombres originales ya no.
- Existe toda la jerarquía de carpetas de la spec §2.
- `.bob/tmp/` eliminado.

**Todo List:**
1. Renombrar `docs/especificaci_n_sdlc_en_ibm_bob_plataforma_analytics_tms.md` a `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md`.
2. Renombrar `docs/Draft dashboard TMS.pdf` a `docs/Draft-dashboard-TMS.pdf`.
3. Crear `docs/audits/`, `oracle/init/`, `etl/dbt_tms/models/{staging,edw_3fn,marts}/`, `etl/dbt_tms/tests/`, `simulator/src/generators/`, `superset/assets/`.
4. Crear `.bob/rules/`, `.bob/rules-dw-architect-oracle/`, `.bob/rules-bi-superset-dev/`, `.bob/skills/` y las 6 subcarpetas de skills (con `templates/` o `checklists/` donde aplique).
5. Añadir un `.gitkeep` en las carpetas vacías que deban versionarse.
6. Eliminar `.bob/tmp/`.

**Relevant Context:** spec §2 (árbol), §5.1 pasos 2 y 3 (lista de carpetas). Requiere Agent mode (renombrado y borrado vía comandos).
**Status:** `[x] done`

### ST-2 — Higiene del repositorio: `.gitignore`, `.bobignore`, `.env.example`
**Intent:** evitar fugas de secretos y ruido antes de generar cualquier otro archivo.
**Expected Outcomes:**
- `.gitignore` y `.bobignore` excluyen `.env`, `**/__pycache__/`, `target/`, `dbt_packages/`, `oracle_data/`, `postgres_data/`, logs y `.bob/tmp/`.
- `.env.example` documenta variables sin valores reales.

**Todo List:**
1. Crear `.gitignore` y `.bobignore` con la lista de la spec §5.1 paso 4, más `.bob/tmp/` (D9).
2. Crear `.env.example` con variables de Oracle (`ORACLE_PWD`, `ORACLE_DSN`), PostgreSQL, Valkey y Superset (`SUPERSET_SECRET_KEY`), todas con placeholders.
3. Añadir en `.env.example` las contraseñas de los usuarios `BI_READER`, `SIM_WRITER` y `ETL_RUNNER`. La spec los menciona (§3.4, §5.2, §5.5 con `${BI_READER_PWD}`) pero no fija los nombres de variable de los otros dos.
4. Verificar que no exista un `.env` real que se sobrescriba (spec §5.1 paso 1).

**Relevant Context:** spec §5.1; regla 03 punto 1.
**Status:** `[-] parcial` — `.env.example` creado. `.gitignore` y `.bobignore` fueron bloqueados por la herramienta (acceso denegado por patrón de ignore); el usuario los crea a mano.

### ST-3 — `AGENTS.md` y reglas globales `.bob/rules/`
**Intent:** fijar los estándares transversales que Bob carga en todos los modos.
**Expected Outcomes:**
- `AGENTS.md` en la raíz.
- `.bob/rules/01-kimball-architecture.md`, `02-licensing-oracle-guardrails.md` y `03-security-and-secrets.md`.

**Todo List:**
1. Crear `AGENTS.md` con el contenido de spec §3.1.
2. Crear la regla 01 desde §3.2, incorporando `FACT_GASTOS_LIQUIDACION` (D3).
3. Crear la regla 02 desde §3.3, con la aclaración sobre el esquema `redis://` (D7).
4. Crear la regla 03 desde §3.4 sin cambios.
5. Releer las 3 reglas contra los criterios de auditoría del modo `sdlc-auditor-critic` (4 verificaciones explícitas en §4.2) para que cada una sea comprobable.

**Relevant Context:** spec §3. Modificar `.bob/rules/` requiere aprobación humana según §6.3. Esta sub-tarea es la creación inicial y por eso se revisa explícitamente.
**Status:** `[x] done`

### ST-4 — Reglas específicas por modo
**Intent:** dar a los modos `dw-architect-oracle` y `bi-superset-dev` convenciones propias, sin duplicar las reglas globales.
**Expected Outcomes:**
- `.bob/rules-dw-architect-oracle/01-oracle-ddl-conventions.md`.
- `.bob/rules-bi-superset-dev/01-drillacross-jinja-standards.md`.

**Todo List:**
1. Redactar `01-oracle-ddl-conventions.md` con: los 4 esquemas y sus roles; los 3 usuarios y sus privilegios; el patrón de dimensiones (surrogate key `GENERATED BY DEFAULT AS IDENTITY` + fila `-1 / DESCONOCIDO`); prefijos `FACT_` / `DIM_` / `VW_`; columnas de auditoría `BATCH_ID`, `INGESTED_AT`, `SOURCE_SYSTEM` en `STG_SRC`; `COMMENT ON` obligatorio; idempotencia de scripts; índices B-Tree en FKs.
2. Incluir la tabla de grains de las 6 tablas de hechos (consistente con D3):
   - **Hechos 1 a 4, con grano definido en docx §6.1:** `FACT_DESPACHO_VIAJE` (un registro por viaje despachado), `FACT_EVENTOS_PARADA` (un registro por parada o hito), `FACT_LINEAS_CARGA_CARTAPORTE` (una fila por partida de mercancía en CFDI) y `FACT_SNAPSHOT_FLOTA_DIARIO` (un registro por vehículo y día calendario).
   - **Hechos 5 y 6, a partir de los procesos 5 y 6 de la Matriz de Bus (docx §4):**
     - `FACT_FACTURACION_FLETE`, proceso "Facturación Comercial Flete". Dimensiones: Fecha, Vehículo, Operador, Cliente, Ubicación (rol Destino). Degeneradas: `UUID_INGRESO`, `FACTURA_ID`.
     - `FACT_GASTOS_LIQUIDACION`, proceso "Gastos y Liquidación Viaje". Dimensiones: Fecha, Vehículo, Remolque, Operador. Degeneradas: `NUMERO_TALON`, `FOLIO_LIQ`.
   - El docx §4 lista dimensiones y degeneradas, pero **no declara el grano** de los procesos 5 y 6. El grano de esos dos hechos se redacta como **propuesta inferida** de sus degeneradas (por ejemplo, un registro por comprobante o factura de ingreso, y un registro por concepto liquidado de un viaje) y se marca en el archivo como "pendiente de validación del Data Architect". No se presenta como dato del docx.
3. Redactar `01-drillacross-jinja-standards.md` con: estructura CTE por hecho y `FULL OUTER JOIN` sobre dimensiones conformadas (docx §7); uso de `{% if from_dttm %}` y `{% if to_dttm %}` dentro de cada CTE; `NULLIF` en divisiones; consultas solo contra `BI_SEMANTIC` / `DWH_MART` con `BI_READER`.

**Relevant Context:** spec §2 (árbol), §3.2, §4.2, §5.2, §5.5; docx §4 (Matriz de Bus, procesos 5 y 6), §6 y §7. La spec nombra estos 2 archivos pero no define su contenido. Se deriva solo de lo ya establecido en esas secciones, sin reglas nuevas.
**Status:** `[x] done`

### ST-5 — `.bob/custom_modes.yaml` con los 5 Custom Modes
**Intent:** separar responsabilidades con `fileRegex` y aplicar el patrón Actor-Crítico.
**Expected Outcomes:**
- Un solo `custom_modes.yaml` con 5 modos: `dw-architect-oracle`, `docker-platform-eng`, `data-sim-eng`, `bi-superset-dev`, `sdlc-auditor-critic`.
- YAML válido, slugs únicos (solo letras, números y guiones), `fileRegex` compilables.

**Todo List:**
1. Transcribir spec §4.2 al archivo.
2. Revisar el escape de los `fileRegex` (la spec usa `\\.` dentro de comillas dobles). Las reglas de Bob indican que un `fileRegex` inválido impide cargar todo el archivo.
3. Aplicar D1: el modo auditor se mantiene sin `execute`.
4. Comprobar que cada modo referencia solo rutas que existen tras ST-1.
5. Validar sintaxis YAML y unicidad de slugs (spec §5.1 paso 6).
6. Probar cada `fileRegex` con 2 o 3 rutas de ejemplo por modo (una permitida, una denegada). Para `dw-architect-oracle`, incluir como ruta permitida `etl/dbt_tms/profiles.template.yml` (D6) y como denegada `etl/dbt_tms/profiles.yml.template`.

**Relevant Context:** spec §4.1 (modos nativos Plan / Agent / Ask), §4.2. Documentación Bob: `groups`, `fileRegex`, `allowedSubagents`, `rules-{slug}/`.
**Status:** `[x] done`

### ST-6 — Skills 1 a 3 y sus plantillas
**Intent:** crear las recetas de bootstrap, DDL y ETL.
**Expected Outcomes:**
- `.bob/skills/bootstrap-tms-workspace/SKILL.md`.
- `.bob/skills/oracle-kimball-ddl-generator/SKILL.md` y `templates/ddl_header_template.sql`.
- `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md` y `checklists/kimball_quality_screens.md`.

**Todo List:**
1. Crear los 3 `SKILL.md` desde spec §5.1 a §5.3. El `name` coincide con el nombre de carpeta (kebab-case, menos de 64 caracteres) y `description` está presente. En `dbt-oracle-etl-pipeline` paso 1, sustituir `profiles.yml.template` por `profiles.template.yml` (D6).
2. Corregir referencias a documentos para que coincidan con los nombres canónicos de `docs/`.
3. Crear `ddl_header_template.sql`: cabecera con propósito, esquema, autor/fecha, nota de compatibilidad SE2 (sin `PARTITION BY`, sin `COMPRESS FOR OLTP`, sin `ENABLE QUERY REWRITE`) y patrón idempotente.
4. Crear `kimball_quality_screens.md` con los 3 tipos de screen de §5.3 paso 6: columna, estructura y regla de negocio.

**Relevant Context:** spec §5.1 a §5.3; docx §6.
**Status:** `[x] done`

### ST-7 — Skills 4 a 6 y sus plantillas
**Intent:** crear las recetas de simulador, Superset y auditoría.
**Expected Outcomes:**
- `.bob/skills/tms-synthetic-data-sim/SKILL.md` y `templates/sim_rules_schema.yaml`.
- `.bob/skills/superset-oracle-drillacross/SKILL.md` y `checklists/draft_dashboard_kpis.md`.
- `.bob/skills/actor-critic-dw-review/SKILL.md`.

**Todo List:**
1. Crear los 3 `SKILL.md` desde spec §5.4 a §5.6, aplicando D1 (paso 1 de la skill 6), D2 (paso 2 de la skill 5) y D5 (nombres de bloque del PDF).
2. Crear `sim_rules_schema.yaml` con las claves de §5.4 paso 1: `seed`, `fleet_size`, `date_range_backfill`, `pricing_model`, `cost_model`. Anotar D4.
3. Crear `draft_dashboard_kpis.md`: checklist de los bloques del PDF con la fuente de hecho propuesta para cada KPI:
   - Indicadores diarios de flota: `FACT_SNAPSHOT_FLOTA_DIARIO`.
   - Indicadores de operación: `FACT_DESPACHO_VIAJE`, `FACT_LINEAS_CARGA_CARTAPORTE`, `FACT_FACTURACION_FLETE`, `FACT_GASTOS_LIQUIDACION`.
   - Indicadores generales: `FACT_DESPACHO_VIAJE`, `FACT_FACTURACION_FLETE`, `FACT_GASTOS_LIQUIDACION`.
   - Top 5 despachos por cliente, gráfica de flota, gráfica de facturación por unidad (Top 10), productividad de unidades y productividad de operadores.
4. Incluir en la checklist los valores del PDF como referencia de conciliación (por ejemplo, facturado mes $492,768.00 y total km mes 3,710).
5. En la skill 6, mantener los 3 subagentes `explore` en paralelo y el reporte `docs/audits/audit-fase-<N>.md` con severidades `BLOCKER / HIGH / MEDIUM / LOW`.

**Relevant Context:** spec §5.4 a §5.6; PDF completo; docx §6.1 y §7.
**Status:** `[x] done`

### ST-8 — Validación del Criterio de Aceptación (DoD de Fase 0)
**Intent:** comprobar que Bob reconoce el gobierno del proyecto y que no queda nada inconsistente.
**Expected Outcomes:**
- El selector de modos muestra los 5 Custom Modes.
- Se cargan las 3 reglas globales.
- *Bob Settings → Skills* lista las 6 skills.
- Resumen de archivos creados entregado.

**Todo List:**
1. Parsear `custom_modes.yaml` y comprobar 5 slugs únicos.
2. Verificar que cada `SKILL.md` tiene frontmatter `name` (igual a su carpeta) y `description`.
3. Listar el árbol final y compararlo con spec §2, descontando lo excluido (`mcp.json`, `gap-analysis-tracking.md`, `docker-compose.yml`). La única diferencia intencional adicional es `etl/dbt_tms/profiles.template.yml` en lugar de `profiles.yml.template` (D6). Hacer `grep` de `profiles.yml.template` en todo el repo, salvo la copia de la spec en `docs/`, y confirmar que no quedan referencias.
4. `grep` de referencias a archivos de `docs/` y comprobar que todas existen.
5. `grep` de `PARTITION BY`, `COMPRESS FOR OLTP`, `ENABLE QUERY REWRITE` e imágenes `redis:`. Las únicas coincidencias deben estar en texto de reglas que las prohíben.
6. Pedir al usuario que confirme en la UI de Bob que los 5 modos y las 6 skills aparecen (esto no se puede verificar desde el código).
7. Indicar el siguiente paso: Fase 1 con el modo `docker-platform-eng`, precedida de un plan en modo Plan.

**Relevant Context:** spec §7 Fase 0 (DoD) y §5.1 pasos 6 y 7.
**Status:** `[x] done`

## Orden y dependencias

ST-1 → ST-2 → ST-3 → ST-4 → ST-5 → ST-6 → ST-7 → ST-8. ST-5 depende de ST-1 (rutas). ST-6 y ST-7 dependen de ST-3 (las skills citan las reglas).

## Riesgos

- Un `fileRegex` mal escapado impide cargar `custom_modes.yaml` completo. Se mitiga con la prueba de ST-5.
- Las skills solo se pueden verificar en la UI de Bob. Se mitiga con el paso 6 de ST-8.
- La Fase 0 genera el contenido de las 2 reglas por modo y de las 4 plantillas a partir de la spec y el docx. Hay que revisar que no añadan reglas nuevas.

