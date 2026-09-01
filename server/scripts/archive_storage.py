#!/usr/bin/env python3
"""Write a safe streaming tar.gz archive of the private storage root to stdout."""

from __future__ import annotations

import os
import sys
import tarfile
from pathlib import Path


def main() -> int:
    root = Path(os.environ.get("BETA_STORAGE_ROOT", "/var/lib/beta-center/storage")).resolve()
    if not root.is_dir():
        raise SystemExit(f"storage root does not exist: {root}")

    with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz", compresslevel=6) as archive:
        directory = tarfile.TarInfo("storage")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o750
        archive.addfile(directory)
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if relative.parts and relative.parts[0].startswith("."):
                continue
            if path.is_symlink():
                raise SystemExit(f"refusing to archive symlink: {relative}")
            if not path.is_file() or path.name.endswith(".part"):
                continue
            archive.add(path, arcname=(Path("storage") / relative).as_posix(), recursive=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
