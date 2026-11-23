{#-
  ST-8: DIM_FECHA (PK natural YYYYMMDD, sin IDENTITY). Rango configurable por vars (2026-01-01..2026-12-31).
  Robusta ante NLS de sesion/BD:
    * nombres de mes/dia: NLS_DATE_LANGUAGE=SPANISH explicito con formato FM (sin relleno);
    * DIA_SEMANA: ISO 1=lunes..7=domingo calculado con TRUNC(.,'IW') (no usa el formato 'D', que depende de NLS_TERRITORY);
    * ES_FIN_SEMANA_FLAG: TO_CHAR(.,'DY','NLS_DATE_LANGUAGE=ENGLISH') IN ('SAT','SUN');
    * SEMANA_ANIO: semana ISO ('IW').
  La fila -1 (DDL 04 §2.1) no se genera aqui; protect_column evita que el UPDATE la toque.
-#}
{%- set d_ini = var('dim_fecha_inicio') -%}
{%- set d_fin = var('dim_fecha_fin') -%}
{%- if not modules.re.match('^[0-9]{4}-[0-9]{2}-[0-9]{2}$', d_ini) or not modules.re.match('^[0-9]{4}-[0-9]{2}-[0-9]{2}$', d_fin) -%}
    {{ exceptions.raise_compiler_error("dim_fecha_inicio/dim_fecha_fin deben tener formato YYYY-MM-DD") }}
{%- endif -%}
{{ config(alias='DIM_FECHA', unique_key='ID_FECHA', protect_column='ID_FECHA') }}
with dias as (
    select date '{{ d_ini }}' + level - 1 as FECHA
    from dual
    connect by level <= (date '{{ d_fin }}' - date '{{ d_ini }}') + 1
)
select
    to_number(to_char(FECHA, 'YYYYMMDD'))                                                  as ID_FECHA,
    FECHA                                                                                  as FECHA,
    to_number(to_char(FECHA, 'YYYY'))                                                      as ANIO,
    to_number(to_char(FECHA, 'MM'))                                                        as MES,
    initcap(to_char(FECHA, 'FMMonth', 'NLS_DATE_LANGUAGE=SPANISH'))                        as NOMBRE_MES,
    to_number(to_char(FECHA, 'DD'))                                                        as DIA,
    to_number(FECHA - trunc(FECHA, 'IW')) + 1                                              as DIA_SEMANA,
    initcap(to_char(FECHA, 'FMDay', 'NLS_DATE_LANGUAGE=SPANISH'))                          as NOMBRE_DIA,
    to_number(to_char(FECHA, 'Q'))                                                         as TRIMESTRE,
    case when to_number(to_char(FECHA, 'MM')) <= 6 then 1 else 2 end                       as SEMESTRE,
    to_number(to_char(FECHA, 'IW'))                                                        as SEMANA_ANIO,
    case when to_char(FECHA, 'DY', 'NLS_DATE_LANGUAGE=ENGLISH') in ('SAT', 'SUN')
         then '1' else '0' end                                                             as ES_FIN_SEMANA_FLAG
from dias
