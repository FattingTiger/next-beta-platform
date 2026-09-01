#!/bin/sh
set -eu

ENTRYPOINT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER_DIR=$(CDPATH= cd -- "$ENTRYPOINT_DIR/.." && pwd)

read_secret() {
    secret_path=$1
    secret_name=$2
    if [ ! -f "$secret_path" ]; then
        echo "missing ${secret_name} secret file" >&2
        exit 1
    fi
    if [ ! -s "$secret_path" ]; then
        echo "empty ${secret_name} secret file" >&2
        exit 1
    fi
    cat "$secret_path"
}

if [ -z "${BETA_DATABASE_URL:-}" ]; then
    db_password_file=${BETA_DB_PASSWORD_FILE:-/run/secrets/db_password}
    if [ ! -s "$db_password_file" ]; then
        echo "missing database password secret file" >&2
        exit 1
    fi
    export BETA_DATABASE_URL="$(python "$SERVER_DIR/scripts/database_url.py" "$db_password_file")"
fi

if [ -z "${BETA_SECRET_KEY:-}" ]; then
    app_secret_file=${BETA_SECRET_KEY_FILE:-/run/secrets/app_secret}
    export BETA_SECRET_KEY="$(read_secret "$app_secret_file" "application")"
fi

if [ "${BETA_RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic -c "$SERVER_DIR/alembic.ini" upgrade head
fi

exec "$@"
