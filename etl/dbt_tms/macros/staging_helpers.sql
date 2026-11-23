{#- Helpers de limpieza para los modelos `staging` (ST-6). Solo generan SQL Oracle estandar. -#}

{#- Texto libre: elimina espacios laterales ('' pasa a NULL por semantica Oracle). -#}
{% macro clean_text(col) -%}
    trim({{ col }})
{%- endmacro %}

{#- Codigos/folios/claves: sin espacios laterales y en mayusculas. -#}
{% macro clean_code(col) -%}
    upper(trim({{ col }}))
{%- endmacro %}

{#- RFC: mayusculas y sin ningun espacio en blanco (incluye interiores). -#}
{% macro clean_rfc(col) -%}
    upper(regexp_replace({{ col }}, '\s', ''))
{%- endmacro %}
