{#-
  ST-9 (regla 01-kimball §2): ningun modelo FACT_* puede referenciar otro FACT_* (cero Fact-to-Fact).
  Inspecciona el grafo de dbt: devuelve una fila por modelo de marts/facts que (a) dependa por ref() de otro modelo fact_*
  o (b) contenga en su CODIGO (sin comentarios Jinja) una referencia textual a otra tabla fact_ (p. ej. DWH_MART.FACT_X).
  Filas = falla.
-#}
{%- set offenders = [] -%}
{%- for node in graph.nodes.values() if node.resource_type == 'model' and node.path.startswith('marts/facts/') -%}
    {%- for dep in node.depends_on.nodes -%}
        {%- if dep.split('.')[-1].startswith('fact_') -%}
            {%- do offenders.append(node.name ~ ' -> ' ~ dep.split('.')[-1]) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- set code = modules.re.sub('\\{#.*?#\\}', '', node.raw_code, flags=modules.re.DOTALL) | lower | replace(node.name, '') -%}
    {%- if 'fact_' in code -%}
        {%- do offenders.append(node.name ~ ' (el codigo referencia otra tabla fact_)') -%}
    {%- endif -%}
{%- endfor -%}
{%- if offenders | length == 0 -%}
select cast(null as varchar2(200)) as VIOLACION from dual where 1 = 0
{%- else -%}
    {%- for o in offenders %}
select '{{ o }}' as VIOLACION from dual{% if not loop.last %} union all{% endif %}
    {%- endfor %}
{%- endif -%}
