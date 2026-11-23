{#-
  ST-9: los unicos -1 permitidos en las FKs de hechos son "evento aun no ocurrido" y deben coincidir exactamente con el
  estado en EDW_3FN (ni falsos -1 por lookup fallido, ni -1 faltantes). Devuelve una fila por control incumplido.
    * FACT_DESPACHO_VIAJE.ID_FECHA_CIERRE = -1  <=>  viaje sin cierre (CONTADOR_CERRADO = 0).
    * FACT_EVENTOS_PARADA.ID_*_LLEGADA = -1     <=>  parada sin llegada real (PENDIENTE).
    * FACT_EVENTOS_PARADA.ID_*_SALIDA  = -1     <=>  parada sin salida real (PENDIENTE o EN_CURSO).
    * Cualquier otra FK de dimension en los 6 hechos = -1  =>  falla (lookup fallido).
-#}
with desp as (
    select 'DESPACHO: cierre -1 incoherente con CONTADOR_CERRADO' as CONTROL, count(*) as N
    from {{ ref('fact_despacho_viaje') }}
    where (ID_FECHA_CIERRE = -1) <> (CONTADOR_CERRADO = 0)
    union all
    select 'DESPACHO: FK de dimension en -1', count(*)
    from {{ ref('fact_despacho_viaje') }}
    where -1 in (ID_FECHA_INICIO, ID_HORA_INICIO, ID_VEHICULO, ID_REMOLQUE, ID_OPERADOR, ID_CLIENTE_ORIGEN, ID_CLIENTE_DESTINO, ID_PERFIL_VIAJE)
),
par as (
    select 'PARADA: llegada -1 vs EDW (sin llegada real)' as CONTROL, count(*) as N
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e
      on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    where ((f.ID_FECHA_LLEGADA = -1) <> (e.FECHA_HORA_LLEGADA_REAL is null))
       or ((f.ID_HORA_LLEGADA = -1) <> (e.FECHA_HORA_LLEGADA_REAL is null))
    union all
    select 'PARADA: salida -1 vs EDW (sin salida real)', count(*)
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e
      on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    where ((f.ID_FECHA_SALIDA = -1) <> (e.FECHA_HORA_SALIDA_REAL is null))
       or ((f.ID_HORA_SALIDA = -1) <> (e.FECHA_HORA_SALIDA_REAL is null))
    union all
    select 'PARADA: FK de dimension en -1', count(*)
    from {{ ref('fact_eventos_parada') }}
    where -1 in (ID_VEHICULO, ID_OPERADOR, ID_UBICACION_PARADA)
    union all
    select 'PARADA: pendiente/abierta con metricas o contadores inconsistentes', count(*)
    from {{ ref('fact_eventos_parada') }} f
    join {{ ref('op_viajes_paradas') }} e
      on e.NUMERO_TALON = f.NUMERO_TALON and e.NUMERO_SECUENCIA = f.NUMERO_SECUENCIA
    where (e.ESTATUS_PARADA = 'PENDIENTE' and (f.CONTADOR_PARADA <> 0 or f.CONTADOR_PUNTUAL <> 0 or f.LAG_LLEGADA_MINUTOS <> 0 or f.LAG_SALIDA_MINUTOS <> 0 or f.TIEMPO_ESTADIA_MINUTOS <> 0))
       or (e.ESTATUS_PARADA = 'EN_CURSO'  and (f.CONTADOR_PARADA <> 1 or f.LAG_SALIDA_MINUTOS <> 0 or f.TIEMPO_ESTADIA_MINUTOS <> 0))
       or (e.ESTATUS_PARADA = 'COMPLETADA' and f.CONTADOR_PARADA <> 1)
),
lin as (
    select 'LINEAS: FK de dimension en -1' as CONTROL, count(*) as N
    from {{ ref('fact_lineas_carga_cartaporte') }}
    where -1 in (ID_FECHA_EMISION, ID_VEHICULO, ID_REMOLQUE, ID_OPERADOR, ID_CLIENTE_REMITENTE, ID_CLIENTE_DESTINATARIO,
                 ID_ORIGEN_UBICACION, ID_DESTINO_UBICACION, ID_PRODUCTO_SAT, ID_POLIZA)
),
fac as (
    select 'FACTURACION: FK de dimension en -1' as CONTROL, count(*) as N
    from {{ ref('fact_facturacion_flete') }}
    where -1 in (ID_FECHA_FACTURACION, ID_VEHICULO, ID_OPERADOR, ID_CLIENTE, ID_DESTINO_UBICACION)
),
gas as (
    select 'GASTOS: FK de dimension en -1' as CONTROL, count(*) as N
    from {{ ref('fact_gastos_liquidacion') }}
    where -1 in (ID_FECHA_LIQUIDACION, ID_VEHICULO, ID_REMOLQUE, ID_OPERADOR)
),
snp as (
    select 'SNAPSHOT: FK de dimension en -1' as CONTROL, count(*) as N
    from {{ ref('fact_snapshot_flota_diario') }}
    where -1 in (ID_FECHA_CORTE, ID_VEHICULO)
)
select CONTROL, N from desp where N > 0
union all select CONTROL, N from par where N > 0
union all select CONTROL, N from lin where N > 0
union all select CONTROL, N from fac where N > 0
union all select CONTROL, N from gas where N > 0
union all select CONTROL, N from snp where N > 0
