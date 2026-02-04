"""
Tier 1 Structured Data Service.

Provides access to compliance data from authoritative structured sources
(CSV, HTML tables) as the highest-trust data layer.

Data Flow:
    Tier 1: Structured Data (CSV/HTML) -> Ground truth, highest confidence
        |
        v (if no data or stale)
    Tier 2: Jurisdiction Repository -> Cached from previous checks
        |
        v (if stale)
    Tier 3: Gemini Research -> Web search fallback
"""

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

import asyncpg

from .parsers import get_parser, ParsedRequirement
from .sources import get_source_for_jurisdiction


class StructuredDataService:
    """Service for managing Tier 1 structured data sources."""

    async def get_tier1_data(
        self,
        conn: asyncpg.Connection,
        jurisdiction_id: UUID,
        city: Optional[str],
        state: str,
        county: Optional[str],
        categories: list[str] | None = None,
        freshness_hours: int = 168,  # 7 days default
    ) -> Optional[list[dict]]:
        """
        Get fresh Tier 1 data for a jurisdiction.

        This is the primary entry point for the compliance service to check
        for authoritative structured data before falling back to Gemini.

        Args:
            conn: Database connection
            jurisdiction_id: UUID of the jurisdiction
            city: City name (if applicable)
            state: 2-letter state code
            county: County name (if applicable)
            categories: List of categories to fetch (default: all)
            freshness_hours: Maximum age of cached data in hours

        Returns:
            List of requirement dicts if fresh data available, None otherwise
        """
        if categories is None:
            categories = ["minimum_wage"]

        # Build jurisdiction key for lookups
        if city:
            level = "city"
            name = city
        elif county:
            level = "county"
            name = county
        else:
            level = "state"
            from .sources import CODE_TO_STATE
            name = CODE_TO_STATE.get(state, state)

        # Normalize to jurisdiction key format
        from .parsers.base import BaseParser
        jurisdiction_key = BaseParser.normalize_jurisdiction_key(name, state, level)

        # Check for cached data within freshness window
        cutoff = datetime.utcnow() - timedelta(hours=freshness_hours)

        results = []
        for category in categories:
            rows = await conn.fetch(
                """
                SELECT
                    c.id,
                    c.jurisdiction_key,
                    c.jurisdiction_name,
                    c.jurisdiction_level,
                    c.state,
                    c.category,
                    c.rate_type,
                    c.current_value,
                    c.numeric_value,
                    c.effective_date,
                    c.next_scheduled_date,
                    c.next_scheduled_value,
                    c.notes,
                    c.fetched_at,
                    s.source_name,
                    s.source_url,
                    s.id as source_id
                FROM structured_data_cache c
                JOIN structured_data_sources s ON c.source_id = s.id
                WHERE c.state = $1
                  AND c.category = $2
                  AND c.fetched_at >= $3
                  AND s.is_active = true
                  AND (
                      c.jurisdiction_key = $4
                      OR c.jurisdiction_level = 'state'
                  )
                ORDER BY
                    CASE c.jurisdiction_level
                        WHEN 'city' THEN 1
                        WHEN 'county' THEN 2
                        WHEN 'state' THEN 3
                    END
                """,
                state, category, cutoff, jurisdiction_key,
            )

            for row in rows:
                results.append(self._cache_row_to_requirement(row))

        if not results:
            print(f"[Tier 1] No fresh data for {jurisdiction_key} (cutoff: {cutoff})")
            return None

        print(f"[Tier 1] Found {len(results)} fresh requirements for {jurisdiction_key}")
        return results

    async def fetch_source(
        self, conn: asyncpg.Connection, source_id: UUID
    ) -> dict[str, Any]:
        """
        Fetch and parse data from a single source.

        Args:
            conn: Database connection
            source_id: UUID of the source to fetch

        Returns:
            Dict with status and count of records fetched
        """
        # Get source configuration
        source = await conn.fetchrow(
            """
            SELECT id, source_key, source_name, source_url, source_type,
                   domain, categories, coverage_scope, parser_config
            FROM structured_data_sources
            WHERE id = $1 AND is_active = true
            """,
            source_id,
        )

        if not source:
            return {"status": "error", "error": "Source not found or inactive"}

        source_key = source["source_key"]
        source_url = source["source_url"]
        source_type = source["source_type"]
        parser_config = source["parser_config"]

        if isinstance(parser_config, str):
            parser_config = json.loads(parser_config)

        print(f"[Tier 1] Fetching {source_key} from {source_url}")

        try:
            # Get appropriate parser
            parser = get_parser(source_type)

            # Fetch and parse
            requirements = await parser.fetch_and_parse(source_url, parser_config)

            if not requirements:
                await self._update_source_status(
                    conn, source_id, "empty", "No requirements parsed"
                )
                return {"status": "empty", "count": 0, "source": source_key}

            # Upsert to cache
            count = await self._upsert_to_cache(conn, source_id, requirements)

            # Update source status
            await self._update_source_status(conn, source_id, "success", None, count)

            return {"status": "success", "count": count, "source": source_key}

        except Exception as e:
            error_msg = str(e)[:500]
            print(f"[Tier 1] Error fetching {source_key}: {error_msg}")
            await self._update_source_status(conn, source_id, "error", error_msg)
            return {"status": "error", "error": error_msg, "source": source_key}

    async def fetch_all_due_sources(self, conn: asyncpg.Connection) -> dict[str, Any]:
        """
        Fetch all sources that are due for refresh.

        A source is due if:
        - It has never been fetched, OR
        - last_fetched_at + fetch_interval_hours < now

        Args:
            conn: Database connection

        Returns:
            Dict with summary of fetch results
        """
        # Find due sources
        due_sources = await conn.fetch(
            """
            SELECT id, source_key, fetch_interval_hours
            FROM structured_data_sources
            WHERE is_active = true
              AND (
                  last_fetched_at IS NULL
                  OR last_fetched_at + (fetch_interval_hours || ' hours')::interval < NOW()
              )
            ORDER BY
                CASE WHEN last_fetched_at IS NULL THEN 0 ELSE 1 END,
                last_fetched_at
            """,
        )

        if not due_sources:
            print("[Tier 1] No sources due for refresh")
            return {"status": "no_sources_due", "fetched": 0}

        print(f"[Tier 1] {len(due_sources)} sources due for refresh")

        results = {
            "status": "completed",
            "fetched": 0,
            "errors": 0,
            "details": [],
        }

        for source in due_sources:
            result = await self.fetch_source(conn, source["id"])
            results["details"].append(result)

            if result.get("status") == "success":
                results["fetched"] += result.get("count", 0)
            elif result.get("status") == "error":
                results["errors"] += 1

        return results

    async def _upsert_to_cache(
        self,
        conn: asyncpg.Connection,
        source_id: UUID,
        requirements: list[ParsedRequirement],
    ) -> int:
        """
        Upsert parsed requirements to the cache table.

        Args:
            conn: Database connection
            source_id: UUID of the source
            requirements: List of parsed requirements

        Returns:
            Number of records upserted
        """
        now = datetime.utcnow()
        count = 0

        for req in requirements:
            try:
                await conn.execute(
                    """
                    INSERT INTO structured_data_cache (
                        source_id, jurisdiction_key, category, rate_type,
                        jurisdiction_level, jurisdiction_name, state,
                        raw_data, current_value, numeric_value,
                        effective_date, next_scheduled_date, next_scheduled_value,
                        notes, fetched_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (source_id, jurisdiction_key, category, rate_type)
                    DO UPDATE SET
                        jurisdiction_name = EXCLUDED.jurisdiction_name,
                        raw_data = EXCLUDED.raw_data,
                        current_value = EXCLUDED.current_value,
                        numeric_value = EXCLUDED.numeric_value,
                        effective_date = EXCLUDED.effective_date,
                        next_scheduled_date = EXCLUDED.next_scheduled_date,
                        next_scheduled_value = EXCLUDED.next_scheduled_value,
                        notes = EXCLUDED.notes,
                        fetched_at = EXCLUDED.fetched_at
                    """,
                    source_id,
                    req.jurisdiction_key,
                    req.category,
                    req.rate_type,
                    req.jurisdiction_level,
                    req.jurisdiction_name,
                    req.state,
                    json.dumps(req.raw_data),
                    req.current_value,
                    req.numeric_value,
                    req.effective_date,
                    req.next_scheduled_date,
                    req.next_scheduled_value,
                    req.notes,
                    now,
                )
                count += 1
            except Exception as e:
                print(f"[Tier 1] Error upserting {req.jurisdiction_key}: {e}")

        return count

    async def _update_source_status(
        self,
        conn: asyncpg.Connection,
        source_id: UUID,
        status: str,
        error: Optional[str],
        record_count: int = 0,
    ) -> None:
        """Update source fetch status."""
        await conn.execute(
            """
            UPDATE structured_data_sources
            SET last_fetched_at = NOW(),
                last_fetch_status = $2,
                last_fetch_error = $3,
                record_count = $4
            WHERE id = $1
            """,
            source_id, status, error, record_count,
        )

    @staticmethod
    def _cache_row_to_requirement(row: asyncpg.Record) -> dict:
        """Convert a cache row to a requirement dict for compliance service."""
        return {
            "title": f"{row['category'].replace('_', ' ').title()} - {row['jurisdiction_name']}",
            "category": row["category"],
            "jurisdiction_level": row["jurisdiction_level"],
            "jurisdiction_name": row["jurisdiction_name"],
            "current_value": row["current_value"],
            "numeric_value": float(row["numeric_value"]) if row["numeric_value"] else None,
            "effective_date": row["effective_date"].isoformat() if row["effective_date"] else None,
            "description": _build_description(row),
            "source_url": row["source_url"],
            "source_name": row["source_name"],
            "rate_type": row["rate_type"],
            # Tier 1 marker for tracking
            "_source_tier": 1,
            "_structured_source_id": str(row["source_id"]),
        }


def _build_description(row: asyncpg.Record) -> str:
    """Build a human-readable description from cache row."""
    parts = []

    if row["current_value"]:
        parts.append(f"Current rate: {row['current_value']}")

    if row["effective_date"]:
        parts.append(f"Effective: {row['effective_date'].strftime('%B %d, %Y')}")

    if row["next_scheduled_value"] and row["next_scheduled_date"]:
        parts.append(
            f"Scheduled change: {row['next_scheduled_value']} "
            f"on {row['next_scheduled_date'].strftime('%B %d, %Y')}"
        )

    if row["notes"]:
        parts.append(f"Note: {row['notes']}")

    return " | ".join(parts) if parts else "No additional details available."
