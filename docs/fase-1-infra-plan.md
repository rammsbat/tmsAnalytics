# Plan de EjecuciÃ³n â€” Fase 1: Infraestructura de Contenedores Docker

## VisiÃ³n General

**Objetivo:** DiseÃ±ar, configurar y endurecer la infraestructura completa de contenedores Docker para la plataforma Analytics TMS, ejecutada mediante el modo `docker-platform-eng`. La infraestructura integra Oracle Database Free 23ai (`gvenzl/oracle-free:23-slim` para desarrollo/staging local), PostgreSQL 16 (metastore de Superset), Valkey 8 (broker, cachÃ© y backend de resultados bajo licencia $0 BSD-3), y Apache Superset customizado con `python-oracledb` en Thin Mode, Celery worker y Celery beat.

**Modo de EjecuciÃ³n:** `docker-platform-eng`

**Fuentes y Referencias:**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` (Â§2, Â§3, Â§4.2, Â§5.5, Â§7 Fase 1).
- `.bob/rules/02-licensing-oracle-guardrails.md` (Licenciamiento $0: `valkey/valkey:8-alpine`, cero imÃ¡genes `redis:*`).
- `.bob/rules/03-security-and-secrets.md` (Cero secretos en cÃ³digo, hardening de contenedores, red interna `tms-internal-net`).
- `.env.example` (Variables de entorno requeridas).

**Alcance de Fase 1:**
- `superset/Dockerfile` (con `oracledb`, `psycopg2-binary` y `redis`, usuario no root `superset`).
- `.dockerignore` para optimizar el contexto de build.
- `superset/superset_config.py` (Valkey cache, Celery broker/backend, `RESULTS_BACKEND` en DB 6, `ENABLE_TEMPLATE_PROCESSING=True`, `ALERT_REPORTS=True`, metastore PostgreSQL).
- `superset/bootstrap.sh` (migraciones de metadatos `superset db upgrade`, creaciÃ³n de usuario admin idempotente, inicializaciÃ³n de roles y registro en metastore de `Analytics_TMS_Oracle` sin bloqueo de test en vivo).
- `docker-compose.yml` con servicios `oracle-dw` (`gvenzl/oracle-free:23-slim`, `shm_size: 1g`), `superset-db`, `superset-valkey`, `superset-app` (healthcheck en `/health`), `superset-worker`, `superset-beat`, red interna `tms-internal-net` y volÃºmenes nombrados.
- ValidaciÃ³n de arranque con `.env` manual, estado `healthy` y conectividad `superset-app` $\rightarrow$ `oracle-dw` (`SELECT 1 FROM DUAL` vÃ­a usuario `SYSTEM`).
- EvaluaciÃ³n tÃ©cnica para posponer la activaciÃ³n de `.bob/mcp.json` hasta el cierre de la Fase 2.

---

## Decisiones TÃ©cnicas y Guardrails de Arquitectura

| # | DecisiÃ³n | Fundamento / Guardrail | Impacto en ImplementaciÃ³n |
|---|---|---|---|
| T1 | **Valkey 8 Alpine** (`valkey/valkey:8-alpine`) | Regla 02 (Licenciamiento $0). ProhibiciÃ³n estricta de imÃ¡genes `redis:*`. | Se usa `valkey/valkey:8-alpine` en `docker-compose.yml`. En `superset_config.py`, el protocolo de conexiÃ³n `redis://superset-valkey:6379/...` es vÃ¡lido como protocolo de comunicaciÃ³n. |
| T2 | **Oracle Free 23 Slim y shm_size** | `gvenzl/oracle-free:23-slim` para dev local. | Mapeo de variable `ORACLE_PASSWORD: ${ORACLE_PWD}` para conservar `.env.example` sin cambios. `shm_size: 1g` para evitar bloqueos de SGA/PGA en Linux. Healthcheck con `healthcheck.sh` y `start_period: 120s`. |
| T3 | **Dependencias Python en Superset** | Thin Mode Oracle + PostgreSQL + Valkey/Celery client. | `superset/Dockerfile` instala `oracledb`, `psycopg2-binary` y `redis`. Retorna a `USER superset`. |
| T4 | **Manejo de Resultados AsÃ­ncronos (`RESULTS_BACKEND`)** | Soporte de consultas asÃ­ncronas (`allow_run_async: true`). | `superset_config.py` configura `RESULTS_BACKEND` apuntando a Valkey DB 6 (`redis://superset-valkey:6379/6`). |
| T5 | **Desacople de Bootstrap y BI_READER** | `BI_READER` se crea en Fase 2. | `bootstrap.sh` inserta/actualiza los metadatos de `Analytics_TMS_Oracle` en el metastore de Superset sin forzar un test de conexiÃ³n en vivo al arrancar, evitando fallos antes de Fase 2. |
| T6 | **Formato LF y Montaje Read-Only** | PrevenciÃ³n de errores de salto de lÃ­nea CRLF en Windows. | `superset_config.py` y `bootstrap.sh` se guardan estrictamente con terminaciones LF y se montan como `:ro` en los contenedores. |
| T7 | **Aislamiento y Hardening de Red** | Regla 03 punto 4. | Red puente interna `tms-internal-net`. Solo se exponen puertos de desarrollo (`8088` Superset, `1521` Oracle). |

