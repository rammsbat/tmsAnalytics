"""Metadatos de lote: BATCH_ID, INGESTED_AT y SOURCE_SYSTEM deterministas (sin reloj).

INGESTED_AT es por FILA y refleja el dia operativo al que pertenece el dato:
`dia 23:00:00 + run_seq segundos`. Asi (D7) la version mas reciente de una llave natural
gana siempre en el dedupe de EDW: el cierre de un viaje (dia siguiente) supera a su apertura y
un cambio de placa con fecha efectiva posterior supera al maestro inicial (ingestado al inicio
del historico).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

BATCH_ID_MAX = 64  # VARCHAR2(64) en STG_SRC
_INGEST_TIME = dt.time(23, 0)


@dataclass(frozen=True)
class BatchInfo:
    batch_id: str
    run_seq: int
    default_day: dt.date

    def ingested_at(self, day: dt.date) -> dt.datetime:
        return dt.datetime.combine(day, _INGEST_TIME) + dt.timedelta(seconds=self.run_seq)


def batch_prefix(mode: str, end_date: dt.date, seed: int) -> str:
    return "SIM-" + mode.upper() + "-" + end_date.strftime("%Y%m%d") + "-s" + str(seed) + "-"


def batch_run_pattern(mode: str, end_date: dt.date, seed: int) -> str:
    """Regex Oracle de los BATCH_ID de corrida (excluye los lotes de evento `-Exx`)."""
    return "^" + batch_prefix(mode, end_date, seed) + "[0-9]{3,}$"


def make_batch(mode: str, end_date: dt.date, seed: int, run_seq: int, suffix: str = "") -> BatchInfo:
    """BATCH_ID = SIM-<MODO>-<AAAAMMDD>-s<seed>-<NNN>[<sufijo>] (p. ej. ...-001-E01)."""
    if run_seq < 1:
        raise ValueError("run_seq debe ser >= 1")
    batch_id = batch_prefix(mode, end_date, seed) + format(run_seq, "03d") + suffix
    if len(batch_id.encode("utf-8")) > BATCH_ID_MAX:
        raise ValueError("BATCH_ID excede VARCHAR2(64)")
    return BatchInfo(batch_id, run_seq, end_date)


def stamp_rows(rows: list[dict], batch: BatchInfo, source_system: str) -> list[dict]:
    """Copia cada fila agregando auditoria. Consume la clave transitoria `_ING_DAY`."""
    out = []
    for r in rows:
        row = dict(r)
        day = row.pop("_ING_DAY", batch.default_day)
        row["BATCH_ID"] = batch.batch_id
        row["INGESTED_AT"] = batch.ingested_at(day)
        row["SOURCE_SYSTEM"] = source_system
        out.append(row)
    return out
