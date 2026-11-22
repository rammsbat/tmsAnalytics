# Especificación Técnica de Implementación SDLC en IBM Bob
## Plataforma Analítica TMS (Oracle DW + Apache Superset + Docker + Simulador de Datos)

**Proyecto:** Analytics TMS — Sunshine Deliveries  
**Metodología de Datos:** Arquitectura Híbrida (EDW 3FN Inmon + Bus de Datos Dimensional Kimball)  
**Framework de Ingeniería:** IBM Bob Agentic SDLC (Modes, Rules, Skills, Subagents, MCP & Bob Shell)  
**Versión:** 1.0  
**Estado:** Listo para Bootstrap de Workspace  

---

## 1. Visión General y Alcance del Sistema

Este documento define el plano maestro para construir, automatizar, probar y desplegar la plataforma contenerizada de **Analytics TMS** utilizando **IBM Bob** como entorno de desarrollo agéntico (*Agentic SDLC*).

El objetivo es cerrar las brechas identificadas entre las fuentes actuales (TrackItWeb y CFDI de Traslado con Complemento Carta Porte) y los requerimientos visuales del **Draft Dashboard TMS (Reporte Diario de Operación)**, garantizando una arquitectura de **costo $0 en licenciamiento adicional** sobre la base de datos Oracle ya contemplada.

### 1.1 Componentes de la Plataforma Objetivo

| Capa | Servicio Docker | Tecnología | Licencia / Costo | Función Principal |
| :--- | :--- | :--- | :--- | :--- |
| **Almacenamiento DW** | `oracle-dw` (o instancia corporativa) | Oracle DB (23ai/26ai Free en dev; SE2/EE en prod) | Contemplada | Aloja `STG_SRC`, `EDW_3FN`, `DWH_MART` y `BI_SEMANTIC`. |
| **Analítica BI** | `superset-app`, `superset-worker`, `superset-beat`, `superset-init` | Apache Superset (imagen custom + `python-oracledb` Thin Mode) | Apache 2.0 ($0) | Dashboards, SQL Lab, Virtual Datasets Jinja (*Drill-Across*) y alertas. |
| **Metastore BI** | `superset-db` | PostgreSQL 16 Alpine | PostgreSQL ($0) | Metadatos internos de Superset (usuarios, roles, charts, dashboards). |
| **Caché & Broker** | `superset-valkey` | Valkey 8 Alpine *(reemplazo 100% compatible de Redis)* | BSD-3 ($0) | Caché de consultas BI y broker de tareas Celery sin restricciones SSPL/AGPL. |
| **ETL / ELT** | `etl-runner` | Python 3.11 + `dbt-core` + `dbt-oracle` | Apache 2.0 ($0) | Orquestación `STG_SRC` $\rightarrow$ `EDW_3FN` $\rightarrow$ `DWH_MART`, llaves subrogadas y *Data Quality Screens*. |
| **Simulación** | `data-simulator` | Python 3.11 (`Faker`, `oracledb`, `numpy`, `PyYAML`) | MIT / PSF ($0) | *Sandbox Source System* en modos `--backfill` e `--incremental` (cubre brechas de flota, CFDI Ingreso 4.0 y liquidaciones). |
| **Proxy (Opcional)** | `reverse-proxy` | Nginx Alpine / Traefik OSS | BSD-2 / MIT ($0) | Exposición HTTP/HTTPS unificada y terminación TLS. |

---

## 2. Arquitectura del Workspace en IBM Bob

IBM Bob descubre automáticamente el contexto, las reglas de cumplimiento, los modos personalizados y las habilidades reutilizables a partir de archivos versionados en el repositorio. Todo el equipo trabajará sobre la siguiente estructura de carpetas:

```text
analytics-tms-platform/
├── AGENTS.md                                    # Estándares transversales del equipo (auto-cargado por Bob)
├── docker-compose.yml                           # Orquestación local/servidor de contenedores
├── .env.example                                 # Plantilla de variables sin secretos reales
├── .bobignore                                   # Exclusión de volúmenes, logs, dumps y archivos .env
│
├── .bob/                                        # Configuración nativa de IBM Bob SDLC
│   ├── custom_modes.yaml                        # Definición de Custom Modes y restricciones fileRegex
│   ├── mcp.json                                 # Configuración de servidores MCP (Oracle, Docker, Git)
│   ├── rules/                                   # Reglas globales del workspace (aplican a TODOS los modos)
│   │   ├── 01-kimball-architecture.md
│   │   ├── 02-licensing-oracle-guardrails.md
│   │   └── 03-security-and-secrets.md
│   ├── rules-dw-architect-oracle/               # Reglas específicas para el modo DW Architect
│   │   └── 01-oracle-ddl-conventions.md
│   ├── rules-bi-superset-dev/                   # Reglas específicas para el modo Superset
│   │   └── 01-drillacross-jinja-standards.md
│   └── skills/                                  # Habilidades reutilizables (recetas SDLC)
│       ├── bootstrap-tms-workspace/
│       │   └── SKILL.md
│       ├── oracle-kimball-ddl-generator/
│       │   ├── SKILL.md
│       │   └── templates/ddl_header_template.sql
│       ├── dbt-oracle-etl-pipeline/
│       │   ├── SKILL.md
│       │   └── checklists/kimball_quality_screens.md
│       ├── tms-synthetic-data-sim/
│       │   ├── SKILL.md
│       │   └── templates/sim_rules_schema.yaml
│       ├── superset-oracle-drillacross/
│       │   ├── SKILL.md
│       │   └── checklists/draft_dashboard_kpis.md
│       └── actor-critic-dw-review/
│           └── SKILL.md
│
├── docs/                                        # Documentos fuente para Context Mentions (@docs/...)
│   ├── Arquitectura-dw-analytics-tms.docx
│   ├── Draft-dashboard-TMS.pdf
│   ├── IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md
│   └── gap-analysis-tracking.md
│
├── oracle/
│   └── init/
│       ├── 01_schemas_and_users.sql             # STG_SRC, EDW_3FN, DWH_MART, BI_SEMANTIC
│       ├── 02_ddl_stg_src.sql                   # Tablas espejo de fuentes + financieras simuladas
│       ├── 03_ddl_edw_3fn.sql                   # Capa atómica normalizada 3FN
│       ├── 04_ddl_dwh_mart.sql                  # Dimensiones conformadas y Tablas de Hechos
│       └── 05_views_bi_semantic.sql             # Vistas de Rol (Origen/Destino) y Vistas Materializadas
│
├── etl/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── dbt_tms/                                 # Proyecto dbt-oracle
│       ├── dbt_project.yml
│       ├── profiles.yml.template
│       ├── models/
│       │   ├── staging/
│       │   ├── edw_3fn/
│       │   └── marts/
│       └── tests/                               # Data Quality Screens (columna, estructura, negocio)
│
├── simulator/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── config_rules.yaml                        # Reglas estadísticas: 100 unidades, tarifas, retrasos
│   └── src/
│       ├── main.py                              # CLI: --mode backfill | incremental
│       ├── generators/
│       │   ├── fleet_master.py                  # Maestro de 100 unidades, operadores, clientes, ubicaciones
│       │   ├── trackit_ops.py                   # Viajes, 12 paradas, odómetros, kWh, FIN VIAJE
│       │   ├── carta_porte.py                   # Partidas CFDI Traslado (UUID_CCP, piezas, peso)
│       │   └── finance_erp.py                   # CFDI Ingreso 4.0, casetas IAVE, nómina operador
│       └── db_loader.py                         # Carga bulk con oracledb (executemany)
│
└── superset/
    ├── Dockerfile                               # apache/superset + pip install oracledb
    ├── superset_config.py                       # Valkey cache, Celery, ENABLE_TEMPLATE_PROCESSING=True
    ├── bootstrap.sh                             # db upgrade, admin user, conexión Oracle automatizada
    └── assets/                                  # Datasets Jinja y definiciones de Dashboard versionadas
```

