{#- ST-7: FISCAL_CFDI_INGRESO. Un CFDI por viaje cerrado (A4); el cliente es el receptor (RFC). -#}
{{ config(alias='FISCAL_CFDI_INGRESO', unique_key='UUID_INGRESO') }}
select
    i.UUID_INGRESO                  as UUID_INGRESO,
    i.FACTURA_ID                    as FACTURA_ID,
    i.SERIE                         as SERIE,
    i.FECHA_FACTURA                 as FECHA_FACTURA,
    vj.ID_VIAJE                     as ID_VIAJE,
    i.NUMERO_TALON                  as NUMERO_TALON,
    c.ID_CLIENTE                    as ID_CLIENTE,
    i.RFC_EMISOR                    as RFC_EMISOR,
    i.RFC_RECEPTOR                  as RFC_RECEPTOR,
    i.USO_CFDI                      as USO_CFDI,
    i.REGIMEN_FISCAL_RECEPTOR       as REGIMEN_FISCAL_RECEPTOR,
    i.MONEDA                        as MONEDA,
    i.TIPO_CAMBIO                   as TIPO_CAMBIO,
    i.IMPORTE_SUBTOTAL              as IMPORTE_SUBTOTAL,
    i.IMPORTE_DESCUENTO             as IMPORTE_DESCUENTO,
    i.IMPORTE_IVA_TRASLADADO        as IMPORTE_IVA_TRASLADADO,
    i.IMPORTE_IVA_RETENIDO          as IMPORTE_IVA_RETENIDO,
    i.IMPORTE_TOTAL                 as IMPORTE_TOTAL,
    i.METODO_PAGO                   as METODO_PAGO,
    i.FORMA_PAGO                    as FORMA_PAGO,
    i.ESTATUS_FACTURA               as ESTATUS_FACTURA,
    i.BATCH_ID                      as BATCH_ID
from {{ ref('stg_cfdi_ingreso') }} i
left join {{ ref('op_viajes_despacho') }} vj on vj.NUMERO_TALON = i.NUMERO_TALON
left join {{ ref('cat_clientes') }} c        on c.RFC_CLIENTE = i.RFC_RECEPTOR
