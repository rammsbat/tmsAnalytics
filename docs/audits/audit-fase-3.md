# Auditoría Actor-Crítico — Cierre de Fase 3 (Analytics TMS)

**Fecha:** 2026-11-23  
**Alcance:** Simulación de Datos Sintéticos (`simulator/`), Pipeline ETL dbt-oracle (`etl/dbt_tms/`), Esquema Kimball & Vistas Semánticas (`DWH_MART`, `BI_SEMANTIC`), Contenedores e Infraestructura (`docker-compose.yml`, Dockerfiles, `.env.example`).  
**Estado General:** **APROBADO SIN BLOQUEADORES (0 BLOCKERS)**

---

## 1. Resumen Ejecutivo de Conformidad

| Eje de Auditoría | Estado | Resumen |
|---|---|---|
| **Seguridad & Secretos (DevSecOps)** | ✅ Conforme | Cero secretos/passwords en código, `.env` fuera de Git, usuarios no-root (`appuser`, `superset`), red interna aislada (`tms-internal-net`), bind variables en Python/SQL, mínimo privilegio en roles Oracle (`BI_READER`, `SIM_WRITER`, `ETL_RUNNER`). |
| **Licenciamiento $0 & Oracle SE2** | ✅ Conforme | `valkey/valkey:8-alpine` (BSD-3) exclusivo (cero imágenes `redis:*`), compatibilidad Oracle SE2 estricta (sin `PARTITION BY`, sin `COMPRESS ADVANCED/OLTP`, sin `ENABLE QUERY REWRITE` en MVs), sin herramientas SaaS propietarias. |
| **Modelado Kimball & Arquitectura** | ✅ Conforme | Cero uniones Fact↔Fact (regla estricta verificada con test de grafo compilado), 10 dimensiones conformadas con fila dummy `-1` (`DESCONOCIDO`), Surrogate Keys enteras, lookup point-in-time en `DIM_VEHICULO` (SCD2), resolución de métricas atómicas en 6 hechos. |
| **Data Quality Screens** | ✅ Conforme | 404 tests dbt en verde (100 % PASS): Column Screens (`not_null`, `unique`, rangos físicos), Structure Screens (`relationships` completas, fila `-1`), Business Rule Screens (conciliaciones monetarias, balance de kilometraje, snapshot de flota diario 100 uds/día). |
| **Cobertura Draft Dashboard (BI)** | ✅ Conforme | Soporte completo para los 7 bloques del Draft Dashboard: filtros globales, KPIs ejecutivos, disponibilidad de flota (56/40/4 %), eficiencia energética, puntualidad y retrasos de paradas (tolerancia 15 min), matriz mensual Drill-Across de productividad ECO en `MV_PRODUCTIVIDAD_ECO_MENSUAL` y líneas de Carta Porte SAT. |

---

## 2. Hallazgos Clasificados por Severidad

### 🛑 BLOCKER (0 Hallazgos)
*Ninguno detectado.*

### 🟡 HIGH / OBSERVACIONES DE MANTENIMIENTO (0 Bloqueadores de Fase 3)
1. **Configuración de CSRF en Superset para Producción (`superset_config.py`):**
   - *Hallazgo:* En Fase 1 se configuró `WTF_CSRF_ENABLED = False` para facilitar bootstrap/pruebas en desarrollo local.
   - *Recomendación para Fase 4:* Al desplegar dashboards de producción en Superset, habilitar CSRF y Talisman.
2. **KPI Derivado de Emisiones CO2 Evitadas (Bloque 4):**
   - *Hallazgo:* El consumo eléctrico en kWh está modelado y conciliado en `FACT_DESPACHO_VIAJE` (`327,999.20 kWh`). Las emisiones evitadas se calcularán como métrica virtual en Superset (`kWh * 0.21 kg CO2/kWh`).

### 🔵 MEDIUM / LOW (Mejoras y Documentación)
1. **Documentación de no-aditividad de `DISTANCIA_DECLARADA_KM`:**
   - La distancia declarada se repite a nivel de partida de un mismo CCP (según DDL de Carta Porte); documentada explícitamente para evitar agregaciones indebidas en la capa semántica de Superset.
2. **Conservación de `LAG_SALIDA_MINUTOS` desde `EDW_3FN`:**
   - Documentado que no se recalcula en dbt debido a que la salida programada no se almacena en STG; valor conservado fielmente de EDW.

---

## 3. Certificación de Calidad y Criterio de Cierre

La suite de pruebas automatizadas dbt ejecuta **404 tests con 0 fallas (PASS=404/404)** y el refresco semántico mediante `SP_REFRESH_MV_SEMANTIC` se ejecuta exitosamente de forma atómica en el hook `on-run-end`. La infraestructura opera en contenedores autocontenidos sin volúmenes temporales de desarrollo.

**Veredicto:** Fase 3 lista para cierre y promoción a Fase 4 (Apache Superset Dashboards & Drill-Across Datasets).
