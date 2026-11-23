-- depends_on: {{ ref('sat_unidad_medida') }}
{#- ST-7: SAT_TIPO_PERMISO desde el seed. -#}
{{ config(alias='SAT_TIPO_PERMISO', unique_key='CLAVE_TIPO_PERMISO') }}
select
    upper(trim(clave_tipo_permiso))     as CLAVE_TIPO_PERMISO,
    trim(descripcion_permiso)           as DESCRIPCION_PERMISO,
    'SEED-SAT-PERMISO-V1'               as BATCH_ID
from {{ ref('seed_sat_tipo_permiso') }}
