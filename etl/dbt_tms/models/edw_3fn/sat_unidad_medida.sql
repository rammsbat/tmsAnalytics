{#- ST-7: SAT_UNIDAD_MEDIDA (PK natural, sin IDENTITY) desde el seed. Primero en el orden de FKs. -#}
{{ config(alias='SAT_UNIDAD_MEDIDA', unique_key='CLAVE_UNIDAD_SAT') }}
select
    upper(trim(clave_unidad_sat))   as CLAVE_UNIDAD_SAT,
    trim(nombre_unidad)             as NOMBRE_UNIDAD,
    trim(descripcion)               as DESCRIPCION,
    trim(simbolo)                   as SIMBOLO,
    'SEED-SAT-UNIDAD-V1'            as BATCH_ID
from {{ ref('seed_sat_unidad_medida') }}