---

## 3. Reglas de Gobernanza del Workspace (`AGENTS.md` y `.bob/rules/`)

Las reglas garantizan determinismo entre conversaciones y evitan la variabilidad de la IA. En IBM Bob, estas reglas se cargan automáticamente en **todos los modos** y no pueden ser anuladas por un Custom Mode.

### 3.1 Archivo Raíz: `AGENTS.md`

```markdown
# Estándares del Equipo — Analytics TMS

## Arquitectura y Stack Obligatorio
- Motor DW: Oracle Database (conexión obligatoria mediante `python-oracledb` en Thin Mode; NO usar `cx_Oracle` ni Instant Client).
- Capa BI: Apache Superset con PostgreSQL (metastore) y Valkey (caché/broker).
- Capa ETL: `dbt-core` + `dbt-oracle` (ejecutado en contenedor `etl-runner`).
- Entorno Contenedores: Docker Engine / Docker Compose v2 (sin dependencias de herramientas licenciadas).

## Principios de Ingeniería
- Todo código SQL debe ser compatible con Oracle 19c/23ai estándar.
- Nunca insertar datos simulados directamente en `DWH_MART`; el simulador SIEMPRE escribe en `STG_SRC` para validar el pipeline completo.
- Toda modificación de DDL o ETL requiere pruebas de integridad referencial y actualización de documentación en `docs/`.
- Utilizar commits atómicos (Conventional Commits: `feat:`, `fix:`, `chore:`, `docs:`).
```

### 3.2 Regla 1: `.bob/rules/01-kimball-architecture.md`

```markdown
# Reglas de Modelado Híbrido (3FN + Kimball)

1. **Separación Estricta de Capas:**
   - `STG_SRC`: Datos crudos de fuentes (TrackItWeb, Carta Porte, ERP Financiero) con marcas de tiempo de ingesta.
   - `EDW_3FN`: Datos atómicos en Tercera Forma Normal con integridad referencial estricta. Prohibido exponer a Superset.
   - `DWH_MART`: Esquema en Constelación de Hechos con Dimensiones Conformadas y llaves subrogadas enteras (`NUMBER GENERATED BY DEFAULT AS IDENTITY`).
   - `BI_SEMANTIC`: Vistas de rol (`VW_DIM_ORIGEN`, `VW_DIM_DESTINO`) y vistas agregadas/materializadas para consumo directo de Superset.

2. **Prohibición de Uniones Directas entre Fact Tables:**
   - JAMÁS unir `FACT_DESPACHO_VIAJE`, `FACT_EVENTOS_PARADA`, `FACT_LINEAS_CARGA_CARTAPORTE`, `FACT_FACTURACION_FLETE` o `FACT_SNAPSHOT_FLOTA_DIARIO` directamente en una misma cláusula `FROM/JOIN`.
   - Toda consulta multi-hecho DEBE implementarse mediante el patrón **Drill-Across** (CTEs agregadas por dimensión conformada + `FULL OUTER JOIN`).

3. **Integridad Dimensional:**
   - Ninguna columna FK en una Fact Table puede ser `NULL` (utilizar registro dummy `-1` / `DESCONOCIDO` en dimensiones).
   - Las Dimensiones Degeneradas (`NUMERO_TALON`, `UUID_CCP`, `UNIDAD_EMBARQUE_UE`, `UUID_INGRESO`) permanecen en la tabla de hechos sin tabla dimensional redundante salvo cuando actúan como ancla conformada.
```

### 3.3 Regla 2: `.bob/rules/02-licensing-oracle-guardrails.md`

