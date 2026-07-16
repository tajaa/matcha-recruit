"""Compliance RAG Service.

Retrieval-Augmented Generation for natural language regulatory Q&A.
Searches vectorized jurisdiction_requirements using pgvector.
"""

import json
from typing import Optional
from uuid import UUID

import asyncpg

from .embedding_service import EmbeddingService


class ComplianceRAGService:
    """Semantic search over compliance embeddings for regulatory Q&A."""

    def __init__(self, embedding_service: EmbeddingService):
        self.embedding_service = embedding_service

    async def search_requirements(
        self,
        query: str,
        conn: asyncpg.Connection,
        jurisdiction_ids: Optional[list[UUID]] = None,
        categories: Optional[list[str]] = None,
        industry_tags: Optional[list[str]] = None,
        top_k: int = 10,
        min_similarity: float = 0.3,
        statuses: Optional[list[str]] = None,
    ) -> list[dict]:
        """Vector similarity search over compliance embeddings.

        Parameters
        ----------
        query : str
            Natural language question.
        conn : asyncpg.Connection
        jurisdiction_ids : list[UUID], optional
            Filter to specific jurisdictions (e.g. from company locations).
        categories : list[str], optional
            Filter to specific compliance categories.
        industry_tags : list[str], optional
            Filter to requirements matching these industries.
        top_k : int
            Max results to return.
        min_similarity : float
            Minimum cosine similarity threshold.
        statuses : list[str], optional
            Filter to jurisdiction_requirements.status values (e.g. ["active"]).
            None keeps the historical behavior of returning every status —
            repealed/superseded rows are embedded too, so callers surfacing
            "current law" should pass ["active"].

        Returns
        -------
        list[dict] with keys: requirement_id, content, similarity, title,
            current_value, description, source_url, source_name,
            statute_citation, effective_date, category, jurisdiction_level,
            jurisdiction_name
        """
        query_embedding = await self.embedding_service.embed_text(
            query, task_type=EmbeddingService.TASK_RETRIEVAL_QUERY,
        )

        sql = """
            SELECT
                ce.requirement_id,
                ce.content,
                ce.category,
                ce.jurisdiction_level,
                ce.jurisdiction_name,
                ce.metadata,
                jr.title,
                jr.current_value,
                jr.numeric_value,
                jr.description,
                jr.source_url,
                jr.source_name,
                jr.effective_date,
                jr.statute_citation,
                1 - (ce.embedding <=> $1::vector) AS similarity
            FROM compliance_embeddings ce
            JOIN jurisdiction_requirements jr ON ce.requirement_id = jr.id
            WHERE jr.status = 'active'
        """
        # This is where the ask-answer's source chips come from, and it reads the
        # catalog rather than any location's projection — so the gate on
        # compliance_requirements never reaches it. Ungated, an answer would cite
        # rows the Requirements tab refuses to show, and the chip's deep-link
        # would land on nothing.
        from .compliance_service import codified_gate_sql

        sql += await codified_gate_sql("jr", conn=conn)

        embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        params: list = [embedding_str]
        idx = 2

        if jurisdiction_ids:
            sql += f" AND ce.jurisdiction_id = ANY(${idx}::uuid[])"
            params.append(jurisdiction_ids)
            idx += 1

        if categories:
            sql += f" AND ce.category = ANY(${idx}::text[])"
            params.append(categories)
            idx += 1

        if industry_tags:
            # NULL *or empty* applicable_industries means the requirement is
            # universal (untagged baseline / general labor law — minimum wage,
            # overtime, etc. are stored as `{}`). Array overlap against NULL
            # yields NULL, and `{} && $tags` is false, so both silently drop
            # universal rows unless we let them through explicitly.
            sql += (
                f" AND (ce.applicable_industries IS NULL"
                f" OR cardinality(ce.applicable_industries) = 0"
                f" OR ce.applicable_industries && ${idx}::text[])"
            )
            params.append(industry_tags)
            idx += 1

        if statuses:
            sql += f" AND jr.status = ANY(${idx}::requirement_status_enum[])"
            params.append(statuses)
            idx += 1

        if min_similarity > 0:
            sql += f" AND 1 - (ce.embedding <=> $1::vector) >= ${idx}"
            params.append(min_similarity)
            idx += 1

        sql += f" ORDER BY ce.embedding <=> $1::vector LIMIT ${idx}"
        params.append(top_k)

        rows = await conn.fetch(sql, *params)

        results = []
        for row in rows:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}

            results.append({
                "requirement_id": str(row["requirement_id"]),
                "content": row["content"],
                "similarity": float(row["similarity"]),
                "title": row["title"],
                "current_value": row["current_value"],
                "numeric_value": str(row["numeric_value"]) if row["numeric_value"] is not None else None,
                "description": row["description"],
                "source_url": row["source_url"],
                "source_name": row["source_name"],
                "statute_citation": row.get("statute_citation"),
                "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
                "category": row["category"],
                "jurisdiction_level": row["jurisdiction_level"],
                "jurisdiction_name": row["jurisdiction_name"],
                "metadata": metadata,
            })

        return results

    async def get_context_for_question(
        self,
        query: str,
        conn: asyncpg.Connection,
        company_id: UUID,
        location_id: Optional[UUID] = None,
        max_tokens: int = 6000,
    ) -> tuple[str, list[dict]]:
        """Build RAG context for a regulatory question.

        Resolves the company's jurisdictions, searches relevant requirements,
        and formats context with source citations.

        Returns
        -------
        tuple[str, list[dict]]
            (context_text, sources) where sources include citation info.
        """
        # Resolve the company's leaf jurisdictions (the location the question is
        # about, or all active locations).
        if location_id:
            jids = await conn.fetch(
                """SELECT jurisdiction_id, state FROM business_locations
                   WHERE id = $1""",
                location_id,
            )
        else:
            jids = await conn.fetch(
                """SELECT jurisdiction_id, state FROM business_locations
                   WHERE company_id = $1 AND is_active = true""",
                company_id,
            )
        leaf_ids = [r["jurisdiction_id"] for r in jids if r["jurisdiction_id"]]
        loc_states = [r["state"] for r in jids if r["state"]]

        jurisdiction_ids: Optional[list[UUID]] = None
        if leaf_ids:
            # Walk the whole chain (city → county → state → federal): minimum
            # wage / overtime / meal breaks live at STATE level, so a leaf-only
            # filter can't see them. Same shape as compliance_risk's penalty CTE.
            chain = await conn.fetch(
                """
                WITH RECURSIVE chain AS (
                    SELECT id, parent_id, 0 AS depth
                    FROM jurisdictions WHERE id = ANY($1::uuid[])
                    UNION ALL
                    SELECT j.id, j.parent_id, c.depth + 1
                    FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
                    WHERE c.depth < 10
                )
                SELECT DISTINCT id FROM chain
                """,
                leaf_ids,
            )
            jurisdiction_ids = [r["id"] for r in chain]
        elif loc_states:
            # No linked jurisdiction — scope to the company's own states +
            # federal rather than searching the entire national catalog. The
            # RAG contract is "requirements that apply to THIS company".
            state_rows = await conn.fetch(
                """SELECT id FROM jurisdictions
                   WHERE UPPER(state) = ANY($1::text[]) OR level = 'federal'""",
                [s.upper() for s in loc_states],
            )
            jurisdiction_ids = [r["id"] for r in state_rows] or None

        # Safety net: ensure federal is present for a resolved chain.
        if jurisdiction_ids:
            federal = await conn.fetchval(
                "SELECT id FROM jurisdictions WHERE level = 'federal' LIMIT 1"
            )
            if federal and federal not in jurisdiction_ids:
                jurisdiction_ids.append(federal)

        # Get company industry tags for filtering
        company = await conn.fetchrow(
            "SELECT industry FROM companies WHERE id = $1",
            company_id,
        )
        industry_tags = None
        if company and company["industry"]:
            industry_tags = [company["industry"].lower()]

        results = await self.search_requirements(
            query=query,
            conn=conn,
            jurisdiction_ids=jurisdiction_ids,
            industry_tags=industry_tags,
            top_k=15,
            min_similarity=0.3,
        )

        if not results:
            return "", []

        # Dedup near-identical rows before building context/sources. The shared
        # catalog can carry the SAME policy under several category labels (a
        # research-run mis-categorization — e.g. one SB 525 wage row filed under
        # pay_frequency / final_pay / i9_everify), which otherwise floods the
        # answer with a dozen clones of one policy. Key on the content, not the
        # category; results are already similarity-ordered so first-seen wins.
        deduped = []
        seen_keys = set()
        for result in results:
            key = (
                " ".join((result.get("title") or "").lower().split()),
                result.get("jurisdiction_level"),
                " ".join((result.get("jurisdiction_name") or "").lower().split()),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(result)
        results = deduped[:8]

        # Build context string with token budget
        context_parts = []
        sources = []
        total_chars = 0
        max_chars = max_tokens * 4  # ~4 chars per token

        for result in results:
            entry = f"[{result['jurisdiction_name']} ({result['jurisdiction_level']}) — {result['category']}]\n"
            entry += f"  {result['title']}"
            if result["current_value"]:
                entry += f": {result['current_value']}"
            if result["description"]:
                entry += f"\n  {result['description']}"
            if result["effective_date"]:
                entry += f"\n  Effective: {result['effective_date']}"
            # Enforcing authority by NAME only — the external URL is deliberately
            # NOT fed to the model (it must not print links; the user opens the
            # requirement from the in-app source chip). URL still travels in the
            # `sources` payload for the chip's deep-link, not the prose.
            if result.get("source_name"):
                entry += f"\n  Authority: {result['source_name']}"
            if result.get("statute_citation"):
                entry += f"\n  Citation: {result['statute_citation']}"

            if total_chars + len(entry) > max_chars:
                break

            context_parts.append(entry)
            sources.append({
                "requirement_id": result["requirement_id"],
                "title": result["title"],
                "category": result["category"],
                "jurisdiction_name": result["jurisdiction_name"],
                "jurisdiction_level": result["jurisdiction_level"],
                "source_url": result["source_url"],
                "source_name": result["source_name"],
                "statute_citation": result.get("statute_citation"),
                "similarity": result["similarity"],
            })
            total_chars += len(entry)

        context_text = "\n\n".join(context_parts)
        return context_text, sources
