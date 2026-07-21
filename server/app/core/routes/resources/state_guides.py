"""state_guides routes (L9 split)."""
import html as _html
import json as _json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.dependencies import get_optional_user
from app.matcha.dependencies import require_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip

from app.core.routes.resources._shared import *  # noqa: F401,F403  (router objects + shared models/consts)
logger = logging.getLogger(__name__)



# ---------------------------------------------------------------------------
# State Compliance Guides — public surface over jurisdictions data.
# ---------------------------------------------------------------------------


@router.get("/state-guides")
async def list_state_guides(current_user: CurrentUser = Depends(require_client)):
    """List US states with state-level compliance data available."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT j.state, COUNT(jr.id) AS req_count, MAX(jr.last_verified_at) AS last_verified
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr
                ON jr.jurisdiction_id = j.id AND jr.status = 'active'
            WHERE j.country_code = 'US' AND j.level = 'state'
            GROUP BY j.state
            HAVING COUNT(jr.id) > 0
            ORDER BY j.state
            """
        )

    out = []
    for r in rows:
        slug = CODE_TO_SLUG.get(r["state"])
        if not slug:
            continue
        meta = STATE_SLUGS[slug]
        out.append({
            "slug": slug,
            "code": meta["code"],
            "name": meta["name"],
            "requirement_count": r["req_count"],
            "last_verified": r["last_verified"].isoformat() if r["last_verified"] else None,
        })
    return {"states": out}




@router.get("/state-guides/{slug}")
async def get_state_guide(slug: str, current_user: CurrentUser = Depends(require_client)):
    """Authenticated state guide — full teaser for signed-in users.

    Intentionally limited: returns category list with counts and a small
    number of sample requirement titles per category. Full requirement
    detail (current values, source URLs, statute citations, summaries)
    is gated behind platform signup. This preserves SEO + lead-gen value
    without giving away the proprietary jurisdiction dataset.
    """
    meta = STATE_SLUGS.get(slug)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown state")

    async with get_connection() as conn:
        jurisdiction = await conn.fetchrow(
            """
            SELECT id, last_verified_at
            FROM jurisdictions
            WHERE state = $1 AND level = 'state' AND country_code = 'US'
            LIMIT 1
            """,
            meta["code"],
        )
        if not jurisdiction:
            raise HTTPException(status_code=404, detail="No data for this state yet")

        rows = await conn.fetch(
            """
            SELECT category, title, current_value
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1 AND status = 'active'
            ORDER BY category, COALESCE(sort_order, 9999), title
            """,
            jurisdiction["id"],
        )

    grouped: dict[str, list[dict]] = {}
    for r in rows:
        cat = r["category"] or "other"
        grouped.setdefault(cat, []).append({
            "title": r["title"],
            "current_value": r["current_value"],
        })

    categories = []
    for cat in sorted(grouped.keys(), key=_category_sort_key):
        items = grouped[cat]
        sample_titles = [it["title"] for it in items[:_MAX_SAMPLE_TITLES_PER_CATEGORY]]
        # Show ONE preview value (anchor stat) only for headline categories.
        preview_value = None
        if cat in _PREVIEW_VALUE_CATEGORIES:
            for it in items:
                if it["current_value"]:
                    preview_value = it["current_value"]
                    break
        categories.append({
            "key": cat,
            "label": _format_category(cat),
            "count": len(items),
            "sample_titles": sample_titles,
            "preview_value": preview_value,
        })

    return {
        "slug": slug,
        "code": meta["code"],
        "name": meta["name"],
        "requirement_count": sum(c["count"] for c in categories),
        "category_count": len(categories),
        "last_verified": jurisdiction["last_verified_at"].isoformat() if jurisdiction["last_verified_at"] else None,
        "categories": categories,
    }