```markdown
# Guardrails de Licenciamiento $0 Adicional

1. **Sin Redis propietario:** Utilizar exclusivamente `valkey/valkey:8-alpine` (licencia BSD-3). Rechazar imágenes `redis:*` en `docker-compose.yml`.
2. **Compatibilidad Oracle Standard Edition 2 (SE2):**
   - NO generar cláusulas `PARTITION BY` (Oracle Partitioning es opción de pago).
   - NO usar `COMPRESS FOR OLTP` / `ADVANCED` (Advanced Compression es opción de pago).
   - NO activar `ENABLE QUERY REWRITE` en `CREATE MATERIALIZED VIEW` (requiere Enterprise Edition).
   - Optimizar consultas únicamente con índices B-Tree estándar, estadísticas actualizadas (`DBMS_STATS`) y Vistas Materializadas consultadas explícitamente desde `BI_SEMANTIC`.
3. **Sin dependencias SaaS/Comerciales:** No incluir configuraciones de dbt Cloud, Preset, NGINX Plus ni Docker Desktop exclusivo.
```

### 3.4 Regla 3: `.bob/rules/03-security-and-secrets.md`

```markdown
# Políticas de Seguridad y Secretos (DevSecOps)

1. **Cero Secretos en Código:** Prohibido escribir contraseñas, `SECRET_KEY` de Superset o cadenas de conexión con credenciales en archivos versionados. Usar exclusivamente variables de entorno referenciadas desde `.env` (ignorado en `.gitignore` y `.bobignore`).
2. **Prevención de SQL Injection:** En el simulador Python y scripts de soporte, toda consulta con parámetros debe usar *bind variables* de Oracle (`:param_name`). Prohibida la interpolación de strings (`f"SELECT ... {var}"`).
3. **Principio de Mínimo Privilegio en Oracle:**
   - El usuario de conexión de Superset (`BI_READER`) solo tiene permisos `SELECT` sobre el esquema `BI_SEMANTIC` y `DWH_MART`. Prohibido `INSERT/UPDATE/DELETE/DDL`.
   - El usuario `SIM_WRITER` solo tiene permisos `INSERT/UPDATE` sobre `STG_SRC`.
4. **Hardening de Contenedores:** No ejecutar procesos de aplicación como `root` dentro de contenedores custom (`USER superset`, `USER appuser`), declarar `healthcheck` en todos los servicios y aislar la red de base de datos en una red Docker interna (`tms-internal-net`).
```

---

## 4. Diseño de Modos en IBM Bob (Built-in y Custom Modes)

### 4.1 Uso de los Modos Nativos de IBM Bob

| Modo Nativo | Rol en el Proyecto | Cuándo Usarlo |
| :--- | :--- | :--- |
| **`Plan`** | Arquitecto / Tech Lead (usa skill `create-plan`, edita solo `.md/.txt`) | Al inicio de cada fase o épica para desglosar tareas, validar contra `@docs/Arquitectura-dw-analytics-tms.docx` y aprobar el plan antes de escribir código. |
| **`Agent`** | Ingeniero Full-Stack (acceso total a herramientas y subagentes) | Para tareas transversales de integración (ej. conectar el flujo completo `simulator` $\rightarrow$ `etl` $\rightarrow$ `superset` y ejecutar pruebas E2E). |
| **`Ask`** | Consultor Técnico (solo lectura, genera diagramas Mermaid) | Para explicar métricas del *Draft Dashboard TMS*, revisar dudas sobre SQL de Oracle o incorporar nuevos desarrolladores al repositorio sin riesgo de modificar archivos. |

### 4.2 Definición de Custom Modes (`.bob/custom_modes.yaml`)

Los **Custom Modes** restringen el alcance de edición mediante `fileRegex` y separan responsabilidades, aplicando el patrón **Actor-Crítico** para garantizar calidad y seguridad antes de cada commit.

