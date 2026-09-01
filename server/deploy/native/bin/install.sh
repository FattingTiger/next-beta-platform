#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ASSET_DIR=$(cd -- "$SCRIPT_DIR/.." && pwd)
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

usage() {
    cat >&2 <<'EOF'
usage: install.sh --runtime-env FILE --source SERVER_DIR --release-id ID \
  --python-prefix DIR --postgres-prefix DIR --caddy-binary FILE \
  --android-build-tools DIR --java-prefix DIR \
  [--app-venv DIR | --wheelhouse DIR --requirements FILE]

All dependencies must already exist on the host or in the offline wheelhouse.
This command never uses a package manager or network downloader.
EOF
    exit 2
}

runtime_env= source_dir= release_id= python_prefix= postgres_prefix=
caddy_binary= android_build_tools= java_prefix= app_venv= wheelhouse= requirements=
while [[ $# -gt 0 ]]; do
    case "$1" in
        --runtime-env) runtime_env=$2; shift 2 ;;
        --source) source_dir=$2; shift 2 ;;
        --release-id) release_id=$2; shift 2 ;;
        --python-prefix) python_prefix=$2; shift 2 ;;
        --postgres-prefix) postgres_prefix=$2; shift 2 ;;
        --caddy-binary) caddy_binary=$2; shift 2 ;;
        --android-build-tools) android_build_tools=$2; shift 2 ;;
        --java-prefix) java_prefix=$2; shift 2 ;;
        --app-venv) app_venv=$2; shift 2 ;;
        --wheelhouse) wheelhouse=$2; shift 2 ;;
        --requirements) requirements=$2; shift 2 ;;
        *) usage ;;
    esac
done

require_root
for value in runtime_env source_dir release_id python_prefix postgres_prefix caddy_binary android_build_tools java_prefix; do
    [[ -n ${!value} ]] || usage
