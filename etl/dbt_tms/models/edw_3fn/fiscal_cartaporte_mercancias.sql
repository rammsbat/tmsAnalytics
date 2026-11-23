-- depends_on: {{ ref('sat_producto_servicio') }}
-- depends_on: {{ ref('sat_unidad_medida') }}
{#- ST-7: FISCAL_CARTAPORTE_MERCANCIAS. Llave de MERGE (ID_CFDI_CCP, NUMERO_PARTIDA) = UQ del DDL. -#}
{{ config(alias='FISCAL_CARTAPORTE_MERCANCIAS', unique_key=['ID_CFDI_CCP', 'NUMERO_PARTIDA']) }}
select
    cc.ID_CFDI_CCP                  as ID_CFDI_CCP,
    m.NUMERO_PARTIDA                as NUMERO_PARTIDA,
    m.CLAVE_PRODUCTO_SAT            as CLAVE_PRODUCTO_SAT,
    m.DESCRIPCION_PRODUCTO_SAT      as DESCRIPCION_PRODUCTO_SAT,
    m.CANTIDAD                      as CANTIDAD,
    m.CLAVE_UNIDAD_SAT              as CLAVE_UNIDAD_SAT,
    m.PESO_KG                       as PESO_KG,
    m.MATERIAL_PELIGROSO_FLAG       as MATERIAL_PELIGROSO_FLAG,
    m.CLAVE_MATERIAL_PELIGROSO      as CLAVE_MATERIAL_PELIGROSO,
    m.EMBALAJE_SAT                  as EMBALAJE_SAT,
    m.UNIDAD_EMBARQUE_UE            as UNIDAD_EMBARQUE_UE,
    m.BATCH_ID                      as BATCH_ID
from {{ ref('stg_carta_porte_mercancias') }} m
left join {{ ref('fiscal_cfdi_cartaporte') }} cc on cc.UUID_CCP = m.UUID_CCP
