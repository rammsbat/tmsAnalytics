{#- ST-7: OP_VIAJES_PARADAS. Llave de MERGE (ID_VIAJE, NUMERO_SECUENCIA) = UQ del DDL. -#}
{{ config(alias='OP_VIAJES_PARADAS', unique_key=['ID_VIAJE', 'NUMERO_SECUENCIA']) }}
select
    vj.ID_VIAJE                     as ID_VIAJE,
    p.TALON_FOLIO                   as NUMERO_TALON,
    p.NUMERO_SECUENCIA              as NUMERO_SECUENCIA,
    u.ID_UBICACION                  as ID_UBICACION,
    p.TIPO_EVENTO                   as TIPO_EVENTO,
    p.FECHA_HORA_PROGRAMADA         as FECHA_HORA_PROGRAMADA,
    p.FECHA_HORA_LLEGADA_REAL       as FECHA_HORA_LLEGADA_REAL,
    p.FECHA_HORA_SALIDA_REAL        as FECHA_HORA_SALIDA_REAL,
    p.UNIDAD_EMBARQUE_UE            as UNIDAD_EMBARQUE_UE,
    p.KMS_TRAMO                     as KMS_TRAMO,
    p.LAG_LLEGADA_MINUTOS           as LAG_LLEGADA_MINUTOS,
    p.LAG_SALIDA_MINUTOS            as LAG_SALIDA_MINUTOS,
    p.TIEMPO_ESTADIA_MINUTOS        as TIEMPO_ESTADIA_MINUTOS,
    p.ESTATUS_PARADA                as ESTATUS_PARADA,
    p.BATCH_ID                      as BATCH_ID
from {{ ref('stg_trackit_paradas') }} p
left join {{ ref('op_viajes_despacho') }} vj on vj.NUMERO_TALON = p.TALON_FOLIO
left join {{ ref('cat_ubicaciones') }} u     on u.CODIGO_UBICACION = p.CODIGO_UBICACION
