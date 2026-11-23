{#-
  stg_liquidaciones_gastos: ultima version por linea (FOLIO_LIQUIDACION, TIPO_GASTO, REFERENCIA_COMPROBANTE) (D7, H5).
  La tabla es atomica (varias casetas por folio); el grano de agregacion (folio, tipo) se resuelve en el mart.
-#}
with src as (
    select
        {{ clean_code('FOLIO_LIQUIDACION') }}           as FOLIO_LIQUIDACION,
        cast(FECHA_LIQUIDACION as timestamp)            as FECHA_LIQUIDACION,
        {{ clean_code('NUMERO_TALON') }}                as NUMERO_TALON,
        {{ clean_code('CODIGO_ECO') }}                  as CODIGO_ECO,
        {{ clean_code('CODIGO_REMOLQUE') }}             as CODIGO_REMOLQUE,
        {{ clean_code('CODIGO_OPERADOR') }}             as CODIGO_OPERADOR,
        {{ clean_code('TIPO_GASTO') }}                  as TIPO_GASTO,
        {{ clean_code('SUBTIPO_GASTO') }}               as SUBTIPO_GASTO,
        coalesce(IMPORTE_GASTO, 0)                      as IMPORTE_GASTO,
        {{ clean_text('REFERENCIA_COMPROBANTE') }}      as REFERENCIA_COMPROBANTE,
        {{ clean_code('ESTATUS_LIQUIDACION') }}         as ESTATUS_LIQUIDACION,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_liquidaciones_gastos') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by FOLIO_LIQUIDACION, TIPO_GASTO, REFERENCIA_COMPROBANTE
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    FOLIO_LIQUIDACION, FECHA_LIQUIDACION, NUMERO_TALON, CODIGO_ECO, CODIGO_REMOLQUE,
    CODIGO_OPERADOR, TIPO_GASTO, SUBTIPO_GASTO, IMPORTE_GASTO, REFERENCIA_COMPROBANTE,
    ESTATUS_LIQUIDACION, BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
