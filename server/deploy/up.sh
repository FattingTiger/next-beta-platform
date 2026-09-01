#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${1:-$SERVER_DIR/.env.production}
COMPOSE_FILE=$SERVER_DIR/docker-compose.yml

if [ ! -f "$ENV_FILE" ]; then
    echo "runtime env file not found: $ENV_FILE" >&2
    exit 1
fi

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

sing_box_config_fingerprint() {
    if [ -d /etc/sing-box ] && command -v sha256sum >/dev/null 2>&1; then
        find /etc/sing-box -type f -exec sha256sum {} \; 2>/dev/null \
            | sort \
            | sha256sum \
            | awk '{print $1}'
    else
        printf 'unavailable\n'
    fi
}

capture_host_invariants() {
    destination=$1
    if ! systemctl show sing-box --property=ActiveState,SubState,MainPID \
        > "$destination.runtime" 2>/dev/null; then
        echo "cannot snapshot sing-box runtime state" >&2
        return 1
    fi
    if ! grep -q '^ActiveState=active$' "$destination.runtime"; then
        echo "sing-box is not active before/after deployment" >&2
        return 1
    fi
    sing_box_config_fingerprint > "$destination.config"

    if ! ss -H -lntup > "$destination.listeners-all" 2>/dev/null; then
        echo "cannot snapshot listening sockets" >&2
        return 1
    fi
    grep 'sing-box' "$destination.listeners-all" 2>/dev/null \
        | LC_ALL=C sort > "$destination.listeners" || true
    rm -f "$destination.listeners-all"

    if ! ip -4 rule show > "$destination.rules4"; then
        echo "cannot snapshot IPv4 policy rules" >&2
        return 1
    fi
    if ! ip -6 rule show > "$destination.rules6" 2>/dev/null; then
        : > "$destination.rules6"
    fi
    cat "$destination.rules4" "$destination.rules6" | LC_ALL=C sort > "$destination.rules"
    rm -f "$destination.rules4" "$destination.rules6"

    if ! ip -4 route show table all > "$destination.routes4"; then
        echo "cannot snapshot IPv4 routes" >&2
        return 1
    fi
    if ! ip -6 route show table all > "$destination.routes6" 2>/dev/null; then
        : > "$destination.routes6"
    fi
    cat "$destination.routes4" "$destination.routes6" \
        | awk '$1 == "default"' \
        | LC_ALL=C sort > "$destination.defaults"
    rm -f "$destination.routes4" "$destination.routes6"
}

host_invariants_unchanged() {
    before=$1
    after=$2
    unchanged=true
    for component in runtime config listeners rules defaults; do
        if ! cmp -s "$before.$component" "$after.$component"; then
            echo "host invariant changed: $component" >&2
            diff -u "$before.$component" "$after.$component" >&2 || true
            unchanged=false
        fi
    done
    [ "$unchanged" = true ]
}

compose_config=$(compose config --format json)
printf '%s\n' "$compose_config" | python3 "$SCRIPT_DIR/verify_compose_isolation.py"

for secret in db_password app_secret; do
    path=$(printf '%s\n' "$compose_config" | python3 -c '
import json, sys
document = json.load(sys.stdin)
print(document["secrets"][sys.argv[1]]["file"])
' "$secret")
    if [ ! -s "$path" ]; then
        echo "missing secret: $path" >&2
        exit 1
    fi
    if command -v stat >/dev/null 2>&1; then
        mode=$(stat -c '%a' "$path" 2>/dev/null || stat -f '%Lp' "$path")
        if [ "$mode" != "600" ]; then
            echo "secret must have mode 0600: $path" >&2
            exit 1
        fi
    fi
done

set -- $(printf '%s\n' "$compose_config" | python3 -c '
import json, sys
document = json.load(sys.stdin)
for name in ("edge", "ingress"):
    network = document["networks"][name]
    print(network["ipam"]["config"][0]["subnet"], network["name"])
')
python3 "$SCRIPT_DIR/check_host_network_overlap.py" "$1" "$2"
python3 "$SCRIPT_DIR/check_host_network_overlap.py" "$3" "$4"

STATE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/beta-center-host-state.XXXXXX")
cleanup() {
    rm -rf "$STATE_DIR"
}
trap cleanup EXIT HUP INT TERM

capture_host_invariants "$STATE_DIR/before"
if ! compose up --detach --build --wait; then
    echo "deployment failed; removing the partial Compose stack" >&2
    compose down >&2 || echo "automatic Compose rollback failed" >&2
    exit 1
fi
if ! capture_host_invariants "$STATE_DIR/after"; then
    echo "post-deployment host snapshot failed; rolling back Compose" >&2
    compose down >&2 || echo "automatic Compose rollback failed" >&2
    exit 1
fi
if ! host_invariants_unchanged "$STATE_DIR/before" "$STATE_DIR/after"; then
    echo "sing-box or its host policy path changed; rolling back Compose" >&2
    compose down >&2 || echo "automatic Compose rollback failed" >&2
    exit 1
fi

compose ps
echo "deployment healthy; gateway remains bound to the configured loopback high port"