---

## Sub-tareas

### ST-1 â€” ConstrucciÃ³n del Dockerfile de Superset y `.dockerignore`
**Intent:** Crear una imagen personalizada de Apache Superset que incluya los drivers nativos `oracledb` (Thin Mode), `psycopg2-binary` y `redis` cumpliendo las polÃ­ticas de seguridad (usuario no root `superset`) y optimizaciÃ³n de contexto de compilaciÃ³n.

**Expected Outcomes:**
- `superset/Dockerfile` existente con instalaciÃ³n de `oracledb`, `psycopg2-binary` y `redis`.
- `.dockerignore` existente en la raÃ­z para excluir `.git`, `.env`, caches y temporales.

**Todo List:**
1. Crear `superset/Dockerfile` basÃ¡ndose en la imagen oficial estable `apache/superset:4.1.1` (o compatible LTS).
2. Cambiar a `USER root` para instalar dependencias vÃ­a `pip install --no-cache-dir oracledb psycopg2-binary redis`.
3. Retornar a `USER superset` como usuario de ejecuciÃ³n por defecto.
4. Crear `.dockerignore` en la raÃ­z del proyecto ignorando `.git/`, `.env`, `oracle_data/`, `postgres_data/`, `__pycache__/`, `target/`, `.bob/tmp/`.

**Relevant Context:**
- `custom_modes.yaml` (permite a `docker-platform-eng` editar `Dockerfile.*` y `.dockerignore`).
- Reglas 02 y 03.

**Status:** `[x] done`

---

### ST-2 â€” ConfiguraciÃ³n AnalÃ­tica Base: `superset/superset_config.py`
**Intent:** Centralizar la configuraciÃ³n de Apache Superset conectando PostgreSQL como metastore, Valkey como cachÃ© y backend de Celery/Resultados, y habilitando el motor de plantillas Jinja para consultas Drill-Across.

**VerificaciÃ³n de Permisos:** Se verificÃ³ `.bob/custom_modes.yaml` y el modo `docker-platform-eng` tiene permiso explÃ­cito sobre `superset/superset_config.py` en su `fileRegex` (`(docker-compose.*\.ya?ml|Dockerfile.*|\.env\.example|\.dockerignore|\.bobignore|superset/bootstrap\.sh|superset/superset_config\.py|.*\.sh)$`). No se requiere modificar `custom_modes.yaml` ni alternar de modo para esta sub-tarea.

**Expected Outcomes:**
- `superset/superset_config.py` implementado con terminaciÃ³n de lÃ­nea LF.
- Flags `ENABLE_TEMPLATE_PROCESSING` y `ALERT_REPORTS` activos en `FEATURE_FLAGS`.
- `RESULTS_BACKEND` configurado en Valkey DB 6.
- Cero contraseÃ±as hardcodeadas (lectura de variables de entorno).

