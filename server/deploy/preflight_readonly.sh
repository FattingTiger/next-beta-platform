#!/bin/sh
set -eu

port=${BETA_HTTP_PORT:-18088}
case "$port" in
    ''|*[!0-9]*) echo "BETA_HTTP_PORT must be numeric" >&2; exit 1 ;;
esac
if [ "$port" -lt 1024 ] || [ "$port" -gt 65535 ]; then
    echo "BETA_HTTP_PORT must be a high port between 1024 and 65535" >&2
    exit 1
fi

section() {
    printf '\n[%s]\n' "$1"
}

section timestamp
date -u +%Y-%m-%dT%H:%M:%SZ
section operating_system
uname -a
if [ -r /etc/os-release ]; then
    cat /etc/os-release
fi
section resources
df -h
free -h 2>/dev/null || true
section listening_sockets
ss -lntup
section routes
ip route show
ip -6 route show 2>/dev/null || true
section firewall_readonly_fingerprints
firewall_fingerprint() {
    label=$1
    shift
    snapshot=$(mktemp)
    if "$@" > "$snapshot" 2>/dev/null; then
        digest=$(sha256sum "$snapshot" | awk '{print $1}')
        printf '%s=%s\n' "$label" "$digest"
    else
        printf '%s=unavailable\n' "$label"
    fi
    rm -f "$snapshot"
}
if command -v nft >/dev/null 2>&1; then
    firewall_fingerprint nft nft list ruleset
fi
if command -v iptables-save >/dev/null 2>&1; then
    firewall_fingerprint iptables iptables-save
fi
if command -v ip6tables-save >/dev/null 2>&1; then
    firewall_fingerprint ip6tables ip6tables-save
fi
section sing_box_service
systemctl is-active sing-box 2>/dev/null || true
systemctl show sing-box \
    --property=ActiveState,SubState,MainPID,FragmentPath,ExecMainStartTimestamp \
    2>/dev/null || true
section sing_box_config_fingerprints
if [ -d /etc/sing-box ]; then
    find /etc/sing-box -type f -exec sha256sum {} \; 2>/dev/null || true
fi
section docker
docker version 2>/dev/null || true
docker compose version 2>/dev/null || true
docker info --format '{{json .SecurityOptions}}' 2>/dev/null || true
section requested_port
if ss -H -ltn "sport = :$port" | head -n 1 | grep -q .; then
    echo "port $port is already in use"
    exit 1
fi
echo "loopback port $port is available"
