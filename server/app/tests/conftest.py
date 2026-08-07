from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.main import app
from app.models.base import Base

TEST_DATABASE_URL = "postgresql+psycopg://matcha:matcha_dev@127.0.0.1:5432/oceanlab_test"


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DATABASE_URL, future=True)
    Base.metadata.create_all(eng)
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
        yield db

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {settings.oceanlab_token}"})
        yield c
    app.dependency_overrides.pop(get_db, None)
