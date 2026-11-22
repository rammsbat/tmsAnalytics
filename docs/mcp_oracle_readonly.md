# Servidor MCP Oracle de solo lectura (`tools/oracle_mcp`)

Servidor MCP propio que da a Bob acceso de lectura a Oracle (`localhost:1521/FREEPDB1`) como `BI_READER`.

## Herramientas expuestas

| Herramienta | Función |
|---|---|
| `list_objects(schema?)` | Lista tablas, vistas y vistas materializadas de `BI_SEMANTIC` y `DWH_MART`. |
| `describe_object(schema, name)` | Columnas, tipos y comentarios (`ALL_TAB_COLUMNS` + `ALL_COL_COMMENTS`). |
| `run_readonly_query(sql, max_rows=100)` | Una sola sentencia `SELECT`/`WITH`. Máximo 500 filas. |

## Doble capa de solo lectura

1. **Validador de SQL (cliente):** rechaza `;` múltiples, DDL/DML, `FOR UPDATE`, `INTO`, `@` (db links), `DBMS_*`/`UTL_*` y los esquemas `EDW_3FN`, `STG_SRC`, `SYS`, `SYSTEM`, `DBA_*`, `V$*`. Ignora comentarios y literales antes de inspeccionar.
2. **Base de datos:** cada consulta corre tras `SET TRANSACTION READ ONLY` y con el usuario `BI_READER`, que solo tiene `SELECT` sobre `BI_SEMANTIC` y `DWH_MART`. Ambas capas son independientes: aunque el validador fallara, Oracle rechazaría la escritura (ORA-41900 / ORA-01031) y el acceso a `EDW_3FN`.

## Credenciales

- El servidor lee `BI_READER_PWD` de `os.environ`; si no existe, del `.env` de la raíz (`python-dotenv`).
- `.bob/mcp.json` no contiene secretos ni bloque `env`. Un `${env:BI_READER_PWD}` sin definir quedaría como texto literal y tendría prioridad sobre `.env`.
- Los errores se filtran para no incluir la contraseña. No se registran URIs de conexión. Los logs van a `stderr`.

## Ejecución y pruebas

```powershell
uv sync --directory tools/oracle_mcp
uv run --directory tools/oracle_mcp python smoke_test.py
```

`mcp` está fijado a `<2` porque la v2 renombró `FastMCP`. El entorno `tools/oracle_mcp/.venv/` está en `.gitignore` y `.bobignore`.

Requisito de entorno: el contenedor `tms-oracle-dw` debe estar levantado y `BI_READER_PWD` definida en `.env`.
