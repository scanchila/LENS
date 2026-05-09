# Custom Postgres image bundling Apache AGE + pgvector.
# Pinned to PG16 for AGE 1.5.0 stability; bump after AGE PG17/PG18 releases stabilize.
FROM postgres:16-bookworm

ARG AGE_VERSION=PG16/1.5.0

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        git \
        bison \
        flex \
        libreadline-dev \
        zlib1g-dev \
        postgresql-server-dev-16 \
        postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "release/${AGE_VERSION}" https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age \
    && make install \
    && rm -rf /tmp/age

# Init scripts auto-run on first DB startup; we enable extensions here so
# downstream Alembic migrations can rely on them existing.
COPY init-extensions.sh /docker-entrypoint-initdb.d/00-extensions.sh
RUN chmod +x /docker-entrypoint-initdb.d/00-extensions.sh
