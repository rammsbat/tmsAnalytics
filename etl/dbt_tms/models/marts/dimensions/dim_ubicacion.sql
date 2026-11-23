{#- ST-8: DIM_UBICACION (SCD1, MERGE por CODIGO_UBICACION; SK IDENTITY). Base de los roles Origen/Destino/Parada (vistas de BI_SEMANTIC). -#}
{{ config(alias='DIM_UBICACION', unique_key='CODIGO_UBICACION') }}
select
    CODIGO_UBICACION    as CODIGO_UBICACION,
    NOMBRE_UBICACION    as NOMBRE_UBICACION,
    CODIGO_POSTAL       as CODIGO_POSTAL,
    ESTADO              as ESTADO,
    MUNICIPIO           as MUNICIPIO,
    LATITUD             as LATITUD,
    LONGITUD            as LONGITUD,
    TIPO_UBICACION      as TIPO_UBICACION
from {{ ref('cat_ubicaciones') }}
