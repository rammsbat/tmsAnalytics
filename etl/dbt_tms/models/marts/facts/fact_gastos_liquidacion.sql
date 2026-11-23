{#-
  ST-9: FACT_GASTOS_LIQUIDACION (grano: 1 fila por (FOLIO_LIQ, TIPO_GASTO); MERGE por esa llave, UQ_FGASTO_FOLIO_TIPO; H5).
  Agrega el detalle atomico de EDW_3FN.OP_LIQUIDACIONES_GASTOS y pivota el importe a MONTO_*:
    CASETA -> MONTO_CASETA | OPERADOR -> MONTO_OPERADOR | MANTENIMIENTO -> MONTO_MANTENIMIENTO |
    OTROS y COMBUSTIBLE_ENERGIA -> MONTO_OTROS_GASTOS.
  IMPORTE_GASTO = suma del grupo = exactamente el monto pivotado (cuadre al centavo; lo valida un test contra EDW_3FN).
  Atributos del folio (talon, fecha, unidad, remolque, operador) son constantes por folio (verificado: 0 folios inconsistentes).
  ID_VEHICULO: lookup point-in-time a la fecha de liquidacion.
-#}
{{ config(alias='FACT_GASTOS_LIQUIDACION', unique_key=['FOLIO_LIQ', 'TIPO_GASTO']) }}
with agg as (
    select
        g.FOLIO_LIQUIDACION                                         as FOLIO_LIQ,
        g.TIPO_GASTO                                                as TIPO_GASTO,
        min(g.NUMERO_TALON)                                         as NUMERO_TALON,
        min(g.FECHA_LIQUIDACION)                                    as FECHA_LIQUIDACION,
        min(g.ID_VEHICULO)                                          as ID_VEHICULO_EDW,
        min(g.ID_REMOLQUE)                                          as ID_REMOLQUE_EDW,
        min(g.ID_OPERADOR)                                          as ID_OPERADOR_EDW,
        sum(nvl(g.IMPORTE_GASTO, 0))                                as IMPORTE_GASTO
    from {{ ref('op_liquidaciones_gastos') }} g
    group by g.FOLIO_LIQUIDACION, g.TIPO_GASTO
)
select
    a.FOLIO_LIQ                                                     as FOLIO_LIQ,
    a.NUMERO_TALON                                                  as NUMERO_TALON,
    a.TIPO_GASTO                                                    as TIPO_GASTO,
    {{ dim_fecha_key('a.FECHA_LIQUIDACION') }}                      as ID_FECHA_LIQUIDACION,
    nvl(dv.ID_VEHICULO, -1)                                         as ID_VEHICULO,
    nvl(dr.ID_REMOLQUE, -1)                                         as ID_REMOLQUE,
    nvl(dop.ID_OPERADOR, -1)                                        as ID_OPERADOR,
    a.IMPORTE_GASTO                                                 as IMPORTE_GASTO,
    case when a.TIPO_GASTO = 'CASETA'        then a.IMPORTE_GASTO else 0 end as MONTO_CASETA,
    case when a.TIPO_GASTO = 'OPERADOR'      then a.IMPORTE_GASTO else 0 end as MONTO_OPERADOR,
    case when a.TIPO_GASTO = 'MANTENIMIENTO' then a.IMPORTE_GASTO else 0 end as MONTO_MANTENIMIENTO,
    case when a.TIPO_GASTO in ('OTROS', 'COMBUSTIBLE_ENERGIA') then a.IMPORTE_GASTO else 0 end as MONTO_OTROS_GASTOS,
    1                                                               as CONTADOR_LIQUIDACION
from agg a
left join {{ ref('cat_vehiculos') }} cv        on cv.ID_VEHICULO = a.ID_VEHICULO_EDW
{{ vehiculo_asof_join('dv', 'cv.CODIGO_ECO', 'a.FECHA_LIQUIDACION') }}
left join {{ ref('cat_remolques') }} cr        on cr.ID_REMOLQUE = a.ID_REMOLQUE_EDW
left join {{ ref('dim_remolque') }} dr         on dr.NUMERO_ECONOMICO_REMOLQUE = cr.NUMERO_ECONOMICO_REMOLQUE and dr.ID_REMOLQUE <> -1
left join {{ ref('cat_operadores') }} co       on co.ID_OPERADOR = a.ID_OPERADOR_EDW
left join {{ ref('dim_operador') }} dop        on dop.CODIGO_OPERADOR = co.CODIGO_OPERADOR and dop.ID_OPERADOR <> -1
