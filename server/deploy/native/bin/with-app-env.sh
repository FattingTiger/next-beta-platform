#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

[[ $# -gt 0 ]] || die "with-app-env.sh requires a command"
validate_runtime_env

readonly app_python="$NATIVE_PREFIX/app/current/.venv/bin/python"
[[ -x "$app_python" ]] || die "application Python is missing: $app_python"
[[ -r "$BETA_DB_PASSWORD_FILE" && -r "$BETA_APP_SECRET_FILE" ]] || die "application secrets are unreadable"

export BETA_ENVIRONMENT=production
export BETA_DATABASE_URL
BETA_DATABASE_URL=$(create_database_url "$app_python" "$BETA_DB_PASSWORD_FILE")
export BETA_SECRET_KEY
BETA_SECRET_KEY=$(tr -d '\n' < "$BETA_APP_SECRET_FILE")
[[ ${#BETA_SECRET_KEY} -ge 32 ]] || die "application secret is too short"
export BETA_STORAGE_ROOT="$NATIVE_STATE/storage"
export BETA_PUBLIC_BASE_URL="https://$BETA_PUBLIC_IP:18443"
export BETA_ALLOWED_HOSTS="[\"$BETA_PUBLIC_IP\"]"
export BETA_TRUSTED_PROXY_NETWORKS='["127.0.0.1/32"]'
export BETA_COOKIE_SECURE=true
export BETA_AUTO_CREATE_SCHEMA=false
export BETA_REQUIRE_APK_TOOLS=true
export BETA_USE_X_ACCEL_REDIRECT=true
# Native-only capacity profile for the one-vCPU staging host. The application
# derives a 20-token database request limiter and 40 AnyIO worker tokens from
# these values. The readiness endpoint shares this pool instead of reserving a
# separate connection. Keep the generic Settings defaults unchanged.
export BETA_DATABASE_POOL_SIZE=16
export BETA_DATABASE_MAX_OVERFLOW=4
export BETA_AAPT_PATH BETA_APKSIGNER_PATH
export JAVA_HOME="$BETA_JAVA_HOME"
export PATH="$JAVA_HOME/bin:$PATH"
export PYTHONPATH="$NATIVE_PREFIX/app/current/src"
export PYTHONUNBUFFERED=1

exec "$@"
