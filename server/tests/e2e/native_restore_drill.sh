#!/usr/bin/env bash

set -Eeuo pipefail

export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
umask 077

readonly NATIVE_PREFIX=/opt/beta-center-native
readonly NATIVE_STATE=/var/lib/beta-center-native
readonly TRANSACTION_ROOT="$NATIVE_STATE/transactions"
readonly LOCK_FILE=/var/lock/beta-center-native.lock
readonly PG_BIN="$NATIVE_PREFIX/postgresql-17/bin"
readonly PG_SOCKET=/run/beta-center-pg
readonly PG_PORT=55432
readonly PG_DATA="$NATIVE_STATE/postgres"
readonly SOURCE_DATABASE=beta_center

log() {
    printf '[native-restore-drill] %s\n' "$*" >&2
}

die() {
    log "ERROR: $*"
    exit 1
}

[[ ${EUID:-$(id -u)} -eq 0 ]] || die "run as root"
for command in awk cmp df flock install runuser sha256sum systemctl; do
    command -v "$command" >/dev/null 2>&1 || die "required command is missing: $command"
done
for command in createdb dropdb pg_dump pg_restore psql; do
    [[ -x "$PG_BIN/$command" ]] || die "PostgreSQL command is missing: $command"
done

[[ ! -L "$LOCK_FILE" ]] || die "native maintenance lock may not be a symlink"
exec 9>>"$LOCK_FILE"
flock -n 9 || die "another native maintenance operation is running"

# Hold the same lock as deploy/rollback before deciding the database is
# quiescent. A maintenance operation cannot start after these checks.
systemctl is-active --quiet beta-center-postgres.service || die "native PostgreSQL must be active"
if systemctl is-active --quiet beta-center-app.service || \
    systemctl is-active --quiet beta-center-caddy.service; then
    die "stop Caddy and the application before taking the consistency snapshot"
fi

server_identity=$(runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --dbname=postgres --no-password \
    --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command="SELECT current_user || '|' || current_setting('data_directory') || '|' || current_setting('port') || '|' || pg_is_in_recovery()")
[[ "$server_identity" == "beta-pg|$PG_DATA|$PG_PORT|false" ]] || \
    die "socket does not identify the writable native PostgreSQL instance"
database_identity=$(runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --dbname=postgres --no-password \
    --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command="SELECT datname || '|' || pg_get_userbyid(datdba) || '|' || datistemplate FROM pg_database WHERE datname = '$SOURCE_DATABASE'")
[[ "$database_identity" == "$SOURCE_DATABASE|beta_center|false" ]] || \
    die "production database identity or owner is unexpected"
role_identity=$(runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --dbname=postgres --no-password \
    --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command="SELECT rolname || '|' || rolsuper || '|' || rolcreatedb || '|' || rolcreaterole || '|' || rolreplication FROM pg_roles WHERE rolname = 'beta_center'")
[[ "$role_identity" == 'beta_center|false|false|false|false' ]] || \
    die "application database role has unexpected privileges"
stale_scratch=$(runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --dbname=postgres --no-password \
    --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command="SELECT coalesce(string_agg(datname, ',' ORDER BY datname), '') FROM pg_database WHERE datname ~ '^beta_restore_drill_[0-9]{14}_[0-9]+$'")
[[ -z "$stale_scratch" ]] || \
    die "stale scratch database(s) require manual inspection before retrying: $stale_scratch"

source_size=$(runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --dbname=postgres --no-password \
    --no-psqlrc --quiet --tuples-only --no-align --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_database_size('$SOURCE_DATABASE')")
[[ "$source_size" =~ ^[0-9]+$ ]] || die "cannot determine production database size"
available_kib=$(df -Pk "$NATIVE_STATE" | awk 'NR == 2 {print $4}')
[[ "$available_kib" =~ ^[0-9]+$ ]] || die "cannot determine native free space"
required_bytes=$((source_size * 3 + 2 * 1024 * 1024 * 1024))
[[ $((available_kib * 1024)) -ge "$required_bytes" ]] || \
    die "insufficient free space for dump, scratch restore, WAL, and 2 GiB reserve"

started=$SECONDS
stamp=$(date -u +%Y%m%dT%H%M%SZ)
destination="$TRANSACTION_ROOT/restore-drill-$stamp-$$"
scratch_database="beta_restore_drill_${stamp//[^0-9]/}_$$"
[[ "$scratch_database" =~ ^beta_restore_drill_[0-9]{14}_[0-9]+$ ]] || \
    die "generated scratch database name failed its safety contract"
[[ "$scratch_database" != "$SOURCE_DATABASE" ]] || die "scratch database may not be production"
[[ -d "$TRANSACTION_ROOT" && ! -L "$TRANSACTION_ROOT" ]] || \
    die "native transaction root is missing or is a symlink"
[[ ! -e "$destination" && ! -L "$destination" ]] || die "result directory already exists"
install -d -o root -g root -m 0700 -- "$destination"
umask 077

scratch_created=false
cleanup() {
    status=$?
    trap - EXIT HUP INT TERM
    if [[ "$scratch_created" == true ]]; then
        if ! runuser -u beta-pg -- "$PG_BIN/dropdb" \
            --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
            --maintenance-db=postgres --if-exists "$scratch_database" \
            >/dev/null 2>&1; then
            log "WARNING: remove only this scratch database manually: $scratch_database"
            [[ "$status" -ne 0 ]] || status=1
        else
            scratch_created=false
        fi
    fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

dump="$destination/database.dump"
runuser -u beta-pg -- "$PG_BIN/pg_dump" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password --format=custom \
    --no-owner --no-acl "$SOURCE_DATABASE" >"$dump"
chmod 0600 "$dump"
runuser -u beta-pg -- "$PG_BIN/pg_restore" --list <"$dump" >"$destination/archive.list"

runuser -u beta-pg -- "$PG_BIN/createdb" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
    --maintenance-db=postgres --owner=beta_center "$scratch_database"
scratch_created=true
runuser -u beta-pg -- "$PG_BIN/pg_restore" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
    --dbname="$scratch_database" \
    --exit-on-error --single-transaction --no-owner --role=beta_center <"$dump"

table_counts() {
    local database=$1
    runuser -u beta-pg -- "$PG_BIN/psql" \
        --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
        --dbname="$database" \
        --no-psqlrc --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align <<'SQL'
SELECT format(
    'SELECT %L || ''='' || count(*) FROM %I.%I;',
    schemaname || '.' || tablename,
    schemaname,
    tablename
)
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename
\gexec
SQL
}

table_counts "$SOURCE_DATABASE" >"$destination/source.counts"
table_counts "$scratch_database" >"$destination/restored.counts"
cmp -s "$destination/source.counts" "$destination/restored.counts" || \
    die "restored table counts differ from the quiescent source database"

runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
    --dbname="$SOURCE_DATABASE" \
    --no-psqlrc --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align \
    --command='SELECT version_num FROM alembic_version' \
    >"$destination/source-alembic-version"
runuser -u beta-pg -- "$PG_BIN/psql" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
    --dbname="$scratch_database" \
    --no-psqlrc --set=ON_ERROR_STOP=1 --quiet --tuples-only --no-align \
    --command='SELECT version_num FROM alembic_version' \
    >"$destination/restored-alembic-version"
[[ -s "$destination/source-alembic-version" ]] || die "source Alembic revision is missing"
cmp -s "$destination/source-alembic-version" "$destination/restored-alembic-version" || \
    die "restored Alembic revision differs from the source"

# Completion means the scratch database is already gone. The EXIT trap remains
# as a second cleanup attempt for every earlier failure and termination signal.
runuser -u beta-pg -- "$PG_BIN/dropdb" \
    --host="$PG_SOCKET" --port="$PG_PORT" --username=beta-pg --no-password \
    --maintenance-db=postgres --if-exists "$scratch_database"
scratch_created=false

sha256sum "$dump" >"$destination/database.dump.sha256"
printf '%s\n' "$((SECONDS - started))" >"$destination/elapsed-seconds"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$destination/complete"
chmod 0600 "$destination"/*
log "PASS: isolated restore and exact table-count comparison completed in $((SECONDS - started))s"
log "verified backup retained at $dump; remove it securely after the acceptance evidence is archived"
