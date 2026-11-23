{#- ST-7: FISCAL_CFDI_CARTAPORTE. Vehiculo/remolque/operador del viaje vienen de OP_VIAJES_DESPACHO (misma fuente de verdad). -#}
{{ config(alias='FISCAL_CFDI_CARTAPORTE', unique_key='UUID_CCP') }}
select
    c.UUID_CCP                      as UUID_CCP,
    c.FOLIO_DOCUMENTO               as FOLIO_DOCUMENTO,
    c.SERIE                         as SERIE,
    c.FECHA_EMISION                 as FECHA_EMISION,
    vj.ID_VIAJE                     as ID_VIAJE,
    c.NUMERO_TALON                  as NUMERO_TALON,
    cr.ID_CLIENTE                   as ID_CLIENTE_REMITENTE,
    cd.ID_CLIENTE                   as ID_CLIENTE_DESTINATARIO,
    v.ID_VEHICULO                   as ID_VEHICULO,
    vj.ID_REMOLQUE                  as ID_REMOLQUE,
    vj.ID_OPERADOR                  as ID_OPERADOR,
    uo.ID_UBICACION                 as ID_ORIGEN_UBICACION,
    ud.ID_UBICACION                 as ID_DESTINO_UBICACION,
    p.ID_POLIZA                     as ID_POLIZA,
    c.DISTANCIA_DECLARADA_KM        as DISTANCIA_DECLARADA_KM,
    c.PESO_BRUTO_TOTAL_KG           as PESO_BRUTO_TOTAL_KG,
    c.NUMERO_TOTAL_MERCANCIAS       as NUMERO_TOTAL_MERCANCIAS,
    c.USO_CFDI                      as USO_CFDI,
    c.MONEDA                        as MONEDA,
    c.BATCH_ID                      as BATCH_ID
from {{ ref('stg_carta_porte_cabecera') }} c
left join {{ ref('op_viajes_despacho') }} vj  on vj.NUMERO_TALON = c.NUMERO_TALON
left join {{ ref('cat_clientes') }} cr        on cr.RFC_CLIENTE = c.RFC_REMITENTE
left join {{ ref('cat_clientes') }} cd        on cd.RFC_CLIENTE = c.RFC_DESTINATARIO
left join {{ ref('cat_vehiculos') }} v        on v.CODIGO_ECO = c.CODIGO_ECO
left join {{ ref('cat_ubicaciones') }} uo     on uo.CODIGO_UBICACION = c.UBICACION_ORIGEN_CP
left join {{ ref('cat_ubicaciones') }} ud     on ud.CODIGO_UBICACION = c.UBICACION_DESTINO_CP
left join {{ ref('cat_polizas_seguro') }} p   on p.NUMERO_POLIZA = c.POLIZA_RESP_CIVIL
