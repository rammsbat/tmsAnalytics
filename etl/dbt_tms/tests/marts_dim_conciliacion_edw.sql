{#-
  ST-8: conciliacion EDW_3FN <-> DWH_MART (filas sin contar la fila -1) y reglas de calendario.
  Devuelve una fila por control que NO cumple (filas = falla).
-#}
with recon as (
    select 'DIM_REMOLQUE' as T, (select count(*) from {{ ref('cat_remolques') }}) as ESPERADO, (select count(*) from {{ ref('dim_remolque') }} where ID_REMOLQUE <> -1) as REAL from dual
    union all
    select 'DIM_OPERADOR', (select count(*) from {{ ref('cat_operadores') }}), (select count(*) from {{ ref('dim_operador') }} where ID_OPERADOR <> -1) from dual
    union all
    select 'DIM_CLIENTE', (select count(*) from {{ ref('cat_clientes') }}), (select count(*) from {{ ref('dim_cliente') }} where ID_CLIENTE <> -1) from dual
    union all
    select 'DIM_UBICACION', (select count(*) from {{ ref('cat_ubicaciones') }}), (select count(*) from {{ ref('dim_ubicacion') }} where ID_UBICACION <> -1) from dual
    union all
    select 'DIM_PRODUCTO_SAT', (select count(*) from {{ ref('sat_producto_servicio') }}), (select count(*) from {{ ref('dim_producto_sat') }} where ID_PRODUCTO_SAT <> -1) from dual
    union all
    select 'DIM_POLIZA', (select count(*) from {{ ref('cat_polizas_seguro') }}), (select count(*) from {{ ref('dim_poliza') }} where ID_POLIZA <> -1) from dual
    union all
    select 'DIM_PERFIL_VIAJE (estatus distintos)', (select count(distinct ESTATUS_DESPACHO) from {{ ref('op_viajes_despacho') }}), (select count(*) from {{ ref('dim_perfil_viaje') }} where ID_PERFIL_VIAJE <> -1) from dual
    union all
    select 'DIM_FECHA (dias del rango)', (date '{{ var("dim_fecha_fin") }}' - date '{{ var("dim_fecha_inicio") }}') + 1, (select count(*) from {{ ref('dim_fecha') }} where ID_FECHA <> -1) from dual
    union all
    select 'DIM_HORA (minutos del dia)', 1440, (select count(*) from {{ ref('dim_hora') }} where ID_HORA <> -1) from dual
    union all
    select 'DIM_FECHA (ES_FIN_SEMANA vs DIA_SEMANA)', 0, (select count(*) from {{ ref('dim_fecha') }} where ID_FECHA <> -1 and (case when DIA_SEMANA in (6, 7) then '1' else '0' end) <> ES_FIN_SEMANA_FLAG) from dual
    union all
    select 'DIM_FECHA (ID_FECHA vs FECHA)', 0, (select count(*) from {{ ref('dim_fecha') }} where ID_FECHA <> -1 and ID_FECHA <> to_number(to_char(FECHA, 'YYYYMMDD'))) from dual
)
select T, ESPERADO, REAL
from recon
where ESPERADO <> REAL
