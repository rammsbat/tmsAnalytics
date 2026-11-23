{#-
  ST-8: DIM_VEHICULO en SCD Tipo 2 (scd2_existing; A5, A6, D4, P3).
  Fuente: EDW_3FN.CAT_VEHICULOS (estado actual por CODIGO_ECO). FECHA_EFECTIVA = TRUNC(UPDATED_AT) (D6; ST-7 fija
  UPDATED_AT = INGESTED_AT de la version vigente) y solo gobierna cierre/apertura de versiones.
  Vigencia inicial UNIFORME (A5): toda llave nueva se inserta con FECHA_INICIO_VALIDEZ = var dim_vehiculo_inicio_validez
  (2026-08-09, inicio del backfill) y FECHA_FIN_VALIDEZ = NULL, incluidas ECO07 y ECO42 (cuyo UPDATED_AT es octubre):
  asi ningun viaje de agosto/septiembre cae a -1 en el lookup por rango de fechas de ST-9.
  Una version nueva (cambio rastreado posterior) solo se abre cuando la llave ya tenia historia en la dimension.
-#}
{{ config(
    alias='DIM_VEHICULO',
    materialized='scd2_existing',
    unique_key='CODIGO_ECO',
    tracked_columns=['PLACA', 'CONFIGURACION_SAT', 'TIPO_PERMISO_SCT', 'PESO_BRUTO_MAX_KG', 'ESTATUS_OPERATIVO'],
    initial_start_date="date '" ~ var('dim_vehiculo_inicio_validez') ~ "'"
) }}
select
    CODIGO_ECO                  as CODIGO_ECO,
    PLACA                       as PLACA,
    ANIO_MODELO                 as ANIO_MODELO,
    MARCA                       as MARCA,
    MODELO                      as MODELO,
    CONFIGURACION_SAT           as CONFIGURACION_SAT,
    TIPO_PERMISO_SCT            as TIPO_PERMISO_SCT,
    PESO_BRUTO_MAX_KG           as PESO_BRUTO_MAX_KG,
    ESTATUS_OPERATIVO           as ESTATUS_OPERATIVO,
    trunc(UPDATED_AT)           as FECHA_EFECTIVA
from {{ ref('cat_vehiculos') }}
