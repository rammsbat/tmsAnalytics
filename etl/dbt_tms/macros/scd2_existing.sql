{#-
  Materializacion `scd2_existing` (D4, A5, A6, P2, P3).

  SCD Tipo 2 sobre una tabla de dimension PREEXISTENTE (p. ej. DWH_MART.DIM_VEHICULO)
  sin `dbt snapshot` y sin crear objetos. El modelo devuelve el estado ACTUAL por llave
  natural (una fila por llave) mas la fecha efectiva del cambio.

  Config:
    unique_key           (obligatorio) llave natural (columna o lista).
    tracked_columns      (obligatorio) atributos SCD2 (A6); un cambio abre nueva version.
    initial_start_date   (obligatorio) expresion SQL de FECHA_INICIO_VALIDEZ para llaves
                         nuevas (A5), p. ej. "date '2026-08-09'". Nunca 1900-01-01 (reservada a -1).
    effective_date_column (def. FECHA_EFECTIVA) columna del modelo con la fecha efectiva del
                         cambio; no se inserta (solo gobierna cierre/apertura).
    start_column / end_column / active_column
                         (def. FECHA_INICIO_VALIDEZ / FECHA_FIN_VALIDEZ / VERSION_ACTIVA).

  Algoritmo (una transaccion, dos sentencias):
    1) CIERRE: MERGE sobre la llave natural; si la version activa difiere en alguna columna
       rastreada (comparacion NULL-safe con DECODE) y la fecha efectiva es POSTERIOR al inicio
       de esa version, fija FECHA_FIN_VALIDEZ = fecha_efectiva - 1 y VERSION_ACTIVA = '0'.
       La condicion VERSION_ACTIVA='1' va en el WHERE del UPDATE (no en el ON) para no
       actualizar columnas del ON (ORA-38104).
    2) APERTURA: INSERT de una version activa para cada llave sin version activa. Inicio =
       fecha_efectiva si la llave ya tenia historia; si es nueva, `initial_start_date`.
       Las columnas IDENTITY se omiten del INSERT (P2); FECHA_FIN_VALIDEZ queda NULL.

  Garantias:
    * Idempotente: sin cambios rastreados no hay cierre ni apertura.
    * A lo mas una version activa por llave natural.
    * Fila dummy -1 intacta: el cierre exige `<IDENTITY> <> -1` y el INSERT no la toca.
    * P3: una fecha efectiva <= inicio de la version activa se IGNORA (evita violar
      UQ (llave, FECHA_INICIO_VALIDEZ) y vigencias invertidas). Los atributos NO rastreados
      conservan su valor al crear la version (no se sobrescriben).
-#}

