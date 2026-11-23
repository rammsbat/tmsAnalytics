{#- stg_trackit_despacho: ultima version por TALON_FOLIO (D7). Ephemeral: no crea objetos. -#}
with src as (
    select
        {{ clean_code('TALON_FOLIO') }}                 as TALON_FOLIO,
        cast(FECHA_DESPACHO as timestamp)               as FECHA_DESPACHO,
        {{ clean_text('HORA_DESPACHO') }}               as HORA_DESPACHO,
        {{ clean_code('CODIGO_ECO') }}                  as CODIGO_ECO,
        {{ clean_code('CODIGO_REMOLQUE') }}             as CODIGO_REMOLQUE,
        {{ clean_code('CODIGO_OPERADOR') }}             as CODIGO_OPERADOR,
        {{ clean_code('TAG_IAVE') }}                    as TAG_IAVE,
        {{ clean_text('CLIENTE_ORIGEN') }}              as CLIENTE_ORIGEN,
        {{ clean_text('CLIENTE_DESTINO') }}             as CLIENTE_DESTINO,
        ODOMETRO_INICIAL,
        ODOMETRO_FINAL,
        coalesce(KMS_CARGADO, 0)                        as KMS_CARGADO,
        coalesce(KMS_VACIO, 0)                          as KMS_VACIO,
        coalesce(KMS_TOTAL, 0)                          as KMS_TOTAL,
        BATERIA_INICIAL_PCT,
        BATERIA_FINAL_PCT,
        coalesce(KWH_CONSUMO, 0)                        as KWH_CONSUMO,
        coalesce(RENDIMIENTO_KMS_KWH, 0)                as RENDIMIENTO_KMS_KWH,
        coalesce(PESO_BRUTO_KG, 0)                      as PESO_BRUTO_KG,
        coalesce(TOTAL_PARADAS, 0)                      as TOTAL_PARADAS,
        {{ clean_code('ESTATUS_DESPACHO') }}            as ESTATUS_DESPACHO,
        cast(FECHA_CIERRE as timestamp)                 as FECHA_CIERRE,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_trackit_despacho') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by TALON_FOLIO
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    TALON_FOLIO, FECHA_DESPACHO, HORA_DESPACHO, CODIGO_ECO, CODIGO_REMOLQUE, CODIGO_OPERADOR,
    TAG_IAVE, CLIENTE_ORIGEN, CLIENTE_DESTINO, ODOMETRO_INICIAL, ODOMETRO_FINAL,
    KMS_CARGADO, KMS_VACIO, KMS_TOTAL, BATERIA_INICIAL_PCT, BATERIA_FINAL_PCT,
    KWH_CONSUMO, RENDIMIENTO_KMS_KWH, PESO_BRUTO_KG, TOTAL_PARADAS,
    ESTATUS_DESPACHO, FECHA_CIERRE, BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
