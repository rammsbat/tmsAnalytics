{#- ST-8: DIM_OPERADOR (SCD1, MERGE por llave natural; SK IDENTITY). -#}
{{ config(alias='DIM_OPERADOR', unique_key='CODIGO_OPERADOR') }}
select
    CODIGO_OPERADOR     as CODIGO_OPERADOR,
    NOMBRE_OPERADOR     as NOMBRE_OPERADOR,
    RFC_OPERADOR        as RFC_OPERADOR,
    NUMERO_LICENCIA     as NUMERO_LICENCIA,
    TIPO_LICENCIA       as TIPO_LICENCIA,
    ESTATUS_ACTIVO      as ESTATUS_ACTIVO
from {{ ref('cat_operadores') }}
