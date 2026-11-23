{#-
  ST-8 (A5): DIM_VEHICULO. Excluye la fila -1. Devuelve una fila por CODIGO_ECO que incumple:
    * exactamente 1 version activa por unidad;
    * la primera version de toda unidad inicia en var dim_vehiculo_inicio_validez (vigencia inicial uniforme, para
      que ningun viaje de agosto/septiembre caiga a -1 en el lookup por rango de ST-9);
    * versiones activas con FECHA_FIN_VALIDEZ NULL y cerradas con FIN >= INICIO;
    * 1 unidad en DIM_VEHICULO por cada unidad en CAT_VEHICULOS.
-#}
with v as (
    select
        CODIGO_ECO,
        count(case when VERSION_ACTIVA = '1' then 1 end)                                        as N_ACTIVAS,
        min(FECHA_INICIO_VALIDEZ)                                                               as PRIMER_INICIO,
        count(case when VERSION_ACTIVA = '1' and FECHA_FIN_VALIDEZ is not null then 1 end)      as ACTIVAS_CERRADAS,
        count(case when VERSION_ACTIVA = '0' and (FECHA_FIN_VALIDEZ is null or FECHA_FIN_VALIDEZ < FECHA_INICIO_VALIDEZ) then 1 end) as CERRADAS_INVALIDAS
    from {{ ref('dim_vehiculo') }}
    where ID_VEHICULO <> -1
    group by CODIGO_ECO
)
select CODIGO_ECO, N_ACTIVAS, PRIMER_INICIO, ACTIVAS_CERRADAS, CERRADAS_INVALIDAS
from v
where N_ACTIVAS <> 1
   or PRIMER_INICIO <> date '{{ var("dim_vehiculo_inicio_validez") }}'
   or ACTIVAS_CERRADAS > 0
   or CERRADAS_INVALIDAS > 0
union all
select 'FALTANTES_VS_CAT_VEHICULOS', count(*), null, null, null
from {{ ref('cat_vehiculos') }} c
where not exists (select 1 from {{ ref('dim_vehiculo') }} d where d.CODIGO_ECO = c.CODIGO_ECO and d.ID_VEHICULO <> -1)
having count(*) > 0
