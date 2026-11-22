"""Servidor MCP de solo lectura para Oracle (Analytics TMS).

- python-oracledb en Thin Mode (sin Instant Client), usuario fijo BI_READER.
- Doble capa de solo lectura:
    1) Validador de SQL (una sola sentencia SELECT/WITH, sin DDL/DML, sin esquemas prohibidos).
    2) Sesion con SET TRANSACTION READ ONLY + privilegios minimos del usuario BI_READER.
- La contrasena se lee de os.environ["BI_READER_PWD"], con respaldo en el .env de la raiz
  del repositorio. Nunca se imprime ni se incluye en respuestas/logs.
- Toda salida de diagnostico va a stderr (stdout es el canal del protocolo MCP).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)  # os.environ tiene prioridad sobre .env

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("oracle_mcp")

DB_USER = "BI_READER"
DB_HOST = "localhost"
DB_PORT = 1521
DB_SERVICE = "FREEPDB1"
ALLOWED_SCHEMAS = ("BI_SEMANTIC", "DWH_MART")
OBJECT_TYPES = ("TABLE", "VIEW", "MATERIALIZED VIEW")
DEFAULT_ROWS = 100
MAX_ROWS = 500
CALL_TIMEOUT_MS = 30_000

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|RENAME|COMMENT|"
    r"EXECUTE|EXEC|CALL|BEGIN|DECLARE|COMMIT|ROLLBACK|SAVEPOINT|LOCK|EXPLAIN|ANALYZE|AUDIT|"
    r"INTO|PRAGMA|DBMS_\w*|UTL_\w*|FOR\s+UPDATE)\b"
)
FORBIDDEN_SCHEMAS = re.compile(
    r"\b(EDW_3FN|STG_SRC|SYS|SYSTEM|DBA_\w+|V\$\w+|GV\$\w+|X\$\w+)\b"
)

mcp = FastMCP("tms-oracle-readonly")


class SqlRejected(ValueError):
    """La sentencia no cumple la politica de solo lectura."""


def _sanitize(sql: str) -> str:
    """Quita comentarios, literales de texto e identificadores entre comillas.

    Devuelve el SQL en mayusculas listo para inspeccion. Lanza SqlRejected si hay
    literales/comentarios sin cerrar o literales q'...' (no soportados).
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if c == "-" and nxt == "-":
            j = sql.find("\n", i)
            i = n if j == -1 else j
            out.append(" ")
        elif c == "/" and nxt == "*":
            j = sql.find("*/", i + 2)
            if j == -1:
                raise SqlRejected("Comentario de bloque sin cerrar.")
            i = j + 2
            out.append(" ")
        elif c == "'":
            if i > 0 and sql[i - 1] in "qQ" and (i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] in "_$#")):
                raise SqlRejected("Literales q'...' no soportados.")
            j = i + 1
            while True:
                j = sql.find("'", j)
                if j == -1:
                    raise SqlRejected("Literal de texto sin cerrar.")
                if sql[j + 1 : j + 2] == "'":
                    j += 2
                    continue
                break
            i = j + 1
            out.append("''")
        elif c == '"':
            j = sql.find('"', i + 1)
            if j == -1:
                raise SqlRejected("Identificador entre comillas sin cerrar.")
            out.append(" " + sql[i + 1 : j] + " ")
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out).upper()


def validate_readonly_sql(sql: str) -> str:
    """Valida y devuelve el SQL original sin ';' final. Lanza SqlRejected si no es seguro."""
    if not sql or not sql.strip():
        raise SqlRejected("Consulta vacia.")
    clean = _sanitize(sql).strip()
    original = sql.strip()
    if clean.endswith(";"):  # un unico ';' final es tolerado
        clean = clean[:-1].rstrip()
        original = original[:-1].rstrip()
    if ";" in clean:
        raise SqlRejected("Solo se permite una unica sentencia (sin ';' multiples).")
    if "@" in clean:
        raise SqlRejected("Database links (@) no permitidos.")
    if not re.match(r"(SELECT|WITH)\b", clean):
        raise SqlRejected("Solo se permiten sentencias SELECT o WITH.")
    m = FORBIDDEN_KEYWORDS.search(clean)
    if m:
        raise SqlRejected(f"Palabra reservada no permitida: {m.group(0)}.")
    m = FORBIDDEN_SCHEMAS.search(clean)
    if m:
        raise SqlRejected(
            f"Acceso no permitido a {m.group(0)}. Solo se consultan {', '.join(ALLOWED_SCHEMAS)}."
        )
    return original


