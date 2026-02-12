"""HR News routes — admin-only endpoints for browsing HR industry news."""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import require_admin
from ...database import get_connection
from ..services.hr_news_service import list_articles, refresh_feeds

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
