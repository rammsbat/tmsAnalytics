# Estándares Drill-Across y Jinja — Modo `bi-superset-dev`

Estas reglas complementan las reglas globales de `.bob/rules/`. Fuentes: `docs/IBM_BOB_SDLC_ANALYTICS_TMS_SPEC.md` §4.2, §5.5 y `docs/Arquitectura-dw-analytics-tms.docx` §7.

## 1. Patrón Drill-Across

- Una consulta (CTE) por tabla de hechos, agregada al nivel de la dimensión conformada compartida (por ejemplo, vehículo y mes).
- Unir los CTE con `FULL OUTER JOIN` sobre los atributos de dimensión conformada. Nunca unir tablas de hechos entre sí en un mismo `FROM/JOIN` (ver `.bob/rules/01-kimball-architecture.md`).
- Esto evita fan traps y productos cartesianos en las tablas Productividad de las Unidades y de los Operadores.
- Ejemplo de CTE nombrados en el docx §7: `Metricas_Despacho`, `Metricas_Facturacion` (y el de carga, desde `FACT_LINEAS_CARGA`), con joins a `DIM_VEHICULO` y `DIM_FECHA`.

## 2. Jinja y filter pushdown

- Requiere `ENABLE_TEMPLATE_PROCESSING: True` en `superset/superset_config.py`.
- Dentro de **cada** CTE, empujar los filtros de tiempo con `{% if from_dttm %}` y `{% if to_dttm %}`, antes del `FULL OUTER JOIN`. No filtrar solo en la consulta externa.
- Usar `filter_values(...)` para filtros de cliente u otras dimensiones, también dentro de cada CTE.

## 3. Seguridad y fuentes

- Las consultas apuntan solo a `BI_SEMANTIC` o `DWH_MART`, con el usuario `BI_READER` (solo lectura). Nunca a `EDW_3FN` ni a `STG_SRC`.
- La conexión de Superset se registra como `Analytics_TMS_Oracle`. Ese registro se hace en `superset/bootstrap.sh`, que edita `docker-platform-eng`, no este modo.

## 4. Robustez de cálculo

- Proteger toda división contra cero con `NULLIF`, por ejemplo `NULLIF(SUM(kms_total), 0)`.
- No usar `PARTITION BY` como cláusula de tabla ni `ENABLE QUERY REWRITE` (ver `.bob/rules/02-licensing-oracle-guardrails.md`). Las funciones analíticas `OVER (PARTITION BY ...)` dentro de un `SELECT` son distintas y están permitidas.

## 5. Trazabilidad con el Draft

- Cada componente visual se mapea al documento `docs/Draft-dashboard-TMS.pdf` y se documenta en `superset/assets/dashboard_mapping.md` (chart, dataset, filtros nativos y métrica equivalente).
- La lista de KPIs a cubrir está en `.bob/skills/superset-oracle-drillacross/checklists/draft_dashboard_kpis.md`.
