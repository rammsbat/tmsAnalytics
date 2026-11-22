
# -----------------------------------------------------------------------------
# Oracle Thin Mode Driver Compatibility (SQLAlchemy 1.4 + python-oracledb)
# -----------------------------------------------------------------------------
import sys, oracledb
oracledb.version = "8.3.0"
sys.modules["cx_Oracle"] = oracledb
# superset_config.py - Configuracion Analitica Base para Analytics TMS
# Formato: saltos de linea LF. Cero secretos en codigo (Regla 03).

import os
from cachelib.redis import RedisCache

# -----------------------------------------------------------------------------
# Secretos y Seguridad
# -----------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("CRITICAL: SUPERSET_SECRET_KEY no esta configurada en las variables de entorno.")

# -----------------------------------------------------------------------------
# Metastore SQL (PostgreSQL)
# -----------------------------------------------------------------------------
POSTGRES_USER = os.environ.get("POSTGRES_USER")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "superset-db")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB")

if not all([POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB]):
    raise RuntimeError("CRITICAL: Credenciales POSTGRES_USER, POSTGRES_PASSWORD o POSTGRES_DB no definidas.")

SQLALCHEMY_DATABASE_URI = (
    f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@"
    f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# -----------------------------------------------------------------------------
# Feature Flags
# -----------------------------------------------------------------------------
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "ALERT_REPORTS": True,
}

# -----------------------------------------------------------------------------
# Cache & Valkey Configuration (Licencia $0 BSD-3)
# Protocolo redis:// valido sobre imagen valkey/valkey:8-alpine (Regla 02)
# -----------------------------------------------------------------------------
VALKEY_HOST = os.environ.get("VALKEY_HOST", "superset-valkey")
VALKEY_PORT = int(os.environ.get("VALKEY_PORT", 6379))

# DB 0: Cache principal de metadatos y vistas
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 86400,
    "CACHE_KEY_PREFIX": "superset_main_",
    "CACHE_REDIS_HOST": VALKEY_HOST,
    "CACHE_REDIS_PORT": VALKEY_PORT,
    "CACHE_REDIS_DB": 0,
}

# DB 1: Cache de datos de consultas (Charts & SQL Lab)
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 86400,
    "CACHE_KEY_PREFIX": "superset_data_",
    "CACHE_REDIS_HOST": VALKEY_HOST,
    "CACHE_REDIS_PORT": VALKEY_PORT,
    "CACHE_REDIS_DB": 1,
}

# DB 2: Cache de estado de filtros nativos del Dashboard
FILTER_STATE_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 86400,
    "CACHE_KEY_PREFIX": "superset_filter_",
    "CACHE_REDIS_HOST": VALKEY_HOST,
    "CACHE_REDIS_PORT": VALKEY_PORT,
    "CACHE_REDIS_DB": 2,
}

# DB 3: Cache de formulario Explore
EXPLORE_FORM_DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 86400,
    "CACHE_KEY_PREFIX": "superset_explore_",
    "CACHE_REDIS_HOST": VALKEY_HOST,
    "CACHE_REDIS_PORT": VALKEY_PORT,
    "CACHE_REDIS_DB": 3,
}

# DB 6: Backend de resultados para consultas asincronas (allow_run_async: True)
RESULTS_BACKEND = RedisCache(
    host=VALKEY_HOST,
    port=VALKEY_PORT,
    db=6,
    key_prefix="superset_results_",
    default_timeout=86400,
)

# -----------------------------------------------------------------------------
# Celery Configuration (Broker DB 4, Result Backend DB 5)
# -----------------------------------------------------------------------------
class CeleryConfig:
    broker_url = f"redis://{VALKEY_HOST}:{VALKEY_PORT}/4"
    imports = ("superset.tasks", "superset.tasks.celery_app")
    result_backend = f"redis://{VALKEY_HOST}:{VALKEY_PORT}/5"
    worker_prefetch_multiplier = 1
    task_acks_late = False

CELERY_CONFIG = CeleryConfig

# -----------------------------------------------------------------------------
# Parametros Web y Limites Analiticos
# -----------------------------------------------------------------------------
ROW_LIMIT = 50000
SUPERSET_WEBSERVER_TIMEOUT = 120
SQLLAB_ASYNC_TIME_LIMIT_SEC = 300
SUPERSET_DASHBOARD_POSITION_DATA_LIMIT = 65536
TALISMAN_ENABLED = False
WTF_CSRF_ENABLED = False