"""
Celery tasks for ER document processing.

Handles document parsing, PII scrubbing, chunking, and embedding generation.
"""

import asyncio
import json
from typing import Any

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress
from ..utils import get_db_connection

# Chunks embedded + inserted per batch. Bounds peak memory to one batch of
# 768-dim vectors rather than the whole document's embedding matrix.
EMBED_BATCH_SIZE = 50

# A document left in 'processing' for longer than this was almost certainly
# killed mid-flight (OOM / container restart) — SIGKILL bypasses the except
# block that would otherwise mark it 'failed', so it never self-heals.
STALE_PROCESSING_MINUTES = 15


def _publish_progress_safe(**kwargs: Any) -> None:
    """Progress events are cosmetic — a Redis outage must never fail a document.

    publish_task_progress raises on a dead Redis. Inside the embed loop that
    would roll back every chunk written so far; before it, it would fail the
    document without embeddings ever being attempted.
    """
    try:
        publish_task_progress(**kwargs)
    except Exception as exc:  # pragma: no cover - best effort
        print(f"[Worker] progress publish failed (ignored): {exc}")


async def _process_document(document_id: str, case_id: str) -> dict[str, Any]:
    """
    Process an uploaded document:
    1. Download from storage
    2. Parse text
    3. Scrub PII
    4. Chunk text
    5. Generate embeddings
    6. Store chunks with embeddings
    """
    from app.core.services.storage import get_storage
    from app.matcha.services.er_document_parser import ERDocumentParser
    from app.core.services.pii_scrubber import PIIScrubber
    from app.core.services.embedding_service import EmbeddingService
    from app.config import load_settings

    settings = load_settings()
    storage = get_storage()
    parser = ERDocumentParser()
    scrubber = PIIScrubber()
    embedding_service = None
    embedding_warning = None
    try:
        embedding_service = EmbeddingService(api_key=settings.gemini_api_key)
    except Exception as e:
        # Embeddings are optional for case analysis; keep processing and fall back to keyword search.
        embedding_warning = f"Embeddings unavailable: {e}"

    conn = await get_db_connection()
    try:
        # Update status to processing
        await conn.execute(
            "UPDATE er_case_documents SET processing_status = 'processing' WHERE id = $1",
            document_id,
        )

        # Get document record
        doc = await conn.fetchrow(
            "SELECT filename, file_path, document_type FROM er_case_documents WHERE id = $1",
            document_id,
        )

        if not doc:
            raise ValueError(f"Document {document_id} not found")

        # Download file from storage
        file_bytes = await storage.download_file(doc["file_path"])

        # Parse document
        parsed = parser.parse_document(file_bytes, doc["filename"])

        # The raw bytes are dead once parsed. Drop the reference before the
        # text copies below multiply memory — the worker cgroup is small and
        # uploads run up to MAX_UPLOAD_SIZE (50MB).
        del file_bytes

        # Scrub PII from text
        scrubbed_text, pii_map = scrubber.scrub(parsed.text)

        # Update document with parsed and scrubbed text
        await conn.execute(
            """
            UPDATE er_case_documents
            SET original_text = $1, scrubbed_text = $2, pii_scrubbed = true, parsed_at = NOW()
            WHERE id = $3
            """,
            parsed.text,
            scrubbed_text,
            document_id,
        )

        # Metadata captured before parsed.text is released below.
        text_length = len(parsed.text)
        speaker_turns = parsed.speaker_turns
        temporal_refs_count = len(parsed.temporal_refs)

        # Chunk the scrubbed text for embeddings
        chunks = parser.chunk_text(scrubbed_text, chunk_size=500, overlap=50)

        # original_text + scrubbed_text are persisted and re-derivable; the
        # chunks now hold everything the rest of this function needs.
        parsed.text = ""
        del scrubbed_text

        if not chunks:
            # No content to embed
            await conn.execute(
                "UPDATE er_case_documents SET processing_status = 'completed' WHERE id = $1",
                document_id,
            )
            return {
                "document_id": document_id,
                "chunks_created": 0,
                "pii_scrubbed": bool(pii_map),
            }

        # Add speaker and temporal info to chunks if detected
        speaker_map = {}
        for turn in speaker_turns:
            for line in range(turn.line_start, turn.line_end + 1):
                speaker_map[line] = turn.speaker

        chunks_created = 0
        # Embed and store in batches. Embedding every chunk up front held the
        # full N x 768 float matrix in memory alongside the chunk list — on a
        # large document that alone exceeded the worker's memory cgroup and got
        # the process SIGKILLed, stranding the row in 'processing' forever.
        # One batch at a time keeps peak memory flat in document size.
        if embedding_service is not None:
            _publish_progress_safe(
                channel=f"er_case:{case_id}",
                task_type="document_processing",
                entity_id=document_id,
                progress=0,
                total=len(chunks),
                message="Generating embeddings...",
            )
            try:
                # Chunks are only useful with their embeddings, so keep the
                # all-or-nothing guarantee: a mid-way embedding failure rolls
                # back every chunk written for this document.
                async with conn.transaction():
                    for start in range(0, len(chunks), EMBED_BATCH_SIZE):
                        batch = chunks[start:start + EMBED_BATCH_SIZE]
                        embeddings = embedding_service.embed_batch_sync(
                            [c["content"] for c in batch]
                        )
                        if len(embeddings) != len(batch):
                            raise ValueError(
                                f"Embedding count {len(embeddings)} != chunk count {len(batch)}"
                            )

                        for chunk, embedding in zip(batch, embeddings):
                            # Try to find speaker for this chunk
                            speaker = speaker_map.get(chunk.get("line_start"))

                            # Convert embedding list to string format for pgvector
                            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
                            await conn.execute(
                                """
                                INSERT INTO er_evidence_chunks
                                (document_id, case_id, chunk_index, content, speaker, page_number, line_start, line_end, embedding, metadata)
                                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                                """,
                                document_id,
                                case_id,
                                chunk["chunk_index"],
                                chunk["content"],
                                speaker,
                                None,  # page_number - could be extracted from PDF
                                chunk.get("line_start"),
                                chunk.get("line_end"),
                                embedding_str,
                                json.dumps({"char_start": chunk.get("char_start")}),
                            )
                            chunks_created += 1

                        del embeddings

                        _publish_progress_safe(
                            channel=f"er_case:{case_id}",
                            task_type="document_processing",
                            entity_id=document_id,
                            progress=chunks_created,
                            total=len(chunks),
                            message=f"Stored {chunks_created}/{len(chunks)} chunks",
                        )
            except Exception as e:
                # Embeddings are optional for case analysis; the document still
                # completes and falls back to keyword search.
                embedding_warning = f"Embeddings failed: {e}"
                chunks_created = 0

        # Update status to completed
        await conn.execute(
            "UPDATE er_case_documents SET processing_status = 'completed' WHERE id = $1",
            document_id,
        )

        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
            "pii_scrubbed": bool(pii_map),
            "text_length": text_length,
            "speaker_turns_detected": len(speaker_turns),
            "temporal_refs_detected": temporal_refs_count,
            "embedding_warning": embedding_warning,
        }

    except Exception as e:
        # Update status to failed
        await conn.execute(
            """
            UPDATE er_case_documents
            SET processing_status = 'failed', processing_error = $1
            WHERE id = $2
            """,
            str(e),
            document_id,
        )
        raise

    finally:
        await conn.close()


