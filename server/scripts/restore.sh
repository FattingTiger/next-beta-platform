#!/bin/sh
set -eu
umask 077

if [ "${1:-}" != "--confirm" ] || [ -z "${2:-}" ]; then
    echo "usage: $0 --confirm BACKUP_DIR [ENV_FILE] [SAFETY_BACKUP_ROOT]" >&2
    exit 2
fi

BACKUP_DIR=$(CDPATH= cd -- "$2" && pwd)
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SERVER_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE=${3:-$SERVER_DIR/.env.production}
SAFETY_BACKUP_ROOT=${4:-$SERVER_DIR/data/backups/pre-restore}
COMPOSE_FILE=$SERVER_DIR/docker-compose.yml
LOCK_DIR=$SERVER_DIR/data/.maintenance.lock

for required in database.dump storage.tar.gz reconcile.json metadata.txt SHA256SUMS; do
    if [ ! -f "$BACKUP_DIR/$required" ]; then
        echo "backup is incomplete; missing $required" >&2
        exit 1
    fi
done
if [ ! -f "$ENV_FILE" ]; then
    echo "runtime env file not found: $ENV_FILE" >&2
    exit 1
fi

mkdir -p "$SERVER_DIR/data"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "another backup or restore already holds $LOCK_DIR" >&2
    exit 1
fi
lock_token=restore-$$-$(date -u +%s)
printf '%s\n' "$lock_token" > "$LOCK_DIR/owner"
lock_owned=true
release_lock() {
    if [ "$lock_owned" = true ]; then
        rm -f "$LOCK_DIR/owner"
        rmdir "$LOCK_DIR" 2>/dev/null || true
        lock_owned=false
    fi
}

restore_started=false
restore_completed=false
SAFETY_BACKUP=
on_exit() {
    if [ "$restore_started" = true ] && [ "$restore_completed" != true ]; then
        echo "restore failed after destructive work began; app and gateway remain stopped" >&2
        echo "recover with safety backup: $SAFETY_BACKUP" >&2
    fi
    release_lock
}
trap on_exit EXIT HUP INT TERM

(
    cd "$BACKUP_DIR"
    sha256sum --check SHA256SUMS
)

compose() {
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
}

compose config >/dev/null
echo "creating mandatory pre-restore safety backup" >&2
SAFETY_BACKUP=$(BETA_MAINTENANCE_LOCK_TOKEN=$lock_token \
    "$SCRIPT_DIR/backup.sh" --lock-held "$ENV_FILE" "$SAFETY_BACKUP_ROOT")
echo "safety backup: $SAFETY_BACKUP" >&2

compose stop gateway >&2
compose stop app >&2
restore_started=true

compose exec -T db sh -ec '
    psql --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid();
DROP SCHEMA public CASCADE;
CREATE SCHEMA public AUTHORIZATION CURRENT_USER;
SQL
'

compose exec -T db sh -ec '
    exec pg_restore \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --exit-on-error \
        --no-owner \
        --no-privileges
' < "$BACKUP_DIR/database.dump"

compose run --rm --no-deps -T \
    -e BETA_RUN_MIGRATIONS=false \
    app python /opt/beta-center/scripts/restore_storage.py --confirm-restore \
    < "$BACKUP_DIR/storage.tar.gz"

compose run --rm --no-deps -T \
    -e BETA_RUN_MIGRATIONS=false \
    app python /opt/beta-center/scripts/reconcile_storage.py --json --fail-on-orphans \
    >&2

compose up --detach --wait app gateway >&2
restore_completed=true
release_lock
trap - EXIT HUP INT TERM
printf 'restore complete; safety backup retained at %s\n' "$SAFETY_BACKUP"
