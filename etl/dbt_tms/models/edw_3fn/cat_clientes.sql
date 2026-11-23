{#-
  ST-7: CAT_CLIENTES por RFC. Fuentes: remitente/destinatario de Carta Porte y receptor de CFDI Ingreso.
  Verificado en ST-6/ST-7: nombre<->RFC es 1:1 en STG, por lo que el cliente de TrackIt (solo nombre)
  se resuelve despues por RAZON_SOCIAL.
-#}
{{ config(alias='CAT_CLIENTES', unique_key='RFC_CLIENTE') }}
with ccp as (
    select * from {{ ref('stg_carta_porte_cabecera') }}
),

cfdi as (
    select
        RFC_RECEPTOR, RAZON_SOCIAL_RECEPTOR, REGIMEN_FISCAL_RECEPTOR, USO_CFDI, INGESTED_AT, BATCH_ID,
        row_number() over (partition by RFC_RECEPTOR order by INGESTED_AT desc, BATCH_ID desc) as RN
    from {{ ref('stg_cfdi_ingreso') }}
),

parties as (
    select RFC_REMITENTE as RFC, NOMBRE_REMITENTE as NOMBRE, INGESTED_AT, BATCH_ID from ccp
    union all
    select RFC_DESTINATARIO, NOMBRE_DESTINATARIO, INGESTED_AT, BATCH_ID from ccp
    union all
    select RFC_RECEPTOR, RAZON_SOCIAL_RECEPTOR, INGESTED_AT, BATCH_ID from cfdi where RN = 1
),

ranked as (
    select
        p.*,
        row_number() over (partition by RFC order by INGESTED_AT desc, BATCH_ID desc) as RN
    from parties p
)

select
    p.RFC                                                   as RFC_CLIENTE,
    coalesce(p.NOMBRE, c.RAZON_SOCIAL_RECEPTOR, p.RFC)      as RAZON_SOCIAL,
    c.REGIMEN_FISCAL_RECEPTOR                               as REGIMEN_FISCAL,
    coalesce(c.USO_CFDI, 'G03')                             as USO_CFDI_HABITUAL,
    p.BATCH_ID                                              as BATCH_ID
from ranked p
left join cfdi c
    on c.RFC_RECEPTOR = p.RFC and c.RN = 1
where p.RN = 1
