"""Tests for ER document processing: batched embeddings + crash durability.

Regression cover for the OOM that stranded documents in 'processing' forever:
embedding the whole document at once blew the worker's memory cgroup, the child
was SIGKILLed, and no Python ran to mark the row 'failed' — so the ER guidance
UI polled the stuck row indefinitely and never generated guidance.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from app.workers.tasks.er_document_processing import (
    EMBED_BATCH_SIZE,
    STALE_PROCESSING_MINUTES,
    _process_document,
    _reset_stale_documents,
    process_er_document,
)


class _FakeConn:
    def __init__(self, doc_row):
        self._doc_row = doc_row
        self.executed: list[tuple[str, tuple]] = []
        self.closed = False

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetchrow(self, query, *args):
        return self._doc_row

    async def fetch(self, query, *args):
        self.executed.append((query, args))
        return [{"id": "doc-1"}, {"id": "doc-2"}]

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *exc):
                return False

        return _Tx()

    async def close(self):
        self.closed = True

    def statuses(self) -> list[str]:
        """processing_status values written, in order."""
        out = []
        for query, args in self.executed:
            if "processing_status = 'processing'" in query:
                out.append("processing")
            elif "processing_status = 'completed'" in query:
                out.append("completed")
            elif "processing_status = 'failed'" in query:
                out.append("failed")
        return out

    def chunk_inserts(self) -> int:
        return sum(1 for q, _ in self.executed if "INSERT INTO er_evidence_chunks" in q)


class _RecordingEmbeddingService:
    """Records the size of each embed call so batching can be asserted."""

    def __init__(self, fail_at_call: int | None = None):
        self.batch_sizes: list[int] = []
        self._fail_at_call = fail_at_call

    def embed_batch_sync(self, texts, **kwargs):
        self.batch_sizes.append(len(texts))
        if self._fail_at_call is not None and len(self.batch_sizes) == self._fail_at_call:
            raise RuntimeError("gemini embed exploded")
        return [[0.0] * 768 for _ in texts]


def _run_process_document(chunk_count, embedding_service, conn):
    """Drive _process_document with every external dependency faked out."""
    chunks = [
        {"chunk_index": i, "content": f"chunk {i}", "line_start": i, "char_start": i}
        for i in range(chunk_count)
    ]
    parsed = SimpleNamespace(text="raw text", speaker_turns=[], temporal_refs=[])

    fake_storage = SimpleNamespace(download_file=_async_return(b"filebytes"))
    fake_parser = SimpleNamespace(
        parse_document=lambda *_a, **_k: parsed,
        chunk_text=lambda *_a, **_k: chunks,
    )
    fake_scrubber = SimpleNamespace(scrub=lambda text: ("scrubbed", {}))

    with (
        patch("app.core.services.storage.get_storage", return_value=fake_storage),
        patch("app.matcha.services.er_document_parser.ERDocumentParser", return_value=fake_parser),
        patch("app.core.services.pii_scrubber.PIIScrubber", return_value=fake_scrubber),
        patch("app.core.services.embedding_service.EmbeddingService", return_value=embedding_service),
        patch("app.config.load_settings", return_value=SimpleNamespace(gemini_api_key="k")),
        patch("app.workers.tasks.er_document_processing.get_db_connection", _async_return(conn)),
        patch("app.workers.tasks.er_document_processing.publish_task_progress"),
    ):
        return asyncio.run(_process_document("doc-1", "case-1"))


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


def _doc_row():
    return {"filename": "statement.pdf", "file_path": "s3://x", "document_type": "transcript"}


def test_embeddings_are_batched_not_loaded_all_at_once():
    """The whole-document embed matrix is what breached the memory cgroup."""
    chunk_count = EMBED_BATCH_SIZE * 2 + 7
    embedder = _RecordingEmbeddingService()
    conn = _FakeConn(_doc_row())

    result = _run_process_document(chunk_count, embedder, conn)

    # Three calls: two full batches plus the remainder — never one call for all.
    assert embedder.batch_sizes == [EMBED_BATCH_SIZE, EMBED_BATCH_SIZE, 7]
    assert max(embedder.batch_sizes) <= EMBED_BATCH_SIZE
    assert result["chunks_created"] == chunk_count
    assert conn.chunk_inserts() == chunk_count
    assert conn.statuses()[-1] == "completed"


def test_embedding_failure_midway_completes_document_without_chunks():
    """Chunks are useless without embeddings — keep the all-or-nothing contract."""
    embedder = _RecordingEmbeddingService(fail_at_call=2)
    conn = _FakeConn(_doc_row())

    result = _run_process_document(EMBED_BATCH_SIZE * 3, embedder, conn)

    assert result["chunks_created"] == 0
    assert "Embeddings failed" in (result["embedding_warning"] or "")
    # Document still completes and falls back to keyword search.
    assert conn.statuses()[-1] == "completed"


def test_on_failure_releases_document_stranded_by_worker_kill():
    """SIGKILL runs no in-process code; the parent's on_failure is the only hook left."""
    marked: list[tuple[str, str]] = []

    async def _fake_mark(document_id, error):
        marked.append((document_id, error))

    with (
        patch("app.workers.tasks.er_document_processing._mark_document_failed", _fake_mark),
        patch("app.workers.tasks.er_document_processing.publish_task_error"),
    ):
        process_er_document.on_failure(
            exc=RuntimeError("Worker exited prematurely: signal 9 (SIGKILL)"),
            task_id="t-1",
            args=("doc-42", "case-1"),
            kwargs={},
            einfo=None,
        )

    assert len(marked) == 1
    document_id, error = marked[0]
    assert document_id == "doc-42"
    assert "SIGKILL" in error


