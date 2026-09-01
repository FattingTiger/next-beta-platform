#!/bin/sh
set -eu
umask 077

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
lock_is_external=false
if [ "${1:-}" = "--lock-held" ]; then
    lock_is_external=true
    shift
fi
ENV_FILE=${1:-$SERVER_DIR/.env.production}
BACKUP_ROOT=${2:-$SERVER_DIR/data/backups}
COMPOSE_FILE=$SERVER_DIR/docker-compose.yml
LOCK_DIR=$SERVER_DIR/data/.maintenance.lock

if [ ! -f "$ENV_FILE" ]; then
    echo "runtime env file not found: $ENV_FILE" >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required" >&2
    exit 1
fi

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose config >/dev/null
mkdir -p "$BACKUP_ROOT" "$SERVER_DIR/data"
lock_owned=false
if [ "$lock_is_external" = true ]; then
    if [ -z "${BETA_MAINTENANCE_LOCK_TOKEN:-}" ] \
        || [ ! -f "$LOCK_DIR/owner" ] \
        || [ "$(cat "$LOCK_DIR/owner")" != "$BETA_MAINTENANCE_LOCK_TOKEN" ]; then
        echo "invalid inherited maintenance lock" >&2
        exit 1
    fi
else
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        echo "another backup or restore already holds $LOCK_DIR" >&2
        exit 1
    fi
    lock_token=backup-$$-$(date -u +%s)
    printf '%s\n' "$lock_token" > "$LOCK_DIR/owner"
    lock_owned=true
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
PARTIAL_DIR=$(mktemp -d "$BACKUP_ROOT/.partial-${timestamp}.XXXXXX")
FINAL_DIR=$BACKUP_ROOT/backup-$timestamp
app_was_running=false
gateway_was_running=false
completed=false

restart_previous_services() {
    restart_failed=false
    if [ "$app_was_running" = true ]; then
        if ! compose up --detach --wait app >&2; then
            echo "failed to restart app after backup" >&2
            restart_failed=true
        fi
    fi
    if [ "$gateway_was_running" = true ]; then
        if ! compose up --detach --wait gateway >&2; then
            echo "failed to restart gateway after backup" >&2
            restart_failed=true
        fi
    fi
    [ "$restart_failed" = false ]
}

release_lock() {
    if [ "$lock_owned" = true ]; then
        rm -f "$LOCK_DIR/owner"
        rmdir "$LOCK_DIR" 2>/dev/null || true
        lock_owned=false
    fi
}

cleanup() {
    if [ "$completed" != true ]; then
        if ! restart_previous_services; then
            echo "backup failed and one or more services also failed to restart" >&2
        fi
        rm -rf "$PARTIAL_DIR"
    fi
    release_lock
}
trap cleanup EXIT HUP INT TERM

running_services=$(compose ps --status running --services)
case "
$running_services
" in
    *"
app
"*) app_was_running=true ;;
esac
case "
$running_services
" in
    *"
gateway
"*) gateway_was_running=true ;;
esac
if [ "$app_was_running" != true ]; then
    echo "the app service must be healthy and running before backup" >&2
    exit 1
fi

compose up --detach --wait db >&2
if [ "$gateway_was_running" = true ]; then
    compose stop gateway >&2
fi
compose stop app >&2

compose run --rm --no-deps -T \
    -e BETA_RUN_MIGRATIONS=false \
    app python /opt/beta-center/scripts/reconcile_storage.py --json --fail-on-orphans \
    > "$PARTIAL_DIR/reconcile.json"

compose exec -T db sh -ec '
    exec pg_dump \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --format=custom \
        --compress=9 \
        --no-owner \
        --no-privileges
' > "$PARTIAL_DIR/database.dump"

compose run --rm --no-deps -T \
    -e BETA_RUN_MIGRATIONS=false \
    app python /opt/beta-center/scripts/archive_storage.py \
    > "$PARTIAL_DIR/storage.tar.gz"

{
    printf 'created_at=%s\n' "$timestamp"
    printf 'compose_project=beta-center\n'
    compose exec -T db sh -ec 'postgres --version'
    compose exec -T db sh -ec \
        'psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --tuples-only --no-align --command="SELECT version_num FROM alembic_version"'
} > "$PARTIAL_DIR/metadata.txt"

(
    cd "$PARTIAL_DIR"
    sha256sum database.dump storage.tar.gz reconcile.json metadata.txt > SHA256SUMS
)

if [ -e "$FINAL_DIR" ]; then
    echo "backup destination already exists: $FINAL_DIR" >&2
    exit 1
fi
mv "$PARTIAL_DIR" "$FINAL_DIR"
completed=true
if ! restart_previous_services; then
    echo "backup was committed at $FINAL_DIR, but service restart failed" >&2
    exit 1
fi
release_lock
trap - EXIT HUP INT TERM
printf '%s\n' "$FINAL_DIR"
