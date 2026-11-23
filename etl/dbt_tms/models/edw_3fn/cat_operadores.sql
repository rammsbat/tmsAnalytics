{#- ST-7: CAT_OPERADORES. TrackIt aporta el codigo; nombre/RFC/licencia salen de la Carta Porte del mismo talon. -#}
{{ config(alias='CAT_OPERADORES', unique_key='CODIGO_OPERADOR') }}
with ranked as (
    select
        d.CODIGO_OPERADOR,
        c.NOMBRE_OPERADOR,
        c.RFC_OPERADOR,
        c.LICENCIA_OPERADOR,
        d.BATCH_ID,
        row_number() over (
            partition by d.CODIGO_OPERADOR
            order by d.INGESTED_AT desc, d.BATCH_ID desc
        ) as RN
    from {{ ref('stg_trackit_despacho') }} d
    left join {{ ref('stg_carta_porte_cabecera') }} c
        on c.NUMERO_TALON = d.TALON_FOLIO
)
select
    CODIGO_OPERADOR                                 as CODIGO_OPERADOR,
    coalesce(NOMBRE_OPERADOR, CODIGO_OPERADOR)      as NOMBRE_OPERADOR,
    RFC_OPERADOR                                    as RFC_OPERADOR,
    coalesce(LICENCIA_OPERADOR, 'DESCONOCIDO')      as NUMERO_LICENCIA,
    BATCH_ID                                        as BATCH_ID
from ranked
where RN = 1
