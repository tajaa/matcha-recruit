"""Legislation watch agent - RSS monitoring + selective Gemini analysis."""

import asyncio
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from .rss_parser import process_feed

# Relevance threshold for triggering Gemini analysis
RELEVANCE_THRESHOLD = 0.3


async def get_active_feeds(conn) -> List[dict]:
    """
    Get all active RSS feed sources.

    Args:
        conn: Database connection

    Returns:
        List of feed dicts with id, state, feed_url, feed_name, feed_type
    """
    rows = await conn.fetch(
        """
        SELECT id, state, feed_url, feed_name, feed_type, categories
        FROM rss_feed_sources
        WHERE is_active = true
        ORDER BY state, feed_name
        """
    )
    return [dict(r) for r in rows]


async def analyze_feed_item_with_gemini(
    item: dict, state: str
) -> Optional[dict]:
    """
    Use Gemini to analyze a high-relevance RSS item for legislation impact.

    Args:
        item: Dict with title, link, description, detected_category
        state: State code (e.g., "CA")

    Returns:
        Dict with analysis results, or None if analysis fails/not relevant
    """
    from .gemini_compliance import get_gemini_compliance_service

    gemini = get_gemini_compliance_service()

    if not gemini._has_api_key():
        print("[Legislation Watch] No Gemini API key configured")
        return None

    # Build a targeted prompt for RSS item analysis
    prompt = f"""Analyze this news item from {state} Department of Labor / Legislature RSS feed:

Title: {item.get('title', 'N/A')}
Link: {item.get('link', 'N/A')}
Description: {item.get('description', 'N/A')[:1000]}

Determine if this represents an actual legislative change or upcoming change to employment law.

Focus on these categories:
- minimum_wage: Changes to minimum wage rates
- sick_leave: Changes to paid sick leave requirements
- overtime: Changes to overtime rules or salary thresholds
- meal_breaks: Changes to meal/rest break requirements
- pay_frequency: Changes to pay period requirements

Respond with JSON:
{{
  "is_relevant": true/false,
  "category": "minimum_wage" | "sick_leave" | "overtime" | "meal_breaks" | "pay_frequency" | null,
  "change_type": "enacted" | "proposed" | "effective_soon" | "informational" | null,
  "summary": "Brief summary of the change (1-2 sentences)",
  "effective_date": "YYYY-MM-DD" or null,
  "value_change": "Description of specific value change if applicable" or null,
  "confidence": 0.0 to 1.0,
  "action_required": "Brief description of what employers should do" or null
}}

If this is just a press release, general news, or not directly about employment law changes, set is_relevant to false.
Be conservative - only mark as relevant if there's a clear legislative change.
"""

    try:
        from google import genai
        from google.genai import types

        tools = [types.Tool(google_search=types.GoogleSearch())]

        response = await asyncio.wait_for(
            gemini.client.aio.models.generate_content(
                model=gemini.settings.analysis_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    tools=tools,
                    response_modalities=["TEXT"],
                ),
            ),
            timeout=45,
        )

        raw_text = response.text.strip()

        # Clean JSON
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]

        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start != -1 and end != -1:
            raw_text = raw_text[start : end + 1]

        data = json.loads(raw_text)
        return data

    except asyncio.TimeoutError:
        print(f"[Legislation Watch] Gemini timeout analyzing: {item.get('title', '?')[:50]}")
        return None
    except json.JSONDecodeError as e:
        print(f"[Legislation Watch] Gemini JSON error: {e}")
        return None
    except Exception as e:
        print(f"[Legislation Watch] Gemini error: {e}")
        return None


