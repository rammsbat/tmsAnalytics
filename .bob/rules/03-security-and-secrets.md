# Políticas de Seguridad y Secretos (DevSecOps)

1. **Cero Secretos en Código:** Prohibido escribir contraseñas, `SECRET_KEY` de Superset o cadenas de conexión con credenciales en archivos versionados. Usar exclusivamente variables de entorno referenciadas desde `.env` (ignorado en `.gitignore` y `.bobignore`).
2. **Prevención de SQL Injection:** En el simulador Python y scripts de soporte, toda consulta con parámetros debe usar *bind variables* de Oracle (`:param_name`). Prohibida la interpolación de strings (`f"SELECT ... {var}"`).
3. **Principio de Mínimo Privilegio en Oracle:**
   - El usuario de conexión de Superset (`BI_READER`) solo tiene permisos `SELECT` sobre el esquema `BI_SEMANTIC` y `DWH_MART`. Prohibido `INSERT/UPDATE/DELETE/DDL`.
   - El usuario `SIM_WRITER` solo tiene permisos `INSERT/UPDATE` sobre `STG_SRC`.
4. **Hardening de Contenedores:** No ejecutar procesos de aplicación como `root` dentro de contenedores custom (`USER superset`, `USER appuser`), declarar `healthcheck` en todos los servicios y aislar la red de base de datos en una red Docker interna (`tms-internal-net`).
