{#-
  ST-7: OP_LIQUIDACIONES_GASTOS conserva el detalle ATOMICO (H5). Llave de MERGE aprobada:
  (FOLIO_LIQUIDACION, TIPO_GASTO, REFERENCIA_COMPROBANTE). El agregado por (folio, tipo) vive en el mart.
-#}
{{ config(alias='OP_LIQUIDACIONES_GASTOS', unique_key=['FOLIO_LIQUIDACION', 'TIPO_GASTO', 'REFERENCIA_COMPROBANTE']) }}
select
    l.FOLIO_LIQUIDACION             as FOLIO_LIQUIDACION,
    l.FECHA_LIQUIDACION             as FECHA_LIQUIDACION,
    vj.ID_VIAJE                     as ID_VIAJE,
    l.NUMERO_TALON                  as NUMERO_TALON,
    v.ID_VEHICULO                   as ID_VEHICULO,
    r.ID_REMOLQUE                   as ID_REMOLQUE,
    o.ID_OPERADOR                   as ID_OPERADOR,
    l.TIPO_GASTO                    as TIPO_GASTO,
    l.SUBTIPO_GASTO                 as SUBTIPO_GASTO,
    l.IMPORTE_GASTO                 as IMPORTE_GASTO,
    l.REFERENCIA_COMPROBANTE        as REFERENCIA_COMPROBANTE,
    l.ESTATUS_LIQUIDACION           as ESTATUS_LIQUIDACION,
    l.BATCH_ID                      as BATCH_ID
from {{ ref('stg_liquidaciones_gastos') }} l
left join {{ ref('op_viajes_despacho') }} vj on vj.NUMERO_TALON = l.NUMERO_TALON
left join {{ ref('cat_vehiculos') }} v       on v.CODIGO_ECO = l.CODIGO_ECO
left join {{ ref('cat_remolques') }} r       on r.NUMERO_ECONOMICO_REMOLQUE = l.CODIGO_REMOLQUE
left join {{ ref('cat_operadores') }} o      on o.CODIGO_OPERADOR = l.CODIGO_OPERADOR
