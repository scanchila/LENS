#!/bin/bash
# Runs once on first DB initialization. Enables pgvector and Apache AGE
# in the application database created from POSTGRES_DB.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE EXTENSION IF NOT EXISTS age;
    LOAD 'age';
    SET search_path = ag_catalog, "\$user", public;
EOSQL
