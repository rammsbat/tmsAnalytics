#!/usr/bin/env bash
# bootstrap.sh - Inicializacion idempotente de Superset para Analytics TMS
# Formato: saltos de linea LF. Cero secretos en codigo (Regla 03).

set -eo pipefail

echo "==> [Bootstrap] Iniciando actualizacion de esquema del metastore..."
superset db upgrade

echo "==> [Bootstrap] Verificando / creando usuario administrador..."
export SUPERSET_ADMIN_USER="${SUPERSET_ADMIN_USER:-admin}"
export SUPERSET_ADMIN_FIRSTNAME="${SUPERSET_ADMIN_FIRSTNAME:-Admin}"
export SUPERSET_ADMIN_LASTNAME="${SUPERSET_ADMIN_LASTNAME:-User}"
export SUPERSET_ADMIN_EMAIL="${SUPERSET_ADMIN_EMAIL:-admin@tms.local}"

if [ -z "${SUPERSET_ADMIN_PASSWORD}" ]; then
    echo "ERROR: SUPERSET_ADMIN_PASSWORD no esta definida en las variables de entorno."
    exit 1
fi

superset fab create-admin \
    --username "${SUPERSET_ADMIN_USER}" \
    --firstname "${SUPERSET_ADMIN_FIRSTNAME}" \
    --lastname "${SUPERSET_ADMIN_LASTNAME}" \
    --email "${SUPERSET_ADMIN_EMAIL}" \
    --password "${SUPERSET_ADMIN_PASSWORD}" || {
        echo "==> [Bootstrap] Usuario admin ya existe o fue creado previamente. Continuando..."
    }

echo "==> [Bootstrap] Inicializando roles y permisos de Superset..."
superset init

echo "==> [Bootstrap] Registrando / sincronizando conexion Analytics_TMS_Oracle en el metastore..."
python - <<'EOF'
import os
import sys
import json
import urllib.parse
from superset.app import create_app

app = create_app()
with app.app_context():
    from superset import db
    from superset.models.core import Database

    db_name = "Analytics_TMS_Oracle"
    bi_reader_pwd = os.environ.get("BI_READER_PWD")
    
    if not bi_reader_pwd:
        print("WARN: BI_READER_PWD no esta definida. Se omite registro automatico de conexion.", file=sys.stderr)
        sys.exit(0)
    
    escaped_pwd = urllib.parse.quote_plus(bi_reader_pwd)
    uri = f"oracle+oracledb://BI_READER:{escaped_pwd}@oracle-dw:1521/?service_name=FREEPDB1"
    
    db_obj = db.session.query(Database).filter_by(database_name=db_name).first()
    if not db_obj:
        print(f"==> [Bootstrap] Creando entrada para '{db_name}' en el metastore...")
        db_obj = Database(database_name=db_name)
    else:
        print(f"==> [Bootstrap] Actualizando entrada existente para '{db_name}' en el metastore...")
    
    db_obj.set_sqlalchemy_uri(uri)
    db_obj.allow_ctas = False
    db_obj.allow_cvas = False
    db_obj.allow_dml = False
    db_obj.allow_run_async = True
    db_obj.expose_in_sqllab = True
    db_obj.extra = json.dumps({"engine_params": {"arraysize": 1000}})
    
    db.session.add(db_obj)
    db.session.commit()
    print(f"==> [Bootstrap] Base de datos '{db_name}' registrada exitosamente (solo metadatos, sin test en vivo).")
EOF

echo "==> [Bootstrap] Inicializacion completada con exito. Arrancando servidor Superset..."
exec /usr/bin/run-server.sh