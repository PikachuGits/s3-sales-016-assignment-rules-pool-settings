"""Database primitives shared by the S3-SALES-016 delivery.

The delivery targets PostgreSQL 16 and uses native ``UUID``, ``JSONB`` and
``UUID[]``.  The connection URL is read from ``DATABASE_URL``; there is
deliberately no fallback to a developer machine's default database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import MetaData
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for the three configuration tables."""

    metadata = MetaData()


def get_database_url() -> str:
    """Return the configured database URL or fail loudly."""

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required, e.g. "
            "postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/DB_NAME"
        )
    return url


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Lazily create the process-wide engine from ``DATABASE_URL``."""

    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Lazily create the process-wide session factory."""

    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, rolled back on error."""

    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
