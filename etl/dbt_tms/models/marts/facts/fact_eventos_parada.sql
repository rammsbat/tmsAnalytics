{#-
  ST-9: FACT_EVENTOS_PARADA (grano: 1 fila por parada/hito; MERGE por (NUMERO_TALON, NUMERO_SECUENCIA), UQ_FPARADA_TALON_SEC).
  Metricas recalculadas desde los timestamps de EDW_3FN (H9):
    LAG_LLEGADA_MINUTOS    = llegada real - llegada programada          (recalculado)
    TIEMPO_ESTADIA_MINUTOS = salida real - llegada real                 (recalculado)
    LAG_SALIDA_MINUTOS     = tomado de EDW (TrackIt): la SALIDA programada no existe en STG/EDW (solo se persiste la
                             llegada programada), por lo que no es derivable de timestamps. Un test concilia ambos recalculos.
  Paradas abiertas (viajes EN_TRANSITO; H9):
    * PENDIENTE (sin llegada ni salida): ID_FECHA/HORA_LLEGADA y _SALIDA = -1; metricas = 0; CONTADOR_PARADA = 0 y
      CONTADOR_PUNTUAL = 0 (la parada aun no ocurrio: no entra en denominador ni numerador de puntualidad).
    * EN_CURSO (llego, no salio): llegada real conocida; ID_*_SALIDA = -1; LAG_SALIDA = 0 y ESTADIA = 0;
      CONTADOR_PARADA = 1 y puntualidad evaluada con la llegada.
    Estos -1 son LEGITIMOS ("evento aun no ocurrido"); el screen de ST-10 los concilia contra EDW_3FN.ESTATUS_PARADA.
  CONTADOR_PUNTUAL = 1 si LAG_LLEGADA_MINUTOS <= var puntualidad_tolerancia_minutos (adelantos cuentan como puntual).
  ID_VEHICULO: lookup point-in-time en DIM_VEHICULO a la fecha del evento (llegada real, o programada si no ha llegado).
-#}
{{ config(alias='FACT_EVENTOS_PARADA', unique_key=['NUMERO_TALON', 'NUMERO_SECUENCIA']) }}
with base as (
    select
        p.NUMERO_TALON,
        p.NUMERO_SECUENCIA,
        p.UNIDAD_EMBARQUE_UE,
        p.TIPO_EVENTO,
        p.FECHA_HORA_LLEGADA_REAL,
        p.FECHA_HORA_SALIDA_REAL,
        coalesce(p.FECHA_HORA_LLEGADA_REAL, p.FECHA_HORA_PROGRAMADA) as FECHA_EVENTO,
        nvl(p.KMS_TRAMO, 0) as KMS_TRAMO,
        case when p.FECHA_HORA_LLEGADA_REAL is not null
             then {{ minutes_between('p.FECHA_HORA_LLEGADA_REAL', 'p.FECHA_HORA_PROGRAMADA') }} end as LAG_LLEGADA,
        case when p.FECHA_HORA_SALIDA_REAL is not null
             then nvl(p.LAG_SALIDA_MINUTOS, 0) end as LAG_SALIDA,
        case when p.FECHA_HORA_SALIDA_REAL is not null and p.FECHA_HORA_LLEGADA_REAL is not null
             then {{ minutes_between('p.FECHA_HORA_SALIDA_REAL', 'p.FECHA_HORA_LLEGADA_REAL') }} end as ESTADIA,
        d.ID_VEHICULO as ID_VEHICULO_EDW,
        d.ID_OPERADOR as ID_OPERADOR_EDW,
        p.ID_UBICACION
    from {{ ref('op_viajes_paradas') }} p
    join {{ ref('op_viajes_despacho') }} d on d.ID_VIAJE = p.ID_VIAJE
)
select
    b.NUMERO_TALON                                                  as NUMERO_TALON,
    b.NUMERO_SECUENCIA                                              as NUMERO_SECUENCIA,
    b.UNIDAD_EMBARQUE_UE                                            as UNIDAD_EMBARQUE_UE,
    {{ dim_fecha_key('b.FECHA_HORA_LLEGADA_REAL') }}                as ID_FECHA_LLEGADA,
    {{ dim_hora_key('b.FECHA_HORA_LLEGADA_REAL') }}                 as ID_HORA_LLEGADA,
    {{ dim_fecha_key('b.FECHA_HORA_SALIDA_REAL') }}                 as ID_FECHA_SALIDA,
    {{ dim_hora_key('b.FECHA_HORA_SALIDA_REAL') }}                  as ID_HORA_SALIDA,
    nvl(dv.ID_VEHICULO, -1)                                         as ID_VEHICULO,
    nvl(dop.ID_OPERADOR, -1)                                        as ID_OPERADOR,
    nvl(du.ID_UBICACION, -1)                                        as ID_UBICACION_PARADA,
    b.TIPO_EVENTO                                                   as TIPO_EVENTO,
    b.KMS_TRAMO                                                     as KMS_TRAMO,
    nvl(b.LAG_LLEGADA, 0)                                           as LAG_LLEGADA_MINUTOS,
    nvl(b.LAG_SALIDA, 0)                                            as LAG_SALIDA_MINUTOS,
    nvl(b.ESTADIA, 0)                                               as TIEMPO_ESTADIA_MINUTOS,
    case when b.FECHA_HORA_LLEGADA_REAL is not null then 1 else 0 end as CONTADOR_PARADA,
    case when b.FECHA_HORA_LLEGADA_REAL is not null
          and b.LAG_LLEGADA <= {{ var('puntualidad_tolerancia_minutos') | int }} then 1 else 0 end as CONTADOR_PUNTUAL
from base b
join {{ ref('cat_vehiculos') }} cv       on cv.ID_VEHICULO = b.ID_VEHICULO_EDW
{{ vehiculo_asof_join('dv', 'cv.CODIGO_ECO', 'b.FECHA_EVENTO') }}
left join {{ ref('cat_operadores') }} co on co.ID_OPERADOR = b.ID_OPERADOR_EDW
left join {{ ref('dim_operador') }} dop  on dop.CODIGO_OPERADOR = co.CODIGO_OPERADOR and dop.ID_OPERADOR <> -1
left join {{ ref('cat_ubicaciones') }} cu on cu.ID_UBICACION = b.ID_UBICACION
left join {{ ref('dim_ubicacion') }} du  on du.CODIGO_UBICACION = cu.CODIGO_UBICACION and du.ID_UBICACION <> -1
