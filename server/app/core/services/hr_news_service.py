"""HR News aggregation service — fetches articles from HR industry RSS feeds."""

import re
from datetime import datetime, timedelta
from typing import Optional

from .rss_parser import fetch_feed, compute_item_hash


# HR news RSS feeds (free, no API key needed)
HR_NEWS_FEEDS = [
    {"name": "HR Dive", "url": "https://www.hrdive.com/feeds/news/"},
    {"name": "SHRM", "url": "https://www.shrm.org/rss/news.xml"},
    {"name": "HR Morning", "url": "https://www.hrmorning.com/feed/"},
]

# Cooldown between refreshes (minutes)
REFRESH_COOLDOWN_MINUTES = 30

# Track last refresh time in-memory
_last_refresh_at: Optional[datetime] = None


def _extract_image_url(description: str) -> Optional[str]:
    """Try to extract an image URL from RSS description HTML."""
    if not description:
        return None
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description)
    return match.group(1) if match else None


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


async def list_articles(
    conn,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Query cached HR news articles with optional source filter."""
    where = ""
    params = []
    param_idx = 1

    if source:
        where = f"WHERE source_name = ${param_idx}"
        params.append(source)
        param_idx += 1

    # Get total count
    total = await conn.fetchval(
        f"SELECT COUNT(*) FROM hr_news_articles {where}",
        *params,
    )

    # Get articles
    rows = await conn.fetch(
        f"""
        SELECT id, item_hash, title, description, link, author, pub_date,
               source_name, source_feed_url, image_url, created_at
        FROM hr_news_articles
        {where}
        ORDER BY pub_date DESC NULLS LAST, created_at DESC
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """,
        *params, limit, offset,
    )

    # Get distinct sources for filter tabs
    source_rows = await conn.fetch(
        "SELECT DISTINCT source_name FROM hr_news_articles ORDER BY source_name"
    )
    sources = [r["source_name"] for r in source_rows]

    articles = []
    for r in rows:
        articles.append({
            "id": str(r["id"]),
            "title": r["title"],
            "description": r["description"],
            "link": r["link"],
            "author": r["author"],
            "pub_date": r["pub_date"].isoformat() if r["pub_date"] else None,
            "source_name": r["source_name"],
            "image_url": r["image_url"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })

    return {
        "articles": articles,
        "total": total,
        "sources": sources,
        "limit": limit,
        "offset": offset,
    }


async def refresh_feeds(conn) -> dict:
    """Fetch all HR RSS feeds, deduplicate, and insert new articles."""
    global _last_refresh_at

    # Check cooldown
    if _last_refresh_at is not None:
        elapsed = datetime.utcnow() - _last_refresh_at
        if elapsed < timedelta(minutes=REFRESH_COOLDOWN_MINUTES):
            remaining = REFRESH_COOLDOWN_MINUTES - int(elapsed.total_seconds() / 60)
            return {
                "status": "cached",
                "message": f"Feed was recently refreshed. Next refresh available in ~{remaining} min.",
                "new_articles": 0,
            }

    total_new = 0
    feed_results = []

    for feed_info in HR_NEWS_FEEDS:
        feed_name = feed_info["name"]
        feed_url = feed_info["url"]

        try:
            items = await fetch_feed(feed_url)
        except Exception as e:
            print(f"[HR News] Error fetching {feed_name}: {e}")
            feed_results.append({"source": feed_name, "error": str(e), "new": 0})
            continue

        new_count = 0
        for item in items:
            title = item.get("title", "")
            link = item.get("link", "")
            if not title:
                continue

            item_hash = compute_item_hash(title, link)

            # Check if already exists
            exists = await conn.fetchval(
                "SELECT 1 FROM hr_news_articles WHERE item_hash = $1",
                item_hash,
            )
            if exists:
                continue

            description_raw = item.get("description", "")
            image_url = _extract_image_url(description_raw)
            description_clean = _strip_html(description_raw)[:500]

            # Extract author if available
            author = item.get("author", None)

            await conn.execute(
                """
                INSERT INTO hr_news_articles
                    (item_hash, title, description, link, author, pub_date,
                     source_name, source_feed_url, image_url)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (item_hash) DO NOTHING
                """,
                item_hash,
                title,
                description_clean,
                link,
                author,
                item.get("published"),
                feed_name,
                feed_url,
                image_url,
            )
            new_count += 1

        feed_results.append({"source": feed_name, "new": new_count})
        total_new += new_count

    _last_refresh_at = datetime.utcnow()

    return {
        "status": "refreshed",
        "new_articles": total_new,
        "feeds": feed_results,
    }
