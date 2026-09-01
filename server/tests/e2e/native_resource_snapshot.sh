#!/usr/bin/env bash

set -Eeuo pipefail

die() {
    printf '[native-resource-snapshot] ERROR: %s\n' "$*" >&2
    exit 1
}

[[ $# -eq 1 ]] || die "usage: $0 OUTPUT_FILE"
[[ ${EUID:-$(id -u)} -eq 0 ]] || die "run as root"
for command in awk cat cut dirname mv systemctl; do
    command -v "$command" >/dev/null 2>&1 || die "required command is missing: $command"
done

destination=$1
[[ "$destination" == /* ]] || die "output path must be absolute"
[[ -d "$(dirname -- "$destination")" ]] || die "output parent directory does not exist"
[[ ! -e "$destination" && ! -L "$destination" ]] || die "output path already exists"

memory_mount=$(awk '$3 == "cgroup" && $4 ~ /(^|,)memory(,|$)/ {print $2; exit}' /proc/mounts)
cpu_mount=$(awk '$3 == "cgroup" && $4 ~ /(^|,)cpu(,|$)/ {print $2; exit}' /proc/mounts)
[[ -d "$memory_mount" ]] || die "cgroup v1 memory controller is unavailable"
[[ -d "$cpu_mount" ]] || die "cgroup v1 cpu controller is unavailable"

temporary="$destination.tmp.$$"
[[ ! -e "$temporary" && ! -L "$temporary" ]] || die "temporary output path already exists"
umask 077
: >"$temporary"
cleanup() {
    status=$?
    trap - EXIT
    rm -f -- "$temporary"
    exit "$status"
}
trap cleanup EXIT

for unit in beta-center.slice beta-center-postgres.service \
    beta-center-app.service beta-center-caddy.service; do
    control_group=$(systemctl show "$unit" --property=ControlGroup | cut -d= -f2-)
    [[ -n "$control_group" ]] || die "unit has no active cgroup: $unit"
    [[ -d "$memory_mount$control_group" && -d "$cpu_mount$control_group" ]] || \
        die "controller path is missing for $unit"
    printf '[%s]\n' "$unit" >>"$temporary"
    for metric in memory.limit_in_bytes memory.usage_in_bytes \
        memory.max_usage_in_bytes memory.failcnt; do
        printf '%s=' "$metric" >>"$temporary"
        cat "$memory_mount$control_group/$metric" >>"$temporary"
    done
    for metric in cpu.cfs_period_us cpu.cfs_quota_us; do
        printf '%s=' "$metric" >>"$temporary"
        cat "$cpu_mount$control_group/$metric" >>"$temporary"
    done
done

chmod 0600 "$temporary"
mv -- "$temporary" "$destination"
trap - EXIT
printf '[native-resource-snapshot] PASS: %s\n' "$destination" >&2
