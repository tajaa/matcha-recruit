import os
from collections.abc import Generator
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.oceanlab.config import settings


def _database_url() -> str:
    # Rides the monolith's shared DATABASE_URL by default (oceanlab's tables
    # live in the matcha DB, prefixed oceanlab_*); OCEANLAB_DATABASE_URL
    # overrides for standalone/test runs. psycopg3 needs the +psycopg driver.
    # load_dotenv() here (not just relying on matcha's own lifespan-time
    # load_settings()) because the engine below is built lazily on first use,
    # which can happen before the monolith's lifespan runs.
    load_dotenv()
    url = settings.database_url or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    # Built lazily (not at module import) so a missing DATABASE_URL raises on
    # the first oceanlab request instead of crashing `app.main` import for the
    # whole monolith.
    return create_engine(_database_url(), pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = _session_factory()()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
