from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_LOCUSTFILE = Path(__file__).parent / "load" / "locustfile.py"
_RANGE_LOCUSTFILE = Path(__file__).parent / "load" / "range_locustfile.py"
_READ_WAIT_RANGE = (
    "import runpy, sys; namespace = runpy.run_path(sys.argv[1]); print(namespace['_load_wait_range']())"
)
_READ_RANGE_CONFIGURATION = (
    "import os, runpy, sys; "
    "namespace = runpy.run_path(sys.argv[1]); "
    "token, phone, password = namespace['_range_auth_inputs'](); "
    "version, chunk, maximum = namespace['_range_parameters'](); "
    "range_token = os.environ.get('BETA_RANGE_ACCESS_TOKEN', '').strip(); "
    "fallback_token = os.environ.get('BETA_LOAD_ACCESS_TOKEN', '').strip(); "
    "source = 'credentials' if phone and password else "
    "('range-token' if range_token and token == range_token else "
    "('fallback-token' if fallback_token and token == fallback_token else 'invalid')); "
    "print(source, version, chunk, maximum)"
)
_RANGE_ENV_NAMES = (
    "BETA_RANGE_ACCESS_TOKEN",
    "BETA_LOAD_ACCESS_TOKEN",
    "BETA_LOAD_PHONE",
    "BETA_LOAD_PASSWORD",
    "BETA_LOAD_VERSION_ID",
    "BETA_RANGE_CHUNK_BYTES",
    "BETA_RANGE_MAX_FILE_BYTES",
)


def run_profile_with_wait_bounds(
    minimum: str | None,
    maximum: str | None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name, value in (
        ("BETA_LOAD_WAIT_MIN_SECONDS", minimum),
        ("BETA_LOAD_WAIT_MAX_SECONDS", maximum),
    ):
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    return subprocess.run(  # noqa: S603 - fixed interpreter and checked-in script
        [sys.executable, "-c", _READ_WAIT_RANGE, str(_LOCUSTFILE)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def run_range_configuration(**values: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    for name in _RANGE_ENV_NAMES:
        environment.pop(name, None)
    environment.update(values)
    return subprocess.run(  # noqa: S603 - fixed interpreter and checked-in script
        [sys.executable, "-c", _READ_RANGE_CONFIGURATION, str(_RANGE_LOCUSTFILE)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_mixed_load_wait_range_defaults_to_user_population_pacing() -> None:
    completed = run_profile_with_wait_bounds(None, None)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "(2.0, 5.0)"


def test_mixed_load_wait_range_accepts_explicit_burst_pacing() -> None:
    completed = run_profile_with_wait_bounds("0.2", "0.8")

    assert completed.returncode == 0
    assert completed.stdout.strip() == "(0.2, 0.8)"


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    (
        ("0.2", None),
        (None, "0.8"),
        ("not-a-number", "0.8"),
        ("0", "0.8"),
        ("2", "1"),
        ("2", "61"),
    ),
)
def test_mixed_load_wait_range_rejects_incomplete_or_unsafe_bounds(
    minimum: str | None,
    maximum: str | None,
) -> None:
    completed = run_profile_with_wait_bounds(minimum, maximum)

    assert completed.returncode != 0
    assert "load wait bounds" in completed.stderr or "must be set together" in completed.stderr


def test_range_load_prefers_its_short_lived_access_token_without_printing_it() -> None:
    range_token = "range-secret-must-not-be-logged"
    fallback_token = "fallback-secret-must-not-be-logged"
    completed = run_range_configuration(
        BETA_RANGE_ACCESS_TOKEN=range_token,
        BETA_LOAD_ACCESS_TOKEN=fallback_token,
        BETA_LOAD_VERSION_ID="published-version",
        BETA_RANGE_CHUNK_BYTES="65536",
        BETA_RANGE_MAX_FILE_BYTES="131072",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "range-token published-version 65536 131072"
    assert range_token not in completed.stdout + completed.stderr
    assert fallback_token not in completed.stdout + completed.stderr


def test_range_load_keeps_generic_token_as_a_compatibility_fallback() -> None:
    completed = run_range_configuration(
        BETA_LOAD_ACCESS_TOKEN="compatibility-secret",
        BETA_LOAD_VERSION_ID="published-version",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "fallback-token published-version 1048576 134217728"
    assert "compatibility-secret" not in completed.stdout + completed.stderr


def test_range_load_keeps_dedicated_account_mode_for_renewable_sessions() -> None:
    completed = run_range_configuration(
        BETA_RANGE_ACCESS_TOKEN="unused-short-token",
        BETA_LOAD_PHONE="+8613800000099",
        BETA_LOAD_PASSWORD="dedicated-secret",
        BETA_LOAD_VERSION_ID="published-version",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "credentials published-version 1048576 134217728"
    assert "dedicated-secret" not in completed.stdout + completed.stderr
    assert "unused-short-token" not in completed.stdout + completed.stderr


def test_range_load_rejects_partial_dedicated_credentials_even_with_a_token() -> None:
    completed = run_range_configuration(
        BETA_RANGE_ACCESS_TOKEN="short-secret",
        BETA_LOAD_PHONE="+8613800000099",
        BETA_LOAD_VERSION_ID="published-version",
    )

    assert completed.returncode != 0
    assert "BETA_LOAD_PHONE and BETA_LOAD_PASSWORD must be set together" in completed.stderr
    assert "short-secret" not in completed.stdout + completed.stderr


def test_range_load_requires_a_token_or_complete_dedicated_credentials() -> None:
    completed = run_range_configuration(BETA_LOAD_VERSION_ID="published-version")

    assert completed.returncode != 0
    assert "set BETA_RANGE_ACCESS_TOKEN (preferred)" in completed.stderr
    assert "or both BETA_LOAD_PHONE and BETA_LOAD_PASSWORD" in completed.stderr


def test_range_load_requires_a_nonblank_published_version() -> None:
    completed = run_range_configuration(
        BETA_RANGE_ACCESS_TOKEN="short-secret",
        BETA_LOAD_VERSION_ID="   ",
    )

    assert completed.returncode != 0
    assert "BETA_LOAD_VERSION_ID is required and cannot be blank" in completed.stderr
    assert "short-secret" not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("values", "expected_message"),
    (
        ({"BETA_RANGE_CHUNK_BYTES": "not-an-integer"}, "must be an integer number of bytes"),
        ({"BETA_RANGE_CHUNK_BYTES": "65535"}, "must be between 64 KiB and 8 MiB"),
        (
            {"BETA_RANGE_CHUNK_BYTES": "1048576", "BETA_RANGE_MAX_FILE_BYTES": "524288"},
            "must be at least BETA_RANGE_CHUNK_BYTES",
        ),
        ({"BETA_RANGE_MAX_FILE_BYTES": "not-an-integer"}, "must be an integer number of bytes"),
        ({"BETA_RANGE_MAX_FILE_BYTES": str(512 * 1024 * 1024 + 1)}, "no more than 512 MiB"),
    ),
)
def test_range_load_rejects_invalid_chunk_and_file_bounds(
    values: dict[str, str],
    expected_message: str,
) -> None:
    completed = run_range_configuration(
        BETA_RANGE_ACCESS_TOKEN="short-secret",
        BETA_LOAD_VERSION_ID="published-version",
        **values,
    )

    assert completed.returncode != 0
    assert expected_message in completed.stderr
    assert "short-secret" not in completed.stdout + completed.stderr
