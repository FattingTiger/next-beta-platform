#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

[[ $# -eq 1 ]] || die "usage: $0 RUNTIME_ENV"
require_root
runtime_env=$1
load_runtime_env "$runtime_env"
validate_runtime_env
[[ -f "$NATIVE_STATE/candidate-release" ]] || die "run install.sh before deploy.sh"
candidate=$(cat "$NATIVE_STATE/candidate-release")
[[ -d "$candidate" && -x "$candidate/.venv/bin/python" ]] || die "invalid candidate release"

exec 9>"$NATIVE_LOCK"
flock -n 9 || die "another native maintenance operation is running"

transaction="$NATIVE_TRANSACTION_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -m 0700 "$transaction"
for unit in beta-center-postgres.service beta-center-app.service beta-center-caddy.service; do
    active=inactive
    enabled=disabled
    service_active "$unit" && active=active
    systemctl is-enabled --quiet "$unit" && enabled=enabled
    printf '%s %s %s\n' "$unit" "$active" "$enabled" >> "$transaction/service-state"
done
if [[ -L "$NATIVE_PREFIX/app/current" ]]; then
    readlink_physical "$NATIVE_PREFIX/app/current" > "$transaction/previous-current"
else
    printf 'NONE\n' > "$transaction/previous-current"
fi
chmod 0600 "$transaction/service-state" "$transaction/previous-current"

rollback_on_error() {
    status=$?
    trap - ERR INT TERM
    log "deployment failed; invoking project-only rollback from $transaction"
    flock -u 9
    "$SCRIPT_DIR/rollback.sh" "$transaction" || \
        log "CRITICAL: automatic rollback failed; keep Beta Center stopped and inspect $transaction"
    exit "$status"
}
trap rollback_on_error ERR INT TERM

"$SCRIPT_DIR/preflight.sh" "$runtime_env" "$transaction/before"

systemctl start beta-center-postgres.service
for _ in {1..30}; do
    if run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/pg_isready" \
        --host=/run/beta-center-pg --port=55432 --quiet; then
        break
    fi
    sleep 1
done
run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/pg_isready" \
    --host=/run/beta-center-pg --port=55432 --quiet
"$SCRIPT_DIR/bootstrap-database.sh" "$runtime_env"

run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/pg_dump" \
    --host=/run/beta-center-pg --port=55432 --format=custom \
    --no-owner --no-acl beta_center > "$transaction/database.dump"
chmod 0600 "$transaction/database.dump"

ln -sfn "$candidate" "$NATIVE_PREFIX/app/current"
run_as beta-app "$NATIVE_PREFIX/bin/migrate.sh"
systemctl restart beta-center-app.service
for _ in {1..45}; do
    if curl --fail --silent --show-error --max-time 3 \
        --header "Host: $BETA_PUBLIC_IP" \
        http://127.0.0.1:18089/health/ready >/dev/null; then
        break
    fi
    sleep 1
done
curl --fail --silent --show-error --max-time 3 \
    --header "Host: $BETA_PUBLIC_IP" \
    http://127.0.0.1:18089/health/ready >/dev/null

BETA_PUBLIC_IP=$BETA_PUBLIC_IP BETA_ACME_EMAIL=${BETA_ACME_EMAIL:-} \
    "$NATIVE_PREFIX/caddy-2.11.4/bin/caddy" adapt \
    --config "$NATIVE_CONFIG/Caddyfile" --adapter caddyfile >/dev/null
systemctl restart beta-center-caddy.service
for _ in {1..120}; do
    if curl --fail --silent --show-error --connect-timeout 3 --max-time 5 \
        "https://$BETA_PUBLIC_IP:18443/health/ready" >/dev/null 2>&1; then
        break
    fi
    sleep 2
done
curl --fail --silent --show-error --connect-timeout 5 --max-time 15 \
    "https://$BETA_PUBLIC_IP:18443/health/ready" >/dev/null
protected_status=$(curl --silent --output /dev/null --write-out '%{http_code}' \
    --connect-timeout 5 --max-time 15 "https://$BETA_PUBLIC_IP:18443/_protected-files/probe")
[[ "$protected_status" == 404 ]] || die "protected storage route returned $protected_status instead of 404"

"$SCRIPT_DIR/host-state.sh" capture "$transaction/after"
"$SCRIPT_DIR/host-state.sh" compare "$transaction/before" "$transaction/after"

systemctl enable beta-center-postgres.service beta-center-app.service beta-center-caddy.service >/dev/null
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$transaction/complete"
rm -f "$NATIVE_STATE/candidate-release"
trap - ERR INT TERM
log "native staging deployment healthy; transaction: $transaction"
