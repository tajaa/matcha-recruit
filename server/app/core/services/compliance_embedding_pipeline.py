"""Compliance Embedding Pipeline.

Indexes jurisdiction_requirements into compliance_embeddings for RAG Q&A.
One embedding per requirement (no chunking — each is a self-contained fact).
"""

import json
import os
from typing import Optional
from uuid import UUID

import asyncpg

from .embedding_service import EmbeddingService
from ...config import get_settings


def _get_embedding_service() -> EmbeddingService:
    api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
    return EmbeddingService(api_key=api_key)


def compose_embedding_text(req: dict) -> str:
    """Compose a single text string from a requirement for embedding.

    Format optimized for retrieval: includes category, title, description,
    current value, and jurisdiction context.
    """
    parts = []

    category = req.get("category", "")
    title = req.get("title", "")
    if category:
        parts.append(f"{category}: {title}")
    else:
        parts.append(title)

    description = req.get("description", "")
    if description:
        parts.append(description)

    current_value = req.get("current_value", "")
    if current_value:
        parts.append(f"Current value: {current_value}")

    jurisdiction_name = req.get("jurisdiction_name", "")
    jurisdiction_level = req.get("jurisdiction_level", "")
    if jurisdiction_name:
        parts.append(f"Jurisdiction: {jurisdiction_name} ({jurisdiction_level})")

    # Include penalty context for retrieval
    meta = req.get("metadata")
    if isinstance(meta, str):
        import json as _json
        try:
            meta = _json.loads(meta)
        except Exception:
            meta = None
    if isinstance(meta, dict):
        penalties = meta.get("penalties") or {}
        if penalties.get("summary"):
            parts.append(f"Penalties: {penalties['summary']}")
        if penalties.get("enforcing_agency"):
            parts.append(f"Enforced by: {penalties['enforcing_agency']}")

    return ". ".join(parts)


async def embed_requirements(
    conn: asyncpg.Connection,
    jurisdiction_id: Optional[UUID] = None,
    batch_size: int = 50,
) -> int:
    """Bulk embed jurisdiction_requirements and upsert into compliance_embeddings.

    Parameters
    ----------
    conn : asyncpg.Connection
    jurisdiction_id : UUID, optional
        If provided, only embed requirements for this jurisdiction.
    batch_size : int
        Number of requirements to embed per Gemini API call.

    Returns
    -------
    int  Number of requirements embedded.
    """
    embedding_service = _get_embedding_service()

    where_clause = ""
    params = []
    if jurisdiction_id:
        where_clause = "WHERE jr.jurisdiction_id = $1"
        params = [jurisdiction_id]

    rows = await conn.fetch(
        f"""
        SELECT jr.id, jr.jurisdiction_id, jr.category, jr.jurisdiction_level,
               jr.jurisdiction_name, jr.title, jr.description, jr.current_value,
               jr.source_url, jr.source_name, jr.statute_citation,
               jr.applicable_industries, jr.effective_date
        FROM jurisdiction_requirements jr
        {where_clause}
        ORDER BY jr.jurisdiction_id, jr.category
        """,
        *params,
    )

    if not rows:
        return 0

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [compose_embedding_text(dict(r)) for r in batch]

        embeddings = await embedding_service.embed_batch(
            texts, task_type=EmbeddingService.TASK_RETRIEVAL_DOCUMENT,
        )

        for row, text, embedding in zip(batch, texts, embeddings):
            metadata = {
                "title": row["title"],
                "source_url": row["source_url"],
                "source_name": row["source_name"],
            }
            if row.get("statute_citation"):
                metadata["statute_citation"] = row["statute_citation"]
            if row.get("effective_date"):
                metadata["effective_date"] = row["effective_date"].isoformat()

            industries = row.get("applicable_industries") or []

            await conn.execute(
                """
                INSERT INTO compliance_embeddings
                    (requirement_id, jurisdiction_id, content, embedding,
                     category, jurisdiction_level, jurisdiction_name,
                     applicable_industries, metadata)
                VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8, $9::jsonb)
                ON CONFLICT (requirement_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    category = EXCLUDED.category,
                    jurisdiction_level = EXCLUDED.jurisdiction_level,
                    jurisdiction_name = EXCLUDED.jurisdiction_name,
                    applicable_industries = EXCLUDED.applicable_industries,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                row["id"],
                row["jurisdiction_id"],
                text,
                "[" + ",".join(str(x) for x in embedding) + "]",
                row["category"],
                row["jurisdiction_level"],
                row["jurisdiction_name"],
                industries,
                json.dumps(metadata),
            )
            total += 1

        print(f"[Embedding Pipeline] Embedded {min(i + batch_size, len(rows))}/{len(rows)} requirements")

    return total


async def embed_updated_requirements(
    conn: asyncpg.Connection,
    jurisdiction_id: Optional[UUID] = None,
) -> int:
    """Re-embed requirements that are newer than their embeddings.

    Only processes requirements whose updated_at is newer than the
    corresponding compliance_embeddings.updated_at, or that have no
    embedding yet.
    """
    embedding_service = _get_embedding_service()

    where_clause = ""
    params = []
    if jurisdiction_id:
        where_clause = "AND jr.jurisdiction_id = $1"
        params = [jurisdiction_id]

    rows = await conn.fetch(
        f"""
        SELECT jr.id, jr.jurisdiction_id, jr.category, jr.jurisdiction_level,
               jr.jurisdiction_name, jr.title, jr.description, jr.current_value,
               jr.source_url, jr.source_name, jr.statute_citation,
               jr.applicable_industries, jr.effective_date
        FROM jurisdiction_requirements jr
        LEFT JOIN compliance_embeddings ce ON ce.requirement_id = jr.id
        WHERE (ce.id IS NULL OR jr.updated_at > ce.updated_at)
        {where_clause}
        ORDER BY jr.jurisdiction_id, jr.category
        """,
        *params,
    )

    if not rows:
        return 0

    total = 0
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [compose_embedding_text(dict(r)) for r in batch]

        embeddings = await embedding_service.embed_batch(
            texts, task_type=EmbeddingService.TASK_RETRIEVAL_DOCUMENT,
        )

        for row, text, embedding in zip(batch, texts, embeddings):
            metadata = {
                "title": row["title"],
                "source_url": row["source_url"],
                "source_name": row["source_name"],
            }
            if row.get("statute_citation"):
                metadata["statute_citation"] = row["statute_citation"]
            if row.get("effective_date"):
                metadata["effective_date"] = row["effective_date"].isoformat()

            industries = row.get("applicable_industries") or []

            await conn.execute(
                """
                INSERT INTO compliance_embeddings
                    (requirement_id, jurisdiction_id, content, embedding,
                     category, jurisdiction_level, jurisdiction_name,
                     applicable_industries, metadata)
                VALUES ($1, $2, $3, $4::vector, $5, $6, $7, $8, $9::jsonb)
                ON CONFLICT (requirement_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    category = EXCLUDED.category,
                    jurisdiction_level = EXCLUDED.jurisdiction_level,
                    jurisdiction_name = EXCLUDED.jurisdiction_name,
                    applicable_industries = EXCLUDED.applicable_industries,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                row["id"],
                row["jurisdiction_id"],
                text,
                "[" + ",".join(str(x) for x in embedding) + "]",
                row["category"],
                row["jurisdiction_level"],
                row["jurisdiction_name"],
                industries,
                json.dumps(metadata),
            )
            total += 1

    if total > 0:
        print(f"[Embedding Pipeline] Updated {total} embeddings")
    return total
