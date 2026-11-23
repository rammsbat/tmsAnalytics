{#-
  Helpers de la capa marts (ST-8/ST-9).
-#}

{#- Etapa del viaje a partir de ESTATUS_DESPACHO (A3). Fuente unica para DIM_PERFIL_VIAJE y FACT_DESPACHO_VIAJE. -#}
{% macro etapa_viaje(estatus_col) -%}
    case {{ estatus_col }}
        when 'EN_TRANSITO' then 'TRANSITO'
        when 'CERRADO'     then 'CERRADO'
        else {{ estatus_col }}
    end
{%- endmacro %}

{#- Minutos (2 decimales) entre dos TIMESTAMP: later - earlier. NULL si alguno es NULL. -#}
{% macro minutes_between(later, earlier) -%}
    round(
        extract(day    from ({{ later }} - {{ earlier }})) * 1440
      + extract(hour   from ({{ later }} - {{ earlier }})) * 60
      + extract(minute from ({{ later }} - {{ earlier }}))
      + extract(second from ({{ later }} - {{ earlier }})) / 60
    , 2)
{%- endmacro %}

{#-
  Lookup point-in-time en DIM_VEHICULO (A5): version vigente a la fecha del evento, sin fila -1.
    alias     alias del JOIN (p. ej. dv)
    eco_expr  expresion con el CODIGO_ECO natural
    date_expr expresion DATE/TIMESTAMP del evento (se trunca)
  Uso:  {{ vehiculo_asof_join('dv', 'cv.CODIGO_ECO', 'd.FECHA_DESPACHO') }}   ->   nvl(dv.ID_VEHICULO, -1)
-#}
{% macro vehiculo_asof_join(alias, eco_expr, date_expr) -%}
    left join {{ ref('dim_vehiculo') }} {{ alias }}
        on  {{ alias }}.CODIGO_ECO = {{ eco_expr }}
        and {{ alias }}.ID_VEHICULO <> -1
        and trunc({{ date_expr }}) between {{ alias }}.FECHA_INICIO_VALIDEZ
                                       and nvl({{ alias }}.FECHA_FIN_VALIDEZ, date '2099-12-31')
{%- endmacro %}

{#- Llave de DIM_FECHA para una fecha/timestamp; NULL o fuera del calendario -> -1 (nunca NULL en FKs). -#}
{% macro dim_fecha_key(date_expr) -%}
    nvl((select f.ID_FECHA from {{ ref('dim_fecha') }} f
          where f.ID_FECHA = to_number(to_char({{ date_expr }}, 'YYYYMMDD'))), -1)
{%- endmacro %}

{#- Llave de DIM_HORA (HHMM) para un timestamp; NULL o fuera del rango -> -1. -#}
{% macro dim_hora_key(ts_expr) -%}
    nvl((select h.ID_HORA from {{ ref('dim_hora') }} h
          where h.ID_HORA = to_number(to_char({{ ts_expr }}, 'HH24MI'))), -1)
{%- endmacro %}