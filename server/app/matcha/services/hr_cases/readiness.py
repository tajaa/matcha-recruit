"""Will a new incident actually open an HR case? — the page's setup check.

A case opens only when the triage check (`triage.py`) finds a likely handbook
violation, and that check has two preconditions HR can't see from the board:
the company has handbook or policy content to check against, and incidents are
being filed at all. Whoever is told is the HR tier from `notifications`.

Never raises: a source that can't be read is reported as `unknown`, not as
ready and not as missing. Names only — nothing from an incident or a case.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


def shape(
    *, threshold: float, handbook_sources: Optional[int], incidents_enabled: Optional[bool],
    notified: Optional[list[str]],
) -> dict[str, Any]:
    """Pure: the response. `None` for a source means it could not be read.

    `ready` is only True when every precondition is known to hold; a check
    that couldn't run is never read as ready."""
    ready = bool(handbook_sources) and incidents_enabled is True and bool(notified)
    return {
        "threshold": threshold,
        "handbook_sources": handbook_sources,
        "incidents_enabled": incidents_enabled,
        "notified": notified,
        "ready": ready,
    }


async def build(conn, *, company_id: UUID, threshold: float) -> dict[str, Any]:
    from app.core.feature_flags import get_company_features
    from app.matcha.services.discipline.discipline_policy_check import build_check_corpus

    from .notifications import hr_recipients

    handbook_sources: Optional[int] = None
    try:
        corpus = await build_check_corpus(conn, company_id)
        if corpus is not None:
            handbook_sources = len(corpus.get("index") or {})
    except Exception:
        logger.exception("[hr_cases] readiness: handbook corpus failed for %s", company_id)

    incidents_enabled: Optional[bool] = None
    try:
        incidents_enabled = bool((await get_company_features(company_id, conn=conn)).get("incidents"))
    except Exception:
        logger.exception("[hr_cases] readiness: features failed for %s", company_id)

    notified: Optional[list[str]] = None
    try:
        notified = [r["name"] for r in await hr_recipients(conn, company_id)]
    except Exception:
        logger.exception("[hr_cases] readiness: recipients failed for %s", company_id)

    return shape(
        threshold=threshold, handbook_sources=handbook_sources,
        incidents_enabled=incidents_enabled, notified=notified,
    )
