from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, create_engine, event, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings

# JSONB on PostgreSQL, plain JSON elsewhere (tests use SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    """Naive UTC timestamp (stored without tz so SQLite and Postgres behave the same)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def make_engine(url: str):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    eng = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(eng, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return eng


engine = make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, server_default=func.now(), nullable=False
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
