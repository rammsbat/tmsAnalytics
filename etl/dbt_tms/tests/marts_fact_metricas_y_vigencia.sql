{#-
  ST-9 (H9 + A5): metricas de paradas y snapshot. Devuelve una fila por control incumplido.
    * LAG_LLEGADA / TIEMPO_ESTADIA recalculados desde timestamps = lo emitido por TrackIt en EDW_3FN (tolerancia 0.01 min);
      LAG_SALIDA se conserva de EDW (la salida programada no existe en STG).
    * CONTADOR_PUNTUAL coherente con la tolerancia de dbt_project.yml (var puntualidad_tolerancia_minutos).
    * Snapshot: exactamente 1 fila por (dia, unidad), n_unidades por dia = unidades vigentes ese dia en DIM_VEHICULO,
      indicadores con suma = 1 y sin estatus 'SIN_REPORTE'.
    * Lookup point-in-time: el ID_VEHICULO de cada hecho transaccional pertenece a una version de DIM_VEHICULO vigente a la
      fecha del evento (despacho / llegada o programada / emision CCP / despacho de la factura / liquidacion).
-#}
with paradas as (
    select 'PARADAS: LAG_LLEGADA recalculado <> EDW' as CONTROL, count(*) as N
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    where e.FECHA_HORA_LLEGADA_REAL is not null and abs(f.LAG_LLEGADA_MINUTOS - e.LAG_LLEGADA_MINUTOS) > 0.01
    union all
    select 'PARADAS: TIEMPO_ESTADIA recalculado <> EDW', count(*)
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    where e.FECHA_HORA_SALIDA_REAL is not null and abs(f.TIEMPO_ESTADIA_MINUTOS - e.TIEMPO_ESTADIA_MINUTOS) > 0.01
    union all
    select 'PARADAS: LAG_SALIDA <> EDW', count(*)
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    where e.FECHA_HORA_SALIDA_REAL is not null and abs(f.LAG_SALIDA_MINUTOS - e.LAG_SALIDA_MINUTOS) > 0.01
    union all
    select 'PARADAS: CONTADOR_PUNTUAL incoherente con la tolerancia', count(*)
    from {{ ref('fact_eventos_parada') }}
    where CONTADOR_PARADA = 1
      and CONTADOR_PUNTUAL <> case when LAG_LLEGADA_MINUTOS <= {{ var('puntualidad_tolerancia_minutos') | int }} then 1 else 0 end
),
snap_dia as (
    select ID_FECHA_CORTE,
           count(*) as FILAS,
           count(distinct ID_VEHICULO) as UNIDADES,
           sum(case when UNIDAD_CON_VIAJE_INDICADOR + UNIDAD_SIN_VIAJE_INDICADOR + UNIDAD_INACTIVA_INDICADOR = FLOTA_TOTAL_INDICADOR and FLOTA_TOTAL_INDICADOR = 1 then 0 else 1 end) as IND_MAL,
           sum(case when ESTATUS_UNIDAD = 'SIN_REPORTE' then 1 else 0 end) as SIN_REP
    from {{ ref('fact_snapshot_flota_diario') }}
    group by ID_FECHA_CORTE
),
snap_esperado as (
    select f.ID_FECHA, count(*) as VIGENTES
    from {{ ref('dim_fecha') }} f
    join {{ ref('dim_vehiculo') }} v
      on v.ID_VEHICULO <> -1
     and f.FECHA between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
    where f.ID_FECHA <> -1
    group by f.ID_FECHA
),
snap as (
    select 'SNAPSHOT: dia con filas <> unidades vigentes en DIM_VEHICULO' as CONTROL, count(*) as N
    from snap_dia s join snap_esperado e on e.ID_FECHA = s.ID_FECHA_CORTE
    where s.FILAS <> e.VIGENTES or s.FILAS <> s.UNIDADES
    union all
    select 'SNAPSHOT: dia con indicadores suma <> 1', count(*) from snap_dia where IND_MAL > 0
    union all
    select 'SNAPSHOT: dia con unidades SIN_REPORTE', count(*) from snap_dia where SIN_REP > 0
    union all
    select 'SNAPSHOT: dia sin 100 unidades (flota)', count(*) from snap_dia where FILAS <> 100
),
pit as (
    select 'PIT despacho: version no vigente a la fecha' as CONTROL, count(*) as N
    from {{ ref('fact_despacho_viaje') }} f
    join {{ ref('op_viajes_despacho') }} e on e.NUMERO_TALON = f.NUMERO_TALON
    join {{ ref('dim_vehiculo') }} v on v.ID_VEHICULO = f.ID_VEHICULO
    where trunc(e.FECHA_DESPACHO) not between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
    union all
    select 'PIT paradas: version no vigente a la fecha', count(*)
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    join {{ ref('dim_vehiculo') }} v on v.ID_VEHICULO = f.ID_VEHICULO
    where trunc(coalesce(e.FECHA_HORA_LLEGADA_REAL, e.FECHA_HORA_PROGRAMADA)) not between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
    union all
    select 'PIT lineas: version no vigente a la fecha', count(*)
    from {{ ref('fact_lineas_carga_cartaporte') }} f
    join {{ ref('fiscal_cfdi_cartaporte') }} e on e.UUID_CCP = f.UUID_CCP
    join {{ ref('dim_vehiculo') }} v on v.ID_VEHICULO = f.ID_VEHICULO
    where trunc(e.FECHA_EMISION) not between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
    union all
    select 'PIT facturacion: version no vigente al despacho', count(*)
    from {{ ref('fact_facturacion_flete') }} f
    join {{ ref('op_viajes_despacho') }} e on e.NUMERO_TALON = f.NUMERO_TALON
    join {{ ref('dim_vehiculo') }} v on v.ID_VEHICULO = f.ID_VEHICULO
    where trunc(e.FECHA_DESPACHO) not between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
    union all
    select 'PIT gastos: version no vigente a la fecha', count(*)
    from {{ ref('fact_gastos_liquidacion') }} f
    join (select FOLIO_LIQUIDACION, TIPO_GASTO, min(FECHA_LIQUIDACION) as FECHA_LIQUIDACION
            from {{ ref('op_liquidaciones_gastos') }} group by FOLIO_LIQUIDACION, TIPO_GASTO) e
      on e.FOLIO_LIQUIDACION = f.FOLIO_LIQ and e.TIPO_GASTO = f.TIPO_GASTO
    join {{ ref('dim_vehiculo') }} v on v.ID_VEHICULO = f.ID_VEHICULO
    where trunc(e.FECHA_LIQUIDACION) not between v.FECHA_INICIO_VALIDEZ and nvl(v.FECHA_FIN_VALIDEZ, date '2099-12-31')
)
select CONTROL, N from paradas where N > 0
union all select CONTROL, N from snap where N > 0
union all select CONTROL, N from pit where N > 0
