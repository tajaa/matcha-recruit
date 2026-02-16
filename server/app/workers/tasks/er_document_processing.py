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
        embedding_service = EmbeddingService(
            api_key=settings.gemini_api_key,
            vertex_project=settings.vertex_project,
            vertex_location=settings.vertex_location,
        )
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

        # Chunk the scrubbed text for embeddings
        chunks = parser.chunk_text(scrubbed_text, chunk_size=500, overlap=50)

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

        embeddings: list[list[float]] | None = None
        if embedding_service is not None:
            try:
                # Publish progress
                publish_task_progress(
                    channel=f"er_case:{case_id}",
                    task_type="document_processing",
                    entity_id=document_id,
                    progress=0,
                    total=len(chunks),
                    message="Generating embeddings...",
                )

                # Generate embeddings for all chunks
                chunk_contents = [c["content"] for c in chunks]
                embeddings = embedding_service.embed_batch_sync(chunk_contents)
            except Exception as e:
                embedding_warning = f"Embeddings failed: {e}"
                embeddings = None

        # Add speaker and temporal info to chunks if detected
        speaker_turns = parsed.speaker_turns
        speaker_map = {}
        for turn in speaker_turns:
            for line in range(turn.line_start, turn.line_end + 1):
                speaker_map[line] = turn.speaker

        chunks_created = 0
        # Store chunks only when embeddings are available.
        if embeddings and len(embeddings) == len(chunks):
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                # Try to find speaker for this chunk
                speaker = None
                if chunk.get("line_start") in speaker_map:
                    speaker = speaker_map[chunk["line_start"]]

                # Store chunk with embedding
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

                # Publish progress periodically
                if (i + 1) % 10 == 0:
                    publish_task_progress(
                        channel=f"er_case:{case_id}",
                        task_type="document_processing",
                        entity_id=document_id,
                        progress=i + 1,
                        total=len(chunks),
                        message=f"Stored {i + 1}/{len(chunks)} chunks",
                    )

        # Update status to completed
        await conn.execute(
            "UPDATE er_case_documents SET processing_status = 'completed' WHERE id = $1",
            document_id,
        )

        return {
            "document_id": document_id,
            "chunks_created": chunks_created,
            "pii_scrubbed": bool(pii_map),
            "text_length": len(parsed.text),
            "speaker_turns_detected": len(speaker_turns),
            "temporal_refs_detected": len(parsed.temporal_refs),
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


@celery_app.task(bind=True, max_retries=3)
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
