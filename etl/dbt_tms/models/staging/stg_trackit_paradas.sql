{#- stg_trackit_paradas: ultima version por (TALON_FOLIO, NUMERO_SECUENCIA) (D7). -#}
with src as (
    select
        {{ clean_code('TALON_FOLIO') }}                 as TALON_FOLIO,
        NUMERO_SECUENCIA,
        {{ clean_code('CODIGO_UBICACION') }}            as CODIGO_UBICACION,
        {{ clean_text('NOMBRE_UBICACION') }}            as NOMBRE_UBICACION,
        {{ clean_code('TIPO_EVENTO') }}                 as TIPO_EVENTO,
        cast(FECHA_HORA_PROGRAMADA as timestamp)        as FECHA_HORA_PROGRAMADA,
        cast(FECHA_HORA_LLEGADA_REAL as timestamp)      as FECHA_HORA_LLEGADA_REAL,
        cast(FECHA_HORA_SALIDA_REAL as timestamp)       as FECHA_HORA_SALIDA_REAL,
        {{ clean_code('UNIDAD_EMBARQUE_UE') }}          as UNIDAD_EMBARQUE_UE,
        coalesce(KMS_TRAMO, 0)                          as KMS_TRAMO,
        coalesce(LAG_LLEGADA_MINUTOS, 0)                as LAG_LLEGADA_MINUTOS,
        coalesce(LAG_SALIDA_MINUTOS, 0)                 as LAG_SALIDA_MINUTOS,
        coalesce(TIEMPO_ESTADIA_MINUTOS, 0)             as TIEMPO_ESTADIA_MINUTOS,
        {{ clean_code('ESTATUS_PARADA') }}              as ESTATUS_PARADA,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_trackit_paradas') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by TALON_FOLIO, NUMERO_SECUENCIA
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    TALON_FOLIO, NUMERO_SECUENCIA, CODIGO_UBICACION, NOMBRE_UBICACION, TIPO_EVENTO,
    FECHA_HORA_PROGRAMADA, FECHA_HORA_LLEGADA_REAL, FECHA_HORA_SALIDA_REAL,
    UNIDAD_EMBARQUE_UE, KMS_TRAMO, LAG_LLEGADA_MINUTOS, LAG_SALIDA_MINUTOS,
    TIEMPO_ESTADIA_MINUTOS, ESTATUS_PARADA, BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
