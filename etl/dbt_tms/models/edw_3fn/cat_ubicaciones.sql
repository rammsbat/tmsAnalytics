{#-
  ST-7: CAT_UBICACIONES. Codigos de paradas TrackIt y de origen/destino de Carta Porte; el nombre sale de
  TrackIt y la geografia (CP, estado, lat/long) del seed (H6). Sin geografia: CP '00000'.
-#}
{{ config(alias='CAT_UBICACIONES', unique_key='CODIGO_UBICACION') }}
with stops as (
    select CODIGO_UBICACION, NOMBRE_UBICACION, INGESTED_AT, BATCH_ID
    from {{ ref('stg_trackit_paradas') }}
    union all
    select UBICACION_ORIGEN_CP, cast(null as varchar2(100)), INGESTED_AT, BATCH_ID
    from {{ ref('stg_carta_porte_cabecera') }}
    union all
    select UBICACION_DESTINO_CP, cast(null as varchar2(100)), INGESTED_AT, BATCH_ID
    from {{ ref('stg_carta_porte_cabecera') }}
),

named as (
    select
        CODIGO_UBICACION,
        max(NOMBRE_UBICACION) keep (dense_rank last order by case when NOMBRE_UBICACION is null then 0 else 1 end, INGESTED_AT, BATCH_ID) as NOMBRE_UBICACION,
        max(BATCH_ID) keep (dense_rank last order by INGESTED_AT, BATCH_ID) as BATCH_ID
    from stops
    where CODIGO_UBICACION is not null
    group by CODIGO_UBICACION
)

select
    n.CODIGO_UBICACION                                  as CODIGO_UBICACION,
    coalesce(g.nombre_ubicacion, n.NOMBRE_UBICACION, n.CODIGO_UBICACION) as NOMBRE_UBICACION,
    coalesce(g.codigo_postal, '00000')                  as CODIGO_POSTAL,
    g.estado                                            as ESTADO,
    g.municipio                                         as MUNICIPIO,
    g.latitud                                           as LATITUD,
    g.longitud                                          as LONGITUD,
    coalesce(g.tipo_ubicacion, 'PLANTA_CEDIS')          as TIPO_UBICACION,
    n.BATCH_ID                                          as BATCH_ID
from named n
left join {{ ref('seed_geo_ubicaciones') }} g
    on upper(trim(g.codigo_ubicacion)) = n.CODIGO_UBICACION
