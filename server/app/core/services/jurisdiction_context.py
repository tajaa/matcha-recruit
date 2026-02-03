"""Dynamic jurisdiction context management.

This module handles learning and retrieving authoritative sources for jurisdictions,
enabling better first-attempt accuracy in compliance research by providing Gemini
with known good sources.

Phase 3.2 adds source reputation tracking for confidence score blending.
"""
from typing import Optional, List, Dict
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


# =============================================================================
# Phase 3.2: Source Reputation Tracking
# =============================================================================

async def get_source_accuracy(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domain: str,
) -> float:
    """Get accuracy score for a source domain with Laplace smoothing.

    Returns a value between 0.0 and 1.0 representing historical accuracy.
    Uses Laplace smoothing (add-1) to handle sources with little data.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        domain: Source domain to look up

    Returns:
        Float between 0.0 and 1.0 (0.5 for unknown sources)
    """
    if not domain:
        return 0.5  # Neutral for unknown

    domain = domain.lower().strip()

    row = await conn.fetchrow("""
        SELECT accurate_count, inaccurate_count
        FROM jurisdiction_sources
        WHERE jurisdiction_id = $1 AND domain = $2
    """, jurisdiction_id, domain)

    if not row:
        return 0.5  # Neutral for unknown sources

    accurate = row["accurate_count"] or 0
    inaccurate = row["inaccurate_count"] or 0

    # Laplace smoothing: (accurate + 1) / (total + 2)
    # This prevents 0/0 and provides a reasonable prior
    total = accurate + inaccurate
    return (accurate + 1) / (total + 2)


async def get_source_reputations(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domains: List[str],
) -> Dict[str, float]:
    """Batch lookup of accuracy scores for multiple domains.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        domains: List of source domains to look up

    Returns:
        Dict mapping domain -> accuracy score (0.0-1.0)
    """
    if not domains:
        return {}

    # Normalize domains
    normalized = [d.lower().strip() for d in domains if d]
    if not normalized:
        return {}

    rows = await conn.fetch("""
        SELECT domain, accurate_count, inaccurate_count
        FROM jurisdiction_sources
        WHERE jurisdiction_id = $1 AND domain = ANY($2)
    """, jurisdiction_id, normalized)

    result = {}
    found_domains = set()

    for row in rows:
        domain = row["domain"]
        found_domains.add(domain)
        accurate = row["accurate_count"] or 0
        inaccurate = row["inaccurate_count"] or 0
        total = accurate + inaccurate
        result[domain] = (accurate + 1) / (total + 2)

    # Fill in unknown domains with neutral 0.5
    for domain in normalized:
        if domain not in found_domains:
            result[domain] = 0.5

    return result


async def update_source_accuracy(
    conn: asyncpg.Connection,
    jurisdiction_id,
    domain: str,
    was_accurate: bool,
):
    """Update accuracy counters for a source domain.

    Args:
        conn: Database connection
        jurisdiction_id: UUID of the jurisdiction
        domain: Source domain
        was_accurate: True if the source provided accurate information
    """
    if not domain:
        return

    domain = domain.lower().strip()

    if was_accurate:
        await conn.execute("""
            UPDATE jurisdiction_sources
            SET accurate_count = COALESCE(accurate_count, 0) + 1,
                last_accuracy_update = NOW()
            WHERE jurisdiction_id = $1 AND domain = $2
        """, jurisdiction_id, domain)
    else:
        await conn.execute("""
            UPDATE jurisdiction_sources
            SET inaccurate_count = COALESCE(inaccurate_count, 0) + 1,
                last_accuracy_update = NOW()
            WHERE jurisdiction_id = $1 AND domain = $2
        """, jurisdiction_id, domain)