**Todo List:**
1. Configurar `FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": True, "ALERT_REPORTS": True}`.
2. Configurar `SQLALCHEMY_DATABASE_URI` apuntando a `superset-db` (`postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@superset-db:5432/${POSTGRES_DB}`).
3. Configurar `CACHE_CONFIG`, `DATA_CACHE_CONFIG`, `FILTER_STATE_CACHE_CONFIG` y `EXPLORE_FORM_DATA_CACHE_CONFIG` utilizando `RedisCache` apuntando a `redis://superset-valkey:6379/<0..3>`.
4. Configurar `CeleryConfig` con `broker_url="redis://superset-valkey:6379/4"` y `result_backend="redis://superset-valkey:6379/5"`.
5. Configurar `RESULTS_BACKEND = RedisCache(host="superset-valkey", port=6379, db=6, key_prefix="superset_results_")`.
6. Configurar `SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY")`.
7. Configurar `ROW_LIMIT = 50000` y `SUPERSET_WEBSERVER_TIMEOUT = 120`.

**Relevant Context:**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` (Â§5.5 paso 1).
- `.bob/rules/02-licensing-oracle-guardrails.md` (uso vÃ¡lido del protocolo `redis://`).

**Status:** `[x] done`

---

### ST-3 â€” Script de InicializaciÃ³n y Bootstrap Automatizado: `superset/bootstrap.sh`
**Intent:** Proveer un script de inicializaciÃ³n reproducible e idempotente con saltos de lÃ­nea LF que aplique migraciones de metadatos, cree el usuario admin si no existe, inicialice roles y registre en el metastore la fuente de datos `Analytics_TMS_Oracle` sin bloquearse por la ausencia inicial de `BI_READER`.

**Expected Outcomes:**
- `superset/bootstrap.sh` con terminaciÃ³n LF y lÃ³gica idempotente.
- Registro en metastore de la conexiÃ³n `Analytics_TMS_Oracle` con URI `oracle+oracledb://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1` sin test en vivo durante el arranque.
- Arranque del servidor web de Superset.

**Todo List:**
1. Crear `superset/bootstrap.sh` con `set -e` y manejo de logs informativos.
2. Ejecutar `superset db upgrade`.
3. Ejecutar `superset fab create-admin` de forma idempotente utilizando `${SUPERSET_ADMIN_USER}` y `${SUPERSET_ADMIN_PASSWORD}`.
4. Ejecutar `superset init`.
5. Registrar o actualizar la base de datos `Analytics_TMS_Oracle` directamente en el metastore de Superset mediante script Python idempotente:
   - Database Name: `Analytics_TMS_Oracle`
   - SQLAlchemy URI: `oracle+oracledb://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1`
   - ParÃ¡metros: `allow_ctas: false`, `allow_cvas: false`, `allow_dml: false`, `allow_run_async: true`, `extra: {"engine_params": {"arraysize": 1000}}`.
   - **Importante:** La inserciÃ³n registra el objeto en el modelo `Database` de Superset sin invocar `db.test_connection()`, evitando fallos en Fase 1 antes de que `BI_READER` sea creado en Fase 2.
6. Ejecutar el servidor web de Superset (`/usr/bin/run-server.sh` o comando estÃ¡ndar).

