import os
import subprocess
from pathlib import Path

import pytest

SERVER_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = SERVER_ROOT / "deploy" / "native" / "bin" / "preflight.sh"


def ntp_check_function() -> str:
    document = PREFLIGHT.read_text(encoding="utf-8")
    start = document.index("clock_is_ntp_synchronized() {")
    end = document.index("\n}\n\nclock_is_ntp_synchronized", start) + len("\n}")
    return document[start:end]


@pytest.mark.parametrize(
    ("show_status", "show_output", "legacy_status", "legacy_output", "expected", "calls"),
    (
        (0, "NTPSynchronized=yes\n", 1, "", 0, ("show --property=NTPSynchronized",)),
        (
            1,
            "",
            0,
            "Local time: Sat 2026-08-29 12:00:00 CST\nNTP enabled: yes\nNTP synchronized: yes\n",
            0,
            ("show --property=NTPSynchronized", "status"),
        ),
        (
            0,
            "NTPSynchronized=no\n",
            0,
            "NTP enabled: yes\nNTP synchronized: no\n",
            1,
            ("show --property=NTPSynchronized", "status"),
        ),
        (1, "", 1, "", 1, ("show --property=NTPSynchronized", "status")),
        (
            1,
            "",
            0,
            "NTP enabled: yes\n",
            1,
            ("show --property=NTPSynchronized", "status"),
        ),
    ),
    ids=("modern-yes", "centos7-status-yes", "explicit-no", "commands-fail", "enabled-only"),
)
def test_ntp_sync_detection_is_strict_and_centos7_compatible(
    tmp_path: Path,
    show_status: int,
    show_output: str,
    legacy_status: int,
    legacy_output: str,
    expected: int,
    calls: tuple[str, ...],
) -> None:
    call_log = tmp_path / "calls"
    timedatectl = tmp_path / "timedatectl"
    timedatectl.write_text(
        """#!/usr/bin/env bash
set -u
printf '%s\\n' "$*" >>"$MOCK_CALL_LOG"
case "$1" in
    show)
        printf '%s' "$MOCK_SHOW_OUTPUT"
        exit "$MOCK_SHOW_STATUS"
        ;;
    status)
        printf '%s' "$MOCK_LEGACY_OUTPUT"
        exit "$MOCK_LEGACY_STATUS"
        ;;
    *) exit 64 ;;
esac
""",
        encoding="utf-8",
    )
    timedatectl.chmod(0o755)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{tmp_path}:{environment['PATH']}",
            "MOCK_CALL_LOG": str(call_log),
            "MOCK_SHOW_STATUS": str(show_status),
            "MOCK_SHOW_OUTPUT": show_output,
            "MOCK_LEGACY_STATUS": str(legacy_status),
            "MOCK_LEGACY_OUTPUT": legacy_output,
        }
    )
    harness = f"set -Eeuo pipefail\n{ntp_check_function()}\nclock_is_ntp_synchronized\n"

    completed = subprocess.run(  # noqa: S603 - fixed shell and extracted checked-in function
        ["/bin/bash", "-c", harness],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == expected, completed.stderr
    assert tuple(call_log.read_text(encoding="utf-8").splitlines()) == calls
