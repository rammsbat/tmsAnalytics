"""Guardrails estaticos y comportamiento del CLI/loader sin conexion a Oracle."""
import ast
import pathlib
import re

import pytest

from src import db_loader, main
from src.contract import ContractError

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
PY_FILES = sorted(SRC.rglob("*.py"))


def test_no_wall_clock_or_uuid4_in_source():
    """D6: sin datetime.now()/utcnow()/today(), time.time() ni uuid4()/uuid1()."""
    # dt.time(h, m) es un constructor (no lee el reloj); solo se prohibe time.time()/time_ns().
    banned = {("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"), ("dt", "now"),
              ("dt", "utcnow"), ("dt", "today"), ("date", "today"), ("time", "time"),
              ("time", "time_ns"), ("uuid", "uuid4"), ("uuid", "uuid1")}
    for path in PY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = getattr(node.func.value, "id", "")
                if (owner, node.func.attr) in banned:
                    pytest.fail(f"{path.name}:{node.lineno} usa {owner}.{node.func.attr}()")
            # datetime.datetime.now() / dt.datetime.now()
            if (isinstance(node, ast.Attribute) and node.attr in {"now", "utcnow", "today"}
                    and isinstance(node.value, ast.Attribute) and node.value.attr in {"datetime", "date"}):
                pytest.fail(f"{path.name}:{node.lineno} usa {node.value.attr}.{node.attr}")
            if isinstance(node, ast.Import) and any(a.name == "uuid" for a in node.names):
                pytest.fail(f"{path.name}: importa uuid")


def test_module_random_is_never_used():
    """Todo el azar debe venir de random.Random(seed) via rng.make_rng."""
    for path in PY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if getattr(node.func.value, "id", "") == "random" and node.func.attr != "Random":
                    pytest.fail(f"{path.name}:{node.lineno} usa random.{node.func.attr}() global")


def test_no_fstring_sql_and_no_cx_oracle():
    """Ningun f-string/.format/% construye SQL: se detecta por forma (f-string que *empieza*
    con una sentencia SQL, o argumento de execute/executemany que no sea literal/identificador)."""
    sql_start = re.compile(r"^\s*(INSERT|SELECT|UPDATE|DELETE|MERGE|WITH)\b", re.I)
    for path in PY_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                head = next((v.value for v in node.values if isinstance(v, ast.Constant)), "")
                assert not sql_start.match(head), f"{path.name}:{node.lineno} f-string con SQL"
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in {"execute", "executemany"} and node.args):
                first = node.args[0]
                assert not isinstance(first, ast.JoinedStr), f"{path.name}:{node.lineno} execute(f-string)"
                assert not (isinstance(first, ast.Call) and isinstance(first.func, ast.Attribute)
                            and first.func.attr == "format"), f"{path.name}:{node.lineno} execute(.format)"
                assert not (isinstance(first, ast.BinOp) and isinstance(first.op, ast.Mod)), \
                    f"{path.name}:{node.lineno} execute(% formato)"
        src = path.read_text(encoding="utf-8")
        assert "cx_Oracle" not in src and "init_oracle_client" not in src


def test_loader_never_issues_delete_or_ddl():
    src = (SRC / "db_loader.py").read_text(encoding="utf-8").upper()
    for word in ("DELETE ", "TRUNCATE", "DROP ", "ALTER ", "UPDATE ", "MERGE "):
        assert word not in src, word


def test_insert_sql_uses_binds_for_every_column(contract):
    t = contract["STG_FLOTA_UNIDADES"]
    sql = db_loader.build_insert_sql(t)
    assert sql.startswith("INSERT INTO STG_SRC.STG_FLOTA_UNIDADES (CODIGO_ECO, ")
    assert sql.count(":") == len(t.columns) and sql.endswith(f":{len(t.columns)})")
    assert "ECO" not in sql.split("VALUES")[1]


def test_connect_requires_env_and_sim_writer(monkeypatch):
    for var in ("SIM_WRITER_PWD", "ORACLE_DSN", "SIM_WRITER_USER"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(db_loader.LoaderError) as exc:
        db_loader.connect()
    assert "SIM_WRITER_PWD" in str(exc.value)
    monkeypatch.setenv("SIM_WRITER_USER", "SYSTEM")
    with pytest.raises(db_loader.LoaderError, match="solo puede conectarse como SIM_WRITER"):
        db_loader.connect()


def test_thin_mode_is_active():
    import oracledb
    assert oracledb.is_thin_mode()


def test_cli_dry_run_is_deterministic_and_offline(monkeypatch, capsys):
    for var in ("SIM_WRITER_PWD", "ORACLE_DSN"):
        monkeypatch.delenv(var, raising=False)
    outs = []
    for _ in range(2):
        assert main.main(["--mode", "backfill", "--days", "90", "--dry-run"]) == 0
        outs.append(capsys.readouterr().out)
    assert outs[0] == outs[1]
    assert "STG_FLOTA_UNIDADES: filas=100 batch_id=SIM-BACKFILL-20261106-s42-001" in outs[0]
    assert "dry_run=True" in outs[0] and "{'with_trip': 56, 'without_trip': 40, 'inactive': 4}" in outs[0]


def test_cli_seed_override_changes_fingerprint(capsys):
    main.main(["--mode", "backfill", "--dry-run"])
    a = capsys.readouterr().out
    main.main(["--mode", "backfill", "--dry-run", "--seed", "7"])
    b = capsys.readouterr().out
    assert a.split("fingerprint=")[1] != b.split("fingerprint=")[1]


def test_cli_rejects_bad_arguments(capsys):
    assert main.main(["--mode", "incremental", "--dry-run"]) == 2          # falta --trips
    assert main.main(["--mode", "backfill", "--days", "0", "--dry-run"]) == 2
    assert main.main(["--mode", "backfill", "--end-date", "no-es-fecha", "--dry-run"]) == 2
    assert "ERROR" in capsys.readouterr().err


def test_cli_incremental_dry_run_matches_real_batch_numbering(capsys):
    assert main.main(["--mode", "incremental", "--trips", "5", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "STG_TRACKIT_DESPACHO: filas=16 batch_id=SIM-INCREMENTAL-20261106-s42-001" in out
    assert "STG_FLOTA_ESTATUS_DIARIO: filas=111" in out and '"viajes_cerrados_ahora": 11' in out


def test_cli_backfill_dry_run_emits_all_8_tables(capsys):
    assert main.main(["--mode", "backfill", "--days", "90", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for name, rows in (("STG_FLOTA_UNIDADES", 100),
                       ("STG_TRACKIT_DESPACHO", 5040), ("STG_TRACKIT_PARADAS", 40458),
                       ("STG_CARTA_PORTE_CABECERA", 5040), ("STG_CARTA_PORTE_MERCANCIAS", 15236),
                       ("STG_FLOTA_ESTATUS_DIARIO", 9000),
                       ("STG_CFDI_INGRESO", 5029)):
        assert f"{name}: filas={rows} " in out
    assert "STG_LIQUIDACIONES_GASTOS: filas=" in out
    assert "batch_id=SIM-BACKFILL-20261106-s42-001-E01" in out and "batch_id=SIM-BACKFILL-20261106-s42-001-E02" in out


def test_scenario_module_is_pure_no_database():
    src = (SRC / "scenario.py").read_text(encoding="utf-8").upper()
    assert "EXECUTE(" not in src and "ORACLEDB" not in src  # el escenario es puro: sin BD
