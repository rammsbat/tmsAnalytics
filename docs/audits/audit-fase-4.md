# Auditoría Actor-Crítico — Cierre de Fase 4 (Superset BI · Analytics TMS)

**Fecha:** 2026-11-23
**Método:** skill `actor-critic-dw-review` — 3 subagentes `explore` de contexto limpio y solo lectura (A: Seguridad y Licencias, B: Kimball y Oracle, C: Cobertura BI). El Actor **no aceptó sus conclusiones sin verificarlas**: cada hallazgo se contrastó con el código y se repitieron con comandos propios los escaneos de seguridad y licenciamiento (ver §6).
**Alcance:** `docker-compose.yml`, `superset/` (Dockerfile, `superset_config.py`, `bootstrap.sh`, `assets/datasets/`, `assets/bundle/`), `tools/`, `tests/`, `oracle/ddl/`, `.gitignore`, `.env.example`.

## Veredicto

**APROBADO — 0 BLOCKER abiertos y 0 HIGH abiertos.**

La auditoría detectó **2 BLOCKER y 1 HIGH** reales. Los tres se remediaron durante la propia auditoría y se re-validaron (§4). Quedan 2 MEDIUM abiertos, aceptados y documentados; el primero (F-04) requiere decisión del equipo antes de cualquier exposición fuera del entorno local.

| Severidad | Detectados | Remediados | Abiertos |
|---|---|---|---|
| BLOCKER | 2 | 2 | **0** |
| HIGH | 1 | 1 | **0** |
| MEDIUM | 2 | 0 | 2 |
| LOW | 2 | 0 | 2 |
| INFO | 4 | — | — |

## 1. Resumen por dimensión

| Dimensión | Resultado | Evidencia principal |
|---|---|---|
| **1. Seguridad y cero secretos** | ✅ PASS | `audit_superset_assets.py` sobre el bundle: PASS (23 archivos, 12 charts, 8 datasets, 1 base, 1 dashboard, 4 Native Filters). Escaneo del repositorio: 0 credenciales literales, 0 claves privadas, 0 máscaras `XXXXXXXXXX` en el bundle (solo en la documentación del README). `.env` y `etl/dbt_tms/profiles.yml` ignorados y no rastreados. Bind variables en `tools/` y `tests/`: 0 f-strings con SQL. |
| **2. Licenciamiento $0 y Oracle SE2** | ✅ PASS | Imágenes: `valkey/valkey:8-alpine` única de caché; 0 imágenes `redis:*`. 0 `PARTITION BY` DDL, 0 `COMPRESS FOR`, 0 `ENABLE QUERY REWRITE`. Sin dbt Cloud, Preset ni NGINX Plus. 0 `import cx_Oracle` reales. |
| **3. Conformidad Kimball** | ✅ PASS (tras F-01/F-02) | 0 joins Fact↔Fact directos en los 8 datasets. Drill-Across con `FULL OUTER JOIN` en ds_02, ds_03, ds_06 y ds_07. `DISTANCIA_DECLARADA_KM` colapsada con `MAX` por `UUID_CCP` en ds_06, ds_07 y ds_08 (test_07: ×2.93–×3.02 evitado). Datasets leen solo `BI_SEMANTIC`. |
| **4. Cobertura funcional BI** | ✅ PASS | 7 bloques + B8 → 8 datasets → 12 charts (UUID coincidentes con `dashboard_mapping.md`), 4 Native Filters. Conciliación: 8/8 grupos, 259 aserciones. Charts en vivo: 100 % PASS en 8 escenarios. |

### Nota explícita: URI `oracle+cx_oracle://` (falso positivo documentado)

`superset/assets/bundle/databases/Analytics_TMS_Oracle.yaml` contiene `oracle+cx_oracle://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1`. Esto **no es una violación** de AGENTS.md ("NO usar `cx_Oracle`"):

- Superset 4.1.1 usa SQLAlchemy 1.4, cuyo dialecto Oracle se llama `cx_oracle` y exige ese esquema de URL.
- `superset/superset_config.py:5-7` puentea con `import oracledb` + `sys.modules["cx_Oracle"] = oracledb`: el driver real es **`python-oracledb` en Thin Mode**, sin Oracle Instant Client y sin el paquete `cx_Oracle`.
- La contraseña es el placeholder `${BI_READER_PWD}`; nunca un valor real ni la máscara.
- Documentado en `superset/assets/README.md` (sección "Falso positivo documentado"). Cualquier regla futura de escaneo debe excluir esta URI **solo** cuando el password sea el placeholder.

El mismo criterio aplica al esquema `redis://` en `superset_config.py` (protocolo de cableado válido con Valkey).

## 2. Hallazgos

