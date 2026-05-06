"""HR News routes — admin management + public read endpoint."""

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ..dependencies import require_admin
from ...database import get_connection
from ..services.hr_news_service import list_articles, refresh_feeds
from ..services.redis_cache import check_rate_limit, client_ip

router = APIRouter()
public_router = APIRouter()


@router.get("/articles")
async def get_articles(
    source: Optional[str] = Query(None, description="Filter by source name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    _user=Depends(require_admin),
):
    """List HR news articles with optional source filter and pagination."""
    async with get_connection() as conn:
        return await list_articles(conn, source=source, limit=limit, offset=offset)


@router.post("/refresh")
async def trigger_refresh(_user=Depends(require_admin)):
    """Trigger a feed refresh (30-min cooldown to prevent spam)."""
    async with get_connection() as conn:
        return await refresh_feeds(conn)


@public_router.get("")
async def public_news(
    request: Request,
    limit: int = Query(12, ge=1, le=50),
):
    """Public — latest HR news headlines for the marketing pages."""
    await check_rate_limit(client_ip(request), "public_news", 60, 60)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, title, description, link, pub_date,
                   source_name, source_feed_url, image_url
            FROM hr_news_articles
            WHERE link IS NOT NULL AND title IS NOT NULL
            ORDER BY pub_date DESC NULLS LAST, created_at DESC
            LIMIT $1
            """,
            limit,
        )
    items = [
        {
            "id": str(r["id"]),
            "title": r["title"],
            "description": r["description"],
            "link": r["link"],
            "pub_date": r["pub_date"].isoformat() if r["pub_date"] else None,
            "source_name": r["source_name"],
            "source_feed_url": r["source_feed_url"],
            "image_url": r["image_url"],
        }
        for r in rows
    ]
    return {"items": items}
