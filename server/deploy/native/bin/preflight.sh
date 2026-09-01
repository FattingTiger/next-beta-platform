#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
    echo "usage: $0 RUNTIME_ENV SNAPSHOT_DIRECTORY" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage
require_root
load_runtime_env "$1"
validate_runtime_env

for command in awk curl find flock getcap grep install ip openssl readlink runuser \
    sed setcap sha256sum ss stat systemctl systemd-tmpfiles tar timedatectl useradd usermod groupadd; do
    require_command "$command"
done

[[ -r /etc/centos-release ]] || die "this staging procedure is restricted to CentOS 7"
grep -Eq 'CentOS Linux release 7\.' /etc/centos-release || \
    die "this staging procedure is restricted to CentOS 7"
log "WARNING: CentOS 7 is end-of-life; this host must remain test-only"

clock_is_ntp_synchronized() {
    local modern_status legacy_status
    if modern_status=$(LC_ALL=C timedatectl show --property=NTPSynchronized 2>/dev/null) && \
        grep -qx 'NTPSynchronized=yes' <<<"$modern_status"; then
        return 0
    fi
    if legacy_status=$(LC_ALL=C timedatectl status 2>/dev/null) && \
        grep -Eq '^[[:space:]]*NTP synchronized:[[:space:]]*yes[[:space:]]*$' \
            <<<"$legacy_status"; then
        return 0
    fi
    return 1
}

clock_is_ntp_synchronized || \
    die "system clock is not NTP-synchronized; ACME and TLS checks would be unreliable"

memory_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
[[ ${memory_kib:-0} -ge 900000 ]] || die "at least 900000 KiB RAM is required"
if [[ -d "$NATIVE_STATE" ]]; then
    available_kib=$(df -Pk "$NATIVE_STATE" | awk 'NR == 2 {print $4}')
else
    available_kib=$(df -Pk /var/lib | awk 'NR == 2 {print $4}')
fi
[[ ${available_kib:-0} -ge 6291456 ]] || die "at least 6 GiB free under /var/lib is required"

service_active sing-box || die "sing-box must be active before deployment"

port_is_listening() {
    local port=$1
    ss -H -ltn | awk -v suffix=":$port" '$4 ~ suffix "$" {found=1} END {exit !found}'
}

check_owned_or_free_port() {
    local port=$1 unit=$2
    if port_is_listening "$port" && ! service_active "$unit"; then
        die "TCP port $port is already used by a non-project service"
    fi
}

check_owned_or_free_port 80 beta-center-caddy.service
check_owned_or_free_port 18443 beta-center-caddy.service
check_owned_or_free_port 55432 beta-center-postgres.service
check_owned_or_free_port 18089 beta-center-app.service

if ! ss -H -ltnp | awk '$4 ~ /:443$/ {print}' | grep -q sing-box; then
    die "TCP 443 must remain owned by sing-box"
fi

"$SCRIPT_DIR/host-state.sh" capture "$2"
log "read-only preflight passed; no firewall, route, or sing-box setting was changed"
