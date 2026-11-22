# Guardrails de Licenciamiento $0 Adicional

1. **Sin Redis propietario:** Utilizar exclusivamente `valkey/valkey:8-alpine` (licencia BSD-3). Rechazar imágenes `redis:*` en `docker-compose.yml`.
   - Aclaración: el esquema de URL `redis://` (por ejemplo, `redis://superset-valkey:6379/0` en `superset_config.py` o `CELERY_BROKER_URL`) es solo el protocolo de cableado y es válido con Valkey. Lo prohibido son las **imágenes** `redis:*`, no el esquema `redis://`.
2. **Compatibilidad Oracle Standard Edition 2 (SE2):**
   - NO generar cláusulas `PARTITION BY` (Oracle Partitioning es opción de pago).
   - NO usar `COMPRESS FOR OLTP` / `ADVANCED` (Advanced Compression es opción de pago).
   - NO activar `ENABLE QUERY REWRITE` en `CREATE MATERIALIZED VIEW` (requiere Enterprise Edition).
   - Optimizar consultas únicamente con índices B-Tree estándar, estadísticas actualizadas (`DBMS_STATS`) y Vistas Materializadas consultadas explícitamente desde `BI_SEMANTIC`.
3. **Sin dependencias SaaS/Comerciales:** No incluir configuraciones de dbt Cloud, Preset, NGINX Plus ni Docker Desktop exclusivo.
