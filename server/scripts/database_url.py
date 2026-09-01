#!/usr/bin/env python3
"""Build a correctly escaped SQLAlchemy URL from a runtime password file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import URL


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: database_url.py PASSWORD_FILE")
    password = Path(sys.argv[1]).read_text(encoding="utf-8").rstrip("\r\n")
    if not password:
        raise SystemExit("empty database password secret file")
    port = int(os.environ.get("BETA_DB_PORT", "5432"))
    if not 1 <= port <= 65535:
        raise SystemExit("invalid database port")
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ.get("BETA_DB_USER", "beta_center"),
        password=password,
        host=os.environ.get("BETA_DB_HOST", "db"),
        port=port,
        database=os.environ.get("BETA_DB_NAME", "beta_center"),
    )
    print(url.render_as_string(hide_password=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
