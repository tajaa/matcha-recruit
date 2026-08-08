from collections.abc import Generator

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from alembic import command
from app.config import settings
from app.db import get_db
from app.main import app
from app.models.base import Base

TEST_DATABASE_URL = "postgresql+psycopg://matcha:matcha_dev@127.0.0.1:5432/oceanlab_test"


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    # Build the schema by actually running the migrations, so drift between
    # models and alembic/versions/*.py surfaces as failing tests (Phase 1
    # exit criterion: `alembic upgrade head` works cleanly).
    Base.metadata.drop_all(eng)
    with eng.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    cfg = _alembic_config()
    # alembic/env.py always resolves the URL from `settings.database_url`
    # (so plain `alembic upgrade head` on the CLI keeps working against the
    # real dev DB); point that at the test DB for the duration of the
    # upgrade so migrations land in oceanlab_test, not the dev database.
    original_url = settings.database_url
    settings.database_url = TEST_DATABASE_URL
    try:
        command.upgrade(cfg, "head")
    finally:
        settings.database_url = original_url
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine) -> Generator[Session, None, None]:
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, future=True)

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, transaction):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture()
def client(db) -> Generator[TestClient, None, None]:
    def _get_db_override():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {settings.oceanlab_token}"})
        yield c
    app.dependency_overrides.pop(get_db, None)


# Real-commit fixtures, for tests that need DEFERRED constraints to actually
# fire (they only fire at COMMIT, and the `db` fixture above never commits —
# it runs inside a savepoint that's always rolled back).
_TRUNCATE_TABLES = (
    "delivery_items, deliveries, registration_tasks, royalty_lines, royalty_statements, "
    "tracks, upc_codes, recording_works, master_splits, credits, work_writers, release_artists, "
    "releases, recordings, works, isrc_config, files, artists, contributors, jobs"
)


@pytest.fixture()
def db_real(engine) -> Generator[Session, None, None]:
    session = Session(bind=engine, future=True)
    try:
        yield session
    finally:
        session.close()
        with engine.begin() as conn:
            conn.execute(sa.text(f"TRUNCATE {_TRUNCATE_TABLES} RESTART IDENTITY CASCADE"))
            # Truncating isrc_config drops the migration-seeded id=1 row; restore it
            # so every test starts from the same invariant as a freshly migrated DB.
            conn.execute(sa.text(
                "INSERT INTO isrc_config (id, registrant_prefix, year_digits, next_designation) "
                "VALUES (1, '', '', 1) ON CONFLICT (id) DO NOTHING"
            ))


@pytest.fixture()
def client_real(db_real) -> Generator[TestClient, None, None]:
    def _get_db_override():
        try:
            yield db_real
        except Exception:
            db_real.rollback()
            raise

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {settings.oceanlab_token}"})
        yield c
    app.dependency_overrides.pop(get_db, None)
