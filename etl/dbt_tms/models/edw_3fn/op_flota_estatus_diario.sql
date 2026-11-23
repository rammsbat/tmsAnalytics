{#- ST-7: OP_FLOTA_ESTATUS_DIARIO. Llave de MERGE (ID_VEHICULO, FECHA_CORTE) = UQ del DDL. -#}
{{ config(alias='OP_FLOTA_ESTATUS_DIARIO', unique_key=['ID_VEHICULO', 'FECHA_CORTE']) }}
select
    v.ID_VEHICULO               as ID_VEHICULO,
    e.FECHA_CORTE               as FECHA_CORTE,
    e.ESTATUS_PATIO             as ESTATUS_PATIO,
    vj.ID_VIAJE                 as ID_VIAJE,
    e.UBICACION_PATIO           as UBICACION_PATIO,
    e.KMS_ODOMETRO_DIA          as KMS_ODOMETRO_DIA,
    e.KWH_CONSUMO_DIA           as KWH_CONSUMO_DIA,
    e.OBSERVACIONES             as OBSERVACIONES,
    e.BATCH_ID                  as BATCH_ID
from {{ ref('stg_flota_estatus_diario') }} e
left join {{ ref('cat_vehiculos') }} v       on v.CODIGO_ECO = e.CODIGO_ECO
left join {{ ref('op_viajes_despacho') }} vj on vj.NUMERO_TALON = e.NUMERO_TALON