```yaml
customModes:
  - slug: dw-architect-oracle
    name: "🏛️ Oracle DW Architect"
    description: "Diseña e implementa DDL Oracle (3FN, Kimball, Vistas Semánticas) y modelos dbt-oracle."
    roleDefinition: >-
      Eres un Arquitecto Senior de Data Warehouse especializado en Oracle Database,
      metodología Kimball/Inmon y dbt-oracle. Traduces requerimientos logísticos TMS
      en esquemas 3FN, estrellas conformadas y vistas semánticas optimizadas sin usar
      opciones licenciadas fuera de Oracle SE2.
    whenToUse: >-
      Usar para crear o modificar scripts SQL en oracle/, modelos SQL/YAML en etl/dbt_tms/
      y pruebas de calidad de datos (Data Quality Screens).
    customInstructions: |-
      - Valida siempre la granularidad de cada tabla de hechos contra docs/Arquitectura-dw-analytics-tms.docx.
      - Incluye comentarios de tabla y columna (`COMMENT ON TABLE/COLUMN`) para documentar el catálogo.
      - Asegura que todas las dimensiones tengan registro dummy (-1) para integridad referencial.
      - Antes de entregar DDL, verifica que no haya PARTITION BY ni ENABLE QUERY REWRITE.
    groups:
      - read
      - - edit
        - fileRegex: "^(oracle/|etl/|docs/).*\\.(sql|yml|yaml|md|txt)$"
          description: "Solo scripts SQL, configuraciones dbt y documentación."
      - execute
      - mcp
      - skill
    allowedSubagents:
      - explore

  - slug: docker-platform-eng
    name: "🐳 Docker Platform Engineer"
    description: "Construye y endurece la infraestructura Docker Compose, Dockerfiles y scripts de bootstrap."
    roleDefinition: >-
      Eres un Ingeniero DevOps / Platform especializado en Docker Engine, Docker Compose v2,
      Apache Superset self-hosted, Valkey y Oracle Free/Enterprise en contenedores Linux.
      Priorizas reproducibilidad, seguridad, healthchecks y cumplimiento de licencias $0.
    whenToUse: >-
      Usar para crear o mantener docker-compose.yml, Dockerfiles, scripts .sh de inicialización,
      .env.example y configuraciones de red/volúmenes.
    customInstructions: |-
      - Usa siempre `valkey/valkey:8-alpine` en lugar de Redis.
      - Instala `oracledb` (Thin Mode) en el Dockerfile de Superset sin Oracle Instant Client.
      - Configura `depends_on` con `condition: service_healthy` para orquestar el arranque ordenado.
      - Nunca expongas contraseñas ni puertos innecesarios en interfaces públicas.
    groups:
      - read
      - - edit
        - fileRegex: "(docker-compose.*\\.ya?ml|Dockerfile.*|\\.env\\.example|\\.dockerignore|\\.bobignore|superset/bootstrap\\.sh|superset/superset_config\\.py|.*\\.sh)$"
          description: "Solo archivos de infraestructura Docker, configuración base y bootstrap."
      - execute
      - skill
    allowedSubagents:
      - explore

  - slug: data-sim-eng
    name: "🎲 TMS Data Simulator Engineer"
    description: "Desarrolla el generador sintético en Python para poblar STG_SRC con datos realistas."
    roleDefinition: >-
      Eres un Ingeniero de Datos en Python especializado en generación de datos sintéticos
      estadísticamente coherentes para logística y transporte (TMS, Carta Porte SAT, CFDI 4.0).
      Escribes código modular, tipado, eficiente con inserción masiva (`executemany`) en Oracle.
    whenToUse: >-
      Usar para diseñar, implementar y calibrar el contenedor simulator/ (modos backfill e incremental)
      y las reglas de generación en config_rules.yaml.
    customInstructions: |-
      - Escribe SIEMPRE en el esquema STG_SRC; nunca directamente en DWH_MART.
      - Garantiza coherencia física y matemática: Kms_Total = Kms_Cargado + Kms_Vacio;
        Peso <= 29,685 kg por unidad C3R2; 100 unidades totales en flota.
      - Genera datos sintéticos explícitos para cerrar las brechas del Draft Dashboard:
        flota completa, evento FIN VIAJE, CFDI Ingreso 4.0 y liquidación de casetas/operadores.
      - Usa bind variables en todas las sentencias SQL y semilla aleatoria configurable (`seed`)
        para pruebas reproducibles.
    groups:
      - read
      - - edit
        - fileRegex: "^simulator/.*\\.(py|ya?ml|txt|md|json)$"
          description: "Solo código Python y configuraciones dentro de simulator/."
      - execute
      - skill
    allowedSubagents:
      - explore

  - slug: bi-superset-dev
    name: "📊 Superset BI Developer"
    description: "Implementa Virtual Datasets Drill-Across con Jinja, métricas y assets de Apache Superset."
    roleDefinition: >-
      Eres un Especialista Senior en Apache Superset y Modelado Semántico BI. Dominas
      Virtual Datasets con Jinja Templating, SQL de Oracle, consultas Drill-Across sin fan traps
      y exportación/importación versionada de dashboards (Superset CLI).
    whenToUse: >-
      Usar para construir las consultas de los KPIs del Draft Dashboard TMS, configurar
      datasets virtuales, alertas/reportes programados y empaquetar assets de Superset.
    customInstructions: |-
      - Habilita y usa macros Jinja (`from_dttm`, `to_dttm`, `filter_values`) para empujar filtros
        de fecha y cliente dentro de cada CTE antes del FULL OUTER JOIN.
      - Mapea cada componente visual al documento docs/Draft-dashboard-TMS.pdf.
      - Verifica que todas las consultas apunten exclusivamente a BI_SEMANTIC o DWH_MART usando
        el usuario de solo lectura BI_READER.
    groups:
      - read
      - - edit
        - fileRegex: "^superset/(assets/|superset_config\\.py|README\\.md).*$"
          description: "Solo assets, datasets SQL/YAML y configuración analítica de Superset."
      - execute
      - mcp
      - skill
    allowedSubagents:
      - explore

  - slug: sdlc-auditor-critic
    name: "🛡️ SDLC Auditor & Critic"
    description: "Modo solo lectura para auditar seguridad, licencias, arquitectura Kimball y cobertura de KPIs."
    roleDefinition: >-
      Eres un Auditor Técnico Principal (Critic Agent) de Seguridad, Licenciamiento y Arquitectura
      de Datos. Evalúas críticamente los artefactos generados por otros modos sin modificar código
      fuente, emitiendo reportes estructurados con severidad (BLOCKER, HIGH, MEDIUM, LOW) y
      acciones de remediación exactas.
    whenToUse: >-
      Usar al finalizar cada fase del SDLC o antes de un Pull Request para ejecutar revisiones
      de seguridad, cumplimiento de licencias $0, reglas Kimball y matriz de brechas.
    customInstructions: |-
      - Nunca modifiques código fuente de aplicación. Solo lee archivos y genera reportes de auditoría.
      - Clasifica todo hallazgo que viole .bob/rules/ como BLOCKER.
      - Verifica explícitamente: (1) ausencia de Redis propietario, (2) ausencia de funciones
        Oracle EE no licenciadas, (3) cero joins directos Fact-to-Fact, (4) cero secretos expuestos.
    groups:
      - read
      - - edit
        - fileRegex: "^docs/audits/.*\\.md$"
          description: "Solo escritura de reportes de auditoría en docs/audits/."
      - mcp
      - skill
    allowedSubagents:
      - explore
```

---

## 5. Catálogo de Skills Reutilizables (`.bob/skills/`)

Las **Skills** encapsulan flujos repetibles y especializados para que IBM Bob ejecute tareas complejas de forma consistente. Cada skill reside en `.bob/skills/<nombre>/SKILL.md` con su encabezado YAML obligatorio (`name` y `description`).

### 5.1 Skill 1: `bootstrap-tms-workspace`
* **Ruta:** `.bob/skills/bootstrap-tms-workspace/SKILL.md`
* **Propósito:** Crear desde cero la estructura de directorios, archivos `.bob/`, `.bobignore`, `.gitignore` y `.env.example`.