async def _mark_document_failed(document_id: str, error: str) -> None:
    """Force a document out of 'processing' after an out-of-process death."""
    conn = await get_db_connection()
    try:
        await conn.execute(
            """
            UPDATE er_case_documents
            SET processing_status = 'failed', processing_error = $1
            WHERE id = $2 AND processing_status = 'processing'
            """,
            error[:500],
            document_id,
        )
    finally:
        await conn.close()


class _ERDocumentTask(celery_app.Task):
    """Task base that guarantees the document row leaves 'processing'.

    `_process_document`'s own `except` marks the row 'failed', but it can only
    run for in-process exceptions. When the child is SIGKILLed (OOM), no Python
    in that process runs at all — Celery raises WorkerLostError in the PARENT
    and calls this hook there, which is the only place left to release the row.
    Without it the row sits in 'processing' forever and the ER guidance UI
    polls it indefinitely instead of ever generating.
    """

    def on_failure(self, exc, task_id, args, kwargs, einfo):  # noqa: D102
        document_id = kwargs.get("document_id") or (args[0] if args else None)
        case_id = kwargs.get("case_id") or (args[1] if len(args) > 1 else None)
        if not document_id:
            return

        error = f"{type(exc).__name__}: {exc}"
        try:
            asyncio.run(_mark_document_failed(document_id, error))
        except Exception:  # pragma: no cover - best effort, never mask the original failure
            pass

        # The in-process error path publishes; this one must too, or a client
        # subscribed to the progress channel hangs on the last progress event.
        if case_id:
            try:
                publish_task_error(
                    channel=f"er_case:{case_id}",
                    task_type="document_processing",
                    entity_id=document_id,
                    error=error,
                )
            except Exception:  # pragma: no cover - best effort
                pass


