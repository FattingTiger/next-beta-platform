#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

[[ $# -eq 1 ]] || die "usage: $0 RUNTIME_ENV"
require_root
load_runtime_env "$1"
validate_runtime_env
service_active beta-center-postgres.service || die "native PostgreSQL is not active"

password=$(tr -d '\n' < "$BETA_DB_PASSWORD_FILE")
[[ "$password" =~ ^[A-Za-z0-9+/=]+$ ]] || die "database secret has an unexpected format"

{
    printf "\\set db_password '%s'\n" "$password"
    cat <<'SQL'
SELECT format('CREATE ROLE beta_center LOGIN PASSWORD %L', :'db_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'beta_center') \gexec
SELECT format('ALTER ROLE beta_center LOGIN PASSWORD %L', :'db_password') \gexec
ALTER ROLE beta_center NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
SELECT 'CREATE DATABASE beta_center OWNER beta_center'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'beta_center') \gexec
REVOKE ALL ON DATABASE beta_center FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE beta_center TO beta_center;
SQL
} | run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/psql" \
    --host=/run/beta-center-pg --port=55432 --dbname=postgres \
    --set=ON_ERROR_STOP=1 --no-psqlrc --quiet
unset password
log "database role and database are ready"

