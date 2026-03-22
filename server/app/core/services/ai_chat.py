import json
import os
from typing import AsyncIterator, List, Optional
from uuid import UUID

import httpx

from ...config import get_settings
from ...database import get_connection
from .compliance_service import _filter_by_jurisdiction_priority

_service = None

MAX_HISTORY_MESSAGES = 50
MAX_POLICIES = 20


class AIChatService:
    def __init__(self, base_url: str, model: str, max_tokens: int = 2048, temperature: float = 0.7):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def build_company_context(self, company_id: UUID) -> str:
        async with get_connection() as conn:
            company = await conn.fetchrow(
                "SELECT name, industry, size FROM companies WHERE id = $1",
                company_id,
            )
            if not company:
                return "You are an HR and compliance assistant."

            parts = [
                f"You are an HR and compliance assistant for {company['name']}.",
            ]
            if company["industry"]:
                parts.append(f"Industry: {company['industry']}.")
            if company["size"]:
                parts.append(f"Company size: {company['size']}.")

            # Locations
            locations = await conn.fetch(
                """SELECT name, city, state FROM business_locations
                   WHERE company_id = $1 ORDER BY name""",
                company_id,
            )
            if locations:
                parts.append("\n## Company Locations")
                for loc in locations:
                    parts.append(f"- {loc['name']}: {loc['city']}, {loc['state']}")

            # Compliance requirements — filtered by jurisdiction priority so
            # superseded entries (e.g. state rule overridden by city) are excluded.
            reqs = await conn.fetch(
                """SELECT cr.category, cr.title, cr.current_value,
                          cr.jurisdiction_level, cr.jurisdiction_name,
                          cr.location_id,
                          bl.name as location_name,
                          bl.city as location_city,
                          bl.state as location_state
                   FROM compliance_requirements cr
                   JOIN business_locations bl ON cr.location_id = bl.id
                   WHERE bl.company_id = $1
                   ORDER BY bl.name, cr.category""",
                company_id,
            )
            if reqs:
                reqs_dicts = [dict(r) for r in reqs]
                # Group by location_id (not name) to keep locations distinct
                by_location: dict[UUID, list[dict]] = {}
                location_labels: dict[UUID, str] = {}
                for r in reqs_dicts:
                    loc_id = r["location_id"]
                    by_location.setdefault(loc_id, []).append(r)
                    if loc_id not in location_labels:
                        name = r["location_name"]
                        city_state = f"{r['location_city']}, {r['location_state']}"
                        location_labels[loc_id] = f"{name} ({city_state})" if name else city_state

                parts.append("\n## Compliance Requirements")
                for loc_id, loc_reqs in by_location.items():
                    filtered = _filter_by_jurisdiction_priority(loc_reqs)
                    if filtered:
                        parts.append(f"### {location_labels[loc_id]}")
                        for req in filtered:
                            parts.append(
                                f"- {req['category']}: {req['current_value']} "
                                f"({req['jurisdiction_level']}: {req['jurisdiction_name']})"
                            )

            # Policies — include category and content excerpt for AI context
            policies = await conn.fetch(
                """SELECT title, description, content, category FROM policies
                   WHERE company_id = $1 AND status = 'active' ORDER BY title
                   LIMIT $2""",
                company_id,
                MAX_POLICIES,
            )
            if policies:
                parts.append("\n## Company Policies")
                for pol in policies:
                    cat = f"[{pol['category']}] " if pol["category"] else ""
                    desc = pol["description"] or ""
                    if len(desc) > 200:
                        desc = desc[:200] + "..."
                    parts.append(f"- {cat}{pol['title']}: {desc}")
                    content_preview = (pol["content"] or "")[:400].strip()
                    if content_preview:
                        parts.append(f"  Content: {content_preview}...")

            return "\n".join(parts)

    async def build_regulatory_context(
        self,
        company_id: UUID,
        query: str,
        location_id: Optional[UUID] = None,
    ) -> tuple[str, list[dict]]:
        """Build RAG-augmented context for regulatory Q&A.

        Returns (system_prompt, sources) where sources include citation info.
        """
        from .embedding_service import EmbeddingService
        from .compliance_rag import ComplianceRAGService

        settings = get_settings()
        api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key

        async with get_connection() as conn:
            # Get company context
            company = await conn.fetchrow(
                "SELECT name, industry, size FROM companies WHERE id = $1",
                company_id,
            )
            company_name = company["name"] if company else "your company"
            industry = company["industry"] if company else ""
            size = company["size"] if company else ""

            # RAG retrieval
            rag_context = ""
            sources: list[dict] = []

            if api_key:
                embedding_service = EmbeddingService(api_key=api_key)
                rag_service = ComplianceRAGService(embedding_service)
                rag_context, sources = await rag_service.get_context_for_question(
                    query=query,
                    conn=conn,
                    company_id=company_id,
                    location_id=location_id,
                )

            # Company locations for context
            locations = await conn.fetch(
                """SELECT name, city, state FROM business_locations
                   WHERE company_id = $1 AND is_active = true ORDER BY name""",
                company_id,
            )

        parts = [
            f"You are a regulatory compliance expert assistant for {company_name}.",
            "Answer the user's question using the regulatory data provided below.",
            "",
            "RULES:",
            "- Only cite information from the provided sources. If the data doesn't contain an answer, say so clearly.",
            "- Always include the jurisdiction level and name when citing a requirement.",
            "- Include source URLs when available.",
            "- If a question spans multiple jurisdictions, compare them.",
            "- Be specific about dollar amounts, dates, and thresholds.",
        ]

        if industry:
            parts.append(f"\nIndustry: {industry}")
        if size:
            parts.append(f"Company size: {size}")

        if locations:
            parts.append("\n## Company Locations")
            for loc in locations:
                parts.append(f"- {loc['name']}: {loc['city']}, {loc['state']}")

        if rag_context:
            parts.append("\n## Relevant Regulatory Data")
            parts.append(rag_context)
        else:
            parts.append(
                "\n## No matching regulatory data found in the local database."
                "\nAnswer based on your general knowledge but clearly indicate this is not from verified local data."
            )

        system_prompt = "\n".join(parts)
        return system_prompt, sources

    async def stream_response(
        self,
        messages: List[dict],
        company_context: str,
    ) -> AsyncIterator[str]:
        system_messages = [{"role": "system", "content": company_context}]
        full_messages = system_messages + messages

        payload = {
            "model": self.model,
            "messages": full_messages,
            "stream": True,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


def get_ai_chat_service() -> AIChatService:
    global _service
    if _service is not None:
        return _service

    settings = get_settings()
    _service = AIChatService(
        base_url=settings.ai_chat_base_url,
        model=settings.ai_chat_model,
        max_tokens=settings.ai_chat_max_tokens,
        temperature=settings.ai_chat_temperature,
    )
    return _service