| ID | Sev. | Estado | Hallazgo |
|---|---|---|---|
| F-01 | BLOCKER | ✅ Remediado | `ds_02_operacion_dia_mes.sql:131-133` combinaba las 4 CTEs de hechos (despacho, liquidaciones, cartaporte, facturación) con `JOIN … ON JOIN_KEY` (INNER), no con `FULL OUTER JOIN` como exige la regla 01 §2 y el estándar Drill-Across. |
| F-02 | BLOCKER | ✅ Remediado | `ds_03_generales_dia_mes.sql:107-108`: mismo patrón con 3 CTEs (despacho, gastos, facturación). |
| F-03 | HIGH | ✅ Remediado | `docker-compose.yml`: `superset-worker` y `superset-beat` tenían `healthcheck: disable: true`, contra la regla 03 §4 ("healthcheck en todos los servicios"). El subagente A lo dio por aceptable; el Actor lo reclasificó como violación. |
| F-04 | MEDIUM | ⚠️ Abierto y **aceptado** para entorno localhost | `superset_config.py:121-122`: `TALISMAN_ENABLED = False` y `WTF_CSRF_ENABLED = False`. Heredado de Fase 1 y señalado en la auditoría de Fase 3. Decisión del equipo (2026-11-23): se mantiene sin cambios en `superset_config.py`. **Obligatorio antes de cualquier despliegue fuera de local**, junto con TLS / proxy inverso: habilitar CSRF y Talisman (con CSP) y servir Superset solo detrás de TLS. Superset emite además un warning de CSP. |
| F-05 | MEDIUM | ⚠️ Abierto | Bloque 8 (ds_08): la conciliación numérica cubre embarques, distancia colapsada y peso (test_07, mes y 91 días), pero no compara fila por fila cada corredor como sí se hace en ds_06/ds_07. Se renderiza y ejecuta en test_00 y en los 8 escenarios en vivo. |
| F-06 | LOW | Documentado | Los Native Filters `UNIDAD`, `NOMBRE_OPERADOR` y `CLIENTE` aplican solo a los datasets que tienen esa dimensión (p. ej. `FACT_GASTOS_LIQUIDACION` no tiene FK a cliente). Diseño Kimball, descrito en `dashboard_mapping.md`. |
| F-07 | LOW | Documentado | `tools/` y `tests/` no se montan en los contenedores (decisión de ST-4); se usa el flujo `docker cp` del README. |
| F-08 | INFO | — | Shim `oracle+cx_oracle://` → `python-oracledb` Thin Mode (ver nota arriba). |
| F-09 | INFO | — | `superset/Dockerfile` instala el paquete Python `redis` y `superset_config.py` usa `cachelib.redis.RedisCache`: son bibliotecas cliente compatibles con Valkey, no la imagen `redis:*` prohibida. |
| F-10 | INFO | — | El stack local usa `gvenzl/oracle-free:23-slim` (Oracle Free, sin costo). El SQL no usa ninguna opción de Enterprise Edition, por lo que es portable a 19c/23ai SE2. |
| F-11 | INFO | — | Superset limita la API a **50 req/s** por cliente (HTTP 429). El benchmark introduce una pausa entre cargas; un dashboard real (12 peticiones por carga) queda muy por debajo. |

### Notas sobre F-01 / F-02
Cada CTE es un agregado sin `GROUP BY`, así que siempre devuelve exactamente una fila y con `INNER JOIN` el resultado numérico actual era el mismo. Aun así incumplía la regla de forma literal y era frágil ante cambios futuros en las CTEs, por lo que se mantuvo la severidad BLOCKER por conformidad.

### Discrepancias entre subagentes y verificación propia
- El subagente C reportó latencias "p95 < 50 ms"; son tiempos en proceso (`test_superset_live_charts.py`), no HTTP. La medición de DoD #5 se hizo por HTTP (§3).
- El subagente C citó "ECO15 (ID 240, 241)"; los IDs reales son 36 y 241 (verificado en ST-5). No afecta la conclusión.
- El subagente A no detectó F-03; el subagente B no clasificó como bloqueo nada que no hubiese verificado el Actor.

## 3. DoD #5 — Rendimiento con caché Valkey

Herramienta: `tools/benchmark_dashboard_latency.py` (nueva). Llama por HTTP real a `/api/v1/chart/data` con los 12 charts en paralelo, como el navegador. **Frío** = `force: true` (omite caché y consulta Oracle en Thin Mode); **caliente** = misma petición sin `force`, verificando `is_cached = true`. 5 escenarios × 5 repeticiones.

