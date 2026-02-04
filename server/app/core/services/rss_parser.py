"""RSS feed parsing and relevance detection for legislation monitoring."""

import asyncio
import hashlib
from datetime import datetime
from typing import List, Optional, Tuple
from uuid import UUID

import httpx

try:
    import feedparser
except ImportError:
    feedparser = None

# Keywords for detecting relevance of RSS items to labor law compliance
RELEVANCE_KEYWORDS = {
    "minimum_wage": [
        "minimum wage",
        "wage increase",
        "hourly rate",
        "wage law",
        "pay rate",
        "wage hike",
        "wage floor",
    ],
    "sick_leave": [
        "sick leave",
        "paid leave",
        "family leave",
        "medical leave",
        "paid sick",
        "leave law",
        "leave policy",
    ],
    "overtime": [
        "overtime",
        "exempt",
        "salary threshold",
        "overtime pay",
        "overtime rules",
        "flsa",
        "fair labor",
    ],
    "meal_breaks": [
        "meal break",
        "rest period",
        "lunch break",
        "rest break",
        "break time",
        "meal period",
    ],
    "pay_frequency": [
        "payday",
        "pay period",
        "wage payment",
        "pay frequency",
        "paycheck",
        "direct deposit",
    ],
}


async def fetch_feed(feed_url: str, timeout: float = 30.0) -> List[dict]:
    """
    Fetch and parse an RSS feed.

    Args:
        feed_url: URL of the RSS feed
        timeout: Request timeout in seconds

    Returns:
        List of feed item dicts with keys: title, link, published, description
    """
    if feedparser is None:
        print("[RSS Parser] feedparser not installed, skipping feed fetch")
        return []

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(feed_url, follow_redirects=True)
            response.raise_for_status()
            content = response.text
    except httpx.HTTPError as e:
        print(f"[RSS Parser] HTTP error fetching {feed_url}: {e}")
        return []
    except Exception as e:
        print(f"[RSS Parser] Error fetching {feed_url}: {e}")
        return []

    # Parse the feed content
    feed = feedparser.parse(content)

    if feed.bozo and not feed.entries:
        print(f"[RSS Parser] Feed parse error for {feed_url}: {feed.bozo_exception}")
        return []

    items = []
    for entry in feed.entries:
        # Extract published date
        published = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                published = datetime(*entry.published_parsed[:6])
            except (TypeError, ValueError):
                pass
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            try:
                published = datetime(*entry.updated_parsed[:6])
            except (TypeError, ValueError):
                pass

        items.append(
            {
                "title": getattr(entry, "title", ""),
                "link": getattr(entry, "link", ""),
                "published": published,
                "description": getattr(entry, "summary", getattr(entry, "description", "")),
            }
        )

    return items


def compute_item_hash(title: str, link: str) -> str:
    """
    Compute a stable hash for an RSS item to detect duplicates.

    Args:
        title: Item title
        link: Item link/URL

    Returns:
        64-character hex hash
    """
    content = f"{title}|{link}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def score_relevance(title: str, description: str) -> Tuple[float, Optional[str]]:
    """
    Score the relevance of an RSS item to labor law compliance.

    Args:
        title: Item title
        description: Item description/summary

    Returns:
        Tuple of (relevance_score, detected_category)
        - score ranges from 0.0 to 1.0
        - category is the most relevant category detected, or None
    """
    text = f"{title} {description}".lower()

    best_score = 0.0
    best_category = None

    for category, keywords in RELEVANCE_KEYWORDS.items():
        # Count how many keywords match
        matches = sum(1 for kw in keywords if kw.lower() in text)

        if matches > 0:
            # Score based on number of matching keywords
            # More matches = higher score, capped at 1.0
            score = min(1.0, matches * 0.25)

            # Boost if keyword appears in title (more prominent)
            title_lower = title.lower()
            title_matches = sum(1 for kw in keywords if kw.lower() in title_lower)
            if title_matches > 0:
                score = min(1.0, score + 0.2)

            if score > best_score:
                best_score = score
                best_category = category

    return (best_score, best_category)


async def process_feed(conn, feed_id: UUID) -> dict:
    """
    Process a single RSS feed: fetch items, detect new ones, score relevance.

    Args:
        conn: Database connection
        feed_id: UUID of the feed in rss_feed_sources table

    Returns:
        Dict with processing stats: new_items, high_relevance_count, errors
    """
    # Get feed details
    feed_row = await conn.fetchrow(
        """
        SELECT id, state, feed_url, feed_name, last_item_hash, error_count
        FROM rss_feed_sources
        WHERE id = $1 AND is_active = true
        """,
        feed_id,
    )

    if not feed_row:
        return {"error": "Feed not found or inactive"}

    feed_url = feed_row["feed_url"]
    feed_name = feed_row["feed_name"]
    state = feed_row["state"]

    print(f"[RSS Parser] Processing feed: {feed_name} ({state})")

    # Fetch the feed
    items = await fetch_feed(feed_url)

    if not items:
        # Increment error count
        await conn.execute(
            """
            UPDATE rss_feed_sources
            SET error_count = error_count + 1, last_fetched_at = NOW()
            WHERE id = $1
            """,
            feed_id,
        )
        return {"error": "No items fetched", "new_items": 0}

    # Get existing item hashes for this feed
    existing_hashes = set()
    rows = await conn.fetch(
        "SELECT item_hash FROM rss_feed_items WHERE feed_id = $1",
        feed_id,
    )
    existing_hashes = {r["item_hash"] for r in rows}

    new_items = 0
    high_relevance_count = 0
    first_new_hash = None

    for item in items:
        item_hash = compute_item_hash(item["title"], item["link"])

        if item_hash in existing_hashes:
            continue

        # Score relevance
        relevance_score, detected_category = score_relevance(
            item["title"], item["description"]
        )

        # Insert new item
        await conn.execute(
            """
            INSERT INTO rss_feed_items (
                feed_id, item_hash, title, link, pub_date, description,
                relevance_score, detected_category
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (feed_id, item_hash) DO NOTHING
            """,
            feed_id,
            item_hash,
            item["title"],
            item["link"],
            item["published"],
            item["description"][:2000] if item["description"] else None,
            relevance_score,
            detected_category,
        )

        new_items += 1
        if first_new_hash is None:
            first_new_hash = item_hash

        if relevance_score >= 0.3:  # Threshold for "potentially relevant"
            high_relevance_count += 1

    # Update feed metadata
    await conn.execute(
        """
        UPDATE rss_feed_sources
        SET last_fetched_at = NOW(),
            last_item_hash = COALESCE($2, last_item_hash),
            error_count = 0
        WHERE id = $1
        """,
        feed_id,
        first_new_hash,
    )

    print(
        f"[RSS Parser] Feed {feed_name}: {new_items} new items, {high_relevance_count} high relevance"
    )

    return {
        "new_items": new_items,
        "high_relevance_count": high_relevance_count,
        "state": state,
    }
