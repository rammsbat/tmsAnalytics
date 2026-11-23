{#-
  ST-9: FACT_SNAPSHOT_FLOTA_DIARIO (grano: 1 fila por vehiculo por dia; MERGE por (ID_FECHA_CORTE, ID_VEHICULO), UQ_FSNAP_FECHA_VEH).
  Universo = DIM_FECHA (rango de dias con estatus en EDW_3FN.OP_FLOTA_ESTATUS_DIARIO) x DIM_VEHICULO vigente ese dia:
    fecha BETWEEN FECHA_INICIO_VALIDEZ AND NVL(FECHA_FIN_VALIDEZ, 2099-12-31) y ID_VEHICULO <> -1 (A5).
  Una unidad con 2 versiones (SCD2) aporta exactamente 1 fila por dia: 100 filas por dia con 100 unidades.
  El estatus se une por CODIGO_ECO (no por la SK de la version) a EDW_3FN.OP_FLOTA_ESTATUS_DIARIO.
  KMS/KWH del dia salen de EDW_3FN (no de FACT_DESPACHO_VIAJE: sin Fact-to-Fact).
  Indicadores (A1): DISPONIBLE_CON_VIAJE -> con viaje; DISPONIBLE_SIN_VIAJE -> sin viaje; EN_MANTENIMIENTO/INACTIVO -> inactiva.
  Unidad-dia sin estatus en EDW: ESTATUS_UNIDAD = 'SIN_REPORTE' y los 3 indicadores en 0 (suma <> 1 -> lo detecta el screen).
-#}
{{ config(alias='FACT_SNAPSHOT_FLOTA_DIARIO', unique_key=['ID_FECHA_CORTE', 'ID_VEHICULO']) }}
with rango as (
    select min(trunc(FECHA_CORTE)) as F_INI, max(trunc(FECHA_CORTE)) as F_FIN
    from {{ ref('op_flota_estatus_diario') }}
),

universo as (
    select f.ID_FECHA, f.FECHA, v.ID_VEHICULO, v.CODIGO_ECO
    from {{ ref('dim_fecha') }} f
    join rango r on f.FECHA between r.F_INI and r.F_FIN
    join {{ ref('dim_vehiculo') }} v
        on  v.ID_VEHICULO <> -1
        and f.FECHA between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
    where f.ID_FECHA <> -1
)

select
    nvl(u.ID_FECHA, -1)                                             as ID_FECHA_CORTE,
    nvl(u.ID_VEHICULO, -1)                                          as ID_VEHICULO,
    nvl(e.ESTATUS_PATIO, 'SIN_REPORTE')                             as ESTATUS_UNIDAD,
    case when e.ESTATUS_PATIO = 'DISPONIBLE_CON_VIAJE' then 1 else 0 end                  as UNIDAD_CON_VIAJE_INDICADOR,
    case when e.ESTATUS_PATIO = 'DISPONIBLE_SIN_VIAJE' then 1 else 0 end                  as UNIDAD_SIN_VIAJE_INDICADOR,
    case when e.ESTATUS_PATIO in ('EN_MANTENIMIENTO', 'INACTIVO') then 1 else 0 end       as UNIDAD_INACTIVA_INDICADOR,
    1                                                               as FLOTA_TOTAL_INDICADOR,
    nvl(e.KMS_ODOMETRO_DIA, 0)                                      as KMS_RECORRIDOS_DIA,
    nvl(e.KWH_CONSUMO_DIA, 0)                                       as KWH_CONSUMO_DIA
from universo u
left join {{ ref('cat_vehiculos') }} cv           on cv.CODIGO_ECO = u.CODIGO_ECO
left join {{ ref('op_flota_estatus_diario') }} e
    on  e.ID_VEHICULO = cv.ID_VEHICULO
    and trunc(e.FECHA_CORTE) = u.FECHA
