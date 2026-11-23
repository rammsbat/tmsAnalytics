{#- Test generico: unicidad de una combinacion de columnas (sin depender de dbt_utils). -#}
{% test unique_combination(model, combination_of_columns) %}

select
    {{ combination_of_columns | join(', ') }},
    count(*) as n_records
from {{ model }}
group by {{ combination_of_columns | join(', ') }}
having count(*) > 1

{% endtest %}
