{#- stg_cfdi_ingreso: ultima version por UUID_INGRESO (D7). RFC en mayusculas y sin espacios. -#}
with src as (
    select
        {{ clean_code('UUID_INGRESO') }}                as UUID_INGRESO,
        {{ clean_code('FACTURA_ID') }}                  as FACTURA_ID,
        {{ clean_code('SERIE') }}                       as SERIE,
        cast(FECHA_FACTURA as timestamp)                as FECHA_FACTURA,
        {{ clean_code('NUMERO_TALON') }}                as NUMERO_TALON,
        {{ clean_rfc('RFC_EMISOR') }}                   as RFC_EMISOR,
        {{ clean_rfc('RFC_RECEPTOR') }}                 as RFC_RECEPTOR,
        {{ clean_text('RAZON_SOCIAL_RECEPTOR') }}       as RAZON_SOCIAL_RECEPTOR,
        {{ clean_code('USO_CFDI') }}                    as USO_CFDI,
        {{ clean_code('REGIMEN_FISCAL_RECEPTOR') }}     as REGIMEN_FISCAL_RECEPTOR,
        coalesce({{ clean_code('MONEDA') }}, 'MXN')     as MONEDA,
        coalesce(TIPO_CAMBIO, 1)                        as TIPO_CAMBIO,
        coalesce(IMPORTE_SUBTOTAL, 0)                   as IMPORTE_SUBTOTAL,
        coalesce(IMPORTE_DESCUENTO, 0)                  as IMPORTE_DESCUENTO,
        coalesce(IMPORTE_IVA_TRASLADADO, 0)             as IMPORTE_IVA_TRASLADADO,
        coalesce(IMPORTE_IVA_RETENIDO, 0)               as IMPORTE_IVA_RETENIDO,
        coalesce(IMPORTE_TOTAL, 0)                      as IMPORTE_TOTAL,
        {{ clean_code('METODO_PAGO') }}                 as METODO_PAGO,
        {{ clean_code('FORMA_PAGO') }}                  as FORMA_PAGO,
        {{ clean_code('ESTATUS_FACTURA') }}             as ESTATUS_FACTURA,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_cfdi_ingreso') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by UUID_INGRESO
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    UUID_INGRESO, FACTURA_ID, SERIE, FECHA_FACTURA, NUMERO_TALON, RFC_EMISOR, RFC_RECEPTOR,
    RAZON_SOCIAL_RECEPTOR, USO_CFDI, REGIMEN_FISCAL_RECEPTOR, MONEDA, TIPO_CAMBIO,
    IMPORTE_SUBTOTAL, IMPORTE_DESCUENTO, IMPORTE_IVA_TRASLADADO, IMPORTE_IVA_RETENIDO,
    IMPORTE_TOTAL, METODO_PAGO, FORMA_PAGO, ESTATUS_FACTURA, BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
