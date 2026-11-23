"""Metadatos de lote: BATCH_ID, INGESTED_AT y SOURCE_SYSTEM deterministas (sin reloj)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

BATCH_ID_MAX = 64  # VARCHAR2(64) en STG_SRC


@dataclass(frozen=True)
class BatchInfo:
    batch_id: str
    ingested_at: dt.datetime
    run_seq: int


def batch_prefix(mode: str, end_date: dt.date, seed: int) -> str:
    return "SIM-" + mode.upper() + "-" + end_date.strftime("%Y%m%d") + "-s" + str(seed) + "-"


def make_batch(mode: str, end_date: dt.date, seed: int, run_seq: int) -> BatchInfo:
    """BATCH_ID = SIM-<MODO>-<AAAAMMDD>-s<seed>-<NNN>.

    Unico por corrida: `run_seq` lo asigna el loader consultando STG_SRC (o el operador con
    --run-seq). INGESTED_AT = medianoche de end_date + run_seq minutos: crece con cada corrida
    del mismo dia (D7: EDW deduplica por INGESTED_AT DESC) sin depender del reloj.
    """
    if run_seq < 1:
        raise ValueError("run_seq debe ser >= 1")
    batch_id = batch_prefix(mode, end_date, seed) + format(run_seq, "03d")
    if len(batch_id.encode("utf-8")) > BATCH_ID_MAX:
        raise ValueError("BATCH_ID excede VARCHAR2(64)")
    ingested = dt.datetime.combine(end_date, dt.time(0, 0)) + dt.timedelta(minutes=run_seq)
    return BatchInfo(batch_id, ingested, run_seq)


def stamp_rows(rows: list[dict], batch: BatchInfo, source_system: str) -> list[dict]:
    """Copia cada fila agregando las columnas de auditoria."""
    return [{**r, "BATCH_ID": batch.batch_id, "INGESTED_AT": batch.ingested_at,
             "SOURCE_SYSTEM": source_system} for r in rows]
