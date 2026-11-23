{#-
  ST-8: DIM_HORA (PK natural HHMM, sin IDENTITY): 1,440 minutos del dia (00:00..23:59). La fila -1 (DDL 04 §2.2)
  no se genera aqui; protect_column evita que el UPDATE la toque. ID_HORA = 0 (00:00) es una fila valida distinta de -1.
-#}
{{ config(alias='DIM_HORA', unique_key='ID_HORA', protect_column='ID_HORA') }}
with minutos as (
    select level - 1 as MIN_DIA
    from dual
    connect by level <= 1440
),

hm as (
    select trunc(MIN_DIA / 60) as H, mod(MIN_DIA, 60) as M
    from minutos
)

select
    H * 100 + M                                         as ID_HORA,
    H                                                   as HORA_24,
    case when mod(H, 12) = 0 then 12 else mod(H, 12) end as HORA_12,
    M                                                   as MINUTO,
    case when H < 12 then 'AM' else 'PM' end            as AM_PM,
    case
        when H < 6  then 'MADRUGADA'
        when H < 12 then 'MAÑANA'
        when H < 19 then 'TARDE'
        else 'NOCHE'
    end                                                 as PERIODO_DIA
from hm
