"""CLI del simulador TMS: escribe unicamente en STG_SRC (como SIM_WRITER).

Uso (dentro del contenedor):
  python -m src.main --mode backfill --days 90 [--dry-run]
  python -m src.main --mode incremental --trips 5 [--dry-run]

ST-3 emite maestros, TrackIt (despacho/paradas), Carta Porte, estatus diario de patio y los
eventos SCD2 de placa. Las tablas financieras (CFDI/liquidaciones) llegan en ST-4.
La corrida es atomica: un unico COMMIT al final; ante cualquier error se hace rollback total.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

from .batch import make_batch, stamp_rows
from .config import ConfigError, load_config, status_counts
from .contract import ContractError, load_contract, validate_rows
from .generators.fleet_master import generate_fleet_master
from .scenario import ScenarioResult, State, build_backfill, build_incremental


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="simulator", description="Simulador de datos sinteticos TMS -> STG_SRC")
    p.add_argument("--mode", choices=("backfill", "incremental"), required=True)
    p.add_argument("--days", type=int, help="backfill: dias hacia atras desde end_date (def. config)")
    p.add_argument("--trips", type=int, help="incremental: numero de viajes a generar")
    p.add_argument("--dry-run", action="store_true", help="genera y valida; no abre conexion a Oracle")
    p.add_argument("--seed", type=int, help="sobrescribe seed de config_rules.yaml")
    p.add_argument("--end-date", help="sobrescribe end_date (YYYY-MM-DD)")
    p.add_argument("--config", type=Path, help="ruta alterna de config_rules.yaml")
    p.add_argument("--run-seq", type=int, help="fuerza el numero de corrida del BATCH_ID (def.: se consulta en BD)")
    return p


def _apply_overrides(cfg: dict, args: argparse.Namespace) -> dict:
    cfg = dict(cfg)
    if args.seed is not None:
        cfg["seed"] = args.seed
    if args.end_date:
        try:
            cfg["end_date"] = dt.date.fromisoformat(args.end_date)
        except ValueError:
            raise ConfigError(f"--end-date invalida: {args.end_date!r}") from None
    if args.mode == "backfill":
        days = args.days if args.days is not None else cfg["date_range_backfill"]["days"]
        if days <= 0:
            raise ConfigError("--days debe ser > 0")
        cfg["_days"] = days
    else:
        if args.trips is None or args.trips <= 0:
            raise ConfigError("--mode incremental requiere --trips N (N > 0)")
        cfg["_trips"] = args.trips
    return cfg


def _fingerprint(rows: list[dict]) -> str:
    h = hashlib.sha256()
    for r in rows:
        h.update(json.dumps(r, sort_keys=True, default=str).encode("utf-8"))
    return h.hexdigest()[:16]


def _scenario(cfg: dict, args: argparse.Namespace, conn) -> tuple[ScenarioResult, int]:
    """(escenario, run_seq por defecto sin BD). El incremental parte del estado real en BD o,
    en --dry-run, del estado que dejaria un backfill por defecto."""
    master = generate_fleet_master(cfg)
    if args.mode == "backfill":
        return build_backfill(cfg, master, cfg["_days"]), 1
    if conn is not None:
        from . import db_loader
        state: State = db_loader.load_state(conn, cfg)
        default_seq = 1
    else:
        state = build_backfill(cfg, master, cfg["date_range_backfill"]["days"]).end_state
        default_seq = 1  # el BATCH_ID lleva el modo: la 1.ª corrida incremental es -001
    return build_incremental(cfg, master, state, cfg["_trips"]), default_seq


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = None
    try:
        cfg = _apply_overrides(load_config(args.config), args)
        contract = load_contract()
        counts = status_counts(cfg["fleet_size"], cfg["fleet_status_mix"])
        print(f"modo={args.mode} seed={cfg['seed']} end_date={cfg['end_date']} dry_run={args.dry_run}")
        print(f"flota={cfg['fleet_size']} mezcla_objetivo={counts}")

        if not args.dry_run:
            from . import db_loader  # import diferido: --dry-run no requiere credenciales
            conn = db_loader.connect()
        result, run_seq = _scenario(cfg, args, conn)
        if args.run_seq is not None:
            run_seq = args.run_seq
        elif conn is not None:
            run_seq = db_loader.next_run_seq(conn, [contract[e.table] for e in result.emissions],
                                             args.mode, cfg["end_date"], cfg["seed"])
        for note in result.notes:
            print(note)

        for em in result.emissions:
            if not em.rows:
                continue
            table = contract[em.table]
            batch = make_batch(args.mode, cfg["end_date"], cfg["seed"], run_seq, em.suffix)
            stamped = stamp_rows(em.rows, batch, em.source)
            validate_rows(table, stamped)
            line = (f"{em.table}: filas={len(stamped)} batch_id={batch.batch_id} "
                    f"source={em.source} fingerprint={_fingerprint(stamped)}")
            if conn:
                inserted = db_loader.insert_rows(conn, table, stamped, commit=False)
                verified = db_loader.count_batch(conn, table, batch.batch_id)
                line += f" insertadas={inserted} verificadas_en_BD={verified}"
                if verified != inserted:
                    print(line)
                    conn.rollback()
                    print("ERROR: el conteo verificado no coincide con lo insertado; rollback aplicado",
                          file=sys.stderr)
                    return 3
            print(line)
        if conn:
            conn.commit()
            print("COMMIT unico aplicado (corrida atomica)")
        print("resumen=" + json.dumps(result.summary, sort_keys=True, default=str))
        return 0
    except (ConfigError, ContractError) as exc:
        if conn:
            conn.rollback()
        print(f"ERROR de configuracion/contrato: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # LoaderError y similares: mensajes ya saneados
        if conn:
            conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