| Medición | n | Media | p50 | **p95** | Máx | Umbral |
|---|---|---|---|---|---|---|
| Chart individual — frío | 300 | 1,759.9 ms | 1,750.4 ms | **1,997.7 ms** | 2,335.1 ms | < 3,000 ms ✅ |
| Chart individual — caliente (Valkey) | 300 | 146.1 ms | 142.2 ms | **195.0 ms** | 286.3 ms | < 3,000 ms ✅ |
| Carga del dashboard (12 charts) — frío | 25 | 1,852.4 ms | 1,811.8 ms | **2,261.1 ms** | 2,339.4 ms | < 3,000 ms ✅ |
| Carga del dashboard (12 charts) — caliente | 25 | 165.1 ms | 155.7 ms | **205.3 ms** | 291.3 ms | < 3,000 ms ✅ |

- Aceleración por caché: **×12.0**. Respuestas calientes sin `is_cached`: **0**. Errores: **0**.
- **PASS**: p95 frío 2.26 s y p95 caliente 0.21 s, ambos < 3 s. El margen en frío es de ~25 %; el caso caliente (el que pide el DoD) tiene margen de ~14×.
- Las consultas Oracle individuales son de ms (ST-2: 2–230 ms); la latencia en frío está dominada por el procesamiento de Superset con 12 peticiones forzadas simultáneas. No se investigó la causa; no compromete el DoD.
- Nota metodológica: una primera corrida reportó fallos por HTTP 429 (límite de 50 req/s). No eran errores de datos; se añadió una pausa de 1.2 s entre cargas y la corrida final tiene 0 errores.

## 4. Remediaciones aplicadas y re-validación

| Cambio | Archivos |
|---|---|
| ds_02 y ds_03: `FULL OUTER JOIN … USING (JOIN_KEY)` entre CTEs de hechos | `superset/assets/datasets/ds_02_operacion_dia_mes.sql`, `ds_03_generales_dia_mes.sql` |
| Bundle regenerado con el exportador (solo cambian los 2 datasets) | `superset/assets/bundle/datasets/Analytics_TMS_Oracle/…Operacion_Dia_vs_Mes.yaml`, `…Generales_Dia_vs_Mes.yaml` |
| Healthchecks reales en worker (`celery inspect ping`) y beat (PID vivo) | `docker-compose.yml` |
| Benchmark DoD #5 | `tools/benchmark_dashboard_latency.py` |

Re-validación posterior a los cambios (todas en verde):

| Prueba | Resultado |
|---|---|
| `docker compose config -q` | válido |
| `tms-superset-worker` / `tms-superset-beat` | `healthy` |
| `verify_explain_plans.py` | 16/16 planes PASS, 0 productos cartesianos |
| `test_superset_kpi_reconciliation.py` | 8/8 grupos, 259 aserciones PASS |
| `test_superset_live_charts.py` | 12 charts × 8 escenarios + 3 filtros: 100 % PASS |
| `audit_superset_assets.py` | PASS (cero secretos, 23 archivos) |
| `import_superset_assets.py` (re-import) | idempotente: 1/8/12/1 antes y después, password cifrada intacta; el bundle exportado no cambia |

## 5. Estado del repositorio al cierre

Cambios pendientes de commit (solo archivos de cierre): los 5 archivos de §4 más `tools/benchmark_dashboard_latency.py`, `docs/audits/audit-fase-4.md` y `docs/fase-4-superset-bi-plan.md`. Ningún otro archivo modificado; sin secretos en el diff.

## 6. Escaneos propios del Actor (reproducibles con `git grep`)

| Verificación | Resultado |
|---|---|
| `image: redis` / `FROM redis` | 0 coincidencias |
| `PARTITION BY` / `COMPRESS FOR` / `ENABLE QUERY REWRITE` fuera de comentarios y de `OVER()` | 0 |
| `import cx_Oracle` / `from cx_Oracle` | 0 |
| f-strings con `SELECT/INSERT/UPDATE/DELETE/WITH` en `tools/`, `tests/`, `simulator/` | 0 |
| Credenciales literales (`password/pwd/secret_key/api_key/token`) fuera de `docs`/`*.md` | 0 |
| `BEGIN … PRIVATE KEY` | 0 |
| `.env`, `profiles.yml`, `*.pem`, `*.key` rastreados | 0 (`.env` y `profiles.yml` ignorados por `.gitignore:2` y `:30`) |
| `XXXXXXXXXX` en `superset/assets/bundle/` | 0 |

## 7. Conclusión

La Fase 4 cumple los criterios de aceptación con **0 BLOCKER y 0 HIGH abiertos**. Pendiente de decisión del equipo: F-04 (CSRF/Talisman) antes de cualquier exposición fuera del entorno local, y F-05 como mejora opcional de cobertura del Bloque 8.
