-- depends_on: {{ ref('sat_unidad_medida') }}
{#- ST-7: SAT_CONFIG_AUTOTRANSPORTE desde el seed (incluye C3R2). -#}
{{ config(alias='SAT_CONFIG_AUTOTRANSPORTE', unique_key='CLAVE_CONFIG_SAT') }}
select
    upper(trim(clave_config_sat))       as CLAVE_CONFIG_SAT,
    trim(descripcion_config)            as DESCRIPCION_CONFIG,
    numero_ejes                         as NUMERO_EJES,
    numero_llantas                      as NUMERO_LLANTAS,
    trim(remolque_permitido_flag)       as REMOLQUE_PERMITIDO_FLAG,
    'SEED-SAT-CONFIG-V1'                as BATCH_ID
from {{ ref('seed_sat_config_autotransporte') }}
