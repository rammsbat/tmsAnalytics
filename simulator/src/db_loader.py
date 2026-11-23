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

from .batch import batch_run_pattern
from .contract import TableContract, validate_rows
from .scenario import OpenTrip, State

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


def next_run_seq(conn: oracledb.Connection, tables: Iterable[TableContract], mode: str, end_date,
                 seed: int) -> int:
    """Siguiente numero de corrida: 1 + el mayor NNN ya usado por lotes de corrida (no `-Exx`).

    Un solo numero para TODA la corrida (todas las tablas comparten BATCH_ID base). Solo SELECT
    con bind variable; los nombres de tabla provienen del contrato cerrado.
    """
    pattern = batch_run_pattern(mode, end_date, seed)
    highest = 0
    with conn.cursor() as cur:
        for table in tables:
            if not _IDENT_RE.match(table.name):
                raise LoaderError("Tabla invalida")
            sql = ("SELECT NVL(MAX(TO_NUMBER(REGEXP_SUBSTR(BATCH_ID, '[0-9]+$'))), 0) FROM STG_SRC."
                   + table.name + " WHERE REGEXP_LIKE(BATCH_ID, :pattern)")
            cur.execute(sql, pattern=pattern)
            highest = max(highest, int(cur.fetchone()[0]))
    return highest + 1


def insert_rows(conn: oracledb.Connection, table: TableContract, rows: list[dict],
                commit: bool = True) -> int:
    """Valida contra el DDL e inserta por lotes.

    `commit=True` (por defecto) confirma al final; el CLI usa `commit=False` en todas las tablas y
    confirma UNA vez, de modo que una corrida es atomica entre tablas (todo o nada).
    """
    validate_rows(table, rows)  # ContractError antes de tocar la BD
    sql = build_insert_sql(table)
    names = table.column_names
    total = 0
    try:
        with conn.cursor() as cur:
            for chunk in _chunks(rows, CHUNK_SIZE):
                cur.executemany(sql, [tuple(r[c] for c in names) for r in chunk])
                total += len(chunk)
        if commit:
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


def _talon_num(prefix: str, talon: str) -> int:
    return int(talon[len(prefix):])


def load_state(conn: oracledb.Connection, cfg: dict) -> State:
    """Estado de lo ya cargado para el modo incremental (solo SELECT con binds)."""
    prefix = cfg["numbering"]["talon_prefix"]
    pattern = "^" + prefix + "[0-9]+$"
    with conn.cursor() as cur:
        cur.execute("SELECT MIN(TRUNC(FECHA_DESPACHO)), MAX(TRUNC(FECHA_DESPACHO)), "
                    "NVL(MAX(TO_NUMBER(REGEXP_SUBSTR(TALON_FOLIO, '[0-9]+$'))), :floor) "
                    "FROM STG_SRC.STG_TRACKIT_DESPACHO WHERE REGEXP_LIKE(TALON_FOLIO, :pattern)",
                    floor=cfg["numbering"]["talon_start"] - 1, pattern=pattern)
        first, last, max_num = cur.fetchone()
        if first is None:
            return State(None, None, cfg["numbering"]["talon_start"])
        cur.execute("SELECT CODIGO_ECO, MAX(ODOMETRO_FINAL) FROM STG_SRC.STG_TRACKIT_DESPACHO "
                    "WHERE ESTATUS_DESPACHO = :cerrado AND ODOMETRO_FINAL IS NOT NULL "
                    "GROUP BY CODIGO_ECO", cerrado="CERRADO")
        odometers = {eco: float(v) for eco, v in cur.fetchall()}
        cur.execute("SELECT d.TALON_FOLIO, d.CODIGO_ECO, d.CODIGO_OPERADOR, TRUNC(d.FECHA_DESPACHO), "
                    "d.HORA_DESPACHO, d.ODOMETRO_INICIAL FROM STG_SRC.STG_TRACKIT_DESPACHO d "
                    "WHERE d.ESTATUS_DESPACHO = :abierto AND NOT EXISTS (SELECT 1 FROM "
                    "STG_SRC.STG_TRACKIT_DESPACHO c WHERE c.TALON_FOLIO = d.TALON_FOLIO "
                    "AND c.ESTATUS_DESPACHO = :cerrado) ORDER BY d.TALON_FOLIO",
                    abierto="EN_TRANSITO", cerrado="CERRADO")
        opened = []
        for talon, eco, op, day, hhmm, odo in cur.fetchall():
            hh, mm = int(hhmm[0:2]), int(hhmm[3:5])
            opened.append(OpenTrip(talon, _talon_num(prefix, talon), eco, op, day.date(),
                                   hh * 60 + mm, float(odo)))
        opened.sort(key=lambda t: t.talon_num)
    return State(first.date(), last.date(), int(max_num) + 1, odometers, opened)
