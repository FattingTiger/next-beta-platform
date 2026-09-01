#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
    echo "usage: $0 capture DIRECTORY | compare BEFORE_DIRECTORY AFTER_DIRECTORY" >&2
    exit 2
}

hash_command() {
    local destination=$1
    shift
    local temporary
    temporary=$(mktemp)
    if "$@" > "$temporary" 2>/dev/null; then
        sha256sum "$temporary" | awk '{print $1}' > "$destination"
    else
        rm -f "$temporary"
        return 1
    fi
    rm -f "$temporary"
}

hash_firewall() {
    local destination=$1
    shift
    local raw normalized
    raw=$(mktemp)
    normalized=$(mktemp)
    if "$@" > "$raw" 2>/dev/null; then
        # CentOS 7 iptables-save can emit Generated/Completed timestamps and
        # live packet:byte counters. Neither represents policy, so normalize
        # both before hashing or an unchanged ruleset will appear different.
        sed -E -e '/^#/d' -e 's/\[[0-9]+:[0-9]+\]/[0:0]/g' "$raw" > "$normalized"
        sha256sum "$normalized" | awk '{print $1}' > "$destination"
    else
        rm -f "$raw" "$normalized"
        return 1
    fi
    rm -f "$raw" "$normalized"
}

hash_routes() {
    local destination=$1
    shift
    local raw normalized
    raw=$(mktemp)
    normalized=$(mktemp)
    if "$@" > "$raw" 2>/dev/null; then
        # Router-advertisement and cache routes can include a countdown even
        # when the route itself is unchanged. Preserve the route and its source
        # while normalizing only the live timer value.
        sed -E 's/(expires)[[:space:]]+[0-9]+(ms|sec)/\1 <dynamic>/g' \
            "$raw" > "$normalized"
        sha256sum "$normalized" | awk '{print $1}' > "$destination"
    else
        rm -f "$raw" "$normalized"
        return 1
    fi
    rm -f "$raw" "$normalized"
}

fingerprint_sing_box_config() {
    local destination=$1 paths=${BETA_SING_BOX_CONFIG_PATHS:-/etc/sing-box}
    local listing
    listing=$(mktemp)
    : > "$listing"
    local item file found=false
    IFS=: read -r -a configured_paths <<<"$paths"
    for item in "${configured_paths[@]}"; do
        [[ -n "$item" ]] || continue
        if [[ -f "$item" ]]; then
            sha256sum "$item" >> "$listing"
            found=true
        elif [[ -d "$item" ]]; then
            while IFS= read -r file; do
                sha256sum "$file" >> "$listing"
                found=true
            done < <(find "$item" -xdev -type f -print | LC_ALL=C sort)
        else
            rm -f "$listing"
            die "configured sing-box fingerprint path is missing: $item"
        fi
    done
    [[ "$found" == true ]] || {
        rm -f "$listing"
        die "no sing-box configuration files were fingerprinted"
    }
    LC_ALL=C sort -o "$listing" "$listing"
    sha256sum "$listing" | awk '{print $1}' > "$destination"
    rm -f "$listing"
}

normalize_listeners() {
    # Recv-Q is live traffic and Send-Q is the current listen backlog. Neither
    # describes listener ownership, so retaining them can make an unchanged VPN
    # look different between the before/after snapshots.
    awk '{
        if ($1 ~ /^(tcp|udp|raw|sctp|dccp)$/) {
            $3 = 0
            $4 = 0
        } else {
            $2 = 0
            $3 = 0
        }
        print
    }'
}

capture() {
    local destination=$1
    require_root
    for command in systemctl sha256sum ss ip iptables-save; do
        require_command "$command"
    done
    # Snapshots contain privileged host metadata and are commonly created from a
    # root shell with a caller-supplied path. Refuse to reuse an existing path so
    # a stale directory or symlink cannot redirect the writes below.
    [[ ! -e "$destination" && ! -L "$destination" ]] || \
        die "snapshot destination already exists: $destination"
    install -d -o root -g root -m 0700 -- "$destination"

    systemctl show sing-box \
        --property=ActiveState,SubState,MainPID,FragmentPath \
        > "$destination/sing-box.runtime"
    grep -qx 'ActiveState=active' "$destination/sing-box.runtime" || \
        die "sing-box is not active"
    systemctl cat sing-box | sha256sum | awk '{print $1}' > "$destination/sing-box.unit"
    fingerprint_sing_box_config "$destination/sing-box.config"

    ss -H -lntup | grep 'sing-box' | normalize_listeners | LC_ALL=C sort \
        > "$destination/sing-box.listeners" || true
    [[ -s "$destination/sing-box.listeners" ]] || die "no sing-box listener is visible"
    ss -H -ltnp | awk '$4 ~ /(^|\]|\*|:|0\.0\.0\.0):443$/ || $4 ~ /:443$/ {print}' \
        | normalize_listeners | LC_ALL=C sort > "$destination/port-443.listeners"
    grep -q 'sing-box' "$destination/port-443.listeners" || \
        die "TCP 443 is not visibly owned by sing-box"

    hash_command "$destination/ip.rules4" ip -4 rule show
    hash_command "$destination/ip.rules6" ip -6 rule show
    hash_routes "$destination/ip.routes4" ip -4 route show table all
    hash_routes "$destination/ip.routes6" ip -6 route show table all
    hash_firewall "$destination/iptables.v4" iptables-save
    if command -v ip6tables-save >/dev/null 2>&1; then
        hash_firewall "$destination/iptables.v6" ip6tables-save
    else
        printf 'unavailable\n' > "$destination/iptables.v6"
    fi

    (cd "$destination" && sha256sum sing-box.* port-443.listeners ip.* iptables.* > manifest.sha256)
    : > "$destination/complete"
    chmod 0600 "$destination"/*
}

compare() {
    local before=$1 after=$2 changed=false component
    [[ -f "$before/complete" && -f "$after/complete" ]] || die "incomplete host snapshot"
    for component in \
        sing-box.runtime sing-box.unit sing-box.config sing-box.listeners \
        port-443.listeners ip.rules4 ip.rules6 ip.routes4 ip.routes6 \
        iptables.v4 iptables.v6; do
        if ! cmp -s "$before/$component" "$after/$component"; then
            log "host invariant changed: $component"
            if [[ "$component" == sing-box.runtime || "$component" == sing-box.listeners || "$component" == port-443.listeners ]]; then
                diff -u "$before/$component" "$after/$component" >&2 || true
            fi
            changed=true
        fi
    done
    [[ "$changed" == false ]]
}

case ${1:-} in
    capture)
        [[ $# -eq 2 ]] || usage
        capture "$2"
        ;;
    compare)
        [[ $# -eq 3 ]] || usage
        compare "$2" "$3"
        ;;
    *) usage ;;
esac
