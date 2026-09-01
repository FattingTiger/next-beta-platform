#!/usr/bin/env python3
"""Compare database file references with the private storage volume."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from sqlalchemy import create_engine, text

from beta_center.config import Settings

REFERENCE_QUERIES = {
    "app_icon": "SELECT icon_storage_key FROM apps WHERE icon_storage_key IS NOT NULL",
    "app_version": "SELECT file_storage_key FROM app_versions",
    "app_screenshot": "SELECT storage_key FROM app_screenshots",
    "bug_attachment": "SELECT storage_key FROM bug_attachments",
}
IGNORED_TOP_LEVEL_PREFIXES = (
    ".orphan-quarantine-",
    ".restore-previous-",
    ".restore-staging-",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--fail-on-orphans",
        action="store_true",
        help="return a non-zero status when unreferenced files exist",
    )
    parser.add_argument(
        "--quarantine-orphans",
        action="store_true",
        help="atomically move unreferenced files aside; never deletes them",
    )
    return parser.parse_args()


def safe_key(raw: str) -> str | None:
    key = PurePosixPath(raw)
    if key.is_absolute() or not key.parts or any(part in {"", ".", ".."} for part in key.parts):
        return None
    return key.as_posix()


def database_references(database_url: str) -> tuple[set[str], list[str], dict[str, int]]:
    engine = create_engine(database_url, pool_pre_ping=True)
    expected: set[str] = set()
    unsafe: list[str] = []
    counts: dict[str, int] = {}
    try:
        with engine.connect() as connection:
            for category, query in REFERENCE_QUERIES.items():
                rows = connection.execute(text(query)).scalars().all()
                counts[category] = len(rows)
                for value in rows:
                    normalized = safe_key(str(value))
                    if normalized is None:
                        unsafe.append(str(value))
                    else:
                        expected.add(normalized)
    finally:
        engine.dispose()
    return expected, sorted(set(unsafe)), counts


def disk_files(root: Path) -> tuple[set[str], list[str], list[str]]:
    actual: set[str] = set()
    temporary: list[str] = []
    symlinks: list[str] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative.split("/", maxsplit=1)[0].startswith(IGNORED_TOP_LEVEL_PREFIXES):
            continue
        if path.is_symlink():
            symlinks.append(relative)
        elif path.is_file() and relative.endswith(".part"):
            temporary.append(relative)
        elif path.is_file():
            actual.add(relative)
    return actual, sorted(temporary), sorted(symlinks)


def quarantine(root: Path, orphan_keys: list[str]) -> str | None:
    if not orphan_keys:
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination_root = root / f".orphan-quarantine-{timestamp}"
    for key in orphan_keys:
        source = (root / key).resolve()
        if root not in source.parents or not source.is_file() or source.is_symlink():
            raise RuntimeError(f"refusing to quarantine unsafe storage path: {key}")
        destination = destination_root / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
    return destination_root.name


def main() -> int:
    args = parse_args()
    settings = Settings()
    root = settings.storage_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    expected, unsafe_database_keys, reference_counts = database_references(settings.database_url)
    actual, temporary, symlinks = disk_files(root)
    missing = sorted(expected - actual)
    orphans = sorted(actual - expected)

    quarantine_directory = None
    if args.quarantine_orphans and not missing and not unsafe_database_keys and not symlinks:
        quarantine_directory = quarantine(root, orphans)

    if missing or unsafe_database_keys or symlinks:
        report_status = "inconsistent"
    elif orphans:
        report_status = "orphaned"
    else:
        report_status = "ok"
    report = {
        "status": report_status,
        "storage_root": str(root),
        "reference_counts": reference_counts,
        "referenced_unique_files": len(expected),
        "disk_files": len(actual),
        "missing": missing,
        "orphans": orphans,
        "temporary_files": temporary,
        "symlinks": symlinks,
        "unsafe_database_keys": unsafe_database_keys,
        "quarantine_directory": quarantine_directory,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if unsafe_database_keys or symlinks:
        return 4
    if missing:
        return 2
    if args.fail_on_orphans and orphans and not args.quarantine_orphans:
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc
