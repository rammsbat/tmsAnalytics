{#-
  ST-9: FACT_LINEAS_CARGA_CARTAPORTE (grano: 1 fila por partida de mercancia; MERGE por (UUID_CCP, NUMERO_PARTIDA)).
  Desde EDW_3FN (FISCAL_CARTAPORTE_MERCANCIAS + FISCAL_CFDI_CARTAPORTE) y dimensiones conformadas.
  ID_VEHICULO: lookup point-in-time a la fecha de emision del CCP. DISTANCIA_DECLARADA_KM es un atributo del CCP que se
  repite en cada partida (segun DDL): NO sumar entre partidas, usar por CCP (DISTINCT UUID_CCP) o promedio.
-#}
{{ config(alias='FACT_LINEAS_CARGA_CARTAPORTE', unique_key=['UUID_CCP', 'NUMERO_PARTIDA']) }}
select
    c.UUID_CCP                                                      as UUID_CCP,
    c.NUMERO_TALON                                                  as NUMERO_TALON,
    m.NUMERO_PARTIDA                                                as NUMERO_PARTIDA,
    m.UNIDAD_EMBARQUE_UE                                            as UNIDAD_EMBARQUE_UE,
    {{ dim_fecha_key('c.FECHA_EMISION') }}                          as ID_FECHA_EMISION,
    nvl(dv.ID_VEHICULO, -1)                                         as ID_VEHICULO,
    nvl(dr.ID_REMOLQUE, -1)                                         as ID_REMOLQUE,
    nvl(dop.ID_OPERADOR, -1)                                        as ID_OPERADOR,
    nvl(dcr.ID_CLIENTE, -1)                                         as ID_CLIENTE_REMITENTE,
    nvl(dcd.ID_CLIENTE, -1)                                         as ID_CLIENTE_DESTINATARIO,
    nvl(duo.ID_UBICACION, -1)                                       as ID_ORIGEN_UBICACION,
    nvl(dud.ID_UBICACION, -1)                                       as ID_DESTINO_UBICACION,
    nvl(dps.ID_PRODUCTO_SAT, -1)                                    as ID_PRODUCTO_SAT,
    nvl(dpo.ID_POLIZA, -1)                                          as ID_POLIZA,
    nvl(m.CANTIDAD, 1)                                              as CANTIDAD_PIEZAS,
    nvl(m.PESO_KG, 0)                                               as PESO_KG,
    nvl(c.DISTANCIA_DECLARADA_KM, 0)                                as DISTANCIA_DECLARADA_KM,
    1                                                               as CONTADOR_PARTIDA
from {{ ref('fiscal_cartaporte_mercancias') }} m
join {{ ref('fiscal_cfdi_cartaporte') }} c     on c.ID_CFDI_CCP = m.ID_CFDI_CCP
join {{ ref('cat_vehiculos') }} cv             on cv.ID_VEHICULO = c.ID_VEHICULO
{{ vehiculo_asof_join('dv', 'cv.CODIGO_ECO', 'c.FECHA_EMISION') }}
left join {{ ref('cat_remolques') }} cr        on cr.ID_REMOLQUE = c.ID_REMOLQUE
left join {{ ref('dim_remolque') }} dr         on dr.NUMERO_ECONOMICO_REMOLQUE = cr.NUMERO_ECONOMICO_REMOLQUE and dr.ID_REMOLQUE <> -1
left join {{ ref('cat_operadores') }} co       on co.ID_OPERADOR = c.ID_OPERADOR
left join {{ ref('dim_operador') }} dop        on dop.CODIGO_OPERADOR = co.CODIGO_OPERADOR and dop.ID_OPERADOR <> -1
left join {{ ref('cat_clientes') }} ccr        on ccr.ID_CLIENTE = c.ID_CLIENTE_REMITENTE
left join {{ ref('dim_cliente') }} dcr         on dcr.RFC_CLIENTE = ccr.RFC_CLIENTE and dcr.ID_CLIENTE <> -1
left join {{ ref('cat_clientes') }} ccd        on ccd.ID_CLIENTE = c.ID_CLIENTE_DESTINATARIO
left join {{ ref('dim_cliente') }} dcd         on dcd.RFC_CLIENTE = ccd.RFC_CLIENTE and dcd.ID_CLIENTE <> -1
left join {{ ref('cat_ubicaciones') }} cuo     on cuo.ID_UBICACION = c.ID_ORIGEN_UBICACION
left join {{ ref('dim_ubicacion') }} duo       on duo.CODIGO_UBICACION = cuo.CODIGO_UBICACION and duo.ID_UBICACION <> -1
left join {{ ref('cat_ubicaciones') }} cud     on cud.ID_UBICACION = c.ID_DESTINO_UBICACION
left join {{ ref('dim_ubicacion') }} dud       on dud.CODIGO_UBICACION = cud.CODIGO_UBICACION and dud.ID_UBICACION <> -1
left join {{ ref('dim_producto_sat') }} dps    on dps.CLAVE_PRODUCTO_SAT = m.CLAVE_PRODUCTO_SAT and dps.ID_PRODUCTO_SAT <> -1
left join {{ ref('cat_polizas_seguro') }} cp   on cp.ID_POLIZA = c.ID_POLIZA
left join {{ ref('dim_poliza') }} dpo          on dpo.NUMERO_POLIZA = cp.NUMERO_POLIZA and dpo.ID_POLIZA <> -1
