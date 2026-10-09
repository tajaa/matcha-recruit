"""Which app's AI-model setting a matcha-work call follows.

Matcha Work (business accounts on `/work`) is part of Matcha; Espresso is the
personal app (`companies.is_personal`, the flag `agent_runtime/eligibility.py`
uses). Both run on this backend, so a shared call site — chat, agent cards,
the project agent, task drafts — asks `work_surface` for its
`agent_surfaces` key instead of hard-coding one.
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from cachetools import TTLCache

from app.core.services import agent_surfaces as reg
from app.database import connection_or_direct

logger = logging.getLogger(__name__)

WorkProduct = Literal["chat", "agent_cards", "projects"]

_BUSINESS: dict[str, str] = {
    "chat": reg.MATCHA_WORK_CHAT,
    "agent_cards": reg.MATCHA_WORK_AGENT_CARDS,
    "projects": reg.MATCHA_WORK_PROJECTS,
}
_PERSONAL: dict[str, str] = {
    "chat": reg.ESPRESSO_CHAT,
    "agent_cards": reg.ESPRESSO_AGENT_CARDS,
    "projects": reg.ESPRESSO_PROJECTS,
}

# A company never changes between personal and business, so the answer can
# be held; the TTL only bounds memory and a hypothetical admin fix-up.
_personal: TTLCache = TTLCache(maxsize=4096, ttl=600)


async def is_personal_company(company_id: UUID | str | None) -> bool:
    """Whether the company is a personal (Espresso) account. Unknown, missing
    or unreadable → False (business): the Matcha setting is the conservative
    default for a workspace we can't place."""
    if not company_id:
        return False
    key = str(company_id)
    if key in _personal:
        return _personal[key]
    try:
        async with connection_or_direct() as conn:
            value = await conn.fetchval(
                "SELECT COALESCE(is_personal, false) FROM companies WHERE id = $1", UUID(key),
            )
    except Exception:
        logger.warning("work_surface: could not read is_personal for %s; using Matcha", key, exc_info=True)
        return False
    _personal[key] = bool(value)
    return _personal[key]


async def work_surface(company_id: UUID | str | None, product: WorkProduct) -> str:
    """`matcha.work_<product>` for a business account, `espresso.<product>`
    for a personal one."""
    table = _PERSONAL if await is_personal_company(company_id) else _BUSINESS
    return table[product]
