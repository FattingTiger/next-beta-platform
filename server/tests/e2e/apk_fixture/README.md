# Signed Android APK fixture

This directory contains the source and a direct Android SDK build for the server's real APK
upload/download end-to-end path. It deliberately avoids Gradle so the fixture has no project
dependency graph and uses only pinned Android SDK command-line tools.

## Contract

- Package: `com.example.betacenter.fixture`
- Version: `1.0.0` (`versionCode` 1)
- SDK: min 23, target 35
- Launcher: `com.example.betacenter.fixture.MainActivity`
- Signing: disposable local RSA key; APK Signature Schemes v1, v2 and v3
- UI: one native `Activity` that renders a centered fixture label

The generated APK goes to `build/beta-center-fixture-1.0.0.apk`. The disposable keystore goes
to `.secrets/fixture-upload.jks`. Both directories are already excluded by `server/.gitignore`
(`build/` and `.secrets/`). Never copy this key into deployment configuration or commit it.

The server keeps archived applications and enforces a globally unique package name. For repeated
acceptance runs against one database, set a distinct package before each build and pass the same
value to the acceptance runner:

```bash
export BETA_FIXTURE_APK_PACKAGE=com.example.betacenter.fixture.round1
export BETA_ACCEPTANCE_APK_PACKAGE="$BETA_FIXTURE_APK_PACKAGE"
./build_fixture.sh
```

The manifest uses a fully qualified launcher class, so changing the application package does not
change or break `com.example.betacenter.fixture.MainActivity`.

## Pinned toolchain

The scripts intentionally require:

- `platforms;android-35`
- `build-tools;35.0.0`
- JDK 17, providing `javac`, `jar`, and `keytool`

With an existing Android SDK:

```bash
export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk"
./build_fixture.sh
```

If a controlled build host needs those exact SDK components, install them once with its existing
`sdkmanager`:

```bash
sdkmanager 'platforms;android-35' 'build-tools;35.0.0' 'platform-tools'
```

No production secret is needed. To replace the default test-only keystore password in process
memory, export `BETA_FIXTURE_KEYSTORE_PASSWORD` before the first build. The scripts pass this
value to `keytool` and `apksigner` through their environment-backed password options, so the
password does not appear in the child process command line. The Java launchers are also bounded
to small heaps so this fixture can be built safely on the one-GiB isolated staging host.

## Verification and device smoke test

`build_fixture.sh` always invokes `verify_fixture.sh`. The verifier fails unless `aapt` confirms
the package/version/SDK/launcher contract, `apksigner` validates the signature, `zipalign` passes,
and the archive contains both `AndroidManifest.xml` and `classes.dex`.

Run it independently with:

```bash
./verify_fixture.sh ./build/beta-center-fixture-1.0.0.apk
```

On a connected Android device or emulator:

```bash
adb install -r ./build/beta-center-fixture-1.0.0.apk
adb shell am start -W -n com.example.betacenter.fixture/.MainActivity
```

Expected result: installation succeeds and the screen shows `Beta Center` and
`APK fixture 1.0.0`. This fixture requests no permissions and makes no network connection.

## Why there is no committed APK or keystore

The APK is a build artifact, and signing private keys must never enter source control. Rebuilding
from the small checked-in manifest and Java source also makes the package metadata explicit and
reviewable. The server's production image contains `aapt` and `apksigner` for upload inspection,
but not the Android platform JAR or D8 compiler required to create an installable APK; creation is
therefore deferred to the pinned Android toolchain used in the Android-client phase.
