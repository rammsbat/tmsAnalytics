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
