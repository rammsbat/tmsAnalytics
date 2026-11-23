{#- D3: usar el nombre de esquema personalizado tal cual (EDW_3FN / DWH_MART),
    sin el prefijo <target.schema>_ que aplica dbt por defecto. Verificado en ST-0. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
