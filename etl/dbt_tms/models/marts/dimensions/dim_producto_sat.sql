{#- ST-8: DIM_PRODUCTO_SAT (SCD1, MERGE por CLAVE_PRODUCTO_SAT; SK IDENTITY). Desnormaliza la unidad por defecto desde SAT_UNIDAD_MEDIDA. -#}
{{ config(alias='DIM_PRODUCTO_SAT', unique_key='CLAVE_PRODUCTO_SAT') }}
select
    p.CLAVE_PRODUCTO_SAT        as CLAVE_PRODUCTO_SAT,
    p.DESCRIPCION_PRODUCTO      as DESCRIPCION_SAT,
    p.MATERIAL_PELIGROSO_FLAG   as MATERIAL_PELIGROSO_FLAG,
    p.CLAVE_UNIDAD_DEFECTO      as CLAVE_UNIDAD_SAT,
    u.NOMBRE_UNIDAD             as NOMBRE_UNIDAD_SAT
from {{ ref('sat_producto_servicio') }} p
left join {{ ref('sat_unidad_medida') }} u
    on u.CLAVE_UNIDAD_SAT = p.CLAVE_UNIDAD_DEFECTO