def _password() -> str:
    pwd = os.environ.get("BI_READER_PWD")
    if not pwd:
        raise RuntimeError("BI_READER_PWD no esta definida (ni en el entorno ni en .env).")
    return pwd


def _safe_msg(exc: BaseException) -> str:
    """Mensaje de error sin la contrasena."""
    msg = str(exc)
    pwd = os.environ.get("BI_READER_PWD")
    if pwd:
        msg = msg.replace(pwd, "***")
    return msg


def _connect() -> oracledb.Connection:
    # Thin Mode: no se llama a init_oracle_client().
    conn = oracledb.connect(
        user=DB_USER,
        password=_password(),
        host=DB_HOST,
        port=DB_PORT,
        service_name=DB_SERVICE,
    )
    conn.call_timeout = CALL_TIMEOUT_MS
    return conn


def _fetch(sql: str, binds: dict[str, Any] | None = None, max_rows: int = MAX_ROWS) -> dict[str, Any]:
    """Ejecuta una consulta en una transaccion READ ONLY y devuelve columnas/filas."""
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.arraysize = min(max_rows + 1, 500)
            cur.execute(sql, binds or {})
            columns = [d[0] for d in cur.description]
            rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]
        return {
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }
    finally:
        conn.rollback()
        conn.close()


def _dump(payload: Any) -> str:
    return json.dumps(payload, default=str, ensure_ascii=False)


def _error(exc: BaseException) -> str:
    if isinstance(exc, SqlRejected):
        return _dump({"error": "BLOQUEADO", "detail": str(exc)})
    log.error("Fallo de base de datos: %s", _safe_msg(exc))
    return _dump({"error": "DB_ERROR", "detail": _safe_msg(exc)})


@mcp.tool()
def list_objects(schema: str | None = None) -> str:
    """Lista tablas, vistas y vistas materializadas de BI_SEMANTIC y DWH_MART.

    Args:
        schema: opcional, 'BI_SEMANTIC' o 'DWH_MART'. Si se omite, lista ambos.
    """
    try:
        owners = ALLOWED_SCHEMAS
        if schema:
            if schema.upper() not in ALLOWED_SCHEMAS:
                raise SqlRejected(f"Esquema no permitido. Use: {', '.join(ALLOWED_SCHEMAS)}.")
            owners = (schema.upper(),)
        sql = (
            "SELECT owner, object_name, object_type FROM all_objects "
            "WHERE owner IN (:o1, :o2) AND object_type IN (:t1, :t2, :t3) "
            "ORDER BY owner, object_type, object_name"
        )
        binds = {
            "o1": owners[0],
            "o2": owners[-1],
            "t1": OBJECT_TYPES[0],
            "t2": OBJECT_TYPES[1],
            "t3": OBJECT_TYPES[2],
        }
        return _dump(_fetch(sql, binds, max_rows=MAX_ROWS))
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@mcp.tool()
def describe_object(schema: str, name: str) -> str:
    """Describe columnas y comentarios de una tabla/vista de BI_SEMANTIC o DWH_MART.

    Args:
        schema: 'BI_SEMANTIC' o 'DWH_MART'.
        name: nombre del objeto (p. ej. 'VW_DIM_VEHICULO').
    """
    try:
        if schema.upper() not in ALLOWED_SCHEMAS:
            raise SqlRejected(f"Esquema no permitido. Use: {', '.join(ALLOWED_SCHEMAS)}.")
        sql = (
            "SELECT c.column_id, c.column_name, c.data_type, c.data_length, c.data_precision, "
            "c.data_scale, c.nullable, m.comments "
            "FROM all_tab_columns c "
            "LEFT JOIN all_col_comments m "
            "  ON m.owner = c.owner AND m.table_name = c.table_name AND m.column_name = c.column_name "
            "WHERE c.owner = :owner AND c.table_name = :name "
            "ORDER BY c.column_id"
        )
        return _dump(_fetch(sql, {"owner": schema.upper(), "name": name.upper()}, max_rows=MAX_ROWS))
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@mcp.tool()
def run_readonly_query(sql: str, max_rows: int = DEFAULT_ROWS) -> str:
    """Ejecuta una unica sentencia SELECT/WITH de solo lectura sobre BI_SEMANTIC/DWH_MART.

    Args:
        sql: sentencia SELECT o WITH (sin ';' multiples, sin DDL/DML).
        max_rows: filas maximas a devolver (por defecto 100, maximo 500).
    """
    try:
        limit = max(1, min(int(max_rows), MAX_ROWS))
        safe_sql = validate_readonly_sql(sql)
        return _dump(_fetch(safe_sql, None, max_rows=limit))
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


if __name__ == "__main__":
    mcp.run()
