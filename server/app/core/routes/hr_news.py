"""HR News routes — admin-only endpoints for browsing HR industry news."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ..dependencies import require_admin
from ...database import get_connection
from ..services.hr_news_service import list_articles, refresh_feeds, fetch_full_article
from ...config import get_settings

router = APIRouter()


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


@router.get("/articles/{article_id}/full-content")
async def get_full_content(
    article_id: UUID,
    _user=Depends(require_admin),
):
    """Fetch full article content via Jina Reader API (lazy-loaded, cached)."""
    settings = get_settings()
    async with get_connection() as conn:
        result = await fetch_full_article(conn, article_id, jina_api_key=settings.jina_api_key)
        if "error" in result and result.get("content") is None and "id" not in result:
            raise HTTPException(status_code=404, detail=result["error"])
        return result
