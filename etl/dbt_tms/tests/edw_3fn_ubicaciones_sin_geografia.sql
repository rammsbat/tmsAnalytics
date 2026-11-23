{#- ST-7 (H6): toda ubicacion de EDW_3FN debe tener geografia del seed; CP '00000' indica codigo sin cobertura. Devuelve filas = falla. -#}
select CODIGO_UBICACION
from {{ ref('cat_ubicaciones') }}
where CODIGO_POSTAL = '00000'
   or ESTADO is null
   or LATITUD is null
   or LONGITUD is null
