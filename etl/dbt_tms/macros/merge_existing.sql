{#-
  Materializacion `merge_existing` (D1, P2; validada en ST-0).

  Emite un MERGE directo sobre una tabla PREEXISTENTE (EDW_3FN / DWH_MART) sin crear
  objetos en el esquema destino. Motivo: el `incremental` nativo falla si el modelo omite
  columnas del destino (p. ej. la SK IDENTITY).

  Config:
    unique_key           (obligatorio) columna o lista de columnas de la clausula ON.
    merge_exclude_columns (opcional)   columnas del destino que el UPDATE no debe tocar.
    protect_column       (opcional)   columna numerica cuyo valor -1 identifica la fila dummy
                         y que el UPDATE nunca debe tocar. Por defecto, la primera columna
                         IDENTITY del destino; si la tabla no tiene IDENTITY ni se configura,
                         NO se emite predicado de proteccion (nunca un `where` vacio).
                         Usar en tablas con PK natural (DIM_FECHA: ID_FECHA, DIM_HORA: ID_HORA).

  Reglas (P2):
    * INSERT: solo columnas presentes en el modelo y en el destino; las IDENTITY se omiten.
    * UPDATE SET: excluye columnas del ON (evita ORA-38104), columnas IDENTITY y CREATED_AT.
      Si el modelo no aporta UPDATED_AT y el destino la tiene, se fija en SYSTIMESTAMP.
    * Fila dummy -1: el UPDATE se protege con `<protect_column> <> -1` cuando aplica.
    * Nunca hace DROP/CREATE: `--full-refresh` no tiene efecto.
-#}

{#- Valida que un identificador provenga de dbt como identificador Oracle simple. -#}
{% macro _assert_oracle_identifier(value) -%}
    {%- if not modules.re.match('^[A-Za-z0-9_$#]+$', value | string) -%}
        {{ exceptions.raise_compiler_error("Identificador Oracle no valido: " ~ value) }}
    {%- endif -%}
{%- endmacro %}

{#- Columnas IDENTITY de una tabla (lista en mayusculas). -#}
{% macro get_identity_columns(relation) -%}
    {%- do _assert_oracle_identifier(relation.schema) -%}
    {%- do _assert_oracle_identifier(relation.identifier) -%}
    {%- set query -%}
        select column_name
          from all_tab_identity_cols
         where owner = upper('{{ relation.schema }}')
           and table_name = upper('{{ relation.identifier }}')
    {%- endset -%}
    {%- set result = run_query(query) -%}
    {%- set cols = [] -%}
    {%- for row in result.rows -%}
        {%- do cols.append(row[0] | upper) -%}
    {%- endfor -%}
    {{ return(cols) }}
{%- endmacro %}

{#- Todas las columnas de una tabla en orden fisico (lista en mayusculas). -#}
{% macro get_table_column_names(relation) -%}
    {%- do _assert_oracle_identifier(relation.schema) -%}
    {%- do _assert_oracle_identifier(relation.identifier) -%}
    {%- set query -%}
        select column_name
          from all_tab_columns
         where owner = upper('{{ relation.schema }}')
           and table_name = upper('{{ relation.identifier }}')
         order by column_id
    {%- endset -%}
    {%- set result = run_query(query) -%}
    {%- set cols = [] -%}
    {%- for row in result.rows -%}
        {%- do cols.append(row[0] | upper) -%}
    {%- endfor -%}
    {{ return(cols) }}
{%- endmacro %}

{#- Columnas que devuelve un SELECT (sin leer filas). -#}
{% macro get_query_column_names(select_sql) -%}
    {%- set result = run_query('select * from (' ~ select_sql ~ ') where 1 = 0') -%}
    {%- set cols = [] -%}
    {%- for name in result.column_names -%}
        {%- do cols.append(name | upper) -%}
    {%- endfor -%}
    {{ return(cols) }}
{%- endmacro %}

{#- Normaliza `unique_key` a lista de columnas en mayusculas. -#}
{% macro _as_upper_list(value) -%}
    {%- set out = [] -%}
    {%- if value is string -%}
        {%- do out.append(value | upper) -%}
    {%- elif value is iterable -%}
        {%- for item in value -%}
            {%- do out.append(item | upper) -%}
        {%- endfor -%}
    {%- endif -%}
    {{ return(out) }}
{%- endmacro %}

{#- Construye el MERGE (P2). Se separa de la materializacion para poder inspeccionarlo. -#}
{% macro build_merge_existing_sql(target_relation, select_sql, on_cols, src_cols, target_cols, identity_cols, exclude_cols, protect_col=none) -%}
    {%- set insert_cols = [] -%}
    {%- for c in target_cols -%}
        {%- if c in src_cols and c not in identity_cols -%}
            {%- do insert_cols.append(c) -%}
        {%- endif -%}
    {%- endfor -%}

    {%- set update_cols = [] -%}
    {%- for c in insert_cols -%}
        {%- if c not in on_cols and c not in exclude_cols and c != 'CREATED_AT' -%}
            {%- do update_cols.append(c) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- set touch_updated_at = ('UPDATED_AT' in target_cols and 'UPDATED_AT' not in src_cols
                                and 'UPDATED_AT' not in on_cols and 'UPDATED_AT' not in exclude_cols) -%}

    merge into {{ target_relation }} t
    using (
{{ select_sql }}
    ) s
    on ({% for c in on_cols %}t.{{ c }} = s.{{ c }}{% if not loop.last %} and {% endif %}{% endfor %})
    {% if update_cols | length > 0 or touch_updated_at -%}
    when matched then update set
        {%- for c in update_cols %}
        t.{{ c }} = s.{{ c }}{% if not loop.last or touch_updated_at %},{% endif %}
        {%- endfor %}
        {%- if touch_updated_at %}
        t.UPDATED_AT = systimestamp
        {%- endif %}
        {%- if protect_col %}
        where t.{{ protect_col }} <> -1
        {%- endif %}
    {% endif -%}
    when not matched then insert (
        {%- for c in insert_cols %}{{ c }}{% if not loop.last %}, {% endif %}{% endfor -%}
    ) values (
        {%- for c in insert_cols %}s.{{ c }}{% if not loop.last %}, {% endif %}{% endfor -%}
    )
{%- endmacro %}

{% materialization merge_existing, adapter='oracle' %}

    {%- set unique_key = config.get('unique_key') -%}
    {%- if unique_key is none -%}
        {{ exceptions.raise_compiler_error("merge_existing requiere config(unique_key=...) en " ~ this) }}
    {%- endif -%}
    {%- set on_cols = _as_upper_list(unique_key) -%}
    {%- set exclude_cols = _as_upper_list(config.get('merge_exclude_columns', [])) -%}

    {%- set target_relation = this.incorporate(type='table') -%}
    {%- set existing_relation = load_relation(this) -%}
    {%- if existing_relation is none -%}
        {{ exceptions.raise_compiler_error("merge_existing: la tabla destino " ~ this ~ " debe existir (DDL en oracle/ddl/).") }}
    {%- endif -%}

    {{ run_hooks(pre_hooks, inside_transaction=False) }}
    {{ run_hooks(pre_hooks, inside_transaction=True) }}

    {%- set target_cols = get_table_column_names(target_relation) -%}
    {%- set identity_cols = get_identity_columns(target_relation) -%}
    {%- set src_cols = get_query_column_names(sql) -%}

    {%- for c in on_cols -%}
        {%- if c not in src_cols or c not in target_cols -%}
            {{ exceptions.raise_compiler_error("merge_existing: la columna ON " ~ c ~ " no existe en el modelo o en " ~ this) }}
        {%- endif -%}
        {%- if c in identity_cols -%}
            {{ exceptions.raise_compiler_error("merge_existing: la columna ON " ~ c ~ " es IDENTITY en " ~ this ~ "; use la llave natural") }}
        {%- endif -%}
    {%- endfor -%}

    {#- Columna de proteccion de la fila -1: configurada, o la primera IDENTITY; sin ninguna => sin predicado. -#}
    {%- set configured_protect = config.get('protect_column') -%}
    {%- if configured_protect -%}
        {%- set protect_col = configured_protect | upper -%}
        {%- if protect_col not in target_cols -%}
            {{ exceptions.raise_compiler_error("merge_existing: protect_column " ~ protect_col ~ " no existe en " ~ this) }}
        {%- endif -%}
    {%- elif identity_cols | length > 0 -%}
        {%- set protect_col = identity_cols[0] -%}
    {%- else -%}
        {%- set protect_col = none -%}
    {%- endif -%}

    {%- set merge_sql = build_merge_existing_sql(target_relation, sql, on_cols, src_cols, target_cols, identity_cols, exclude_cols, protect_col) -%}

    {% call statement('main') -%}
        {{ merge_sql }}
    {%- endcall %}

    {{ run_hooks(post_hooks, inside_transaction=True) }}
    {% do adapter.commit() %}
    {{ run_hooks(post_hooks, inside_transaction=False) }}

    {{ return({'relations': [target_relation]}) }}

{% endmaterialization %}
