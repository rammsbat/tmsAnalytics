{#- stg_carta_porte_cabecera: ultima version por UUID_CCP (D7). RFC en mayusculas y sin espacios. -#}
with src as (
    select
        {{ clean_code('UUID_CCP') }}                    as UUID_CCP,
        {{ clean_code('FOLIO_DOCUMENTO') }}             as FOLIO_DOCUMENTO,
        {{ clean_code('SERIE') }}                       as SERIE,
        cast(FECHA_EMISION as timestamp)                as FECHA_EMISION,
        {{ clean_code('NUMERO_TALON') }}                as NUMERO_TALON,
        {{ clean_rfc('RFC_REMITENTE') }}                as RFC_REMITENTE,
        {{ clean_text('NOMBRE_REMITENTE') }}            as NOMBRE_REMITENTE,
        {{ clean_rfc('RFC_DESTINATARIO') }}             as RFC_DESTINATARIO,
        {{ clean_text('NOMBRE_DESTINATARIO') }}         as NOMBRE_DESTINATARIO,
        {{ clean_code('CODIGO_ECO') }}                  as CODIGO_ECO,
        {{ clean_code('PLACA_VEHICULO') }}              as PLACA_VEHICULO,
        {{ clean_code('CONFIGURACION_SAT') }}           as CONFIGURACION_SAT,
        {{ clean_code('NUMERO_REMOLQUE') }}             as NUMERO_REMOLQUE,
        {{ clean_code('PLACA_REMOLQUE') }}              as PLACA_REMOLQUE,
        {{ clean_rfc('RFC_OPERADOR') }}                 as RFC_OPERADOR,
        {{ clean_text('NOMBRE_OPERADOR') }}             as NOMBRE_OPERADOR,
        {{ clean_text('LICENCIA_OPERADOR') }}           as LICENCIA_OPERADOR,
        {{ clean_text('UBICACION_ORIGEN_CP') }}         as UBICACION_ORIGEN_CP,
        {{ clean_text('UBICACION_DESTINO_CP') }}        as UBICACION_DESTINO_CP,
        coalesce(DISTANCIA_DECLARADA_KM, 0)             as DISTANCIA_DECLARADA_KM,
        coalesce(PESO_BRUTO_TOTAL_KG, 0)                as PESO_BRUTO_TOTAL_KG,
        coalesce(NUMERO_TOTAL_MERCANCIAS, 0)            as NUMERO_TOTAL_MERCANCIAS,
        {{ clean_code('USO_CFDI') }}                    as USO_CFDI,
        {{ clean_code('MONEDA') }}                      as MONEDA,
        {{ clean_text('POLIZA_RESP_CIVIL') }}           as POLIZA_RESP_CIVIL,
        {{ clean_text('ASEGURADORA_RESP_CIVIL') }}      as ASEGURADORA_RESP_CIVIL,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_carta_porte_cabecera') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by UUID_CCP
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    UUID_CCP, FOLIO_DOCUMENTO, SERIE, FECHA_EMISION, NUMERO_TALON,
    RFC_REMITENTE, NOMBRE_REMITENTE, RFC_DESTINATARIO, NOMBRE_DESTINATARIO,
    CODIGO_ECO, PLACA_VEHICULO, CONFIGURACION_SAT, NUMERO_REMOLQUE, PLACA_REMOLQUE,
    RFC_OPERADOR, NOMBRE_OPERADOR, LICENCIA_OPERADOR, UBICACION_ORIGEN_CP, UBICACION_DESTINO_CP,
    DISTANCIA_DECLARADA_KM, PESO_BRUTO_TOTAL_KG, NUMERO_TOTAL_MERCANCIAS,
    USO_CFDI, MONEDA, POLIZA_RESP_CIVIL, ASEGURADORA_RESP_CIVIL,
    BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
