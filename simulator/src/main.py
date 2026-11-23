"""CLI del simulador TMS: escribe unicamente en STG_SRC (como SIM_WRITER).

Uso (dentro del contenedor):
  python -m src.main --mode backfill --days 90 [--dry-run]
  python -m src.main --mode incremental --trips 5 [--dry-run]

ST-2 entrega maestros de flota (STG_FLOTA_UNIDADES). Los generadores operativos
(TrackIt, Carta Porte, ERP) se registran en ST-3/ST-4 en `_operational_generators`.
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
from .generators.fleet_master import SOURCE_SYSTEM_FLOTA, FleetMaster, generate_fleet_master


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


def _operational_generators(cfg: dict, master: FleetMaster, mode: str) -> dict[str, tuple[str, list[dict]]]:
    """Gancho ST-3/ST-4: {tabla: (SOURCE_SYSTEM, filas)}. Vacio en ST-2."""
    return {}


def plan_tables(cfg: dict, mode: str) -> dict[str, tuple[str, list[dict]]]:
    """Tablas a emitir en esta corrida (sin columnas de auditoria)."""
    master = generate_fleet_master(cfg)
    tables: dict[str, tuple[str, list[dict]]] = {}
    if mode == "backfill":  # los maestros se emiten una sola vez, en el backfill
        tables["STG_FLOTA_UNIDADES"] = (SOURCE_SYSTEM_FLOTA, master.units)
    tables.update(_operational_generators(cfg, master, mode))
    return tables


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = _apply_overrides(load_config(args.config), args)
        contract = load_contract()
        tables = plan_tables(cfg, args.mode)

        counts = status_counts(cfg["fleet_size"], cfg["fleet_status_mix"])
        print(f"modo={args.mode} seed={cfg['seed']} end_date={cfg['end_date']} dry_run={args.dry_run}")
        print(f"flota={cfg['fleet_size']} mezcla_objetivo={counts}")
        if not tables:
            print("Sin tablas que emitir: los generadores operativos llegan en ST-3/ST-4.")
            return 0

        conn = None
        if not args.dry_run:
            from . import db_loader  # import diferido: --dry-run no requiere credenciales
            conn = db_loader.connect()
        try:
            for name, (source, rows) in tables.items():
                table = contract[name]
                run_seq = args.run_seq
                if run_seq is None:
                    run_seq = db_loader.next_run_seq(conn, table, args.mode, cfg["end_date"], cfg["seed"]) \
                        if conn else 1
                batch = make_batch(args.mode, cfg["end_date"], cfg["seed"], run_seq)
                stamped = stamp_rows(rows, batch, source)
                validate_rows(table, stamped)
                line = (f"{name}: filas={len(stamped)} batch_id={batch.batch_id} "
                        f"source={source} fingerprint={_fingerprint(stamped)}")
                if conn:
                    inserted = db_loader.insert_rows(conn, table, stamped)
                    verified = db_loader.count_batch(conn, table, batch.batch_id)
                    line += f" insertadas={inserted} verificadas_en_BD={verified}"
                    if verified != inserted:
                        print(line)
                        print("ERROR: el conteo verificado no coincide con lo insertado", file=sys.stderr)
                        return 3
                print(line)
        finally:
            if conn:
                conn.close()
        return 0
    except (ConfigError, ContractError) as exc:
        print(f"ERROR de configuracion/contrato: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # LoaderError y similares: mensajes ya saneados
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
