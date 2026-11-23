{#- ST-7: CAT_POLIZAS_SEGURO desde las polizas de STG_FLOTA_UNIDADES (una por NUMERO_POLIZA). -#}
{{ config(alias='CAT_POLIZAS_SEGURO', unique_key='NUMERO_POLIZA') }}
with ranked as (
    select
        f.*,
        row_number() over (
            partition by NUMERO_POLIZA_SEGURO
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from {{ ref('stg_flota_unidades') }} f
    where NUMERO_POLIZA_SEGURO is not null
)
select
    NUMERO_POLIZA_SEGURO                            as NUMERO_POLIZA,
    coalesce(ASEGURADORA, 'DESCONOCIDO')            as ASEGURADORA,
    coalesce(VIGENCIA_POLIZA, date '2099-12-31')    as VIGENCIA_HASTA,
    BATCH_ID                                        as BATCH_ID
from ranked
where RN = 1
