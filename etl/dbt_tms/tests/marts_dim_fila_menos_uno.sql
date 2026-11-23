{#-
  ST-8: la fila dummy -1 debe existir exactamente una vez y con valores DESCONOCIDO/dummy intactos en las 10
  dimensiones. Devuelve una fila por dimension que incumple (filas = falla).
-#}
with chk as (
    select 'DIM_FECHA' as T, count(*) as N, count(case when FECHA = date '1900-01-01' and NOMBRE_MES = 'DESCONOCIDO' then 1 end) as OK from {{ ref('dim_fecha') }} where ID_FECHA = -1
    union all
    select 'DIM_HORA', count(*), count(case when PERIODO_DIA = 'DESCONOCIDO' and AM_PM = 'NA' then 1 end) from {{ ref('dim_hora') }} where ID_HORA = -1
    union all
    select 'DIM_VEHICULO', count(*), count(case when CODIGO_ECO = 'DESCONOCIDO' and VERSION_ACTIVA = '1' and FECHA_INICIO_VALIDEZ = date '1900-01-01' and FECHA_FIN_VALIDEZ = date '2099-12-31' then 1 end) from {{ ref('dim_vehiculo') }} where ID_VEHICULO = -1
    union all
    select 'DIM_REMOLQUE', count(*), count(case when NUMERO_ECONOMICO_REMOLQUE = 'DESCONOCIDO' then 1 end) from {{ ref('dim_remolque') }} where ID_REMOLQUE = -1
    union all
    select 'DIM_OPERADOR', count(*), count(case when CODIGO_OPERADOR = 'DESCONOCIDO' then 1 end) from {{ ref('dim_operador') }} where ID_OPERADOR = -1
    union all
    select 'DIM_CLIENTE', count(*), count(case when RFC_CLIENTE = 'DESCONOCIDO' then 1 end) from {{ ref('dim_cliente') }} where ID_CLIENTE = -1
    union all
    select 'DIM_UBICACION', count(*), count(case when CODIGO_UBICACION = 'DESCONOCIDO' then 1 end) from {{ ref('dim_ubicacion') }} where ID_UBICACION = -1
    union all
    select 'DIM_PRODUCTO_SAT', count(*), count(case when CLAVE_PRODUCTO_SAT = 'DESCONOCIDO' then 1 end) from {{ ref('dim_producto_sat') }} where ID_PRODUCTO_SAT = -1
    union all
    select 'DIM_POLIZA', count(*), count(case when NUMERO_POLIZA = 'DESCONOCIDO' then 1 end) from {{ ref('dim_poliza') }} where ID_POLIZA = -1
    union all
    select 'DIM_PERFIL_VIAJE', count(*), count(case when ETAPA_VIAJE = 'DESCONOCIDO' and TIPO_COBRO_FLETE = 'DESCONOCIDO' then 1 end) from {{ ref('dim_perfil_viaje') }} where ID_PERFIL_VIAJE = -1
)
select T, N, OK
from chk
where N <> 1 or OK <> 1
