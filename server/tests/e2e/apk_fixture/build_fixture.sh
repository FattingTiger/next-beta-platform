#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
readonly PLATFORM_NAME="${BETA_ANDROID_PLATFORM:-android-35}"
readonly BUILD_TOOLS_VERSION="${BETA_ANDROID_BUILD_TOOLS:-35.0.0}"
readonly APK_PACKAGE="${BETA_FIXTURE_APK_PACKAGE:-com.example.betacenter.fixture}"
readonly OUTPUT_DIR="${SCRIPT_DIR}/build"
readonly SECRETS_DIR="${SCRIPT_DIR}/.secrets"
readonly KEYSTORE="${SECRETS_DIR}/fixture-upload.jks"
readonly KEY_ALIAS="beta-center-fixture"
readonly APK="${OUTPUT_DIR}/beta-center-fixture-1.0.0.apk"

# This is an intentionally public password for a disposable test-only key. The private key
# itself stays under .secrets/ and must never be committed or reused outside local E2E tests.
export BETA_FIXTURE_KEYSTORE_PASSWORD="${BETA_FIXTURE_KEYSTORE_PASSWORD:-fixture-only-change-me}"

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

[[ -n "${SDK_ROOT}" ]] || fail \
    'ANDROID_SDK_ROOT (or ANDROID_HOME) is unset; see README.md for the pinned SDK packages.'
[[ "${APK_PACKAGE}" =~ ^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$ ]] || \
    fail 'BETA_FIXTURE_APK_PACKAGE is not a valid Android package name'

readonly PLATFORM_DIR="${SDK_ROOT}/platforms/${PLATFORM_NAME}"
readonly BUILD_TOOLS_DIR="${SDK_ROOT}/build-tools/${BUILD_TOOLS_VERSION}"
readonly ANDROID_JAR="${PLATFORM_DIR}/android.jar"
readonly AAPT="${BUILD_TOOLS_DIR}/aapt"
readonly D8="${BUILD_TOOLS_DIR}/d8"
readonly ZIPALIGN="${BUILD_TOOLS_DIR}/zipalign"
readonly APKSIGNER="${BUILD_TOOLS_DIR}/apksigner"
readonly -a JAVA_LAUNCHER_ARGS=(
    -J-Xms16m
    -J-Xmx128m
    -J-XX:MaxMetaspaceSize=96m
    -J-XX:+UseSerialGC
    -J-XX:ActiveProcessorCount=1
    -J-Djava.awt.headless=true
)
readonly -a D8_JAVA_ARGS=(
    -JXms16m
    -JXmx192m
    -JXX:MaxMetaspaceSize=96m
    -JXX:+UseSerialGC
    -JXX:ActiveProcessorCount=1
    -JDjava.awt.headless=true
)
readonly -a APKSIGNER_JAVA_ARGS=(
    -JXms16m
    -JXmx128m
    -JXX:MaxMetaspaceSize=96m
    -JXX:+UseSerialGC
    -JXX:ActiveProcessorCount=1
    -JDjava.awt.headless=true
)

[[ -f "${ANDROID_JAR}" ]] || fail "missing ${ANDROID_JAR}"
for tool in "${AAPT}" "${D8}" "${ZIPALIGN}" "${APKSIGNER}"; do
    [[ -x "${tool}" ]] || fail "missing executable ${tool}"
done
for command_name in javac jar keytool; do
    command -v "${command_name}" >/dev/null 2>&1 || fail "missing command ${command_name}"
done

umask 077
mkdir -p "${OUTPUT_DIR}" "${SECRETS_DIR}"
readonly WORK_DIR="$(mktemp -d "${OUTPUT_DIR}/work.XXXXXX")"
cleanup() {
    # WORK_DIR is created above, inside this fixture's ignored build directory.
    find "${WORK_DIR}" -depth -mindepth 1 -delete 2>/dev/null || true
    rmdir "${WORK_DIR}" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "${WORK_DIR}/classes" "${WORK_DIR}/dex"

if [[ ! -f "${KEYSTORE}" ]]; then
    keytool "${JAVA_LAUNCHER_ARGS[@]}" -genkeypair -noprompt \
        -keystore "${KEYSTORE}" \
        -storepass:env BETA_FIXTURE_KEYSTORE_PASSWORD \
        -keypass:env BETA_FIXTURE_KEYSTORE_PASSWORD \
        -alias "${KEY_ALIAS}" \
        -keyalg RSA \
        -keysize 2048 \
        -validity 3650 \
        -dname 'CN=Beta Center APK Fixture, OU=Tests, O=Example, C=CN' >/dev/null
    chmod 600 "${KEYSTORE}"
fi

javac "${JAVA_LAUNCHER_ARGS[@]}" \
    -encoding UTF-8 \
    -source 8 \
    -target 8 \
    -bootclasspath "${ANDROID_JAR}" \
    -classpath "${ANDROID_JAR}" \
    -d "${WORK_DIR}/classes" \
    "${SCRIPT_DIR}/src/com/example/betacenter/fixture/MainActivity.java"

(
    cd "${WORK_DIR}/classes"
    jar cf "${WORK_DIR}/classes.jar" .
)

"${D8}" \
    "${D8_JAVA_ARGS[@]}" \
    --lib "${ANDROID_JAR}" \
    --min-api 23 \
    --output "${WORK_DIR}/dex" \
    "${WORK_DIR}/classes.jar"

"${AAPT}" package -f \
    -M "${SCRIPT_DIR}/AndroidManifest.xml" \
    -I "${ANDROID_JAR}" \
    --rename-manifest-package "${APK_PACKAGE}" \
    -F "${WORK_DIR}/unsigned-unaligned.apk"

(
    cd "${WORK_DIR}/dex"
    "${AAPT}" add -f "${WORK_DIR}/unsigned-unaligned.apk" classes.dex >/dev/null
)

"${ZIPALIGN}" -f -p 4 \
    "${WORK_DIR}/unsigned-unaligned.apk" \
    "${WORK_DIR}/unsigned-aligned.apk"

"${APKSIGNER}" "${APKSIGNER_JAVA_ARGS[@]}" sign \
    --ks "${KEYSTORE}" \
    --ks-key-alias "${KEY_ALIAS}" \
    --ks-pass env:BETA_FIXTURE_KEYSTORE_PASSWORD \
    --key-pass env:BETA_FIXTURE_KEYSTORE_PASSWORD \
    --v1-signing-enabled true \
    --v2-signing-enabled true \
    --v3-signing-enabled true \
    --out "${APK}" \
    "${WORK_DIR}/unsigned-aligned.apk"

"${SCRIPT_DIR}/verify_fixture.sh" "${APK}"
printf '\nFixture ready: %s\n' "${APK}"