async def create_proactive_alerts(
    conn, legislation: dict, jurisdiction_id: UUID, feed_item_id: UUID
) -> int:
    """
    Create compliance alerts for detected legislation changes.

    Args:
        conn: Database connection
        legislation: Analysis result from Gemini
        jurisdiction_id: UUID of the jurisdiction
        feed_item_id: UUID of the RSS feed item

    Returns:
        Number of alerts created
    """
    if not legislation.get("is_relevant"):
        return 0

    # Get all business locations in this jurisdiction's state
    jurisdiction = await conn.fetchrow(
        "SELECT city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )

    if not jurisdiction:
        return 0

    # Find locations in this state (proactive alerts go to state-level)
    locations = await conn.fetch(
        """
        SELECT DISTINCT bl.id AS location_id, bl.company_id
        FROM business_locations bl
        WHERE bl.state = $1
          AND bl.is_active = true
        """,
        jurisdiction["state"],
    )

    if not locations:
        return 0

    alerts_created = 0
    category = legislation.get("category")
    change_type = legislation.get("change_type", "informational")

    # Determine severity based on change type
    severity = "info"
    if change_type == "enacted" or change_type == "effective_soon":
        severity = "warning"

    for loc in locations:
        # Check if we already have an alert for this feed item + location
        existing = await conn.fetchval(
            """
            SELECT id FROM compliance_alerts
            WHERE location_id = $1
              AND metadata->>'rss_feed_item_id' = $2
            """,
            loc["location_id"],
            str(feed_item_id),
        )

        if existing:
            continue

        # Create the proactive alert
        # Safely get summary (handle None/non-string from LLM JSON)
        summary = legislation.get("summary")
        if not isinstance(summary, str) or not summary:
            summary = "New legislation detected"
        action_required = legislation.get("action_required")
        if not isinstance(action_required, str) or not action_required:
            action_required = summary if summary else "Review pending legislation"

        await conn.execute(
            """
            INSERT INTO compliance_alerts (
                location_id, company_id, title, message, severity, category,
                alert_type, confidence_score, effective_date, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            loc["location_id"],
            loc["company_id"],
            f"[{change_type.upper()}] {summary[:200]}",
            action_required,
            severity,
            category,
            "proactive",  # New alert type for RSS-detected changes
            legislation.get("confidence"),
            legislation.get("effective_date"),
            {
                "rss_feed_item_id": str(feed_item_id),
                "change_type": change_type,
                "value_change": legislation.get("value_change"),
                "source": "legislation_watch",
            },
        )
        alerts_created += 1

    return alerts_created


async def run_legislation_watch_cycle(conn) -> dict:
    """
    Run one cycle of the legislation watch agent.

    1. Fetch all active RSS feeds
    2. Process each feed to detect new items
    3. For high-relevance items, call Gemini for detailed analysis
    4. Create proactive alerts for detected legislation changes

    Args:
        conn: Database connection

    Returns:
        Dict with cycle stats
    """
    print("[Legislation Watch] Starting watch cycle...")

    feeds = await get_active_feeds(conn)
    print(f"[Legislation Watch] Found {len(feeds)} active feeds")

    total_new_items = 0
    total_gemini_calls = 0
    total_alerts_created = 0
    errors = []

    for feed in feeds:
        try:
            # Process the feed to get new items
            result = await process_feed(conn, feed["id"])

            if "error" in result:
                errors.append(f"{feed['feed_name']}: {result['error']}")
                continue

            total_new_items += result.get("new_items", 0)

            # Get high-relevance unprocessed items from this feed
            high_relevance_items = await conn.fetch(
                """
                SELECT id, title, link, description, detected_category, relevance_score
                FROM rss_feed_items
                WHERE feed_id = $1
                  AND processed = false
                  AND relevance_score >= $2
                ORDER BY relevance_score DESC
                LIMIT 5
                """,
                feed["id"],
                RELEVANCE_THRESHOLD,
            )

            for item in high_relevance_items:
                # Mark as processed before calling Gemini
                await conn.execute(
                    "UPDATE rss_feed_items SET processed = true WHERE id = $1",
                    item["id"],
                )

                # Analyze with Gemini
                analysis = await analyze_feed_item_with_gemini(
                    dict(item), feed["state"]
                )

                if analysis:
                    total_gemini_calls += 1

                    # Mark that Gemini was triggered
                    await conn.execute(
                        "UPDATE rss_feed_items SET gemini_triggered = true WHERE id = $1",
                        item["id"],
                    )

                    # Find or create jurisdiction for this state
                    # Note: RSS feeds are state-level, so we use state capital as representative
                    jurisdiction = await conn.fetchrow(
                        """
                        SELECT id FROM jurisdictions
                        WHERE state = $1
                        LIMIT 1
                        """,
                        feed["state"],
                    )

                    if jurisdiction and analysis.get("is_relevant"):
                        alerts = await create_proactive_alerts(
                            conn, analysis, jurisdiction["id"], item["id"]
                        )
                        total_alerts_created += alerts

        except Exception as e:
            errors.append(f"{feed['feed_name']}: {str(e)}")
            print(f"[Legislation Watch] Error processing {feed['feed_name']}: {e}")

    # Mark all remaining unprocessed low-relevance items as processed
    await conn.execute(
        """
        UPDATE rss_feed_items
        SET processed = true
        WHERE processed = false AND relevance_score < $1
        """,
        RELEVANCE_THRESHOLD,
    )

    result = {
        "feeds_processed": len(feeds),
        "new_items": total_new_items,
        "gemini_calls": total_gemini_calls,
        "alerts_created": total_alerts_created,
        "errors": errors,
    }

    print(f"[Legislation Watch] Cycle complete: {result}")
    return result
