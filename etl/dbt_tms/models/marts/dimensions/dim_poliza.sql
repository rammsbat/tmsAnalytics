{#- ST-8: DIM_POLIZA (SCD1, MERGE por NUMERO_POLIZA; SK IDENTITY). -#}
{{ config(alias='DIM_POLIZA', unique_key='NUMERO_POLIZA') }}
select
    NUMERO_POLIZA           as NUMERO_POLIZA,
    ASEGURADORA             as ASEGURADORA_RESP_CIVIL,
    VIGENCIA_HASTA          as VIGENCIA_HASTA,
    TIPO_COBERTURA          as TIPO_COBERTURA,
    MONTO_COBERTURA_RC      as MONTO_COBERTURA_RC
from {{ ref('cat_polizas_seguro') }}
