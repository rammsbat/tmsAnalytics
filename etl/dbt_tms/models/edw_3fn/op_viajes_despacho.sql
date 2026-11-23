{#- ST-7: OP_VIAJES_DESPACHO. FKs naturales -> IDs de EDW_3FN. Vehiculo/operador son NOT NULL: un lookup fallido falla ruidosamente (ORA-01400), no descarta filas. -#}
{{ config(alias='OP_VIAJES_DESPACHO', unique_key='NUMERO_TALON') }}
select
    d.TALON_FOLIO               as NUMERO_TALON,
    d.FECHA_DESPACHO            as FECHA_DESPACHO,
    d.HORA_DESPACHO             as HORA_DESPACHO,
    v.ID_VEHICULO               as ID_VEHICULO,
    r.ID_REMOLQUE               as ID_REMOLQUE,
    o.ID_OPERADOR               as ID_OPERADOR,
    co.ID_CLIENTE               as ID_CLIENTE_ORIGEN,
    cd.ID_CLIENTE               as ID_CLIENTE_DESTINO,
    d.TAG_IAVE                  as TAG_IAVE,
    d.ODOMETRO_INICIAL          as ODOMETRO_INICIAL,
    d.ODOMETRO_FINAL            as ODOMETRO_FINAL,
    d.KMS_CARGADO               as KMS_CARGADO,
    d.KMS_VACIO                 as KMS_VACIO,
    d.KMS_TOTAL                 as KMS_TOTAL,
    d.BATERIA_INICIAL_PCT       as BATERIA_INICIAL_PCT,
    d.BATERIA_FINAL_PCT         as BATERIA_FINAL_PCT,
    d.KWH_CONSUMO               as KWH_CONSUMO,
    d.RENDIMIENTO_KMS_KWH       as RENDIMIENTO_KMS_KWH,
    d.PESO_BRUTO_KG             as PESO_BRUTO_KG,
    d.TOTAL_PARADAS             as TOTAL_PARADAS,
    d.ESTATUS_DESPACHO          as ESTATUS_DESPACHO,
    d.FECHA_CIERRE              as FECHA_CIERRE,
    d.BATCH_ID                  as BATCH_ID
from {{ ref('stg_trackit_despacho') }} d
left join {{ ref('cat_vehiculos') }} v   on v.CODIGO_ECO = d.CODIGO_ECO
left join {{ ref('cat_remolques') }} r   on r.NUMERO_ECONOMICO_REMOLQUE = d.CODIGO_REMOLQUE
left join {{ ref('cat_operadores') }} o  on o.CODIGO_OPERADOR = d.CODIGO_OPERADOR
left join {{ ref('cat_clientes') }} co   on co.RAZON_SOCIAL = d.CLIENTE_ORIGEN
left join {{ ref('cat_clientes') }} cd   on cd.RAZON_SOCIAL = d.CLIENTE_DESTINO
