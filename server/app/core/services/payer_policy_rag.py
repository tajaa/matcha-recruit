"""Payer Policy RAG Service.

Retrieval-Augmented Generation for payer medical policy Q&A.
Searches vectorized payer_medical_policies using pgvector.
"""

import json
from typing import Optional
from uuid import UUID

import asyncpg

from .embedding_service import EmbeddingService


class PayerPolicyRAGService:
    """Semantic search over payer policy embeddings for medical policy Q&A."""

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    async def search_policies(
        self,
        query: str,
        conn: asyncpg.Connection,
        payer_names: Optional[list[str]] = None,
        top_k: int = 10,
        min_similarity: float = 0.3,
    ) -> list[dict]:
        """Vector similarity search over payer policy embeddings."""
        query_embedding = await self.embedding_service.embed_text(
            query, task_type=EmbeddingService.TASK_RETRIEVAL_QUERY,
        )

        sql = """
            SELECT
                pe.policy_id,
                pe.content,
                pe.payer_name,
                pe.metadata AS embed_metadata,
                pp.policy_number,
                pp.policy_title,
                pp.payer_type,
                pp.procedure_codes,
                pp.diagnosis_codes,
                pp.procedure_description,
                pp.coverage_status,
                pp.requires_prior_auth,
                pp.clinical_criteria,
                pp.documentation_requirements,
                pp.medical_necessity_criteria,
                pp.age_restrictions,
                pp.frequency_limits,
                pp.place_of_service,
                pp.effective_date,
                pp.source_url,
                pp.source_document,
                1 - (pe.embedding <=> $1::vector) AS similarity
            FROM payer_policy_embeddings pe
            JOIN payer_medical_policies pp ON pe.policy_id = pp.id
            WHERE 1=1
        """
        params: list = [query_embedding]
        idx = 2

        if payer_names:
            sql += f" AND pe.payer_name = ANY(${idx}::text[])"
            params.append(payer_names)
            idx += 1

        if min_similarity > 0:
            sql += f" AND 1 - (pe.embedding <=> $1::vector) >= ${idx}"
            params.append(min_similarity)
            idx += 1

        sql += f" ORDER BY pe.embedding <=> $1::vector LIMIT ${idx}"
        params.append(top_k)

        rows = await conn.fetch(sql, *params)

        results = []
        for row in rows:
            results.append({
                "policy_id": str(row["policy_id"]),
                "content": row["content"],
                "similarity": float(row["similarity"]),
                "payer_name": row["payer_name"],
                "payer_type": row["payer_type"],
                "policy_number": row["policy_number"],
                "policy_title": row["policy_title"],
                "procedure_codes": row["procedure_codes"] or [],
                "procedure_description": row["procedure_description"],
                "coverage_status": row["coverage_status"],
                "requires_prior_auth": row["requires_prior_auth"],
                "clinical_criteria": row["clinical_criteria"],
                "documentation_requirements": row["documentation_requirements"],
                "medical_necessity_criteria": row["medical_necessity_criteria"],
                "frequency_limits": row["frequency_limits"],
                "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
                "source_url": row["source_url"],
                "source_document": row["source_document"],
            })

        return results

    async def get_context_for_query(
        self,
        query: str,
        conn: asyncpg.Connection,
        company_id: UUID,
        location_id: Optional[UUID] = None,
        payer_name: Optional[str] = None,
        max_tokens: int = 8000,
    ) -> tuple[str, list[dict]]:
        """Build RAG context for a payer policy question.

        Resolves the company's payer contracts and searches for relevant policies.
        Returns (context_text, sources).
        """
        # Resolve payer names to search
        payer_names = None
        if payer_name:
            payer_names = [payer_name]
        else:
            # Get payer contracts from company's facility attributes
            if location_id:
                row = await conn.fetchrow(
                    """SELECT facility_attributes->'payer_contracts' AS payers
                       FROM business_locations WHERE id = $1 AND company_id = $2""",
                    location_id, company_id,
                )
                if row and row["payers"]:
                    payer_names = json.loads(row["payers"]) if isinstance(row["payers"], str) else row["payers"]
            else:
                rows = await conn.fetch(
                    """SELECT DISTINCT jsonb_array_elements_text(facility_attributes->'payer_contracts') AS payer
                       FROM business_locations
                       WHERE company_id = $1 AND is_active = true
                         AND facility_attributes IS NOT NULL
                         AND facility_attributes->'payer_contracts' IS NOT NULL""",
                    company_id,
                )
                if rows:
                    payer_names = [r["payer"] for r in rows]

        # Normalize payer names for search (facility stores "medicare", API stores "Medicare")
        if payer_names:
            normalized = []
            for p in payer_names:
                p_lower = p.lower()
                if p_lower in ("medicare", "medi_cal", "medicaid_other"):
                    normalized.append("Medicare")
                else:
                    normalized.append(p.title())
            payer_names = list(set(normalized))

        results = await self.search_policies(
            query=query,
            conn=conn,
            payer_names=payer_names,
            top_k=15,
            min_similarity=0.25,
        )

        if not results:
            return "", []

        # Build context with token budget
        context_parts = []
        sources = []
        total_chars = 0
        max_chars = max_tokens * 4

        for result in results:
            entry = f"[{result['payer_name']} — {result['policy_title']}]\n"
            if result["procedure_description"]:
                entry += f"  Procedure: {result['procedure_description']}"
                if result["procedure_codes"]:
                    entry += f" (CPT: {', '.join(result['procedure_codes'][:10])})"
                entry += "\n"
            entry += f"  Coverage: {result['coverage_status']}"
            if result["requires_prior_auth"]:
                entry += " | Prior Auth: REQUIRED"
            entry += "\n"
            if result["clinical_criteria"]:
                criteria = result["clinical_criteria"]
                if len(criteria) > 1500:
                    criteria = criteria[:1500] + "..."
                entry += f"  Clinical Criteria: {criteria}\n"
            if result["documentation_requirements"]:
                entry += f"  Documentation: {result['documentation_requirements'][:500]}\n"
            if result["frequency_limits"]:
                entry += f"  Frequency: {result['frequency_limits']}\n"
            if result["source_url"]:
                entry += f"  Source: {result['source_url']}\n"

            if total_chars + len(entry) > max_chars:
                break

            context_parts.append(entry)
            sources.append({
                "policy_id": result["policy_id"],
                "payer_name": result["payer_name"],
                "policy_title": result["policy_title"],
                "policy_number": result["policy_number"],
                "procedure_description": result["procedure_description"],
                "coverage_status": result["coverage_status"],
                "source_url": result["source_url"],
                "source_document": result["source_document"],
                "similarity": result["similarity"],
            })
            total_chars += len(entry)

        context_text = "\n\n".join(context_parts)
        return context_text, sources
