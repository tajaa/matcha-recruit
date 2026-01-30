import json
from typing import AsyncIterator, List
from uuid import UUID

import httpx

from ...config import get_settings
from ...database import get_connection

_service = None


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

            # Compliance requirements grouped by location
            reqs = await conn.fetch(
                """SELECT cr.category, cr.current_value, cr.jurisdiction_level,
                          cr.jurisdiction_name, bl.name as location_name
                   FROM compliance_requirements cr
                   JOIN business_locations bl ON cr.location_id = bl.id
                   WHERE bl.company_id = $1
                   ORDER BY bl.name, cr.category""",
                company_id,
            )
            if reqs:
                parts.append("\n## Compliance Requirements")
                current_loc = None
                for req in reqs:
                    if req["location_name"] != current_loc:
                        current_loc = req["location_name"]
                        parts.append(f"### {current_loc}")
                    parts.append(
                        f"- {req['category']}: {req['current_value']} "
                        f"({req['jurisdiction_level']}: {req['jurisdiction_name']})"
                    )

            # Policies
            policies = await conn.fetch(
                """SELECT title, description FROM policies
                   WHERE company_id = $1 ORDER BY title""",
                company_id,
            )
            if policies:
                parts.append("\n## Company Policies")
                for pol in policies:
                    desc = pol["description"] or ""
                    if len(desc) > 200:
                        desc = desc[:200] + "..."
                    parts.append(f"- {pol['title']}: {desc}")

            return "\n".join(parts)

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
