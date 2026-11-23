"""
Auditoria de cero secretos (Regla 03) y de completitud del bundle de Superset en superset/assets/bundle/.

Verifica:
  1. Cero secretos: sin passwords en texto plano, tokens, claves privadas ni valores de variables
     sensibles del entorno (BI_READER_PWD, ORACLE_PWD, SUPERSET_SECRET_KEY, ...) ni de .env.
  2. La unica URI con credencial es oracle+cx_oracle://BI_READER:${BI_READER_PWD}@... (placeholder).
     oracle+cx_oracle es OBLIGATORIA en SQLAlchemy 1.4 (Superset 4.1.1); se puentea a
     python-oracledb Thin Mode via sys.modules["cx_Oracle"] = oracledb en superset_config.py.
     No es una dependencia real de cx_Oracle ni de Instant Client (falso positivo documentado).
  3. Completitud: 1 base, 8 datasets, 12 charts, 1 dashboard, 4 Native Filters, 8 filas de layout
     (7 ROW_* + HEADER_MAIN; cubren los 7 bloques + B8 corredores).

Uso (host, sin dependencias de Superset):  python tools/audit_superset_assets.py [bundle_dir]
Sale con codigo 1 si hay algun hallazgo.
"""
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "${BI_READER_PWD}"
SENSITIVE_ENV = (
    "BI_READER_PWD", "ORACLE_PWD", "SIM_WRITER_PWD", "ETL_RUNNER_PWD", "POSTGRES_PASSWORD",
    "SUPERSET_SECRET_KEY", "SUPERSET_ADMIN_PASSWORD",
)
URI_CRED_RE = re.compile(r"(?P<scheme>[\w+]+)://(?P<user>[^:/@\s]+):(?P<pwd>[^@\s]+)@")
PATTERNS = {
    "clave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "token/clave API": re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|bearer)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}"),
    "password literal": re.compile(r"(?im)^\s*(password|passwd|secret_key|encrypted_extra|private_key)\s*:\s*(?!null\b|~|\s*$)\S+"),
    "password enmascarada": re.compile(r"XXXXXXXXXX"),
}


def load_env_secrets() -> dict:
    values = {k: os.environ[k] for k in SENSITIVE_ENV if os.environ.get(k)}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k in SENSITIVE_ENV and v:
                    values.setdefault(k, v)
    return values


def main() -> int:
    bundle = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "superset" / "assets" / "bundle"
    files = sorted(p for p in bundle.rglob("*") if p.is_file())
    findings = []

    secrets = load_env_secrets()
    for path in files:
        rel = path.relative_to(bundle).as_posix()
        text = path.read_text(encoding="utf-8")
        for k, v in secrets.items():
            if len(v) >= 6 and v in text:
                findings.append(f"{rel}: contiene el valor de {k}")
        for label, rx in PATTERNS.items():
            if rx.search(text):
                findings.append(f"{rel}: patron '{label}'")
        for m in URI_CRED_RE.finditer(text):
            if m.group("pwd") != PLACEHOLDER:
                findings.append(f"{rel}: URI con credencial no placeholder ({m.group('scheme')}://{m.group('user')}:***@)")

    # Completitud
    by_dir = {d: [p for p in files if p.relative_to(bundle).parts[0] == d] for d in ("databases", "datasets", "charts", "dashboards")}
    expected = {"databases": 1, "datasets": 8, "charts": 12, "dashboards": 1}
    for d, n in expected.items():
        if len(by_dir[d]) != n:
            findings.append(f"completitud: {d} esperado {n}, encontrado {len(by_dir[d])}")

    dash = yaml.safe_load(by_dir["dashboards"][0].read_text(encoding="utf-8")) if by_dir["dashboards"] else {}
    filters = [f["name"] for f in dash.get("metadata", {}).get("native_filter_configuration", [])]
    rows = dash.get("position", {}).get("GRID_ID", {}).get("children", [])
    chart_nodes = [k for k, v in dash.get("position", {}).items() if isinstance(v, dict) and v.get("type") == "CHART"]
    if len(filters) != 4:
        findings.append(f"completitud: Native Filters esperados 4, encontrados {len(filters)}")
    if len([r for r in rows if r.startswith("ROW_")]) != 7:
        findings.append(f"completitud: filas de layout esperadas 7, encontradas {len([r for r in rows if r.startswith('ROW_')])}")
    if len(chart_nodes) != 12:
        findings.append(f"completitud: charts en layout esperados 12, encontrados {len(chart_nodes)}")

    datasets = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in by_dir["datasets"]]
    non_jinja = [d["table_name"] for d in datasets if "{%" not in (d.get("sql") or "")]
    if non_jinja:
        findings.append(f"completitud: datasets sin Jinja: {non_jinja}")

    print(f"Bundle: {bundle}  ({len(files)} archivos)")
    print(f"Variables sensibles contrastadas: {sorted(secrets) or 'ninguna disponible'}")
    print(f"Charts: {len(by_dir['charts'])} | Datasets: {len(by_dir['datasets'])} | Bases: {len(by_dir['databases'])} | "
          f"Dashboards: {len(by_dir['dashboards'])}")
    print(f"Native Filters: {filters}")
    print(f"Filas de layout: {[r for r in rows if r.startswith('ROW_')]}")
    if findings:
        print(f"\n[FAIL] {len(findings)} hallazgo(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("\n[PASS] Cero secretos y bundle completo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
