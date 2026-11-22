---
name: actor-critic-dw-review
description: Orquesta una auditoría automatizada Actor-Crítico usando subagentes aislados para validar seguridad, licenciamiento $0, conformidad Kimball y cobertura del Draft Dashboard antes de commit o despliegue.
---

# Workflow: Auditoría Actor-Crítico de la Plataforma

## Pasos de Ejecución
1. Identificar los archivos creados o modificados en la fase actual. El modo `sdlc-auditor-critic` es de solo lectura y no tiene `execute`, por lo que no puede correr `git status` / `git diff`. Usar en su lugar `list_files`, `glob` y `grep` sobre `oracle/`, `etl/`, `simulator/`, `superset/`, `docker-compose.yml` y `.env.example`, o pedir al humano la lista de cambios (salida de `git status` / `git diff --name-only`).
2. Lanzar en paralelo hasta 3 subagentes de tipo `explore` con contexto limpio:
   - **Subagente A (Seguridad & Licencias):** Audita `.env`, `docker-compose.yml`, `Dockerfiles` y scripts Python/SQL contra `.bob/rules/02-licensing-oracle-guardrails.md` y `.bob/rules/03-security-and-secrets.md`.
   - **Subagente B (Integridad Kimball & Oracle):** Audita `oracle/` y `etl/` contra `.bob/rules/01-kimball-architecture.md` verificando ausencia de joins Fact-to-Fact y presencia de *Quality Screens*.
   - **Subagente C (Cobertura Funcional BI):** Compara los Virtual Datasets de `superset/assets/` y el simulador contra los 7 bloques visuales de `@docs/Draft-dashboard-TMS.pdf` (ver `.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md`).
3. Consolidar los hallazgos en `docs/audits/audit-fase-<N>.md` clasificando por severidad (`BLOCKER`, `HIGH`, `MEDIUM`, `LOW`).
4. Si existe cualquier `BLOCKER`, detener la promoción y generar la lista de tareas (`Todo`) para remediación inmediata por el modo Actor correspondiente.

## Notas
- El esquema de URL `redis://` apuntando a Valkey es válido. Solo es hallazgo una imagen `redis:*` (ver regla 02).
