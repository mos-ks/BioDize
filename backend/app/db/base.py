"""SQLAlchemy engine, session and declarative base."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# check_same_thread is a SQLite-only flag; harmless to compute conditionally.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. (Hackathon-grade; use Alembic for real migrations.)"""
    from app.db import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
    _ensure_columns()


def _ensure_columns() -> None:
    """Add columns introduced after a DB already exists (no Alembic). SQLite only;
    on other backends the PRAGMA fails and is skipped (create_all covers new DBs)."""
    from sqlalchemy import text
    wanted = {"fields": [("is_handwritten", "BOOLEAN")],
              "documents": [("processing_ms", "INTEGER")]}
    try:
        with engine.begin() as conn:
            for table, cols in wanted.items():
                have = {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
                if not have:
                    continue
                for name, sqltype in cols:
                    if name not in have:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sqltype}"))
    except Exception:
        pass
