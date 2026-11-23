{#-
  ST-9: FACT_FACTURACION_FLETE (grano: 1 fila por CFDI de Ingreso; MERGE por UUID_INGRESO, UQ_FFACT_UUID).
  Vehiculo/operador/destino se resuelven via el viaje y la Carta Porte en EDW_3FN (NO via FACT_DESPACHO_VIAJE).
  ID_VEHICULO: lookup point-in-time a la fecha del SERVICIO (despacho del viaje), no a la fecha de facturacion: la factura
  puede emitirse dias despues y la unidad que presto el servicio es la version vigente al despacho.
  ID_DESTINO_UBICACION: destino declarado en la Carta Porte del mismo viaje (1 CCP por viaje).
-#}
{{ config(alias='FACT_FACTURACION_FLETE', unique_key='UUID_INGRESO') }}
select
    i.UUID_INGRESO                                                  as UUID_INGRESO,
    i.FACTURA_ID                                                    as FACTURA_ID,
    i.NUMERO_TALON                                                  as NUMERO_TALON,
    {{ dim_fecha_key('i.FECHA_FACTURA') }}                          as ID_FECHA_FACTURACION,
    nvl(dv.ID_VEHICULO, -1)                                         as ID_VEHICULO,
    nvl(dop.ID_OPERADOR, -1)                                        as ID_OPERADOR,
    nvl(dc.ID_CLIENTE, -1)                                          as ID_CLIENTE,
    nvl(dud.ID_UBICACION, -1)                                       as ID_DESTINO_UBICACION,
    nvl(i.IMPORTE_SUBTOTAL, 0)                                      as IMPORTE_SUBTOTAL,
    nvl(i.IMPORTE_DESCUENTO, 0)                                     as IMPORTE_DESCUENTO,
    nvl(i.IMPORTE_IVA_TRASLADADO, 0)                                as IMPORTE_IVA_TRASLADADO,
    nvl(i.IMPORTE_IVA_RETENIDO, 0)                                  as IMPORTE_IVA_RETENIDO,
    nvl(i.IMPORTE_TOTAL, 0)                                         as IMPORTE_TOTAL_FACTURADO,
    1                                                               as CONTADOR_FACTURA
from {{ ref('fiscal_cfdi_ingreso') }} i
left join {{ ref('op_viajes_despacho') }} v    on v.ID_VIAJE = i.ID_VIAJE
left join {{ ref('cat_vehiculos') }} cv        on cv.ID_VEHICULO = v.ID_VEHICULO
{{ vehiculo_asof_join('dv', 'cv.CODIGO_ECO', 'v.FECHA_DESPACHO') }}
left join {{ ref('cat_operadores') }} co       on co.ID_OPERADOR = v.ID_OPERADOR
left join {{ ref('dim_operador') }} dop        on dop.CODIGO_OPERADOR = co.CODIGO_OPERADOR and dop.ID_OPERADOR <> -1
left join {{ ref('cat_clientes') }} cc         on cc.ID_CLIENTE = i.ID_CLIENTE
left join {{ ref('dim_cliente') }} dc          on dc.RFC_CLIENTE = cc.RFC_CLIENTE and dc.ID_CLIENTE <> -1
left join {{ ref('fiscal_cfdi_cartaporte') }} ccp on ccp.ID_VIAJE = i.ID_VIAJE
left join {{ ref('cat_ubicaciones') }} cud     on cud.ID_UBICACION = ccp.ID_DESTINO_UBICACION
left join {{ ref('dim_ubicacion') }} dud       on dud.CODIGO_UBICACION = cud.CODIGO_UBICACION and dud.ID_UBICACION <> -1
