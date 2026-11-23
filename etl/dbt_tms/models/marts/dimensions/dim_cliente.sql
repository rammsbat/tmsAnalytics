{#- ST-8: DIM_CLIENTE (SCD1, MERGE por RFC; SK IDENTITY). Rol remitente/destinatario/receptor. -#}
{{ config(alias='DIM_CLIENTE', unique_key='RFC_CLIENTE') }}
select
    RFC_CLIENTE             as RFC_CLIENTE,
    RAZON_SOCIAL            as RAZON_SOCIAL,
    REGIMEN_FISCAL          as REGIMEN_FISCAL,
    USO_CFDI_HABITUAL       as USO_CFDI_HABITUAL,
    DIRECCION_FISCAL_CP     as DIRECCION_FISCAL_CP,
    ESTATUS_ACTIVO          as ESTATUS_ACTIVO
from {{ ref('cat_clientes') }}
