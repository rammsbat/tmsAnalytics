FROM apache/superset:4.1.1

USER root

RUN pip install --no-cache-dir \
    oracledb \
    psycopg2-binary \
    redis

USER superset
