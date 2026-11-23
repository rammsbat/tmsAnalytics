{#-
  stg_flota_unidades: estado ACTUAL por CODIGO_ECO (D7). Los cambios de placa llegan como nuevas
  versiones; aqui se conserva la mas reciente. FECHA_EFECTIVA = dia de INGESTED_AT de esa version
  (el simulador asigna INGESTED_AT = dia operativo del cambio 23:00 + run_seq, ver ST-3); ST-8 la usa
  como fecha efectiva del cierre/apertura SCD2 (P3).
-#}
with src as (
    select
        {{ clean_code('CODIGO_ECO') }}                  as CODIGO_ECO,
        {{ clean_code('TIPO_UNIDAD') }}                 as TIPO_UNIDAD,
        {{ clean_code('PLACA') }}                       as PLACA,
        ANIO_MODELO,
        {{ clean_text('MARCA') }}                       as MARCA,
        {{ clean_text('MODELO') }}                      as MODELO,
        {{ clean_code('CONFIGURACION_SAT') }}           as CONFIGURACION_SAT,
        {{ clean_code('TIPO_PERMISO_SCT') }}            as TIPO_PERMISO_SCT,
        {{ clean_text('NUMERO_PERMISO_SCT') }}          as NUMERO_PERMISO_SCT,
        PESO_BRUTO_MAX_KG,
        CAPACIDAD_CARGA_KG,
        {{ clean_code('NUMERO_SERIE_VIN') }}            as NUMERO_SERIE_VIN,
        {{ clean_code('NUMERO_MOTOR') }}                as NUMERO_MOTOR,
        {{ clean_code('NUMERO_POLIZA_SEGURO') }}        as NUMERO_POLIZA_SEGURO,
        {{ clean_text('ASEGURADORA') }}                 as ASEGURADORA,
        cast(VIGENCIA_POLIZA as date)                   as VIGENCIA_POLIZA,
        {{ clean_code('ESTATUS_INVENTARIO') }}          as ESTATUS_INVENTARIO,
        {{ clean_text('BATCH_ID') }}                    as BATCH_ID,
        INGESTED_AT,
        {{ clean_code('SOURCE_SYSTEM') }}               as SOURCE_SYSTEM
    from {{ source('stg_src', 'stg_flota_unidades') }}
),

ranked as (
    select
        src.*,
        row_number() over (
            partition by CODIGO_ECO
            order by INGESTED_AT desc, BATCH_ID desc
        ) as RN
    from src
)

select
    CODIGO_ECO, TIPO_UNIDAD, PLACA, ANIO_MODELO, MARCA, MODELO, CONFIGURACION_SAT,
    TIPO_PERMISO_SCT, NUMERO_PERMISO_SCT, PESO_BRUTO_MAX_KG, CAPACIDAD_CARGA_KG,
    NUMERO_SERIE_VIN, NUMERO_MOTOR, NUMERO_POLIZA_SEGURO, ASEGURADORA, VIGENCIA_POLIZA,
    ESTATUS_INVENTARIO,
    trunc(cast(INGESTED_AT as date))                    as FECHA_EFECTIVA,
    BATCH_ID, INGESTED_AT, SOURCE_SYSTEM
from ranked
where RN = 1