{#- Condicion NULL-safe "alguna columna rastreada difiere" entre destino (t) y modelo (s). -#}
{% macro scd2_changed_predicate(tracked_cols) -%}
    (
    {%- for c in tracked_cols %}
        decode(t.{{ c }}, s.{{ c }}, 0, 1) = 1{% if not loop.last %} or{% endif %}
    {%- endfor %}
    )
{%- endmacro %}

{% macro build_scd2_close_sql(target_relation, select_sql, key_cols, tracked_cols, identity_cols, eff_col, start_col, end_col, active_col) -%}
    merge into {{ target_relation }} t
    using (
{{ select_sql }}
    ) s
    on ({% for c in key_cols %}t.{{ c }} = s.{{ c }}{% if not loop.last %} and {% endif %}{% endfor %})
    when matched then update set
        t.{{ end_col }} = s.{{ eff_col }} - 1,
        t.{{ active_col }} = '0'
    where t.{{ active_col }} = '1'
      {%- if identity_cols | length > 0 %}
      and t.{{ identity_cols[0] }} <> -1
      {%- endif %}
      and s.{{ eff_col }} > t.{{ start_col }}
      and {{ scd2_changed_predicate(tracked_cols) }}
{%- endmacro %}

{% macro build_scd2_open_sql(target_relation, select_sql, key_cols, insert_cols, eff_col, start_col, end_col, active_col, initial_start_date) -%}
    insert into {{ target_relation }} (
        {%- for c in insert_cols %}{{ c }}, {% endfor -%}
        {{ start_col }}, {{ end_col }}, {{ active_col }}
    )
    select
        {%- for c in insert_cols %} s.{{ c }},{% endfor %}
        case
            when exists (
                select 1 from {{ target_relation }} h
                 where {% for c in key_cols %}h.{{ c }} = s.{{ c }}{% if not loop.last %} and {% endif %}{% endfor %}
            ) then s.{{ eff_col }}
            else {{ initial_start_date }}
        end,
        cast(null as date),
        '1'
      from (
{{ select_sql }}
      ) s
     where not exists (
        select 1 from {{ target_relation }} a
         where {% for c in key_cols %}a.{{ c }} = s.{{ c }} and {% endfor %}a.{{ active_col }} = '1'
     )
{%- endmacro %}

{% materialization scd2_existing, adapter='oracle' %}

    {%- set key_cols = _as_upper_list(config.get('unique_key')) -%}
    {%- set tracked_cols = _as_upper_list(config.get('tracked_columns')) -%}
    {%- set initial_start_date = config.get('initial_start_date') -%}
    {%- set eff_col = (config.get('effective_date_column', 'FECHA_EFECTIVA')) | upper -%}
    {%- set start_col = (config.get('start_column', 'FECHA_INICIO_VALIDEZ')) | upper -%}
    {%- set end_col = (config.get('end_column', 'FECHA_FIN_VALIDEZ')) | upper -%}
    {%- set active_col = (config.get('active_column', 'VERSION_ACTIVA')) | upper -%}

    {%- if key_cols | length == 0 or tracked_cols | length == 0 or not initial_start_date -%}
        {{ exceptions.raise_compiler_error("scd2_existing requiere unique_key, tracked_columns e initial_start_date en " ~ this) }}
    {%- endif -%}

    {%- set target_relation = this.incorporate(type='table') -%}
    {%- set existing_relation = load_relation(this) -%}
    {%- if existing_relation is none -%}
        {{ exceptions.raise_compiler_error("scd2_existing: la tabla destino " ~ this ~ " debe existir (DDL en oracle/ddl/).") }}
    {%- endif -%}

    {{ run_hooks(pre_hooks, inside_transaction=False) }}
    {{ run_hooks(pre_hooks, inside_transaction=True) }}

    {%- set target_cols = get_table_column_names(target_relation) -%}
    {%- set identity_cols = get_identity_columns(target_relation) -%}
    {%- set src_cols = get_query_column_names(sql) -%}

    {%- for c in key_cols + tracked_cols + [eff_col] -%}
        {%- if c not in src_cols -%}
            {{ exceptions.raise_compiler_error("scd2_existing: la columna " ~ c ~ " no existe en el modelo " ~ this) }}
        {%- endif -%}
    {%- endfor -%}
    {%- for c in key_cols + tracked_cols + [start_col, end_col, active_col] -%}
        {%- if c not in target_cols -%}
            {{ exceptions.raise_compiler_error("scd2_existing: la columna " ~ c ~ " no existe en " ~ this) }}
        {%- endif -%}
    {%- endfor -%}

    {#- Columnas a insertar: presentes en modelo y destino, sin IDENTITY ni columnas SCD2 de control. -#}
    {%- set control_cols = [start_col, end_col, active_col, eff_col] -%}
    {%- set insert_cols = [] -%}
    {%- for c in target_cols -%}
        {%- if c in src_cols and c not in identity_cols and c not in control_cols -%}
            {%- do insert_cols.append(c) -%}
        {%- endif -%}
    {%- endfor -%}

    {% call statement('scd2_close') -%}
        {{ build_scd2_close_sql(target_relation, sql, key_cols, tracked_cols, identity_cols, eff_col, start_col, end_col, active_col) }}
    {%- endcall %}

    {% call statement('main') -%}
        {{ build_scd2_open_sql(target_relation, sql, key_cols, insert_cols, eff_col, start_col, end_col, active_col, initial_start_date) }}
    {%- endcall %}

    {{ run_hooks(post_hooks, inside_transaction=True) }}
    {% do adapter.commit() %}
    {{ run_hooks(post_hooks, inside_transaction=False) }}

    {{ return({'relations': [target_relation]}) }}

{% endmaterialization %}