```markdown
---
name: bootstrap-tms-workspace
description: Inicializa la estructura completa del repositorio Analytics TMS y la configuración de IBM Bob (.bob/rules, .bob/custom_modes.yaml, .bob/skills y AGENTS.md) lista para desarrollo.
---

# Workflow: Bootstrap del Workspace Analytics TMS

## Pasos de Ejecución
1. Verificar el directorio raíz actual y confirmar que no se sobrescriban archivos `.env` existentes.
2. Crear la jerarquía de carpetas: `docs/audits`, `oracle/init`, `etl/dbt_tms/models/{staging,edw_3fn,marts}`, `etl/dbt_tms/tests`, `simulator/src/generators`, `superset/assets`.
3. Crear la estructura de gobierno de Bob: `.bob/rules/`, `.bob/rules-dw-architect-oracle/`, `.bob/rules-bi-superset-dev/`, `.bob/skills/`.
4. Generar `.gitignore` y `.bobignore` excluyendo `.env`, `**/__pycache__/`, `target/`, `dbt_packages/`, `oracle_data/`, `postgres_data/` y logs.
5. Generar `.env.example` con variables documentadas para Oracle (`ORACLE_PWD`, `ORACLE_DSN`), PostgreSQL, Valkey y Superset (`SUPERSET_SECRET_KEY`).
6. Validar que `.bob/custom_modes.yaml` tenga sintaxis YAML válida y slugs únicos.
7. Entregar un resumen de archivos creados y listar el siguiente paso en Modo `Plan`.
```

### 5.2 Skill 2: `oracle-kimball-ddl-generator`
* **Ruta:** `.bob/skills/oracle-kimball-ddl-generator/SKILL.md`
* **Propósito:** Generar los scripts SQL idempotentes de Oracle para los 4 esquemas (`STG_SRC`, `EDW_3FN`, `DWH_MART`, `BI_SEMANTIC`).

```markdown
---
name: oracle-kimball-ddl-generator
description: Genera scripts DDL de Oracle Database para la arquitectura híbrida Analytics TMS (Staging, EDW 3FN, Data Mart Kimball y Vistas Semánticas) cumpliendo compatibilidad SE2 y reglas de seguridad.
---

# Workflow: Generación de DDL Oracle Híbrido (3FN + Kimball)

## Entradas Requeridas
- Leer `@docs/Arquitectura-dw-analytics-tms.docx` y `.bob/rules/01-kimball-architecture.md`.

## Pasos de Ejecución
1. **Esquemas y Usuarios (`01_schemas_and_users.sql`):**
   - Crear usuarios/esquemas `STG_SRC`, `EDW_3FN`, `DWH_MART`, `BI_SEMANTIC`, `SIM_WRITER`, `ETL_RUNNER`, `BI_READER`.
   - Aplicar privilegios mínimos por rol.
2. **Capa Staging (`02_ddl_stg_src.sql`):**
   - Crear tablas espejo de TrackItWeb (cabecera y paradas), Carta Porte (cabecera y mercancías), Maestro de Flota (100 unidades), CFDI Ingreso 4.0 y Liquidaciones (casetas/operador/mantenimiento).
   - Incluir columnas de auditoría: `BATCH_ID`, `INGESTED_AT`, `SOURCE_SYSTEM`.
3. **Capa Atómica (`03_ddl_edw_3fn.sql`):**
   - Crear entidades normalizadas con PKs, FKs y restricciones `CHECK`/`UNIQUE`.
4. **Capa Dimensional (`04_ddl_dwh_mart.sql`):**
   - Crear las 10 Dimensiones Conformadas (`DIM_FECHA`, `DIM_HORA`, `DIM_VEHICULO`, `DIM_REMOLQUE`, `DIM_OPERADOR`, `DIM_CLIENTE`, `DIM_UBICACION`, `DIM_PRODUCTO_SAT`, `DIM_POLIZA`, `DIM_PERFIL_VIAJE`) con llaves subrogadas `GENERATED BY DEFAULT AS IDENTITY` y fila `-1` (`DESCONOCIDO`).
   - Crear las 5 Tablas de Hechos (`FACT_DESPACHO_VIAJE`, `FACT_EVENTOS_PARADA`, `FACT_LINEAS_CARGA_CARTAPORTE`, `FACT_FACTURACION_FLETE`, `FACT_SNAPSHOT_FLOTA_DIARIO`) + `FACT_GASTOS_LIQUIDACION`.
   - Crear índices B-Tree en todas las llaves foráneas (comenzando por `FK_FECHA_*`).
5. **Capa Semántica (`05_views_bi_semantic.sql`):**
   - Crear vistas de rol (`VW_DIM_UBICACION_ORIGEN`, `VW_DIM_UBICACION_DESTINO`, `VW_DIM_UBICACION_PARADA`).
   - Crear vistas de negocio base para los KPIs diarios/mensuales y vistas materializadas sin `ENABLE QUERY REWRITE`.
6. **Auto-validación:** Confirmar ausencia de `PARTITION BY`, `COMPRESS FOR OLTP` y errores de sintaxis Oracle.
```

### 5.3 Skill 3: `dbt-oracle-etl-pipeline`
* **Ruta:** `.bob/skills/dbt-oracle-etl-pipeline/SKILL.md`
* **Propósito:** Implementar la transformación `STG_SRC` $\rightarrow$ `EDW_3FN` $\rightarrow$ `DWH_MART` con pruebas de calidad de datos (Kimball *Quality Screens*).

```markdown
---
name: dbt-oracle-etl-pipeline
description: Construye y prueba modelos dbt-oracle para transformar datos desde STG_SRC hacia EDW_3FN y DWH_MART, incluyendo llaves subrogadas, SCD Tipo 1/2, snapshot diario de flota y Data Quality Screens.
---

# Workflow: Pipeline ELT en dbt-oracle

## Pasos de Ejecución
1. Configurar `etl/dbt_tms/dbt_project.yml` y `profiles.yml.template` usando `type: oracle`, `protocol: thin` y variables de entorno (`env_var`).
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
```

