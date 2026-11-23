"""Contrato de STG_SRC derivado de oracle/ddl/02_ddl_stg_src.sql.

El DDL versionado es la fuente de verdad: se parsea (no se copia a mano) y se usa para
validar tipos, longitudes exactas (BYTES, NLS_LENGTH_SEMANTICS=BYTE en AL32UTF8),
precision/escala y nulabilidad antes de cualquier INSERT.
"""
from __future__ import annotations

import datetime as dt
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

DDL_FILENAME = "02_ddl_stg_src.sql"
AUDIT_COLUMNS = ("BATCH_ID", "INGESTED_AT", "SOURCE_SYSTEM")

_CREATE_RE = re.compile(r"CREATE\s+TABLE\s+STG_SRC\.([A-Z0-9_]+)\s*\(", re.IGNORECASE)
_COLUMN_RE = re.compile(
    r"^\s*([A-Z][A-Z0-9_]*)\s+(VARCHAR2|NUMBER|DATE|TIMESTAMP)\s*"
    r"(?:\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\))?(.*)$",
    re.IGNORECASE,
)
_END_RE = re.compile(r"^\s*\)\s*'\s*;")


class ContractError(ValueError):
    """Fila o contrato que viola el DDL de STG_SRC."""


@dataclass(frozen=True)
class Column:
    name: str
    type: str  # VARCHAR2 | NUMBER | DATE | TIMESTAMP
    length: int | None  # VARCHAR2: bytes
    precision: int | None
    scale: int | None
    nullable: bool


@dataclass(frozen=True)
class TableContract:
    name: str
    columns: tuple[Column, ...]

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)


def parse_ddl(text: str) -> dict[str, TableContract]:
    tables: dict[str, TableContract] = {}
    current: str | None = None
    cols: list[Column] = []
    for line in text.splitlines():
        if current is None:
            m = _CREATE_RE.search(line)
            if m:
                current, cols = m.group(1).upper(), []
            continue
        if _END_RE.match(line):
            tables[current] = TableContract(current, tuple(cols))
            current = None
            continue
        m = _COLUMN_RE.match(line)
        if not m:
            continue
        name, typ, p, s, rest = m.groups()
        typ = typ.upper()
        nullable = "NOT NULL" not in rest.upper()
        if typ == "VARCHAR2":
            cols.append(Column(name.upper(), typ, int(p), None, None, nullable))
        elif typ == "NUMBER":
            cols.append(Column(name.upper(), typ, None, int(p) if p else None,
                               int(s) if s else (0 if p else None), nullable))
        else:
            cols.append(Column(name.upper(), typ, None, None, None, nullable))
    if current is not None:
        raise ContractError(f"DDL truncado: tabla {current} sin cierre")
    return tables


def default_ddl_path() -> Path:
    env = os.environ.get("STG_DDL_PATH")
    here = Path(__file__).resolve()
    candidates = [Path(env)] if env else []
    candidates += [
        here.parents[1] / "contract" / DDL_FILENAME,              # imagen: /app/contract
        here.parents[2] / "oracle" / "ddl" / DDL_FILENAME,         # repo: ./oracle/ddl
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise ContractError("No se encontro 02_ddl_stg_src.sql (defina STG_DDL_PATH)")


def load_contract(path: Path | None = None) -> dict[str, TableContract]:
    p = path or default_ddl_path()
    return parse_ddl(p.read_text(encoding="utf-8"))


def _check_value(col: Column, value: object) -> str | None:
    if value is None:
        return None if col.nullable else "NULL en columna NOT NULL"
    if col.type == "VARCHAR2":
        if not isinstance(value, str):
            return f"se esperaba str, llego {type(value).__name__}"
        if value == "":
            return "cadena vacia (Oracle la trata como NULL); use None"
        n = len(value.encode("utf-8"))
        if n > (col.length or 0):
            return f"{n} bytes exceden VARCHAR2({col.length})"
    elif col.type == "NUMBER":
        if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
            return f"se esperaba numero, llego {type(value).__name__}"
        try:
            d = Decimal(str(value))
        except InvalidOperation:
            return "numero invalido"
        if not d.is_finite():
            return "numero no finito"
        if col.precision is not None:
            scale = col.scale or 0
            if -d.as_tuple().exponent > scale:  # type: ignore[operator]
                return f"mas de {scale} decimales para NUMBER({col.precision},{scale})"
            if abs(d) >= Decimal(10) ** (col.precision - scale):
                return f"{value} excede NUMBER({col.precision},{scale})"
    elif col.type == "DATE":
        if not isinstance(value, (dt.date, dt.datetime)):
            return f"se esperaba date/datetime, llego {type(value).__name__}"
    elif col.type == "TIMESTAMP":
        if not isinstance(value, dt.datetime):
            return f"se esperaba datetime, llego {type(value).__name__}"
    return None


def validate_rows(table: TableContract, rows: list[dict], max_errors: int = 20) -> None:
    """Valida cada fila contra el DDL; lanza ContractError con los primeros errores."""
    expected = set(table.column_names)
    errors: list[str] = []
    for i, row in enumerate(rows):
        keys = set(row)
        if keys != expected:
            errors.append(f"{table.name}[{i}]: columnas faltantes={sorted(expected - keys)} "
                          f"extra={sorted(keys - expected)}")
        else:
            for col in table.columns:
                msg = _check_value(col, row[col.name])
                if msg:
                    errors.append(f"{table.name}[{i}].{col.name}: {msg}")
        if len(errors) >= max_errors:
            break
    if errors:
        raise ContractError("; ".join(errors[:max_errors]))