**Relevant Context:**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` (Â§5.5 paso 2).
- `.bob/rules-dw-architect-oracle/01-oracle-ddl-conventions.md` (usuario `BI_READER` de Fase 2).

**Status:** `[x] done`

---

### ST-4 â€” OrquestaciÃ³n del Stack Completo: `docker-compose.yml`
**Intent:** Orquestar los servicios `oracle-dw`, `superset-db`, `superset-valkey`, `superset-app`, `superset-worker` y `superset-beat` con healthchecks explÃ­citos, memoria compartida adecuada, redes internas, volÃºmenes persistentes y montajes `:ro` con LF.

**Expected Outcomes:**
- `docker-compose.yml` vÃ¡lido segÃºn la especificaciÃ³n Docker Compose v2.
- 0 imÃ¡genes de Redis propietario (`valkey/valkey:8-alpine`).
- `oracle-dw` usando `gvenzl/oracle-free:23-slim`, `ORACLE_PASSWORD: ${ORACLE_PWD}`, `shm_size: 1g` y `healthcheck.sh` (`start_period: 120s`).
- `superset-app` con healthcheck HTTP `/health` vÃ­a Python y archivos de configuraciÃ³n montados `:ro`.

**Todo List:**
1. Definir servicio `oracle-dw`:
   - Imagen: `gvenzl/oracle-free:23-slim`.
   - Puertos: `1521:1521`.
   - Variables de entorno: `ORACLE_PASSWORD: ${ORACLE_PWD}`.
   - Recursos: `shm_size: 1g`.
   - VolÃºmenes: `oracle_data:/opt/oracle/oradata`, `./oracle/init:/container-entrypoint-initdb.d:ro`.
   - Healthcheck: `test: ["CMD-SHELL", "healthcheck.sh"]`, `interval: 15s`, `timeout: 10s`, `retries: 10`, `start_period: 120s`.
2. Definir servicio `superset-db`:
   - Imagen: `postgres:16-alpine`.
   - Variables de entorno: `POSTGRES_DB: ${POSTGRES_DB}`, `POSTGRES_USER: ${POSTGRES_USER}`, `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}`.
   - VolÃºmenes: `postgres_data:/var/lib/postgresql/data`.
   - Healthcheck: `test: ["CMD", "pg_isready", "-U", "${POSTGRES_USER}", "-d", "${POSTGRES_DB}"]`, `interval: 10s`, `timeout: 5s`, `retries: 5`.
3. Definir servicio `superset-valkey`:
   - Imagen: `valkey/valkey:8-alpine`.
   - Healthcheck: `test: ["CMD", "valkey-cli", "ping"]`, `interval: 10s`, `timeout: 5s`, `retries: 5`.
4. Definir servicio `superset-app`:
   - Build: `context: .`, `dockerfile: superset/Dockerfile`.
   - Puertos: `8088:8088`.
   - Variables de entorno: paso de `.env` (`SUPERSET_SECRET_KEY`, `POSTGRES_*`, `BI_READER_PWD`, etc.) y `SUPERSET_CONFIG_PATH: /app/pythonpath/superset_config.py`.
   - VolÃºmenes: `./superset/superset_config.py:/app/pythonpath/superset_config.py:ro`, `./superset/bootstrap.sh:/app/bootstrap.sh:ro`, `./superset/assets:/app/assets`.
   - Healthcheck: `test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8088/health')\" || exit 1"]`, `interval: 15s`, `timeout: 10s`, `retries: 5`, `start_period: 60s`.
   - Entrypoint/Command: `/bin/bash /app/bootstrap.sh`.
   - Depends on con `condition: service_healthy` sobre `superset-db`, `superset-valkey` y `oracle-dw`.
5. Definir servicios `superset-worker` y `superset-beat`:
   - Misma imagen de compilaciÃ³n de Superset.
   - User: `superset`.
   - Command para worker: `celery --app=superset.tasks.celery_app:app worker -O fair -c 2`.
   - Command para beat: `celery --app=superset.tasks.celery_app:app beat --pidfile /tmp/celerybeat.pid -s /tmp/celerybeat-schedule`.
   - Depends on sobre `superset-app` (healthy), `superset-db` y `superset-valkey`.
6. Configurar red `tms-internal-net` (driver bridge) y volÃºmenes nombrados `oracle_data`, `postgres_data`.