### 5.4 Skill 4: `tms-synthetic-data-sim`
* **Ruta:** `.bob/skills/tms-synthetic-data-sim/SKILL.md`
* **Propósito:** Crear el simulador de datos sintéticos que desbloquea todos los KPIs del *Draft Dashboard TMS*.

```markdown
---
name: tms-synthetic-data-sim
description: Implementa el simulador de datos sintéticos en Python para el sistema TMS (TrackItWeb, Carta Porte, Flota de 100 unidades, CFDI Ingreso 4.0 y Liquidaciones) con modos backfill e incremental.
---

# Workflow: Simulador de Datos Sintéticos TMS

## Reglas de Realismo Obligatorias
- Referenciar los ejemplos reales de `@docs/Draft-dashboard-TMS.pdf` y `@docs/Arquitectura-dw-analytics-tms.docx` (ej. Procter & Gamble, `ECO01`..`ECO100`, `CAJA05`, ubicaciones `IMESA`, `SMO`, `MERCURIO`, productos SAT `12161902` / `24112701`).

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
```

### 5.5 Skill 5: `superset-oracle-drillacross`
* **Ruta:** `.bob/skills/superset-oracle-drillacross/SKILL.md`
* **Propósito:** Construir los Virtual Datasets con Jinja *Drill-Across* y mapear cada tarjeta/gráfica del *Draft Dashboard TMS*.

```markdown
---
name: superset-oracle-drillacross
description: Crea Virtual Datasets con Jinja Templating para consultas Drill-Across en Oracle, configura el bootstrap de Apache Superset y mapea todos los componentes del Draft Dashboard TMS.
---

# Workflow: Implementación Analítica en Apache Superset

## Inventario de Componentes a Cubrir (Draft Dashboard TMS)
1. **Indicadores Diarios de Flota (KPIs + Dona):** Unidades C/Viaje, S/Viaje, Inactivas, Total (fuente: `FACT_SNAPSHOT_FLOTA_DIARIO`).
2. **Indicadores Generales (Día vs. Mes):** Despachos, Cierres, Liq. Casetas, Liq. Operador, CFDI Traslado, Facturados.
3. **Indicadores de Operación (Día vs. Mes):** Total Kms, Rendimiento Kms/kWh, Pago Casetas, Pago Operadores, Facturado ($).
4. **Top 5 Despachos / Cliente (Día vs. Mes).**
5. **Gráfica Facturación por Unidad (Top 10).**
6. **Tabla Productividad de las Unidades (Mes):** Consulta *Drill-Across* (Despacho + Carga + Facturación + Gastos).
7. **Tabla Productividad de los Operadores (Mes):** Consulta *Drill-Across* por Operador.

## Pasos de Ejecución
1. Configurar `superset/superset_config.py`:
   - `FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": True, "ALERT_REPORTS": True}`
   - `SQLALCHEMY_DATABASE_URI` apuntando a `superset-db` (PostgreSQL).
   - `CACHE_CONFIG` y `CELERY_BROKER_URL` apuntando a `redis://superset-valkey:6379/...`.
2. Configurar `superset/bootstrap.sh` para registrar automáticamente la conexión `Analytics_TMS_Oracle` usando `oracle+oracledb://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1`.
3. Generar en `superset/assets/datasets/` los SQL de los Virtual Datasets usando macros Jinja:
   - Usar `{% if from_dttm %}` y `{% if to_dttm %}` dentro de cada CTE para hacer *filter pushdown* en Oracle antes del `FULL OUTER JOIN`.
   - Proteger divisiones por cero (`NULLIF(SUM(kms_total), 0)`).
4. Documentar en `superset/assets/dashboard_mapping.md` la relación exacta entre cada Chart, su Dataset, sus filtros nativos y su métrica equivalente en `@docs/Draft-dashboard-TMS.pdf`.
```

### 5.6 Skill 6: `actor-critic-dw-review`
* **Ruta:** `.bob/skills/actor-critic-dw-review/SKILL.md`
* **Propósito:** Ejecutar validación automatizada mediante el patrón **Actor-Crítico** usando subagentes independientes antes de promover cambios.

```markdown
---
name: actor-critic-dw-review
description: Orquesta una auditoría automatizada Actor-Crítico usando subagentes aislados para validar seguridad, licenciamiento $0, conformidad Kimball y cobertura del Draft Dashboard antes de commit o despliegue.
---

# Workflow: Auditoría Actor-Crítico de la Plataforma

## Pasos de Ejecución
1. Identificar todos los archivos creados o modificados en la fase actual (`git status` / `git diff`).
2. Lanzar en paralelo hasta 3 subagentes de tipo `explore` con contexto limpio:
   - **Subagente A (Seguridad & Licencias):** Audita `.env`, `docker-compose.yml`, `Dockerfiles` y scripts Python/SQL contra `.bob/rules/02-licensing-oracle-guardrails.md` y `.bob/rules/03-security-and-secrets.md`.
   - **Subagente B (Integridad Kimball & Oracle):** Audita `oracle/` y `etl/` contra `.bob/rules/01-kimball-architecture.md` verificando ausencia de joins Fact-to-Fact y presencia de *Quality Screens*.
   - **Subagente C (Cobertura Funcional BI):** Compara los Virtual Datasets de `superset/assets/` y el simulador contra los 7 bloques visuales de `@docs/Draft-dashboard-TMS.pdf`.
