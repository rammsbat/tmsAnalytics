-- depends_on: {{ ref('sat_unidad_medida') }}
{#- ST-7: SAT_PRODUCTO_SERVICIO (FK a SAT_UNIDAD_MEDIDA) desde el seed. -#}
{{ config(alias='SAT_PRODUCTO_SERVICIO', unique_key='CLAVE_PRODUCTO_SAT') }}
select
    upper(trim(clave_producto_sat))     as CLAVE_PRODUCTO_SAT,
    trim(descripcion_producto)          as DESCRIPCION_PRODUCTO,
    trim(material_peligroso_flag)       as MATERIAL_PELIGROSO_FLAG,
    upper(trim(clave_unidad_defecto))   as CLAVE_UNIDAD_DEFECTO,
    'SEED-SAT-PRODUCTO-V1'              as BATCH_ID
from {{ ref('seed_sat_producto_servicio') }}