**Relevant Context:**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` (Â§5.1, Â§5.5, Â§7 Fase 1).
- `.bob/rules/02-licensing-oracle-guardrails.md`.

**Status:** `[x] done`

---

### ST-5 â€” ValidaciÃ³n de Infraestructura, Conectividad Superset-Oracle y EvaluaciÃ³n MCP
**Intent:** Validar el criterio de aceptaciÃ³n (DoD) de la Fase 1, instruir la creaciÃ³n manual de `.env`, verificar la conectividad `SELECT 1 FROM DUAL` usando el usuario administrador `SYSTEM` en Thin Mode, y ratificar la postergaciÃ³n de `.bob/mcp.json` para Fase 2.

**Expected Outcomes:**
- VerificaciÃ³n de creaciÃ³n manual de `.env` a partir de `.env.example`.
- ComprobaciÃ³n de que todos los contenedores levantan y reportan estado `healthy`.
- VerificaciÃ³n exitosa de consulta `SELECT 1 FROM DUAL` hacia `oracle-dw` desde `superset-app` con `SYSTEM` / `${ORACLE_PWD}`.
- ConexiÃ³n con `BI_READER` diferida explÃ­citamente para Fase 2.
- EvaluaciÃ³n de `.bob/mcp.json` documentada recomendando activaciÃ³n al cierre de Fase 2.

**Todo List:**
1. Registrar que el usuario debe copiar `.env.example` a `.env` con contraseÃ±as reales antes de ejecutar `docker compose up -d`.
2. Validar sintaxis de `docker-compose.yml` (`docker compose config`).
3. Comprobar que no existan imÃ¡genes `redis:*`.
4. Ejecutar prueba de conectividad Python Thin Mode desde el contenedor `superset-app` hacia `oracle-dw` ejecutando `SELECT 1 FROM DUAL` usando el usuario `SYSTEM` y `${ORACLE_PWD}`:
   ```bash
   docker compose exec superset-app python -c "import oracledb, os; conn = oracledb.connect(user='system', password=os.environ.get('ORACLE_PWD'), dsn='oracle-dw:1521/FREEPDB1'); cursor = conn.cursor(); cursor.execute('SELECT 1 FROM DUAL'); print('Oracle connectivity OK:', cursor.fetchone()); conn.close()"
   ```
5. Confirmar que la validaciÃ³n de `BI_READER` queda agendada para Fase 2 (tras ejecutar `01_schemas_and_users.sql`).
6. Ratificar la postergaciÃ³n de `.bob/mcp.json`: Mantener su configuraciÃ³n para Fase 2 una vez que los esquemas y usuarios de Oracle estÃ©n provisionados.

**Relevant Context:**
- `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` (Â§7 Fase 1 DoD).
- Reglas 02 y 03.

**Status:** `[x] done`

---

## Orden y Dependencias

```
ST-1 (Dockerfile & .dockerignore)
  â”‚
  â”œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â–¼                        â–¼
ST-2 (superset_config.py) ST-3 (bootstrap.sh)
  â”‚                        â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â–¼
ST-4 (docker-compose.yml)
              â”‚
              â–¼
ST-5 (ValidaciÃ³n, Conectividad SYSTEM y EvaluaciÃ³n MCP)
```

---

## Riesgos y Mitigaciones

1. **Tiempo de inicializaciÃ³n de Oracle Free:**
   - *Riesgo:* `oracle-dw` tarda entre 60 y 120 segundos en crear y montar la PDB `FREEPDB1`.
   - *MitigaciÃ³n:* Se fijÃ³ `gvenzl/oracle-free:23-slim` con `shm_size: 1g`, `healthcheck.sh` y `start_period: 120s`. `superset-app` no iniciarÃ¡ hasta que `oracle-dw` estÃ© `healthy`.
2. **Saltos de lÃ­nea CRLF en Windows:**
   - *Riesgo:* `bootstrap.sh` o `superset_config.py` con CRLF fallan dentro del contenedor Linux.
   - *MitigaciÃ³n:* GeneraciÃ³n estricta con saltos LF e invocaciÃ³n mediante `/bin/bash /app/bootstrap.sh`.
3. **Bloqueo por usuario BI_READER inexistente:**
   - *Riesgo:* `bootstrap.sh` fallarÃ­a si intentara validar la conexiÃ³n en vivo contra `BI_READER` en Fase 1.
   - *MitigaciÃ³n:* InserciÃ³n pura de metadatos en el catÃ¡logo de Superset sin test de conexiÃ³n activo al arrancar; validaciÃ³n de Fase 1 realizada con `SYSTEM`.