3. Consolidar los hallazgos en `docs/audits/audit-fase-<N>.md` clasificando por severidad (`BLOCKER`, `HIGH`, `MEDIUM`, `LOW`).
4. Si existe cualquier `BLOCKER`, detener la promoción y generar la lista de tareas (`Todo`) para remediación inmediata por el modo Actor correspondiente.
```

---

## 6. Habilidades Humanas, Integraciones MCP y Política de Control

El desarrollo agéntico en IBM Bob requiere puntos de control humanos (*Human-in-the-Loop*) y herramientas conectadas con privilegios controlados.

### 6.1 Matriz de Habilidades del Equipo (Roles Humanos)

| Rol Humano | Habilidades Clave Requeridas | Interacción Principal con IBM Bob |
| :--- | :--- | :--- |
| **Data Architect / BI Lead** | Modelado Kimball, SQL Oracle, validación de negocio TMS y Carta Porte SAT. | Aprueba planes en Modo `Plan`, revisa DDL en `dw-architect-oracle`, valida KPIs del *Draft Dashboard*. |
| **Data / Python Engineer** | Python, `dbt-core`, `oracledb`, diseño estadístico de simulaciones y pruebas de calidad. | Dirige `data-sim-eng` y `dw-architect-oracle` (dbt), ejecuta pruebas `dbt test` y calibra reglas de simulación. |
| **DevOps / Platform Engineer** | Docker Engine Linux, redes/volúmenes, seguridad de contenedores y administración básica Oracle. | Opera `docker-platform-eng`, configura `Bob Shell` en CI/CD y gestiona secretos de producción. |
| **BI Analyst / Product Owner** | Apache Superset, UX analítica, conciliación financiera/operativa con Sunshine Deliveries. | Trabaja con `bi-superset-dev` y `Ask`, valida visualmente los dashboards generados contra el reporte real. |

### 6.2 Servidores MCP Recomendados (`.bob/mcp.json`)

Configurar servidores **Model Context Protocol (MCP)** permite a Bob consultar metadatos reales sin copiar/pegar salidas de consola manualmente:

1. **Oracle SQLcl MCP (`oracle-readonly`):** Conectado únicamente con el usuario `BI_READER` para que los modos `dw-architect-oracle`, `bi-superset-dev` y `sdlc-auditor-critic` puedan inspeccionar catálogos (`ALL_TAB_COLUMNS`), planes de ejecución (`EXPLAIN PLAN`) y validar conteos de filas en vivo.
2. **Docker MCP (solo entorno local/dev):** Permite inspeccionar logs de contenedores (`superset-app`, `etl-runner`, `oracle-dw`), estados `healthy` y uso de memoria.
3. **Git / Repository MCP:** Facilita la generación de diffs limpios, trazabilidad de cambios y preparación de Pull Requests.

### 6.3 Política de Aprobación (*Auto-Approve*) y Rollback

* **Auto-Approve Permitido:** Lectura de archivos (`Read`), activación de **Skills** del proyecto (`.bob/skills/`), comandos de solo lectura (`docker compose ps`, `dbt test`, `pytest`).
* **Aprobación Humana Obligatoria:** Ejecución de comandos destructivos (`docker compose down -v`, `DROP TABLE`, `TRUNCATE`), lanzamiento de subagentes con escritura (`general`), y cambios en `docker-compose.yml` o `.bob/rules/`.
* **Uso de Rollback:** Si una iteración de generación de código se desvía del diseño, usar la función nativa de **Rollback** de IBM Bob para restaurar el estado previo en lugar de acumular parches contradictorios en el mismo contexto.

---

## 7. Flujo de Trabajo SDLC End-to-End en IBM Bob

El proyecto se ejecuta en **6 fases incrementales**, pasando siempre por el ciclo **Planificar $\rightarrow$ Implementar (Custom Mode + Skill) $\rightarrow$ Auditar (Critic) $\rightarrow$ Confirmar (Git)**.

```mermaid
flowchart LR
    F0["Fase 0: Bootstrap<br/>Modo: Plan -> Agent<br/>Skill: bootstrap-tms-workspace"]
    F1["Fase 1: Docker Stack<br/>Modo: docker-platform-eng<br/>Valkey + Superset + Oracle"]
    F2["Fase 2: DDL Oracle<br/>Modo: dw-architect-oracle<br/>Skill: oracle-kimball-ddl-generator"]
    F3["Fase 3: Simulador + ETL<br/>Modos: data-sim-eng & dw-architect<br/>Skills: sim + dbt-oracle"]
    F4["Fase 4: Superset BI<br/>Modo: bi-superset-dev<br/>Skill: superset-oracle-drillacross"]
    F5["Fase 5: QA & CI/CD<br/>Modo: sdlc-auditor-critic + Bob Shell<br/>Skill: actor-critic-dw-review"]

    F0 --> F1 --> F2 --> F3 --> F4 --> F5
    F5 -.->|"Si hay BLOCKER:<br/>Remediación"| F2
