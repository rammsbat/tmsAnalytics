# ETL ELT dbt-core + dbt-oracle (Thin Mode, ejecuta como ETL_RUNNER)
# Contexto de build: raiz del repositorio (aplica .dockerignore raiz).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# git: requerido por dbt (dbt debug devuelve exit 1 sin git en la imagen)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY etl/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# profiles.yml generado desde la plantilla (solo env_var(...), sin secretos)
# DBT_TARGET_PATH / DBT_LOG_PATH apuntan a rutas escribibles por appuser.
ENV DBT_PROFILES_DIR=/app/profiles \
    DBT_TARGET_PATH=/home/appuser/dbt_artifacts/target \
    DBT_LOG_PATH=/home/appuser/dbt_artifacts/logs

RUN mkdir -p /app/profiles "$DBT_TARGET_PATH" "$DBT_LOG_PATH" \
    && chown -R appuser:appuser /app /home/appuser/dbt_artifacts

COPY --chown=appuser:appuser etl/dbt_tms/profiles.template.yml /app/profiles/profiles.yml
COPY --chown=appuser:appuser etl/dbt_tms/ /app/dbt_tms/

WORKDIR /app/dbt_tms

USER appuser

CMD ["dbt", "--version"]
