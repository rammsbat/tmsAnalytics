# Simulador de datos sinteticos TMS (escribe unicamente en STG_SRC como SIM_WRITER)
# Contexto de build: raiz del repositorio (aplica .dockerignore raiz).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY simulator/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY --chown=appuser:appuser simulator/ /app/

USER appuser

CMD ["python", "-m", "src.main", "--help"]
