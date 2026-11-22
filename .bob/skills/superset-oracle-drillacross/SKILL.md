---
name: superset-oracle-drillacross
description: Crea Virtual Datasets con Jinja Templating para consultas Drill-Across en Oracle, configura el bootstrap de Apache Superset y mapea todos los componentes del Draft Dashboard TMS.
---

# Workflow: Implementación Analítica en Apache Superset

## Inventario de Componentes a Cubrir (Draft Dashboard TMS)
Los nombres de bloque siguen el PDF `@docs/Draft-dashboard-TMS.pdf`. El detalle de KPIs y valores de conciliación está en `checklists/draft_dashboard_kpis.md`.
1. **Indicadores Diarios de Flota (KPIs + Dona):** Unidades C/Viaje, S/Viaje, Inactivas, Total (fuente: `FACT_SNAPSHOT_FLOTA_DIARIO`).
2. **Indicadores de Operación (Día vs. Mes):** Despachos, Cierres, Liq. Casetas, Liq. Operador, CFDI de Traslado, Facturados.
3. **Indicadores Generales (Día vs. Mes):** Total Kms, Rendimiento Kms/kWh, Pago Casetas, Pago Operadores, Facturado ($).
4. **Top 5 Despachos / Cliente (Día vs. Mes).**
5. **Gráfica Facturación por Unidad (Top 10).**
6. **Tabla Productividad de las Unidades (Mes):** Consulta *Drill-Across* (Despacho + Carga + Facturación + Gastos).
7. **Tabla Productividad de los Operadores (Mes):** Consulta *Drill-Across* por Operador.

## Pasos de Ejecución
1. Configurar `superset/superset_config.py`:
   - `FEATURE_FLAGS = {"ENABLE_TEMPLATE_PROCESSING": True, "ALERT_REPORTS": True}`
   - `SQLALCHEMY_DATABASE_URI` apuntando a `superset-db` (PostgreSQL).
   - `CACHE_CONFIG` y `CELERY_BROKER_URL` apuntando a `redis://superset-valkey:6379/...`.
2. **Coordinar** con el modo `docker-platform-eng` el registro automático de la conexión `Analytics_TMS_Oracle` en `superset/bootstrap.sh` (este modo no puede editar ese archivo), usando `oracle+oracledb://BI_READER:${BI_READER_PWD}@oracle-dw:1521/?service_name=FREEPDB1`. Verificar después que la conexión exista y use `BI_READER`.
3. Generar en `superset/assets/datasets/` los SQL de los Virtual Datasets usando macros Jinja:
   - Usar `{% if from_dttm %}` y `{% if to_dttm %}` dentro de cada CTE para hacer *filter pushdown* en Oracle antes del `FULL OUTER JOIN`.
   - Proteger divisiones por cero (`NULLIF(SUM(kms_total), 0)`).
4. Documentar en `superset/assets/dashboard_mapping.md` la relación exacta entre cada Chart, su Dataset, sus filtros nativos y su métrica equivalente en `@docs/Draft-dashboard-TMS.pdf`.
