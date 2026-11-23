{#- stg_flota_estatus_diario: ultima version por (CODIGO_ECO, FECHA_CORTE) (D7). FECHA_CORTE normalizada a dia. -#}
with src as (
    select
        trunc(cast(FECHA_CORTE as date))                as FECHA_CORTE,
        {{ clean_code('CODIGO_ECO') }}                  as CODIGO_ECO,
        {{ clean_code('ESTATUS_PATIO') }}               as ESTATUS_PATIO,
        {{ clean_code('NUMERO_TALON') }}                as NUMERO_TALON,
        {{ clean_text('UBICACION_PATIO') }}             as UBICACION_PATIO,
        coalesce(KMS_ODOMETRO_DIA, 0)                   as KMS_ODOMETRO_DIA,
        coalesce(KWH_CONSUMO_DIA, 0)                    as KWH_CONSUMO_DIA,
        {{ clean_text('OBSERVACIONES') }}               as OBSERVACIONES,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_flota_estatus_diario') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by CODIGO_ECO, FECHA_CORTE
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    FECHA_CORTE, CODIGO_ECO, ESTATUS_PATIO, NUMERO_TALON, UBICACION_PATIO,
    KMS_ODOMETRO_DIA, KWH_CONSUMO_DIA, OBSERVACIONES, BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