def test_on_failure_reads_document_id_from_kwargs():
    marked: list[str] = []

    async def _fake_mark(document_id, error):
        marked.append(document_id)

    with (
        patch("app.workers.tasks.er_document_processing._mark_document_failed", _fake_mark),
        patch("app.workers.tasks.er_document_processing.publish_task_error"),
    ):
        process_er_document.on_failure(
            exc=RuntimeError("boom"),
            task_id="t-1",
            args=(),
            kwargs={"document_id": "doc-99", "case_id": "case-1"},
            einfo=None,
        )

    assert marked == ["doc-99"]


def test_stale_sweep_only_targets_processing_rows_past_the_threshold():
    conn = _FakeConn(_doc_row())

    with patch("app.workers.tasks.er_document_processing.get_db_connection", _async_return(conn)):
        reset = asyncio.run(_reset_stale_documents())

    assert reset == 2
    sweep_sql, sweep_args = conn.executed[0]
    assert "processing_status = 'processing'" in sweep_sql
    # Threshold is bound, not interpolated into the SQL text.
    assert "make_interval(mins => $1)" in sweep_sql
    assert sweep_args == (STALE_PROCESSING_MINUTES,)
    assert conn.closed


def test_redis_outage_does_not_fail_the_document():
    """Progress events are cosmetic; a dead Redis must not cost us the document."""
    embedder = _RecordingEmbeddingService()
    conn = _FakeConn(_doc_row())

    chunks = [
        {"chunk_index": i, "content": f"chunk {i}", "line_start": i, "char_start": i}
        for i in range(3)
    ]
    parsed = SimpleNamespace(text="raw text", speaker_turns=[], temporal_refs=[])
    fake_storage = SimpleNamespace(download_file=_async_return(b"filebytes"))
    fake_parser = SimpleNamespace(
        parse_document=lambda *_a, **_k: parsed,
        chunk_text=lambda *_a, **_k: chunks,
    )
    fake_scrubber = SimpleNamespace(scrub=lambda text: ("scrubbed", {}))

    def _boom(**_kwargs):
        raise ConnectionError("redis is down")

    with (
        patch("app.core.services.storage.get_storage", return_value=fake_storage),
        patch("app.matcha.services.er_document_parser.ERDocumentParser", return_value=fake_parser),
        patch("app.core.services.pii_scrubber.PIIScrubber", return_value=fake_scrubber),
        patch("app.core.services.embedding_service.EmbeddingService", return_value=embedder),
        patch("app.config.load_settings", return_value=SimpleNamespace(gemini_api_key="k")),
        patch("app.workers.tasks.er_document_processing.get_db_connection", _async_return(conn)),
        patch("app.workers.tasks.er_document_processing.publish_task_progress", _boom),
    ):
        result = asyncio.run(_process_document("doc-1", "case-1"))

    # Embeddings still ran, chunks still stored, document still completed.
    assert result["chunks_created"] == 3
    assert result["embedding_warning"] is None
    assert conn.statuses()[-1] == "completed"


def test_on_failure_publishes_error_to_the_progress_channel():
    """A listener on er_case:{id} would otherwise hang on the last progress event."""
    published: list[dict] = []

    async def _fake_mark(document_id, error):
        return None

    with (
        patch("app.workers.tasks.er_document_processing._mark_document_failed", _fake_mark),
        patch(
            "app.workers.tasks.er_document_processing.publish_task_error",
            lambda **kw: published.append(kw),
        ),
    ):
        process_er_document.on_failure(
            exc=RuntimeError("Worker exited prematurely: signal 9 (SIGKILL)"),
            task_id="t-1",
            args=("doc-42", "case-7"),
            kwargs={},
            einfo=None,
        )

    assert len(published) == 1
    assert published[0]["channel"] == "er_case:case-7"
    assert published[0]["entity_id"] == "doc-42"
    assert "SIGKILL" in published[0]["error"]
