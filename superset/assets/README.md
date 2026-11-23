# Bundle reproducible de assets de Superset

Directorio `bundle/`: exportación YAML (formato `/api/v1/assets/export`) del dashboard TRA099R1.

| Contenido | Cantidad |
|---|---|
| `databases/` (`Analytics_TMS_Oracle`) | 1 |
| `datasets/` (virtual datasets Jinja ds_01..ds_08) | 8 |
| `charts/` (B1 x5, B2..B8) | 12 |
| `dashboards/` (7 filas `ROW_*` + header, 4 Native Filters) | 1 |

## Flujo

Todos los comandos se ejecutan dentro de `tms-superset-app` (el contenedor ya tiene `BI_READER_PWD`).

```powershell
# 1. Copiar herramientas (el directorio tools/ no se monta en el contenedor)
docker exec tms-superset-app mkdir -p /tmp/tools
docker cp tools/export_superset_assets.py tms-superset-app:/tmp/tools/
docker cp tools/import_superset_assets.py tms-superset-app:/tmp/tools/
docker cp tools/audit_superset_assets.py  tms-superset-app:/tmp/tools/

# 2. Exportar (escribe en superset/assets/bundle/ vía el volumen ./superset/assets)
docker exec tms-superset-app python /tmp/tools/export_superset_assets.py

# 3. Auditar cero secretos + completitud (sale con código 1 si hay hallazgos)
docker exec tms-superset-app python /tmp/tools/audit_superset_assets.py /app/assets/bundle

# 4. Restaurar en frío / re-importar (idempotente; --dry-run solo valida)
docker exec tms-superset-app python /tmp/tools/import_superset_assets.py

# 5. Validar charts contra Oracle (Thin Mode)
docker cp tools/test_superset_live_charts.py tms-superset-app:/tmp/tools/
docker exec tms-superset-app python /tmp/tools/test_superset_live_charts.py

# 6. Latencia frío vs caliente (DoD #5: p95 < 3 s con caché Valkey)
docker cp tools/benchmark_dashboard_latency.py tms-superset-app:/tmp/tools/
docker exec tms-superset-app python /tmp/tools/benchmark_dashboard_latency.py
```

## Garantías (Regla 03)

- El bundle **no contiene contraseñas**: la URI usa el placeholder `${BI_READER_PWD}`. El exportador
  sustituye la máscara `XXXXXXXXXX` de Superset por el placeholder, elimina `password` y
  `encrypted_extra`, y aborta si detecta una credencial real.
- El importador convierte el placeholder a la máscara que exige Superset e **inyecta la password real
  desde `BI_READER_PWD`** por el canal `passwords` de `ImportAssetsCommand`. Si la variable no existe y la
  base ya está en el metastore, **conserva la password cifrada existente**; si no existe la base, aborta.
  Nunca persiste la máscara ni un valor vacío.
- Idempotencia: los assets se identifican por `uuid` y se sobrescriben; no se duplican charts, datasets,
  dashboards ni bases de datos.
- El bundle es determinista para Git: sin `timestamp`, sin sufijo de ID en los nombres de archivo y con
  `chartsInScope: []` (el importador lo recalcula con los IDs reales de la instancia).

## Falso positivo documentado: `oracle+cx_oracle://`

La URI `oracle+cx_oracle://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1` es
**obligatoria** en Superset 4.1.1 porque usa SQLAlchemy 1.4, cuyo dialecto Oracle se llama `cx_oracle`.
`superset/superset_config.py` puentea ese nombre al driver `python-oracledb` en **Thin Mode**
(`sys.modules["cx_Oracle"] = oracledb`). No se usa `cx_Oracle` real ni Oracle Instant Client, por lo que el
cumplimiento de `AGENTS.md` se mantiene. La auditoría de ST-6 no debe tratar esta cadena como hallazgo.
`${BI_READER_PWD}` es un placeholder, no un secreto.

## Fuente de verdad de los datasets

El campo `sql` de cada dataset del bundle es una copia de `datasets/ds_0X_*.sql`. Si se edita un `.sql`,
sincronizar el metastore con `tools/build_superset_dashboard.py`, volver a exportar y auditar.
