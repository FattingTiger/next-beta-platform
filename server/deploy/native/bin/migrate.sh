#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
readonly APP_PYTHON=/opt/beta-center-native/app/current/.venv/bin/python

cd /opt/beta-center-native/app/current
exec "$SCRIPT_DIR/with-app-env.sh" "$APP_PYTHON" -m alembic -c alembic.ini upgrade head

