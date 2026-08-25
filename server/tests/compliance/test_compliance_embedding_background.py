"""Background compliance embedding must not reuse released request connections."""

import asyncio
from uuid import uuid4

from app.core.services.compliance_service import _run


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.connection

    async def __aexit__(self, *_args):
        self.exited = True


def test_embedding_background_task_acquires_its_own_connection(monkeypatch):
    fresh_connection = object()
    context = _ConnectionContext(fresh_connection)
    embedded = []

    async def embed_updated_requirements(conn, jurisdiction_id):
        embedded.append((conn, jurisdiction_id))

    import app.database
    import app.core.services.compliance_embedding_pipeline as pipeline

    monkeypatch.setattr(app.database, "get_connection", lambda: context)
    monkeypatch.setattr(pipeline, "embed_updated_requirements", embed_updated_requirements)

    jurisdiction_id = uuid4()
    asyncio.run(_run._embed_updated_requirements_bg(jurisdiction_id))

    assert context.entered is True
    assert context.exited is True
    assert embedded == [(fresh_connection, jurisdiction_id)]
