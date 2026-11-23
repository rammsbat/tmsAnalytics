"""
Importacion segura e idempotente del bundle de assets de Superset (superset/assets/bundle/).

Equivale al endpoint REST /api/v1/assets/import (ImportAssetsCommand), con estas garantias:
  - Idempotente: los assets se identifican por UUID y se sobrescriben; no se duplican
    charts, datasets, dashboards ni bases de datos.
  - Cero secretos en el bundle (Regla 03): el bundle solo contiene el placeholder
    `${BI_READER_PWD}`. Aqui se convierte a la mascara estandar de Superset (XXXXXXXXXX) y la
    password real se inyecta por el canal `passwords` desde la variable de entorno BI_READER_PWD.
  - Si BI_READER_PWD no esta definida y la base ya existe en el metastore, se PRESERVA la
    password cifrada existente (nunca se sobrescribe con mascara ni vacio).
    Si no esta definida y la base no existe, aborta con error.
  - URI `oracle+cx_oracle://` es obligatoria en SQLAlchemy 1.4 (Superset 4.1.1); el puente a
    python-oracledb Thin Mode se hace en superset_config.py (sys.modules["cx_Oracle"] = oracledb).

Uso (dentro del contenedor tms-superset-app, con BI_READER_PWD en el entorno):
    python /tmp/tools/import_superset_assets.py [--bundle DIR] [--dry-run]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import yaml

from superset.app import create_app

PLACEHOLDER = "${BI_READER_PWD}"
MASK = "XXXXXXXXXX"
DB_PWD_ENV = "BI_READER_PWD"


def default_bundle_dir() -> Path:
    app_dir = Path("/app/assets/bundle")
    if app_dir.exists():
        return app_dir
    return Path(__file__).resolve().parent.parent / "superset" / "assets" / "bundle"


def load_bundle(bundle_dir: Path) -> dict:
    """Lee el bundle YAML como dict {ruta_relativa_posix: contenido} (formato de ImportAssetsCommand)."""
    contents = {}
    for path in sorted(bundle_dir.rglob("*.yaml")):
        contents[path.relative_to(bundle_dir).as_posix()] = path.read_text(encoding="utf-8")
    if "metadata.yaml" not in contents:
        raise SystemExit(f"[ERROR] {bundle_dir} no contiene metadata.yaml (bundle invalido)")
    return contents


def prepare_database_contents(contents: dict, env_pwd) -> dict:
    """Sustituye el placeholder por la mascara de Superset y arma el mapa de passwords."""
    passwords = {}
    for name, text in list(contents.items()):
        if not name.startswith("databases/"):
            continue
        cfg = yaml.safe_load(text)
        uri = cfg["sqlalchemy_uri"]
        if PLACEHOLDER not in uri and f":{MASK}@" not in uri:
            raise SystemExit(f"[ERROR] {name}: la URI no usa placeholder {PLACEHOLDER} (Regla 03)")
        cfg["sqlalchemy_uri"] = uri.replace(PLACEHOLDER, MASK)
        contents[name] = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
        if env_pwd:
            passwords[name] = env_pwd
    return passwords


def counts(db, models) -> dict:
    return {label: db.session.query(model).count() for label, model in models.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--bundle", type=Path, default=default_bundle_dir())
    parser.add_argument("--dry-run", action="store_true", help="Solo valida el bundle, no escribe")
    args = parser.parse_args()

    contents = load_bundle(args.bundle)
    env_pwd = os.environ.get(DB_PWD_ENV) or None
    passwords = prepare_database_contents(contents, env_pwd)

    app = create_app()
    with app.app_context():
        from flask import g
        from superset import db, security_manager
        from superset.commands.importers.v1.assets import ImportAssetsCommand
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database
        from superset.models.dashboard import Dashboard
        from superset.models.slice import Slice

        g.user = security_manager.find_user(username="admin")

        models = {"databases": Database, "datasets": SqlaTable, "charts": Slice, "dashboards": Dashboard}
        before = counts(db, models)

        for name in contents:
            if name.startswith("databases/"):
                cfg = yaml.safe_load(contents[name])
                existing = db.session.query(Database).filter_by(uuid=cfg["uuid"]).first()
                if not env_pwd and not (existing and existing.password):
                    raise SystemExit(
                        f"[ERROR] {DB_PWD_ENV} no definida y la base '{cfg['database_name']}' no existe "
                        "en el metastore: no hay password que inyectar."
                    )
                origin = f"env {DB_PWD_ENV}" if env_pwd else "password existente del metastore (preservada)"
                print(f"[INFO] {cfg['database_name']}: password desde {origin}")

        command = ImportAssetsCommand(contents, passwords=passwords)
        if args.dry_run:
            command.validate()
            print(f"[OK] Bundle valido (dry-run). Archivos: {len(contents)}")
            return 0
        command.run()

        # Normaliza chartsInScope (IDs numericos no portables) con los IDs reales de la instancia
        for dash in db.session.query(Dashboard).all():
            if dash.uuid and any(n.startswith("dashboards/") for n in contents):
                meta = json.loads(dash.json_metadata or "{}")
                gcc = meta.get("global_chart_configuration")
                if gcc is not None:
                    gcc["chartsInScope"] = sorted(s.id for s in dash.slices)
                    dash.json_metadata = json.dumps(meta, ensure_ascii=False)
        db.session.commit()

        after = counts(db, models)
        print(f"[OK] Importacion completada ({len(contents)} archivos)")
        print(f"     antes  : {before}")
        print(f"     despues: {after}")

        database = db.session.query(Database).filter_by(database_name="Analytics_TMS_Oracle").one()
        stored_uri = database.sqlalchemy_uri
        print(f"[INFO] URI almacenada (enmascarada): {stored_uri}")
        if MASK in (database.password or "") or not database.password:
            print("[ERROR] La password almacenada esta vacia o enmascarada")
            return 1
        print("[OK] Password almacenada cifrada en el metastore y distinta de mascara/vacio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
