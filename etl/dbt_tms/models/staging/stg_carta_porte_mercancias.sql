{#- stg_carta_porte_mercancias: ultima version por (UUID_CCP, NUMERO_PARTIDA) (D7). -#}
with src as (
    select
        {{ clean_code('UUID_CCP') }}                    as UUID_CCP,
        {{ clean_code('NUMERO_TALON') }}                as NUMERO_TALON,
        NUMERO_PARTIDA,
        {{ clean_code('CLAVE_PRODUCTO_SAT') }}          as CLAVE_PRODUCTO_SAT,
        {{ clean_text('DESCRIPCION_PRODUCTO_SAT') }}    as DESCRIPCION_PRODUCTO_SAT,
        coalesce(CANTIDAD, 1)                           as CANTIDAD,
        {{ clean_code('CLAVE_UNIDAD_SAT') }}            as CLAVE_UNIDAD_SAT,
        {{ clean_text('UNIDAD_SAT') }}                  as UNIDAD_SAT,
        coalesce(PESO_KG, 0)                            as PESO_KG,
        coalesce({{ clean_code('MATERIAL_PELIGROSO_FLAG') }}, '0') as MATERIAL_PELIGROSO_FLAG,
        {{ clean_code('CLAVE_MATERIAL_PELIGROSO') }}    as CLAVE_MATERIAL_PELIGROSO,
        {{ clean_code('EMBALAJE_SAT') }}                as EMBALAJE_SAT,
        {{ clean_code('UNIDAD_EMBARQUE_UE') }}          as UNIDAD_EMBARQUE_UE,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_carta_porte_mercancias') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by UUID_CCP, NUMERO_PARTIDA
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    UUID_CCP, NUMERO_TALON, NUMERO_PARTIDA, CLAVE_PRODUCTO_SAT, DESCRIPCION_PRODUCTO_SAT,
    CANTIDAD, CLAVE_UNIDAD_SAT, UNIDAD_SAT, PESO_KG, MATERIAL_PELIGROSO_FLAG,
    CLAVE_MATERIAL_PELIGROSO, EMBALAJE_SAT, UNIDAD_EMBARQUE_UE,
    BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
