{#-
  ST-9/ST-10: conciliacion STG_SRC / EDW_3FN <-> DWH_MART de conteos (grano), montos al centavo y reglas de negocio.
  Filas = falla. Se compara contra fuentes/EDW_3FN y se agrega cada hecho de forma independiente (sin Fact-to-Fact).
-#}
with recon as (
    select 'CONTEO despacho' as T, (select count(*) from {{ ref('op_viajes_despacho') }}) as ESPERADO, (select count(*) from {{ ref('fact_despacho_viaje') }}) as REAL from dual
    union all
    select 'CONTEO paradas', (select count(*) from {{ ref('op_viajes_paradas') }}), (select count(*) from {{ ref('fact_eventos_parada') }}) from dual
    union all
    select 'CONTEO lineas de carga', (select count(*) from {{ ref('fiscal_cartaporte_mercancias') }}), (select count(*) from {{ ref('fact_lineas_carga_cartaporte') }}) from dual
    union all
    select 'CONTEO facturacion', (select count(*) from {{ ref('fiscal_cfdi_ingreso') }}), (select count(*) from {{ ref('fact_facturacion_flete') }}) from dual
    union all
    select 'CONTEO gastos (folio,tipo)', (select count(*) from (select distinct FOLIO_LIQUIDACION, TIPO_GASTO from {{ ref('op_liquidaciones_gastos') }})), (select count(*) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'CONTEO viajes cerrados', (select count(*) from {{ ref('op_viajes_despacho') }} where ESTATUS_DESPACHO = 'CERRADO'), (select nvl(sum(CONTADOR_CERRADO), 0) from {{ ref('fact_despacho_viaje') }}) from dual
    union all
    select 'MONTO facturado total (vs EDW)', (select nvl(sum(IMPORTE_TOTAL), 0) from {{ ref('fiscal_cfdi_ingreso') }}), (select nvl(sum(IMPORTE_TOTAL_FACTURADO), 0) from {{ ref('fact_facturacion_flete') }}) from dual
    union all
    select 'MONTO facturado total (vs STG)', (select nvl(sum(IMPORTE_TOTAL), 0) from (select distinct UUID_INGRESO, IMPORTE_TOTAL from {{ source('stg_src', 'stg_cfdi_ingreso') }})), (select nvl(sum(IMPORTE_TOTAL_FACTURADO), 0) from {{ ref('fact_facturacion_flete') }}) from dual
    union all
    select 'MONTO facturado subtotal', (select nvl(sum(IMPORTE_SUBTOTAL), 0) from {{ ref('fiscal_cfdi_ingreso') }}), (select nvl(sum(IMPORTE_SUBTOTAL), 0) from {{ ref('fact_facturacion_flete') }}) from dual
    union all
    select 'MONTO facturado cuadre fiscal (total = sub - desc + iva - ret)', 0, (select count(*) from {{ ref('fact_facturacion_flete') }} where IMPORTE_TOTAL_FACTURADO <> IMPORTE_SUBTOTAL - IMPORTE_DESCUENTO + IMPORTE_IVA_TRASLADADO - IMPORTE_IVA_RETENIDO) from dual
    union all
    select 'MONTO gastos total (vs EDW)', (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('op_liquidaciones_gastos') }}), (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'MONTO gastos total (vs STG)', (select nvl(sum(IMPORTE_GASTO), 0) from (select distinct upper(trim(FOLIO_LIQUIDACION)), upper(trim(TIPO_GASTO)), trim(REFERENCIA_COMPROBANTE), IMPORTE_GASTO from {{ source('stg_src', 'stg_liquidaciones_gastos') }})), (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'MONTO gastos pivot = IMPORTE_GASTO por fila', 0, (select count(*) from {{ ref('fact_gastos_liquidacion') }} where IMPORTE_GASTO <> MONTO_CASETA + MONTO_OPERADOR + MONTO_MANTENIMIENTO + MONTO_OTROS_GASTOS) from dual
    union all
    select 'MONTO gastos CASETA', (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('op_liquidaciones_gastos') }} where TIPO_GASTO = 'CASETA'), (select nvl(sum(MONTO_CASETA), 0) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'MONTO gastos OPERADOR', (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('op_liquidaciones_gastos') }} where TIPO_GASTO = 'OPERADOR'), (select nvl(sum(MONTO_OPERADOR), 0) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'MONTO gastos MANTENIMIENTO', (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('op_liquidaciones_gastos') }} where TIPO_GASTO = 'MANTENIMIENTO'), (select nvl(sum(MONTO_MANTENIMIENTO), 0) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'MONTO gastos OTROS+COMBUSTIBLE', (select nvl(sum(IMPORTE_GASTO), 0) from {{ ref('op_liquidaciones_gastos') }} where TIPO_GASTO in ('OTROS', 'COMBUSTIBLE_ENERGIA')), (select nvl(sum(MONTO_OTROS_GASTOS), 0) from {{ ref('fact_gastos_liquidacion') }}) from dual
    union all
    select 'KMS despacho (vs EDW)', (select nvl(sum(KMS_TOTAL), 0) from {{ ref('op_viajes_despacho') }}), (select nvl(sum(KMS_TOTAL), 0) from {{ ref('fact_despacho_viaje') }}) from dual
    union all
    select 'KWH despacho (vs EDW)', (select nvl(sum(KWH_CONSUMO), 0) from {{ ref('op_viajes_despacho') }}), (select nvl(sum(KWH_CONSUMO_ENERGIA), 0) from {{ ref('fact_despacho_viaje') }}) from dual
    union all
    select 'KMS snapshot (vs EDW estatus diario)', (select nvl(sum(KMS_ODOMETRO_DIA), 0) from {{ ref('op_flota_estatus_diario') }}), (select nvl(sum(KMS_RECORRIDOS_DIA), 0) from {{ ref('fact_snapshot_flota_diario') }}) from dual
    union all
    select 'KWH snapshot (vs EDW estatus diario)', (select nvl(sum(KWH_CONSUMO_DIA), 0) from {{ ref('op_flota_estatus_diario') }}), (select nvl(sum(KWH_CONSUMO_DIA), 0) from {{ ref('fact_snapshot_flota_diario') }}) from dual
    union all
    select 'PESO lineas vs CCP', (select nvl(sum(PESO_KG), 0) from {{ ref('fiscal_cartaporte_mercancias') }}), (select nvl(sum(PESO_KG), 0) from {{ ref('fact_lineas_carga_cartaporte') }}) from dual
    union all
    select 'REGLA: KMS_CARGADO + KMS_VACIO = KMS_TOTAL', 0, (select count(*) from {{ ref('fact_despacho_viaje') }} where abs(KMS_TOTAL - (KMS_CARGADO + KMS_VACIO)) > 0.001) from dual
    union all
    select 'RANGO: KMS_TOTAL, CARGADO, VACIO >= 0', 0, (select count(*) from {{ ref('fact_despacho_viaje') }} where KMS_TOTAL < 0 or KMS_CARGADO < 0 or KMS_VACIO < 0) from dual
    union all
    select 'RANGO: KMS_RECORRIDOS_DIA >= 0', 0, (select count(*) from {{ ref('fact_snapshot_flota_diario') }} where KMS_RECORRIDOS_DIA < 0) from dual
    union all
    select 'RANGO: PESO_KG lineas entre 0 y 35000', 0, (select count(*) from {{ ref('fact_lineas_carga_cartaporte') }} where PESO_KG < 0 or PESO_KG > 35000) from dual
    union all
    select 'RANGO: PESO_BRUTO_TOTAL_KG viaje entre 0 y 35000', 0, (select count(*) from {{ ref('fact_despacho_viaje') }} where PESO_BRUTO_TOTAL_KG < 0 or PESO_BRUTO_TOTAL_KG > 35000) from dual
)
select T, ESPERADO, REAL
from recon
where ESPERADO <> REAL