```

### Fase 0 — Bootstrap del Workspace (Día 1)
* **Modo:** `Plan` (para validar estructura) $\rightarrow$ `Agent`.
* **Skill:** `bootstrap-tms-workspace`.
* **Context Mentions:** `@docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md`, `@docs/Arquitectura-dw-analytics-tms.docx`, `@docs/Draft-dashboard-TMS.pdf`.
* **Entregables:** Árbol de carpetas, `AGENTS.md`, `.bob/rules/*`, `.bob/custom_modes.yaml`, `.bob/skills/*/SKILL.md`, `.env.example`, `.bobignore`.
* **Criterio de Aceptación (DoD):** IBM Bob reconoce los 5 Custom Modes en el selector, las 3 reglas globales y las 6 Skills en *Bob Settings $\rightarrow$ Skills*.

### Fase 1 — Infraestructura de Contenedores Docker (Días 2–3)
* **Modo:** `docker-platform-eng`.
* **Prompt Maestro Sugerido:**
  > *"Genera `docker-compose.yml`, `superset/Dockerfile` (con `oracledb` en Thin Mode), `superset/superset_config.py` y `superset/bootstrap.sh` integrando Oracle Free 23 (para dev), PostgreSQL 16 y Valkey 8. Aplica healthchecks, redes aisladas y variables desde `.env`."*
* **Entregables:** Stack Docker levantado con `docker compose up -d`.
* **Criterio de Aceptación (DoD):** Todos los contenedores en estado `healthy`; acceso web a Superset (`:8088`); prueba de conexión `SELECT 1 FROM DUAL` exitosa desde el contenedor `superset-app` hacia Oracle.

### Fase 2 — Capa de Datos Oracle: 3FN, Kimball y Vistas Semánticas (Días 4–6)
* **Modo:** `dw-architect-oracle`.
* **Skill:** `oracle-kimball-ddl-generator`.
* **Context Mentions:** `@docs/Arquitectura-dw-analytics-tms.docx`.
* **Entregables:** Scripts `oracle/init/01_*.sql` a `05_*.sql` ejecutados y verificados.
* **Criterio de Aceptación (DoD):** Los 4 esquemas creados sin errores ORA; las 10 dimensiones tienen fila `-1`; las tablas de hechos tienen índices B-Tree; `BI_READER` no puede ejecutar `INSERT` ni consultar `EDW_3FN`.

### Fase 3 — Simulador de Datos Sintéticos y Pipeline ETL `dbt-oracle` (Días 7–11)
* **Modos:** `data-sim-eng` (en paralelo o secuencia con `dw-architect-oracle`).
* **Skills:** `tms-synthetic-data-sim` y `dbt-oracle-etl-pipeline`.
* **Ejecución:**
  1. Correr `docker compose run --rm data-simulator python src/main.py --mode backfill --days 90`.
  2. Correr `docker compose run --rm etl-runner dbt build`.
  3. Habilitar corrida programada en modo `--mode incremental` seguida de `dbt run`.
* **Criterio de Aceptación (DoD):**
  * 100% de los `dbt test` (*Column, Structure y Business Rule Screens*) en verde.
  * `FACT_SNAPSHOT_FLOTA_DIARIO` refleja las 100 unidades diarias con porcentajes coherentes (~56% con viaje).
  * Existen registros en `FACT_FACTURACION_FLETE` y `FACT_GASTOS_LIQUIDACION` desbloqueando los KPIs monetarios.

### Fase 4 — Capa Semántica y Dashboards en Apache Superset (Días 12–15)
* **Modo:** `bi-superset-dev`.
* **Skill:** `superset-oracle-drillacross`.
* **Context Mentions:** `@docs/Draft-dashboard-TMS.pdf`, `@oracle/init/05_views_bi_semantic.sql`.
* **Entregables:** Virtual Datasets con Jinja *Drill-Across*, Dashboard **Reporte Diario de Operación — Analytics TMS** exportado y versionado en `superset/assets/`.
* **Criterio de Aceptación (DoD):**
  * Los 7 bloques del *Draft Dashboard TMS* renderizan sin errores ni productos cartesianos.
  * El cambio de filtro de fecha en el dashboard empuja el predicado `WHERE` a cada CTE en Oracle (verificado con `EXPLAIN PLAN`).
  * Tiempo de respuesta p95 del dashboard $< 3$ segundos con caché Valkey activa.

### Fase 5 — Auditoría Actor-Crítico, Bob Shell y Promoción a Producción (Días 16–18)
* **Modo:** `sdlc-auditor-critic` + **Bob Shell** en CI/CD.
* **Skill:** `actor-critic-dw-review`.
* **Integración en CI/CD (Bob Shell no interactivo):**
  * Ejecutar revisión automatizada de Pull Requests con el modo `sdlc-auditor-critic`.
  * Validar construcción de imágenes Docker, escaneo de secretos, `pytest` del simulador y `dbt test`.
  * Sustituir `oracle-dw` local por la cadena de conexión de la instancia Oracle corporativa en el archivo `.env` de producción.
* **Criterio de Aceptación (DoD):** Reporte `docs/audits/audit-fase-5.md` con **0 hallazgos BLOCKER / HIGH** y visto bueno de Arquitectura y Negocio.

---

## 8. Matriz de Trazabilidad y Gobernanza Continua (Bobalytics)

Para medir tanto la efectividad técnica del pipeline como el valor entregado durante el ciclo SDLC con IBM Bob, se dará seguimiento a dos grupos de métricas:

| Categoría | Métrica | Meta / Umbral | Fuente de Verificación |
| :--- | :--- | :--- | :--- |
| **Calidad de Datos (DW)** | Tasa de aprobación de *Data Quality Screens* | $100\%$ en producción | `dbt test` / Logs de `etl-runner` |
| **Fidelidad Analítica** | Cobertura de KPIs del *Draft Dashboard TMS* | $100\%$ (7/7 bloques operativos y financieros) | Conciliación `DWH_MART` vs. Superset |
| **Rendimiento BI** | Latencia de carga del Dashboard (p95) | $< 3.0\text{ s}$ (cache hit) / $< 8.0\text{ s}$ (cold) | Logs Superset + Oracle `EXPLAIN PLAN` |
| **Cumplimiento y Costo** | Costo adicional de licencias de software | $\$0.00\text{ USD}$ | Auditoría `sdlc-auditor-critic` |
| **Productividad SDLC** | Tasa de aceptación de cambios y defectos bloqueados pre-PR | Reducción de retrabajo y $0$ secretos filtrados | **Bobalytics** + reportes `docs/audits/` |

---

## 9. Prompt de Arranque Inmediato para IBM Bob (Fase 0)

Una vez creada la carpeta vacía del proyecto y copiados los documentos fuente en `docs/`, abre IBM Bob en **Modo `Plan`** y utiliza el siguiente prompt para iniciar la implementación:

> *"Actúa como arquitecto de inicio de proyecto. Lee `@docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md`, `@docs/Arquitectura-dw-analytics-tms.docx` y `@docs/Draft-dashboard-TMS.pdf`. Genera el plan de ejecución de la Fase 0 para crear toda la estructura del workspace, `AGENTS.md`, las reglas en `.bob/rules/`, los 5 Custom Modes en `.bob/custom_modes.yaml` y las 6 Skills en `.bob/skills/`. Espera mi aprobación antes de cambiar a modo Agent para crear los archivos."*