@celery_app.task(base=_ERDocumentTask, bind=True, max_retries=3)
def process_er_document(self, document_id: str, case_id: str) -> dict[str, Any]:
    """
    Celery task wrapper for document processing.

    Args:
        document_id: The document to process.
        case_id: The case the document belongs to.

    Returns:
        Processing result with chunk count and metadata.
    """
    try:
        result = asyncio.run(_process_document(document_id, case_id))

        publish_task_complete(
            channel=f"er_case:{case_id}",
            task_type="document_processing",
            entity_id=document_id,
            result=result,
        )

        return {"status": "success", **result}

    except Exception as e:
        publish_task_error(
            channel=f"er_case:{case_id}",
            task_type="document_processing",
            entity_id=document_id,
            error=str(e),
        )

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


async def _reset_stale_documents() -> int:
    conn = await get_db_connection()
    try:
        # Keying the age off created_at is safe despite reprocessing not
        # touching it: the reprocess endpoint resets the row to 'pending', and
        # only _process_document itself flips it to 'processing'. So a re-queued
        # document is never in this WHERE clause while it waits. And a task that
        # is genuinely running cannot be swept out from under itself — celery's
        # task_time_limit (600s) is well inside STALE_PROCESSING_MINUTES, and
        # worker concurrency is 1, so this sweep never overlaps a live task.
        rows = await conn.fetch(
            """
            UPDATE er_case_documents
            SET processing_status = 'failed',
                processing_error = 'Processing did not finish (worker terminated). Re-upload or reprocess.'
            WHERE processing_status = 'processing'
              AND created_at < NOW() - make_interval(mins => $1)
            RETURNING id
            """,
            STALE_PROCESSING_MINUTES,
        )
        return len(rows)
    finally:
        await conn.close()


@celery_app.task
def reset_stale_er_documents() -> dict[str, Any]:
    """Release documents stranded in 'processing' by an out-of-process death.

    Safety net for the case `_ERDocumentTask.on_failure` cannot cover — e.g. the
    whole worker container is killed, so even the parent never runs its hook.
    Dispatched on worker startup; concurrency is 1, so nothing legitimate is
    mid-flight at that moment, and the age threshold guards against racing a
    long-running task anyway.
    """
    reset = asyncio.run(_reset_stale_documents())
    if reset:
        print(f"[Worker] Reset {reset} stale ER document(s) from 'processing' to 'failed'")
    return {"status": "success", "reset": reset}
