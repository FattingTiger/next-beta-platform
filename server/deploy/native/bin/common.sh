#!/usr/bin/env bash

set -Eeuo pipefail

readonly NATIVE_PREFIX=/opt/beta-center-native
readonly NATIVE_CONFIG=/etc/beta-center-native
readonly NATIVE_STATE=/var/lib/beta-center-native
readonly NATIVE_RUNTIME_ENV="$NATIVE_CONFIG/runtime.env"
readonly NATIVE_TRANSACTION_ROOT="$NATIVE_STATE/transactions"
readonly NATIVE_LOCK=/var/lock/beta-center-native.lock

log() {
    printf '[native-staging] %s\n' "$*" >&2
}

die() {
    log "ERROR: $*"
    exit 1
}

require_root() {
    [[ ${EUID:-$(id -u)} -eq 0 ]] || die "run as root"
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command is missing: $1"
}

load_runtime_env() {
    local env_file=${1:-$NATIVE_RUNTIME_ENV}
    [[ -f "$env_file" ]] || die "runtime environment file not found: $env_file"
    [[ ! -L "$env_file" ]] || die "runtime environment file must not be a symlink"
    local owner mode
    owner=$(stat -c '%u' "$env_file")
    mode=$(stat -c '%a' "$env_file")
    [[ "$owner" == 0 ]] || die "runtime environment file must be owned by root"
    [[ "$mode" == 600 || "$mode" == 640 ]] || die "runtime environment file must be mode 0600 or 0640"

    local raw key value
    while IFS= read -r raw || [[ -n "$raw" ]]; do
        raw=${raw%$'\r'}
        [[ -z "$raw" || "$raw" == \#* ]] && continue
        [[ "$raw" == *=* ]] || die "invalid runtime environment line"
        key=${raw%%=*}
        value=${raw#*=}
        case "$key" in
            BETA_ACK_CENTOS7_EOL|BETA_PUBLIC_IP|BETA_ACME_EMAIL|BETA_DB_HOST|BETA_DB_PORT|BETA_DB_NAME|BETA_DB_USER|BETA_APP_HOST|BETA_APP_PORT|BETA_DB_PASSWORD_FILE|BETA_APP_SECRET_FILE|BETA_SING_BOX_CONFIG_PATHS|BETA_AAPT_PATH|BETA_APKSIGNER_PATH|BETA_JAVA_HOME)
                export "$key=$value"
                ;;
            *) die "unsupported key in runtime environment: $key" ;;
        esac
    done < "$env_file"
}

is_public_ipv4() {
    local address=$1
    awk -F. '
        NF != 4 { exit 1 }
        {
            for (i = 1; i <= 4; i++) {
                if ($i !~ /^[0-9]+$/ || $i < 0 || $i > 255) exit 1
            }
            if ($1 == 0 || $1 == 10 || $1 == 127 || $1 >= 224) exit 1
            if ($1 == 100 && $2 >= 64 && $2 <= 127) exit 1
            if ($1 == 169 && $2 == 254) exit 1
            if ($1 == 172 && $2 >= 16 && $2 <= 31) exit 1
            if ($1 == 192 && $2 == 0 && $3 == 0) exit 1
            if ($1 == 192 && $2 == 0 && $3 == 2) exit 1
            if ($1 == 192 && $2 == 168) exit 1
            if ($1 == 198 && ($2 == 18 || $2 == 19)) exit 1
            if ($1 == 198 && $2 == 51 && $3 == 100) exit 1
            if ($1 == 203 && $2 == 0 && $3 == 113) exit 1
        }
    ' <<<"$address"
}

validate_runtime_env() {
    [[ ${BETA_ACK_CENTOS7_EOL:-} == I_UNDERSTAND_TEST_ONLY ]] || \
        die "CentOS 7 EOL acknowledgement is missing; this layout is test-only"
    [[ -n ${BETA_PUBLIC_IP:-} && ${BETA_PUBLIC_IP:-} != __PUBLIC_IPV4__ ]] || \
        die "replace the public IPv4 placeholder"
    is_public_ipv4 "$BETA_PUBLIC_IP" || die "BETA_PUBLIC_IP must be a public IPv4 address"
    if [[ -n ${BETA_ACME_EMAIL:-} && ${BETA_ACME_EMAIL:-} != *@*.* ]]; then
        die "BETA_ACME_EMAIL must be empty or a valid contact address"
    fi

    [[ ${BETA_DB_HOST:-} == 127.0.0.1 ]] || die "PostgreSQL must remain on IPv4 loopback"
    [[ ${BETA_DB_PORT:-} == 55432 ]] || die "PostgreSQL port must remain 55432"
    [[ ${BETA_DB_NAME:-} == beta_center ]] || die "unexpected database name"
    [[ ${BETA_DB_USER:-} == beta_center ]] || die "unexpected database user"
    [[ ${BETA_APP_HOST:-} == 127.0.0.1 ]] || die "Uvicorn must remain on IPv4 loopback"
    [[ ${BETA_APP_PORT:-} == 18089 ]] || die "Uvicorn port must remain 18089"
    [[ ${BETA_DB_PASSWORD_FILE:-} == "$NATIVE_CONFIG/secrets/db_password" ]] || \
        die "database secret must remain under the native config prefix"
    [[ ${BETA_APP_SECRET_FILE:-} == "$NATIVE_CONFIG/secrets/app_secret" ]] || \
        die "application secret must remain under the native config prefix"
    [[ ${BETA_AAPT_PATH:-} == "$NATIVE_PREFIX/android-tools/bin/aapt" ]] || \
        die "unexpected aapt path"
    [[ ${BETA_APKSIGNER_PATH:-} == "$NATIVE_PREFIX/android-tools/bin/apksigner" ]] || \
        die "unexpected apksigner path"
    [[ ${BETA_JAVA_HOME:-} == "$NATIVE_PREFIX/java" ]] || die "unexpected Java prefix"
}

run_as() {
    local account=$1
    shift
    runuser -u "$account" -- "$@"
}

service_active() {
    systemctl is-active --quiet "$1"
}

ensure_secret_file() {
    local path=$1 group=$2 bytes=$3
    if [[ ! -e "$path" ]]; then
        umask 077
        openssl rand -base64 "$bytes" > "$path"
    fi
    [[ -f "$path" && ! -L "$path" && -s "$path" ]] || die "invalid secret file: $path"
    chown root:"$group" "$path"
    chmod 0640 "$path"
}

readlink_physical() {
    readlink -f "$1"
}

create_database_url() {
    local python_bin=$1 password_file=$2
    "$python_bin" -c '
import sys
from urllib.parse import quote

password = sys.stdin.read().rstrip("\n")
if not password:
    raise SystemExit("empty database password")
user, host, port, database = sys.argv[1:]
escaped_user = quote(user, safe="")
escaped_password = quote(password, safe="")
escaped_database = quote(database, safe="")
print(f"postgresql+psycopg://{escaped_user}:{escaped_password}@{host}:{port}/{escaped_database}")
' "$BETA_DB_USER" "$BETA_DB_HOST" "$BETA_DB_PORT" "$BETA_DB_NAME" < "$password_file"
}
