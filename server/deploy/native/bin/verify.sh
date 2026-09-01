#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ASSET_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
caddy_binary=
require_systemd=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --caddy) caddy_binary=$2; shift 2 ;;
        --require-systemd) require_systemd=true; shift ;;
        *) echo "usage: $0 [--caddy FILE] [--require-systemd]" >&2; exit 2 ;;
    esac
done

if [[ "$require_systemd" == true && -z "$caddy_binary" ]]; then
    echo "--require-systemd requires --caddy so target verification includes adapted transport JSON" >&2
    exit 2
fi

for script in "$SCRIPT_DIR"/*.sh; do
    bash -n "$script"
done

python_command=python3
command -v "$python_command" >/dev/null 2>&1 || python_command=/opt/beta-center-native/python-3.12/bin/python3
"$python_command" "$ASSET_DIR/verify_assets.py"

if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "$ASSET_DIR"/systemd/*.service "$ASSET_DIR"/systemd/*.slice
elif [[ "$require_systemd" == true ]]; then
    echo "systemd-analyze is required on the target host" >&2
    exit 1
else
    echo "systemd-analyze unavailable; target verification remains required" >&2
fi

if [[ -n "$caddy_binary" ]]; then
    [[ -x "$caddy_binary" ]] || { echo "Caddy binary is not executable" >&2; exit 1; }
    caddy_version=$("$caddy_binary" version)
    [[ "$caddy_version" =~ ^v2\.11\.4([[:space:]]|$) ]] || {
        echo "Caddy must be exactly v2.11.4" >&2
        exit 1
    }
    adapted_json=$(mktemp)
    trap 'rm -f "$adapted_json"' EXIT
    BETA_PUBLIC_IP=192.0.2.1 BETA_ACME_EMAIL= \
        "$caddy_binary" adapt --config "$ASSET_DIR/Caddyfile" --adapter caddyfile \
        > "$adapted_json"
    "$python_command" "$ASSET_DIR/verify_assets.py" --adapted-json "$adapted_json"
    rm -f "$adapted_json"
    trap - EXIT
else
    echo "Caddy binary not supplied; exact 2.11.4 and GHSA-6365 transport adaptation remain required" >&2
fi

echo "native staging static verification: ok"
