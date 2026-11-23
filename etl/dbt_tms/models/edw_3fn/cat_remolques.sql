{#- ST-7: CAT_REMOLQUES. TrackIt aporta el codigo (CAJAnn); la placa sale de la Carta Porte del mismo talon. -#}
{{ config(alias='CAT_REMOLQUES', unique_key='NUMERO_ECONOMICO_REMOLQUE') }}
with ranked as (
    select
        d.CODIGO_REMOLQUE,
        c.PLACA_REMOLQUE,
        d.BATCH_ID,
        row_number() over (
            partition by d.CODIGO_REMOLQUE
            order by d.INGESTED_AT desc, d.BATCH_ID desc
        ) as RN
    from {{ ref('stg_trackit_despacho') }} d
    left join {{ ref('stg_carta_porte_cabecera') }} c
        on c.NUMERO_TALON = d.TALON_FOLIO
    where d.CODIGO_REMOLQUE is not null
)
select
    CODIGO_REMOLQUE                                 as NUMERO_ECONOMICO_REMOLQUE,
    coalesce(PLACA_REMOLQUE, 'DESCONOCIDO')         as PLACA_REMOLQUE,
    BATCH_ID                                        as BATCH_ID
from ranked
where RN = 1
