"""
Exporta de forma reproducible los assets de Superset (bases de datos, datasets virtuales,
charts y dashboards) a un bundle YAML versionable en superset/assets/bundle/.

Usa el mismo comando interno que el endpoint REST /api/v1/assets/export
(superset.commands.export.assets.ExportAssetsCommand) y aplica sanitizacion Regla 03:
  - password de la base de datos enmascarada por Superset ("XXXXXXXXXX") -> reemplazada por
    un placeholder explicito no secreto que el importador reinyecta desde BI_READER_PWD.
  - Se verifica que no quede ningun secreto en el bundle; si lo hay, aborta sin escribir.

Uso (dentro del contenedor tms-superset-app):
    python /tmp/tools/export_superset_assets.py [directorio_salida]
"""
import re
import shutil
import sys
from pathlib import Path

import yaml

from superset.app import create_app

PLACEHOLDER = "${BI_READER_PWD}"
MASKED = "XXXXXXXXXX"
BUNDLE_VERSION_FILE = "metadata.yaml"

# Patron de credenciales embebidas en URIs (user:pass@host) donde pass no es placeholder/mascara
URI_CRED_RE = re.compile(r"^(?P<scheme>[\w+]+)://(?P<user>[^:/@]+):(?P<pwd>[^@]*)@")


def default_out_dir() -> Path:
    app_dir = Path("/app/assets")
    if app_dir.exists():
        return app_dir / "bundle"
    return Path(__file__).resolve().parent.parent / "superset" / "assets" / "bundle"


def sanitize_database_yaml(content: str) -> str:
    """Sustituye la mascara de password por el placeholder de variable de entorno."""
    data = yaml.safe_load(content)
    uri = data.get("sqlalchemy_uri", "")
    m = URI_CRED_RE.match(uri)
    if m and m.group("pwd") not in (MASKED, PLACEHOLDER):
        raise RuntimeError("Password en texto claro detectada en sqlalchemy_uri (Regla 03)")
    if m:
        data["sqlalchemy_uri"] = uri.replace(f":{m.group('pwd')}@", f":{PLACEHOLDER}@", 1)
    # Cualquier otro campo con secretos conocidos se elimina
    data.pop("password", None)
    data.pop("masked_encrypted_extra", None)
    data.pop("encrypted_extra", None)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def normalize_for_git(files: dict) -> dict:
    """Hace el bundle estable entre exportaciones (diffs minimos en Git):
    - elimina el sufijo numerico de ID del nombre de archivo (charts/dashboards)
    - elimina el timestamp de metadata.yaml
    - vacia dashboards.metadata.global_chart_configuration.chartsInScope (IDs no portables;
      el importador lo recalcula con los IDs reales de la instancia destino).
    """
    out = {}
    for name, text in files.items():
        if name.startswith(("charts/", "dashboards/")):
            name = re.sub(r"_\d+\.yaml$", ".yaml", name)
        if name == "metadata.yaml":
            data = yaml.safe_load(text)
            data.pop("timestamp", None)
            text = yaml.safe_dump(data, sort_keys=False)
        if name.startswith("dashboards/"):
            data = yaml.safe_load(text)
            gcc = data.get("metadata", {}).get("global_chart_configuration")
            if gcc is not None:
                gcc["chartsInScope"] = []
            text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        out[name] = text
    return out


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else default_out_dir()
    app = create_app()
    with app.app_context():
        from flask import g
        from superset import security_manager
        from superset.commands.export.assets import ExportAssetsCommand

        # El comando requiere un usuario con acceso total (equivalente al REST autenticado)
        g.user = security_manager.find_user(username="admin")

        files = {}
        for name, content_fn in ExportAssetsCommand().run():
            text = content_fn()
            if name.startswith("databases/"):
                text = sanitize_database_yaml(text)
            files[name] = text

    files = normalize_for_git(files)

    # Auditoria previa a escritura: ningun archivo puede contener la mascara con credencial real
    for name, text in files.items():
        for m in re.finditer(r"[\w+]+://[^:/@\s]+:([^@\s]+)@", text):
            if m.group(1) not in (PLACEHOLDER, MASKED):
                raise RuntimeError(f"Credencial embebida en {name} (Regla 03)")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    for name, text in files.items():
        dest = out_dir / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="\n")
    print(f"[OK] {len(files)} archivos exportados a {out_dir}")
    for name in sorted(files):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
