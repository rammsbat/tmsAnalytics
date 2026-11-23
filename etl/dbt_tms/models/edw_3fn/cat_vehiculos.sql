-- depends_on: {{ ref('sat_config_autotransporte') }}
-- depends_on: {{ ref('sat_tipo_permiso') }}
{#-
  ST-7: CAT_VEHICULOS (estado ACTUAL por CODIGO_ECO).
  UPDATED_AT = INGESTED_AT de la version vigente (NO SYSTIMESTAMP): propaga de forma determinista (D6) la fecha
  efectiva del cambio de placa para que DIM_VEHICULO (ST-8) derive FECHA_EFECTIVA = TRUNC(UPDATED_AT) desde
  EDW_3FN sin saltarse capas ni depender del reloj real. Tambien aplica al INSERT inicial.
-#}
{{ config(alias='CAT_VEHICULOS', unique_key='CODIGO_ECO') }}
select
    f.CODIGO_ECO                                        as CODIGO_ECO,
    f.PLACA                                             as PLACA,
    f.ANIO_MODELO                                       as ANIO_MODELO,
    f.MARCA                                             as MARCA,
    f.MODELO                                            as MODELO,
    f.CONFIGURACION_SAT                                 as CONFIGURACION_SAT,
    f.TIPO_PERMISO_SCT                                  as TIPO_PERMISO_SCT,
    f.NUMERO_PERMISO_SCT                                as NUMERO_PERMISO_SCT,
    coalesce(f.PESO_BRUTO_MAX_KG, 29685)                as PESO_BRUTO_MAX_KG,
    p.ID_POLIZA                                         as ID_POLIZA_SEGURO,
    f.ESTATUS_INVENTARIO                                as ESTATUS_OPERATIVO,
    f.INGESTED_AT                                       as UPDATED_AT,
    f.BATCH_ID                                          as BATCH_ID
from {{ ref('stg_flota_unidades') }} f
left join {{ ref('cat_polizas_seguro') }} p
    on p.NUMERO_POLIZA = f.NUMERO_POLIZA_SEGURO
