"""SQLAlchemy engine/session setup and the `get_db()` FastAPI dependency."""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

# SQLite needs check_same_thread=False since FastAPI serves each request on a
# threadpool thread, not the thread the connection was created on.
_connect_args = {"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {}

engine: Engine = create_engine(
    _settings.database_url, pool_pre_ping=True, connect_args=_connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
