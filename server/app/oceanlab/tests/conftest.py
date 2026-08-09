import importlib.util
from collections.abc import Generator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.oceanlab.config import settings
from app.oceanlab.db import get_db
from app.oceanlab.main import app
from app.oceanlab.models.base import Base

TEST_DATABASE_URL = "postgresql+psycopg://matcha:matcha_dev@127.0.0.1:5432/oceanlab_test"


@pytest.fixture(scope="session", autouse=True)
def _ensure_test_token():
    # require_auth (deps.py) 503s when settings.token is unset — this suite's
    # `client`/`client_real` fixtures send Bearer settings.token, so tests
    # must not depend on an ambient OCEANLAB_TOKEN env var to pass.
    if not settings.token:
        settings.token = "oceanlab-test-token"

# The oceanlab schema now ships as a hand-SQL migration in matcha's shared
# alembic chain (server/alembic/versions/), not a standalone alembic dir.
# Load and run it directly against the test engine rather than shelling out
# through matcha's full multi-head chain, so drift between models and the
# shipped migration still surfaces as a failing test.
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3] / "alembic" / "versions" / "oceanlab_app_01_standalone.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("oceanlab_app_01_standalone", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.drop_all(eng)
    with eng.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    migration = _load_migration()
    with eng.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            migration.upgrade()
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
        c.headers.update({"Authorization": f"Bearer {settings.token}"})
        yield c
    app.dependency_overrides.pop(get_db, None)


# Real-commit fixtures, for tests that need DEFERRED constraints to actually
# fire (they only fire at COMMIT, and the `db` fixture above never commits —
# it runs inside a savepoint that's always rolled back).
_TRUNCATE_TABLES = (
    "oceanlab_delivery_items, oceanlab_deliveries, oceanlab_registration_tasks, oceanlab_royalty_lines, "
    "oceanlab_royalty_statements, oceanlab_tracks, oceanlab_upc_codes, oceanlab_recording_works, "
    "oceanlab_master_splits, oceanlab_credits, oceanlab_work_writers, oceanlab_release_artists, "
    "oceanlab_releases, oceanlab_recordings, oceanlab_works, oceanlab_isrc_config, oceanlab_files, "
    "oceanlab_artists, oceanlab_contributors, oceanlab_jobs"
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
                "INSERT INTO oceanlab_isrc_config (id, registrant_prefix, year_digits, next_designation) "
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
        c.headers.update({"Authorization": f"Bearer {settings.token}"})
        yield c
    app.dependency_overrides.pop(get_db, None)
