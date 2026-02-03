"""Dynamic jurisdiction context management.

This module handles learning and retrieving authoritative sources for jurisdictions,
enabling better first-attempt accuracy in compliance research by providing Gemini
with known good sources.
"""
from typing import Optional, List
from urllib.parse import urlparse
import asyncpg


async def get_known_sources(conn: asyncpg.Connection, jurisdiction_id) -> List[dict]:
    """Get known authoritative sources for a jurisdiction.

    Returns the top 5 most successful sources, ordered by success count.
    """
    rows = await conn.fetch("""
        SELECT domain, source_name, categories, success_count
        FROM jurisdiction_sources
        WHERE jurisdiction_id = $1
        ORDER BY success_count DESC
        LIMIT 5
    """, jurisdiction_id)
    return [dict(r) for r in rows]


async def record_source(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domain: str,
    source_name: Optional[str],
    category: str,
):
    """Record a source seen in research results.

    Uses upsert to increment success_count for existing sources or insert new ones.
    Categories are accumulated in an array for sources that cover multiple categories.
    """
    if not domain:
        return

    # Normalize domain
    domain = domain.lower().strip()

    await conn.execute("""
        INSERT INTO jurisdiction_sources (jurisdiction_id, domain, source_name, categories, success_count, last_seen_at)
        VALUES ($1, $2, $3, ARRAY[$4], 1, NOW())
        ON CONFLICT (jurisdiction_id, domain) DO UPDATE SET
            source_name = COALESCE(EXCLUDED.source_name, jurisdiction_sources.source_name),
            categories = (
                SELECT array_agg(DISTINCT elem)
                FROM unnest(jurisdiction_sources.categories || ARRAY[$4]) AS elem
            ),
            success_count = jurisdiction_sources.success_count + 1,
            last_seen_at = NOW()
    """, jurisdiction_id, domain, source_name, category)


def extract_domain(url: str) -> str:
    """Extract the domain from a URL.

    Example: "https://dir.ca.gov/dlse/faq_overtime.htm" -> "dir.ca.gov"
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]
        # Remove www. prefix if present
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


def build_context_prompt(known_sources: List[dict]) -> str:
    """Build prompt section from known sources.

    Returns an empty string if no sources are known, or a formatted
    section listing known authoritative sources for the jurisdiction.
    """
    if not known_sources:
        return ""

    lines = ["\nKNOWN AUTHORITATIVE SOURCES (prefer these when available):"]
    for s in known_sources:
        source_name = s.get('source_name', 'unknown')
        domain = s.get('domain', '')
        categories = s.get('categories', [])
        cat_str = ", ".join(categories) if categories else "general"
        lines.append(f"- {domain} ({source_name}) - covers: {cat_str}")

    return "\n".join(lines)
