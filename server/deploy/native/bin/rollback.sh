#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

[[ $# -eq 1 ]] || die "usage: $0 TRANSACTION_DIRECTORY"
require_root
transaction=$(readlink_physical "$1")
case "$transaction/" in
    "$NATIVE_TRANSACTION_ROOT"/*/) ;;
    *) die "transaction must be below $NATIVE_TRANSACTION_ROOT" ;;
esac
[[ -d "$transaction" && ! -L "$transaction" && -f "$transaction/service-state" ]] || \
    die "invalid transaction directory"

exec 9>"$NATIVE_LOCK"
flock -n 9 || die "another native maintenance operation is running"

log "rolling back only Beta Center native services; sing-box is never restarted or reconfigured"
systemctl stop beta-center-caddy.service beta-center-app.service || true

if [[ -f "$transaction/previous-current" ]]; then
    previous=$(cat "$transaction/previous-current")
    if [[ "$previous" == NONE ]]; then
        rm -f "$NATIVE_PREFIX/app/current"
    else
        [[ -d "$previous" ]] || die "previous application release is missing: $previous"
        ln -sfn "$previous" "$NATIVE_PREFIX/app/current"
    fi
fi

if [[ -f "$transaction/database.dump" ]]; then
    systemctl start beta-center-postgres.service
    for _ in {1..30}; do
        if run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/pg_isready" \
            --host=/run/beta-center-pg --port=55432 --quiet; then
            break
        fi
        sleep 1
    done
    run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/psql" \
        --host=/run/beta-center-pg --port=55432 --dbname=postgres \
        --set=ON_ERROR_STOP=1 --no-psqlrc <<'SQL'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname = 'beta_center' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS beta_center;
CREATE DATABASE beta_center OWNER beta_center;
REVOKE ALL ON DATABASE beta_center FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE beta_center TO beta_center;
SQL
    run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/pg_restore" \
        --host=/run/beta-center-pg --port=55432 --dbname=beta_center \
        --exit-on-error --no-owner --role=beta_center < "$transaction/database.dump"
fi

while read -r unit was_active was_enabled; do
    if [[ "$was_enabled" == enabled ]]; then
        systemctl enable "$unit" >/dev/null
    else
        systemctl disable "$unit" >/dev/null 2>&1 || true
    fi
    if [[ "$was_active" == active ]]; then
        systemctl start "$unit"
    else
        systemctl stop "$unit" || true
    fi
done < "$transaction/service-state"

if [[ -d "$transaction/before" ]]; then
    rm -rf "$transaction/after-rollback"
    "$SCRIPT_DIR/host-state.sh" capture "$transaction/after-rollback"
    "$SCRIPT_DIR/host-state.sh" compare "$transaction/before" "$transaction/after-rollback" || \
        die "rollback completed but sing-box/network invariants differ; inspect manually without changing sing-box"
fi
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$transaction/rolled-back"
log "native staging rollback completed"
