#!/usr/bin/env bash
set -Eeuo pipefail

readonly SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}"
readonly BUILD_TOOLS_VERSION="${BETA_ANDROID_BUILD_TOOLS:-35.0.0}"
readonly APK_PACKAGE="${BETA_FIXTURE_APK_PACKAGE:-com.example.betacenter.fixture}"
readonly APK="${1:-${SCRIPT_DIR}/build/beta-center-fixture-1.0.0.apk}"

fail() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

[[ -n "${SDK_ROOT}" ]] || fail 'ANDROID_SDK_ROOT (or ANDROID_HOME) is unset'
[[ "${APK_PACKAGE}" =~ ^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$ ]] || \
    fail 'BETA_FIXTURE_APK_PACKAGE is not a valid Android package name'
readonly BUILD_TOOLS_DIR="${SDK_ROOT}/build-tools/${BUILD_TOOLS_VERSION}"
readonly AAPT="${BUILD_TOOLS_DIR}/aapt"
readonly APKSIGNER="${BUILD_TOOLS_DIR}/apksigner"
readonly ZIPALIGN="${BUILD_TOOLS_DIR}/zipalign"
readonly -a APKSIGNER_JAVA_ARGS=(
    -JXms16m
    -JXmx128m
    -JXX:MaxMetaspaceSize=96m
    -JXX:+UseSerialGC
    -JXX:ActiveProcessorCount=1
    -JDjava.awt.headless=true
)

[[ -f "${APK}" ]] || fail "APK not found: ${APK}"
for tool in "${AAPT}" "${APKSIGNER}" "${ZIPALIGN}"; do
    [[ -x "${tool}" ]] || fail "missing executable ${tool}"
done
command -v jar >/dev/null 2>&1 || fail 'missing command jar'

readonly BADGING="$("${AAPT}" dump badging "${APK}")"
printf '%s\n' "${BADGING}"

grep -Fq "package: name='${APK_PACKAGE}' versionCode='1' versionName='1.0.0'" \
    <<<"${BADGING}" || fail 'package/version contract mismatch'
grep -Fq "sdkVersion:'23'" <<<"${BADGING}" || fail 'minSdk contract mismatch'
grep -Fq "targetSdkVersion:'35'" <<<"${BADGING}" || fail 'targetSdk contract mismatch'
grep -Fq "launchable-activity: name='com.example.betacenter.fixture.MainActivity'" \
    <<<"${BADGING}" || fail 'launcher activity contract mismatch'

readonly SIGNATURE_REPORT="$(
    "${APKSIGNER}" "${APKSIGNER_JAVA_ARGS[@]}" verify --verbose --print-certs "${APK}"
)"
printf '%s\n' "${SIGNATURE_REPORT}"
grep -Fq 'Verified using v1 scheme (JAR signing): true' <<<"${SIGNATURE_REPORT}" || \
    fail 'APK Signature Scheme v1 is missing'
grep -Fq 'Verified using v2 scheme (APK Signature Scheme v2): true' <<<"${SIGNATURE_REPORT}" || \
    fail 'APK Signature Scheme v2 is missing'
grep -Fq 'Verified using v3 scheme (APK Signature Scheme v3): true' <<<"${SIGNATURE_REPORT}" || \
    fail 'APK Signature Scheme v3 is missing'
"${ZIPALIGN}" -c -p 4 "${APK}"

readonly ARCHIVE_ENTRIES="$(jar tf "${APK}")"
grep -Fxq 'AndroidManifest.xml' <<<"${ARCHIVE_ENTRIES}" || fail 'missing AndroidManifest.xml'
grep -Fxq 'classes.dex' <<<"${ARCHIVE_ENTRIES}" || fail 'missing classes.dex'

printf 'Verified installable APK contract: %s\n' "${APK}"
