{#-
  ST-9: FACT_DESPACHO_VIAJE (grano: 1 fila por viaje; MERGE por NUMERO_TALON, UQ_FDESP_TALON).
  Todo se resuelve desde EDW_3FN y dimensiones conformadas (nunca desde otro FACT_*).
  * ID_VEHICULO: lookup point-in-time en DIM_VEHICULO a la fecha de despacho (A5), sin fila -1.
  * ID_PERFIL_VIAJE: misma derivacion que DIM_PERFIL_VIAJE (A3): EN_TRANSITO -> TRANSITO, CERRADO -> CERRADO;
    TIPO_COBRO_FLETE/CASETAS/PAGO_OPERADOR = valores por defecto del DDL (DESTINO / COMPLETO / DESTINO).
  * Viaje abierto (EN_TRANSITO): ID_FECHA_CIERRE = -1 (el cierre aun no ocurre; es -1 LEGITIMO y los screens de ST-10
    lo excluyen por CONTADOR_CERRADO = 0). CONTADOR_CERRADO = 1 solo con ESTATUS_DESPACHO = CERRADO y FECHA_CIERRE.
  * Todas las FKs van envueltas en NVL(..., -1).
-#}
{{ config(alias='FACT_DESPACHO_VIAJE', unique_key='NUMERO_TALON') }}
select
    d.NUMERO_TALON                                                  as NUMERO_TALON,
    {{ dim_fecha_key('d.FECHA_DESPACHO') }}                         as ID_FECHA_INICIO,
    {{ dim_hora_key('d.FECHA_DESPACHO') }}                          as ID_HORA_INICIO,
    {{ dim_fecha_key('d.FECHA_CIERRE') }}                           as ID_FECHA_CIERRE,
    nvl(dv.ID_VEHICULO, -1)                                         as ID_VEHICULO,
    nvl(dr.ID_REMOLQUE, -1)                                         as ID_REMOLQUE,
    nvl(dop.ID_OPERADOR, -1)                                        as ID_OPERADOR,
    nvl(dco.ID_CLIENTE, -1)                                         as ID_CLIENTE_ORIGEN,
    nvl(dcd.ID_CLIENTE, -1)                                         as ID_CLIENTE_DESTINO,
    nvl(dp.ID_PERFIL_VIAJE, -1)                                     as ID_PERFIL_VIAJE,
    d.ODOMETRO_INICIAL                                              as ODOMETRO_INICIAL,
    d.ODOMETRO_FINAL                                                as ODOMETRO_FINAL,
    nvl(d.KMS_CARGADO, 0)                                           as KMS_CARGADO,
    nvl(d.KMS_VACIO, 0)                                             as KMS_VACIO,
    nvl(d.KMS_TOTAL, 0)                                             as KMS_TOTAL,
    d.BATERIA_INICIAL_PCT                                           as BATERIA_INICIAL_PCT,
    d.BATERIA_FINAL_PCT                                             as BATERIA_FINAL_PCT,
    nvl(d.KWH_CONSUMO, 0)                                           as KWH_CONSUMO_ENERGIA,
    nvl(d.RENDIMIENTO_KMS_KWH, 0)                                   as RENDIMIENTO_KMS_KWH,
    nvl(d.PESO_BRUTO_KG, 0)                                         as PESO_BRUTO_TOTAL_KG,
    nvl(d.TOTAL_PARADAS, 0)                                         as TOTAL_PARADAS,
    1                                                               as CONTADOR_DESPACHO,
    case when d.ESTATUS_DESPACHO = 'CERRADO' and d.FECHA_CIERRE is not null then 1 else 0 end as CONTADOR_CERRADO
from {{ ref('op_viajes_despacho') }} d
join {{ ref('cat_vehiculos') }} cv            on cv.ID_VEHICULO = d.ID_VEHICULO
{{ vehiculo_asof_join('dv', 'cv.CODIGO_ECO', 'd.FECHA_DESPACHO') }}
left join {{ ref('cat_remolques') }} cr       on cr.ID_REMOLQUE = d.ID_REMOLQUE
left join {{ ref('dim_remolque') }} dr        on dr.NUMERO_ECONOMICO_REMOLQUE = cr.NUMERO_ECONOMICO_REMOLQUE and dr.ID_REMOLQUE <> -1
left join {{ ref('cat_operadores') }} co      on co.ID_OPERADOR = d.ID_OPERADOR
left join {{ ref('dim_operador') }} dop       on dop.CODIGO_OPERADOR = co.CODIGO_OPERADOR and dop.ID_OPERADOR <> -1
left join {{ ref('cat_clientes') }} cco       on cco.ID_CLIENTE = d.ID_CLIENTE_ORIGEN
left join {{ ref('dim_cliente') }} dco        on dco.RFC_CLIENTE = cco.RFC_CLIENTE and dco.ID_CLIENTE <> -1
left join {{ ref('cat_clientes') }} ccd       on ccd.ID_CLIENTE = d.ID_CLIENTE_DESTINO
left join {{ ref('dim_cliente') }} dcd        on dcd.RFC_CLIENTE = ccd.RFC_CLIENTE and dcd.ID_CLIENTE <> -1
left join {{ ref('dim_perfil_viaje') }} dp
    on  dp.TIPO_COBRO_FLETE   = 'DESTINO'
    and dp.TIPO_COBRO_CASETAS = 'COMPLETO'
    and dp.PAGO_OPERADOR      = 'DESTINO'
    and dp.ETAPA_VIAJE        = {{ etapa_viaje('d.ESTATUS_DESPACHO') }}
    and dp.ID_PERFIL_VIAJE   <> -1
