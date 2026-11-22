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
