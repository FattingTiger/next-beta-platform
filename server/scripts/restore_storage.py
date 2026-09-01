#!/usr/bin/env python3
"""Safely replace the private storage root from a tar.gz stream on stdin."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tarfile
import uuid
from pathlib import Path, PurePosixPath


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-restore", action="store_true")
    return parser.parse_args()


def checked_target(staging: Path, member_name: str) -> Path:
    pure = PurePosixPath(member_name)
    if pure.is_absolute() or not pure.parts or pure.parts[0] != "storage":
        raise ValueError(f"unexpected archive member: {member_name}")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe archive member: {member_name}")
    target = (staging.joinpath(*pure.parts[1:])).resolve()
    if target != staging and staging not in target.parents:
        raise ValueError(f"archive path escaped staging directory: {member_name}")
    return target


def extract_to_staging(staging: Path) -> int:
    restored_files = 0
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
        for member in archive:
            target = checked_target(staging, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise ValueError(f"unsupported archive member type: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read archive member: {member.name}")
            with target.open("xb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            target.chmod(0o640)
            restored_files += 1
    return restored_files


def swap_storage(root: Path, staging: Path, previous: Path) -> None:
    previous.mkdir(mode=0o700)
    old_entries = [entry for entry in root.iterdir() if entry not in {staging, previous}]
    deployed_entries: list[Path] = []
    try:
        for entry in old_entries:
            os.replace(entry, previous / entry.name)
        for entry in list(staging.iterdir()):
            destination = root / entry.name
            os.replace(entry, destination)
            deployed_entries.append(destination)
    except Exception:
        for entry in deployed_entries:
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink(missing_ok=True)
        for entry in list(previous.iterdir()):
            os.replace(entry, root / entry.name)
        raise
    else:
        shutil.rmtree(previous)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    args = parse_args()
    if not args.confirm_restore:
        raise SystemExit("restore requires --confirm-restore")

    root = Path(os.environ.get("BETA_STORAGE_ROOT", "/var/lib/beta-center/storage")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    operation_id = uuid.uuid4().hex
    staging = root / f".restore-staging-{operation_id}"
    previous = root / f".restore-previous-{operation_id}"
    staging.mkdir(mode=0o700)
    try:
        restored_files = extract_to_staging(staging)
        swap_storage(root, staging, previous)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(json.dumps({"status": "restored", "files": restored_files}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}), file=sys.stderr)
        raise SystemExit(1) from exc