done
[[ "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || die "invalid release id"
if [[ -n "$app_venv" ]]; then
    [[ -z "$wheelhouse" && -z "$requirements" ]] || usage
else
    [[ -n "$wheelhouse" && -n "$requirements" ]] || usage
fi

exec 9>"$NATIVE_LOCK"
flock -n 9 || die "another native maintenance operation is running"

load_runtime_env "$runtime_env"
validate_runtime_env

[[ -x "$python_prefix/bin/python3" ]] || die "Python 3 executable is missing"
"$python_prefix/bin/python3" -c 'import sys; assert sys.version_info[:2] == (3, 12)'
[[ -x "$postgres_prefix/bin/postgres" && -x "$postgres_prefix/bin/initdb" ]] || \
    die "PostgreSQL binaries are missing"
"$postgres_prefix/bin/postgres" --version | grep -Eq ' 17\.' || die "PostgreSQL 17 is required"
[[ -x "$caddy_binary" ]] || die "Caddy binary is missing"
caddy_version=$("$caddy_binary" version)
[[ "$caddy_version" =~ ^v2\.11\.4([[:space:]]|$) ]] || die "Caddy 2.11.4 is required"
[[ -x "$android_build_tools/aapt" && -x "$android_build_tools/apksigner" ]] || \
    die "Android build-tools aapt/apksigner are missing"
[[ -x "$java_prefix/bin/java" ]] || die "Java runtime is missing"
[[ -f "$source_dir/pyproject.toml" && -f "$source_dir/alembic.ini" ]] || die "invalid server source directory"

create_account() {
    local account=$1 home=$2
    if ! getent passwd "$account" >/dev/null; then
        useradd --system --user-group --home-dir "$home" --create-home --shell /sbin/nologin "$account"
    fi
    [[ $(id -u "$account") -ne 0 ]] || die "refusing privileged service account: $account"
    [[ $(id -gn "$account") == "$account" ]] || die "unexpected primary group for $account"
    [[ $(getent passwd "$account" | cut -d: -f6) == "$home" ]] || die "unexpected home for $account"
    [[ $(getent passwd "$account" | cut -d: -f7) == /sbin/nologin ]] || \
        die "unexpected login shell for $account"
}

install -d -m 0755 "$NATIVE_STATE"
getent group beta-files >/dev/null || groupadd --system beta-files
create_account beta-pg "$NATIVE_STATE/postgres-home"
create_account beta-app "$NATIVE_STATE/app-home"
create_account beta-caddy "$NATIVE_STATE/caddy-home"
# These are dedicated accounts. Replace, rather than append to, supplementary
# groups so a pre-existing name collision cannot carry unrelated privileges
# into a project service.
usermod -G beta-files beta-app
usermod -G beta-files beta-caddy

install -d -m 0755 "$NATIVE_PREFIX" "$NATIVE_PREFIX/bin" "$NATIVE_PREFIX/app/releases"
# Caddy must traverse the configuration directory to read its public 0644
# Caddyfile. Secrets remain in a separate application-only directory.
install -d -o root -g root -m 0755 "$NATIVE_CONFIG"
install -d -o root -g beta-app -m 0750 "$NATIVE_CONFIG/secrets"
install -d -m 0700 "$NATIVE_TRANSACTION_ROOT"
install -d -o beta-pg -g beta-pg -m 0700 "$NATIVE_STATE/postgres" "$NATIVE_STATE/postgres-home"
install -d -o beta-app -g beta-files -m 2750 "$NATIVE_STATE/storage"
install -d -o beta-app -g beta-app -m 0700 "$NATIVE_STATE/upload-tmp" "$NATIVE_STATE/app-home"
install -d -o beta-caddy -g beta-caddy -m 0700 \
    "$NATIVE_STATE/caddy-home" "$NATIVE_STATE/caddy-data" "$NATIVE_STATE/caddy-config"

adopt_prefix() {
    local source=$1 destination=$2
    source=$(readlink_physical "$source")
    if [[ -e "$destination" && ! -L "$destination" ]]; then
        [[ $(readlink_physical "$destination") == "$source" ]] || die "refusing to replace existing prefix: $destination"
        return
    fi
    ln -sfn "$source" "$destination"
}

adopt_prefix "$python_prefix" "$NATIVE_PREFIX/python-3.12"
adopt_prefix "$postgres_prefix" "$NATIVE_PREFIX/postgresql-17"
adopt_prefix "$java_prefix" "$NATIVE_PREFIX/java"

install -d -m 0755 "$NATIVE_PREFIX/android-tools/bin"
aapt_target="$NATIVE_PREFIX/android-tools/bin/aapt"
apksigner_target="$NATIVE_PREFIX/android-tools/bin/apksigner"
if [[ $(readlink_physical "$android_build_tools/aapt") != $(readlink_physical "$aapt_target" 2>/dev/null || printf missing) ]]; then
cat > "$aapt_target" <<EOF
#!/usr/bin/env bash
exec "$android_build_tools/aapt" "\$@"
EOF
fi
if [[ $(readlink_physical "$android_build_tools/apksigner") != $(readlink_physical "$apksigner_target" 2>/dev/null || printf missing) ]]; then
cat > "$apksigner_target" <<EOF
#!/usr/bin/env bash
export JAVA_HOME="$NATIVE_PREFIX/java"
export PATH="\$JAVA_HOME/bin:\$PATH"
exec "$android_build_tools/apksigner" \
    -JXms16m -JXmx128m -JXX:MaxMetaspaceSize=96m \
    -JXX:+UseSerialGC -JXX:ActiveProcessorCount=1 \
    -JDjava.awt.headless=true "\$@"
EOF
fi
chmod 0755 "$aapt_target" "$apksigner_target"

candidate="$NATIVE_PREFIX/app/releases/$release_id"
[[ ! -e "$candidate" ]] || die "release already exists: $candidate"
install -d -m 0755 "$candidate"
tar -C "$source_dir" \
    --exclude='./.env' --exclude='*/.env' \
    --exclude='./.secrets' --exclude='*/.secrets' \
    --exclude='./.venv' --exclude='./data' --exclude='./.git' \
    -cf - . | tar -C "$candidate" --no-same-owner --no-same-permissions -xf -

if [[ -n "$app_venv" ]]; then
    [[ -x "$app_venv/bin/python" ]] || die "application environment Python is missing"
    "$app_venv/bin/python" -c 'import fastapi, psycopg, sqlalchemy, uvicorn, PIL, jwt, argon2, alembic'
    ln -s "$(readlink_physical "$app_venv")" "$candidate/.venv"
else
    [[ -d "$wheelhouse" && -f "$requirements" ]] || die "offline dependency inputs are missing"
    "$NATIVE_PREFIX/python-3.12/bin/python3" -m venv "$candidate/.venv"
    "$candidate/.venv/bin/pip" install --no-index --no-cache-dir --require-hashes \
        --find-links "$wheelhouse" -r "$requirements"
fi

# Verify the exact execution identity and working-directory permissions used by
# migrations and the service. Root-only smoke tests can hide unreadable shared
# runtimes or release files. The tool checks also execute the generated
# apksigner wrapper instead of merely checking that its source file exists.
(
    cd "$candidate"
    run_as beta-app "$NATIVE_PREFIX/java/bin/java" -version >/dev/null 2>&1
    run_as beta-app "$aapt_target" version >/dev/null
    run_as beta-app "$apksigner_target" version >/dev/null
    run_as beta-app env PYTHONPATH="$candidate/src" "$candidate/.venv/bin/python" \
        -c 'import beta_center, fastapi, psycopg, uvicorn'
)

if [[ $(readlink_physical "$runtime_env") != $(readlink_physical "$NATIVE_RUNTIME_ENV" 2>/dev/null || printf missing) ]]; then
    install -m 0640 -o root -g beta-app "$runtime_env" "$NATIVE_RUNTIME_ENV"
else
    chown root:beta-app "$NATIVE_RUNTIME_ENV"
    chmod 0640 "$NATIVE_RUNTIME_ENV"
fi
ensure_secret_file "$NATIVE_CONFIG/secrets/db_password" beta-app 36
ensure_secret_file "$NATIVE_CONFIG/secrets/app_secret" beta-app 48
install -m 0644 "$ASSET_DIR/postgresql.conf" "$NATIVE_CONFIG/postgresql.conf"
install -m 0644 "$ASSET_DIR/pg_hba.conf" "$NATIVE_CONFIG/pg_hba.conf"
install -d -m 0755 /etc/tmpfiles.d
cat > /etc/tmpfiles.d/beta-center-native.conf <<'EOF'
d /run/beta-center-pg 0750 beta-pg beta-pg -
d /run/caddy 0700 beta-caddy beta-caddy -
EOF
chmod 0644 /etc/tmpfiles.d/beta-center-native.conf
systemd-tmpfiles --create /etc/tmpfiles.d/beta-center-native.conf

for helper in common.sh with-app-env.sh start-app.sh migrate.sh host-state.sh rollback.sh; do
    install -m 0755 "$SCRIPT_DIR/$helper" "$NATIVE_PREFIX/bin/$helper"
done

install -d -m 0755 "$NATIVE_PREFIX/caddy-2.11.4/bin"
caddy_target="$NATIVE_PREFIX/caddy-2.11.4/bin/caddy"
if [[ $(readlink_physical "$caddy_binary") != $(readlink_physical "$caddy_target" 2>/dev/null || printf missing) ]]; then
    install -m 0755 "$caddy_binary" "$caddy_target"
else
    chmod 0755 "$caddy_target"
fi
setcap 'cap_net_bind_service=+ep' "$NATIVE_PREFIX/caddy-2.11.4/bin/caddy"
getcap "$NATIVE_PREFIX/caddy-2.11.4/bin/caddy" | grep -q 'cap_net_bind_service' || \
    die "Caddy file capabilities were not applied"
install -m 0644 "$ASSET_DIR/Caddyfile" "$NATIVE_CONFIG/Caddyfile"

if [[ ! -f "$NATIVE_STATE/postgres/PG_VERSION" ]]; then
    run_as beta-pg "$NATIVE_PREFIX/postgresql-17/bin/initdb" \
        --pgdata="$NATIVE_STATE/postgres" --encoding=UTF8 --locale=C \
        --username=beta-pg --auth-local=peer --auth-host=scram-sha-256 --data-checksums
fi

for unit in \
    beta-center.slice \
    beta-center-postgres.service \
    beta-center-app.service \
    beta-center-caddy.service; do
    install -m 0644 "$ASSET_DIR/systemd/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload

printf '%s\n' "$candidate" > "$NATIVE_STATE/candidate-release"
chmod 0600 "$NATIVE_STATE/candidate-release"
log "native assets installed without starting listeners; candidate: $candidate"
