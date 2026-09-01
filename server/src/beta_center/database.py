from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from anyio import CapacityLimiter
from sqlalchemy import Engine, event
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import Session, sessionmaker

from beta_center.config import Settings
from beta_center.models import Base


class Database:
    def __init__(self, settings: Settings) -> None:
        database_capacity = settings.database_pool_size + settings.database_max_overflow
        # This limiter is acquired by get_db before any synchronous dependency
        # or endpoint work starts. Requests beyond the SQLAlchemy pool capacity
        # therefore wait on the event loop instead of occupying worker threads
        # while they wait for a connection.
        self.request_limiter = CapacityLimiter(database_capacity)
        connect_args: dict[str, object] = {}
        is_sqlite = settings.database_url.startswith("sqlite")
        if is_sqlite:
            connect_args["check_same_thread"] = False
            self.engine = create_engine(
                settings.database_url,
                connect_args=connect_args,
                pool_pre_ping=True,
            )
        else:
            self.engine = create_engine(
                settings.database_url,
                connect_args=connect_args,
                pool_pre_ping=True,
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
                pool_timeout=settings.database_pool_timeout_seconds,
            )
        if is_sqlite:
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_schema(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def dispose(self) -> None:
        self.engine.dispose()


def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.exec_driver_sql("SELECT 1")
