"""Payer Policy Embedding Pipeline.

Indexes payer_medical_policies into payer_policy_embeddings for RAG search.
One embedding per policy (no chunking).
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


def compose_policy_embedding_text(policy: dict) -> str:
    """Compose text for embedding a payer medical policy.

    Front-loads payer name and procedure description (what users query on),
    includes procedure codes for exact code matching.
    """
    parts = []

    payer = policy.get("payer_name", "")
    desc = policy.get("procedure_description") or policy.get("policy_title", "")
    parts.append(f"{payer}: {desc}")

    codes = policy.get("procedure_codes") or []
    if codes:
        parts.append(f"CPT/HCPCS: {', '.join(codes[:20])}")

    dx_codes = policy.get("diagnosis_codes") or []
    if dx_codes:
        parts.append(f"ICD-10: {', '.join(dx_codes[:20])}")

    status = policy.get("coverage_status", "")
    if status:
        parts.append(f"Coverage: {status}")

    if policy.get("requires_prior_auth"):
        parts.append("Requires prior authorization")

    criteria = policy.get("clinical_criteria", "")
    if criteria:
        # Truncate to keep embedding focused
        parts.append(f"Clinical criteria: {criteria[:800]}")

    doc_reqs = policy.get("documentation_requirements", "")
    if doc_reqs:
        parts.append(f"Documentation: {doc_reqs[:400]}")

    necessity = policy.get("medical_necessity_criteria", "")
    if necessity and necessity != criteria:
        parts.append(f"Medical necessity: {necessity[:400]}")

    return ". ".join(parts)


async def embed_policies(
    conn: asyncpg.Connection,
    payer_name: Optional[str] = None,
    batch_size: int = 50,
) -> int:
    """Bulk embed payer medical policies and upsert into payer_policy_embeddings."""
    embedding_service = _get_embedding_service()

    where_clause = ""
    params = []
    if payer_name:
        where_clause = "WHERE payer_name = $1"
        params = [payer_name]

    rows = await conn.fetch(
        f"""
        SELECT id, payer_name, payer_type, policy_number, policy_title,
               procedure_codes, diagnosis_codes, procedure_description,
               coverage_status, requires_prior_auth, clinical_criteria,
               documentation_requirements, medical_necessity_criteria,
               source_url
        FROM payer_medical_policies
        {where_clause}
        ORDER BY payer_name, policy_title
        """,
        *params,
    )

    if not rows:
        return 0

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [compose_policy_embedding_text(dict(r)) for r in batch]

        embeddings = await embedding_service.embed_batch(
            texts, task_type=EmbeddingService.TASK_RETRIEVAL_DOCUMENT,
        )

        for row, text, embedding in zip(batch, texts, embeddings):
            metadata = {
                "policy_title": row["policy_title"],
                "policy_number": row["policy_number"],
                "source_url": row["source_url"],
            }

            await conn.execute(
                """
                INSERT INTO payer_policy_embeddings
                    (policy_id, payer_name, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                ON CONFLICT (policy_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    payer_name = EXCLUDED.payer_name,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                row["id"],
                row["payer_name"],
                text,
                embedding,
                json.dumps(metadata),
            )
            total += 1

        print(f"[Payer Embedding] Embedded {min(i + batch_size, len(rows))}/{len(rows)} policies")

    return total


async def embed_updated_policies(conn: asyncpg.Connection) -> int:
    """Re-embed policies newer than their embeddings, or with no embedding yet."""
    embedding_service = _get_embedding_service()

    rows = await conn.fetch(
        """
        SELECT pp.id, pp.payer_name, pp.payer_type, pp.policy_number, pp.policy_title,
               pp.procedure_codes, pp.diagnosis_codes, pp.procedure_description,
               pp.coverage_status, pp.requires_prior_auth, pp.clinical_criteria,
               pp.documentation_requirements, pp.medical_necessity_criteria,
               pp.source_url
        FROM payer_medical_policies pp
        LEFT JOIN payer_policy_embeddings pe ON pe.policy_id = pp.id
        WHERE pe.id IS NULL OR pp.updated_at > pe.updated_at
        ORDER BY pp.payer_name, pp.policy_title
        """,
    )

    if not rows:
        return 0

    total = 0
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [compose_policy_embedding_text(dict(r)) for r in batch]

        embeddings = await embedding_service.embed_batch(
            texts, task_type=EmbeddingService.TASK_RETRIEVAL_DOCUMENT,
        )

        for row, text, embedding in zip(batch, texts, embeddings):
            metadata = {
                "policy_title": row["policy_title"],
                "policy_number": row["policy_number"],
                "source_url": row["source_url"],
            }

            await conn.execute(
                """
                INSERT INTO payer_policy_embeddings
                    (policy_id, payer_name, content, embedding, metadata)
                VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                ON CONFLICT (policy_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    payer_name = EXCLUDED.payer_name,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                row["id"],
                row["payer_name"],
                text,
                embedding,
                json.dumps(metadata),
            )
            total += 1

    if total > 0:
        print(f"[Payer Embedding] Updated {total} embeddings")
    return total
