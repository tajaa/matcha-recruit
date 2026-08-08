import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.oceanlab.config import settings


def _database_url() -> str:
    # Rides the monolith's shared DATABASE_URL by default (oceanlab's tables
    # live in the matcha DB, prefixed oceanlab_*); OCEANLAB_DATABASE_URL
    # overrides for standalone/test runs. psycopg3 needs the +psycopg driver.
    # load_dotenv() here (not just relying on matcha's own lifespan-time
    # load_settings()) because this module builds its engine at import time,
    # which happens before the monolith's lifespan runs.
    load_dotenv()
    url = settings.database_url or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(_database_url(), pool_pre_ping=True, future=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
