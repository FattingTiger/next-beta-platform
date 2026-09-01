#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly APP_PYTHON=/opt/beta-center-native/app/current/.venv/bin/python

# The product ceiling is 100 simultaneous testers. Keep headroom for
# readiness and download-completion requests without spawning another worker
# or increasing the one-GiB staging host's steady memory footprint.
exec "$SCRIPT_DIR/with-app-env.sh" \
    "$APP_PYTHON" -m uvicorn beta_center.main:app \
    --host 127.0.0.1 \
    --port 18089 \
    --workers 1 \
    --limit-concurrency 128 \
    --no-proxy-headers \
    --no-access-log
