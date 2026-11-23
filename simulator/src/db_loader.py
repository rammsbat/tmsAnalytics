"""Carga append-only a STG_SRC como SIM_WRITER (python-oracledb Thin, bind variables).

* Solo INSERT (SIM_WRITER ya no tiene DELETE; D5/06_etl_grants.sql).
* executemany en lotes de 5,000 filas; todos los valores viajan como binds posicionales (:1, :2, ...).
* Los identificadores (tabla/columnas) salen del contrato parseado de 02_ddl_stg_src.sql y se
  verifican contra una lista cerrada: jamas se interpolan valores ni texto externo en el SQL.
* Credenciales solo desde variables de entorno; los errores no incluyen password ni DSN.
"""
from __future__ import annotations

import os
import re
from typing import Iterable

import oracledb

from .batch import BatchInfo, batch_prefix, make_batch
from .contract import ContractError, TableContract, validate_rows

CHUNK_SIZE = 5000
_IDENT_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


class LoaderError(RuntimeError):
    """Error de carga sin datos sensibles."""


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise LoaderError(f"Falta la variable de entorno {name}")
    return value


def connect() -> oracledb.Connection:
    """Conexion Thin como SIM_WRITER. Rechaza cualquier otro usuario."""
    user = os.environ.get("SIM_WRITER_USER", "SIM_WRITER")
    if user.upper() != "SIM_WRITER":
        raise LoaderError("El simulador solo puede conectarse como SIM_WRITER")
    if not oracledb.is_thin_mode():
        raise LoaderError("python-oracledb debe operar en Thin Mode")
    try:
        return oracledb.connect(user=user, password=_env("SIM_WRITER_PWD"), dsn=_env("ORACLE_DSN"))
    except oracledb.Error as exc:
        code = getattr(exc.args[0], "code", None) if exc.args else None
        raise LoaderError(f"No se pudo conectar a Oracle (ORA-{code})" if code else
                          "No se pudo conectar a Oracle") from None


def build_insert_sql(table: TableContract) -> str:
    """INSERT con una bind variable por columna. Identificadores validados contra el contrato."""
    for ident in (table.name, *table.column_names):
        if not _IDENT_RE.match(ident):
            raise LoaderError(f"Identificador no permitido: {ident!r}")
    cols = ", ".join(table.column_names)
    binds = ", ".join(f":{i + 1}" for i in range(len(table.columns)))
    return "INSERT INTO STG_SRC." + table.name + " (" + cols + ") VALUES (" + binds + ")"


def _chunks(rows: list, size: int) -> Iterable[list]:
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def next_run_seq(conn: oracledb.Connection, table: TableContract, mode: str, end_date, seed: int) -> int:
    """Siguiente numero de corrida: 1 + corridas previas con el mismo prefijo de BATCH_ID.

    Solo SELECT con bind variable (el nombre de tabla proviene del contrato cerrado).
    """
    if not _IDENT_RE.match(table.name):
        raise LoaderError("Tabla invalida")
    sql = ("SELECT COUNT(DISTINCT BATCH_ID) FROM STG_SRC." + table.name
           + " WHERE BATCH_ID LIKE :prefix ESCAPE '\\'")
    prefix = batch_prefix(mode, end_date, seed).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with conn.cursor() as cur:
        cur.execute(sql, prefix=prefix + "%")
        return int(cur.fetchone()[0]) + 1


def insert_rows(conn: oracledb.Connection, table: TableContract, rows: list[dict]) -> int:
    """Valida contra el DDL e inserta por lotes; commit unico al final (todo o nada)."""
    validate_rows(table, rows)  # ContractError antes de tocar la BD
    sql = build_insert_sql(table)
    names = table.column_names
    total = 0
    try:
        with conn.cursor() as cur:
            for chunk in _chunks(rows, CHUNK_SIZE):
                cur.executemany(sql, [tuple(r[c] for c in names) for r in chunk])
                total += len(chunk)
        conn.commit()
    except oracledb.Error as exc:
        conn.rollback()
        code = getattr(exc.args[0], "code", None) if exc.args else None
        raise LoaderError(f"Fallo INSERT en STG_SRC.{table.name} (ORA-{code}); rollback aplicado") from None
    return total


def count_batch(conn: oracledb.Connection, table: TableContract, batch_id: str) -> int:
    sql = "SELECT COUNT(*) FROM STG_SRC." + table.name + " WHERE BATCH_ID = :batch_id"
    with conn.cursor() as cur:
        cur.execute(sql, batch_id=batch_id)
        return int(cur.fetchone()[0])
