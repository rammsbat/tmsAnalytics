{#-
  ST-7: conciliacion STG_SRC <-> EDW_3FN (cuenta de filas distintas por llave natural, no filas crudas:
  STG es append-only con versiones). Devuelve una fila por tabla que NO concilia (filas = falla).
-#}
with recon as (
    select 'OP_VIAJES_DESPACHO' as T,
           (select count(distinct upper(trim(TALON_FOLIO))) from {{ source('stg_src', 'stg_trackit_despacho') }}) as ORIGEN,
           (select count(*) from {{ ref('op_viajes_despacho') }}) as DESTINO from dual
    union all
    select 'OP_VIAJES_PARADAS',
           (select count(*) from (select distinct upper(trim(TALON_FOLIO)), NUMERO_SECUENCIA from {{ source('stg_src', 'stg_trackit_paradas') }})),
           (select count(*) from {{ ref('op_viajes_paradas') }}) from dual
    union all
    select 'OP_FLOTA_ESTATUS_DIARIO',
           (select count(*) from (select distinct upper(trim(CODIGO_ECO)), trunc(FECHA_CORTE) from {{ source('stg_src', 'stg_flota_estatus_diario') }})),
           (select count(*) from {{ ref('op_flota_estatus_diario') }}) from dual
    union all
    select 'FISCAL_CFDI_CARTAPORTE',
           (select count(distinct upper(trim(UUID_CCP))) from {{ source('stg_src', 'stg_carta_porte_cabecera') }}),
           (select count(*) from {{ ref('fiscal_cfdi_cartaporte') }}) from dual
    union all
    select 'FISCAL_CARTAPORTE_MERCANCIAS',
           (select count(*) from (select distinct upper(trim(UUID_CCP)), NUMERO_PARTIDA from {{ source('stg_src', 'stg_carta_porte_mercancias') }})),
           (select count(*) from {{ ref('fiscal_cartaporte_mercancias') }}) from dual
    union all
    select 'FISCAL_CFDI_INGRESO',
           (select count(distinct upper(trim(UUID_INGRESO))) from {{ source('stg_src', 'stg_cfdi_ingreso') }}),
           (select count(*) from {{ ref('fiscal_cfdi_ingreso') }}) from dual
    union all
    select 'OP_LIQUIDACIONES_GASTOS',
           (select count(*) from (select distinct upper(trim(FOLIO_LIQUIDACION)), upper(trim(TIPO_GASTO)), trim(REFERENCIA_COMPROBANTE) from {{ source('stg_src', 'stg_liquidaciones_gastos') }})),
           (select count(*) from {{ ref('op_liquidaciones_gastos') }}) from dual
    union all
    select 'CAT_VEHICULOS',
           (select count(distinct upper(trim(CODIGO_ECO))) from {{ source('stg_src', 'stg_flota_unidades') }}),
           (select count(*) from {{ ref('cat_vehiculos') }}) from dual
)
select T, ORIGEN, DESTINO
from recon
where ORIGEN <> DESTINO
