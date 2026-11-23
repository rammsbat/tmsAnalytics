{#-
  ST-8: DIM_PERFIL_VIAJE (junk, A3/H6). Solo combinaciones realmente presentes en OP_VIAJES_DESPACHO.
  ETAPA_VIAJE se deriva de ESTATUS_DESPACHO (EN_TRANSITO -> TRANSITO, CERRADO -> CERRADO); TIPO_COBRO_FLETE,
  TIPO_COBRO_CASETAS y PAGO_OPERADOR usan los valores por defecto del DDL (DESTINO, COMPLETO, DESTINO).
  Llave del MERGE: los 4 atributos (UQ_DIM_PERFIL); SK IDENTITY. ST-9 resuelve el perfil con la misma derivacion.
-#}
{{ config(
    alias='DIM_PERFIL_VIAJE',
    unique_key=['TIPO_COBRO_FLETE', 'TIPO_COBRO_CASETAS', 'PAGO_OPERADOR', 'ETAPA_VIAJE']
) }}
with perfiles as (
    select distinct
        'DESTINO'   as TIPO_COBRO_FLETE,
        'COMPLETO'  as TIPO_COBRO_CASETAS,
        'DESTINO'   as PAGO_OPERADOR,
        {{ etapa_viaje('ESTATUS_DESPACHO') }} as ETAPA_VIAJE
    from {{ ref('op_viajes_despacho') }}
)
select
    TIPO_COBRO_FLETE,
    TIPO_COBRO_CASETAS,
    PAGO_OPERADOR,
    ETAPA_VIAJE,
    'FLETE ' || TIPO_COBRO_FLETE || ' / CASETAS ' || TIPO_COBRO_CASETAS
        || ' / OPERADOR ' || PAGO_OPERADOR || ' / ' || ETAPA_VIAJE as DESCRIPCION_PERFIL
from perfiles
