from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy import select, update

from beta_center.config import Settings
from beta_center.database import Database, check_database
from beta_center.models import AuditLog, AuthSession, User, UserRole, utc_now
from beta_center.security import hash_password, normalize_phone
from beta_center.services.apk import ApkInspector
from beta_center.services.storage import LocalStorage


def main() -> None:
    parser = argparse.ArgumentParser(prog="beta-center")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin = subparsers.add_parser("create-admin", help="Create the first administrator")
    create_admin.add_argument("--phone", required=True)
    create_admin.add_argument("--name", required=True)
    create_admin.add_argument("--allow-existing", action="store_true")

    recover_admin = subparsers.add_parser(
        "recover-admin",
        help="Break-glass recovery for an existing local administrator account",
    )
    recover_admin.add_argument("--phone", required=True)
    recover_admin.add_argument("--name")
    recover_admin.add_argument("--confirm-break-glass", action="store_true", required=True)

    subparsers.add_parser("doctor", help="Check database, storage and APK tools")
    args = parser.parse_args()
    settings = Settings()
    settings.ensure_runtime_directories()
    database = Database(settings)
    if settings.auto_create_schema:
        database.create_schema()
    try:
        if args.command == "create-admin":
            _create_admin(database, phone=args.phone, name=args.name, allow_existing=args.allow_existing)
        elif args.command == "recover-admin":
            _recover_admin(database, phone=args.phone, name=args.name)
        elif args.command == "doctor":
            _doctor(settings, database)
    finally:
        database.dispose()


def _create_admin(database: Database, *, phone: str, name: str, allow_existing: bool) -> None:
    password = os.environ.pop("BETA_BOOTSTRAP_PASSWORD", None) or getpass.getpass("Initial password: ")
    normalized_phone = normalize_phone(phone)
    with database.session() as db:
        existing = db.scalar(select(User).where(User.phone == normalized_phone))
        if existing:
            if allow_existing and existing.role == UserRole.ADMIN:
                print("Administrator already exists")
                return
            raise SystemExit("A user with this phone already exists")
        admin = User(
            phone=normalized_phone,
            display_name=name.strip(),
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            must_change_password=True,
        )
        db.add(admin)
        db.flush()
        print(f"Created administrator {admin.id}; initial password must be changed at first login")


def _doctor(settings: Settings, database: Database) -> None:
    failures = 0
    try:
        check_database(database.engine)
        print("database: ok")
    except Exception as exc:
        print(f"database: failed ({type(exc).__name__})")
        failures += 1
    storage = LocalStorage(settings.storage_root)
    print(f"storage: ok ({storage.root})")
    inspector = ApkInspector(
        apksigner_path=settings.apksigner_path,
        aapt_path=settings.aapt_path,
        timeout_seconds=settings.apk_tool_timeout_seconds,
        require_tools=settings.require_apk_tools,
    )
    tools = inspector.tools_available()
    print(f"apk tools: {'ok' if tools else 'missing'}")
    if settings.require_apk_tools and not tools:
        failures += 1
    if failures:
        sys.exit(1)


def _recover_admin(database: Database, *, phone: str, name: str | None) -> None:
    password = os.environ.pop("BETA_BOOTSTRAP_PASSWORD", None) or getpass.getpass("New temporary password: ")
    normalized_phone = normalize_phone(phone)
    with database.session() as db:
        user = db.scalar(select(User).where(User.phone == normalized_phone).with_for_update())
        if user is None:
            raise SystemExit("Break-glass recovery only supports an existing account")
        user.role = UserRole.ADMIN
        user.is_active = True
        user.must_change_password = True
        user.password_hash = hash_password(password)
        user.session_generation += 1
        if name and name.strip():
            user.display_name = name.strip()
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
        db.add(
            AuditLog(
                actor_id=None,
                action="break_glass.admin_recover",
                entity_type="user",
                entity_id=user.id,
                outcome="success",
                details={"phone_suffix": normalized_phone[-4:]},
                request_ip="local-cli",
            )
        )
        print(f"Recovered administrator {user.id}; all sessions revoked and password change required")


if __name__ == "__main__":
    main()
