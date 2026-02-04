"""Cross-jurisdiction pattern detection for coordinated compliance changes."""

from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

# Known patterns of coordinated legislative changes
KNOWN_PATTERNS = [
    {
        "pattern_key": "jan_1_wage_update",
        "display_name": "January 1st Minimum Wage Update",
        "category": "minimum_wage",
        "trigger_month": 1,
        "trigger_day": 1,
        "lookback_days": 60,  # Check 60 days before/after Jan 1
        "min_jurisdictions": 3,
        "description": "Many states update minimum wage on January 1st",
    },
    {
        "pattern_key": "july_1_fiscal_year",
        "display_name": "July 1st Fiscal Year Updates",
        "category": None,  # Any category
        "trigger_month": 7,
        "trigger_day": 1,
        "lookback_days": 30,
        "min_jurisdictions": 2,
        "description": "Some states align wage/benefit changes with fiscal year",
    },
    {
        "pattern_key": "jan_1_sick_leave",
        "display_name": "January 1st Sick Leave Update",
        "category": "sick_leave",
        "trigger_month": 1,
        "trigger_day": 1,
        "lookback_days": 45,
        "min_jurisdictions": 2,
        "description": "Paid sick leave requirements often update at year start",
    },
]


async def detect_patterns(conn, lookback_days: int = 60) -> List[dict]:
    """
    Detect patterns of coordinated changes across jurisdictions.

    Looks at recent changes in jurisdiction_requirements to identify
    patterns where multiple jurisdictions updated the same category
    around the same time.

    Args:
        conn: Database connection
        lookback_days: How far back to look for changes

    Returns:
        List of detected patterns with matched jurisdictions
    """
    detected = []
    today = date.today()
    current_year = today.year

    for pattern in KNOWN_PATTERNS:
        # Calculate the target date for this year
        target_date = date(
            current_year, pattern["trigger_month"], pattern["trigger_day"]
        )

        # If target date is in the future, check last year's pattern
        if target_date > today:
            target_date = date(
                current_year - 1, pattern["trigger_month"], pattern["trigger_day"]
            )
            detection_year = current_year - 1
        else:
            detection_year = current_year

        # Define the window around the target date
        window_start = target_date - timedelta(days=pattern["lookback_days"])
        window_end = target_date + timedelta(days=pattern["lookback_days"])

        # Skip if window hasn't started yet
        if window_start > today:
            continue

        # Query for jurisdictions with changes in this window
        category_filter = ""
        params = [window_start, window_end]
        if pattern["category"]:
            category_filter = "AND category = $3"
            params.append(pattern["category"])

        query = f"""
            SELECT DISTINCT
                j.id AS jurisdiction_id,
                j.state,
                j.city,
                jr.category,
                jr.effective_date,
                jr.current_value,
                jr.last_verified_at
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON jr.jurisdiction_id = j.id
            WHERE jr.effective_date BETWEEN $1 AND $2
            {category_filter}
            ORDER BY j.state, jr.effective_date
        """

        rows = await conn.fetch(query, *params)

        if len(rows) >= pattern["min_jurisdictions"]:
            # Pattern detected!
            matched_jurisdictions = []
            for r in rows:
                matched_jurisdictions.append(
                    {
                        "jurisdiction_id": str(r["jurisdiction_id"]),
                        "state": r["state"],
                        "city": r["city"],
                        "category": r["category"],
                        "effective_date": r["effective_date"].isoformat()
                        if r["effective_date"]
                        else None,
                        "current_value": r["current_value"],
                    }
                )

            detected.append(
                {
                    "pattern_key": pattern["pattern_key"],
                    "display_name": pattern["display_name"],
                    "category": pattern["category"],
                    "target_date": target_date.isoformat(),
                    "detection_year": detection_year,
                    "jurisdictions_matched": matched_jurisdictions,
                    "count": len(matched_jurisdictions),
                }
            )

    return detected


async def flag_stale_jurisdictions(
    conn, pattern: dict, recent_changes: List[dict]
) -> List[dict]:
    """
    Find jurisdictions that might need review based on a detected pattern.

    If multiple states updated minimum wage on Jan 1, flag other states
    that haven't been verified recently.

    Args:
        conn: Database connection
        pattern: Detected pattern dict
        recent_changes: List of jurisdictions that had recent changes

    Returns:
        List of jurisdictions that may need review
    """
    # Get states that were part of the pattern
    changed_states = {j["state"] for j in recent_changes}

    # Find jurisdictions in other states that haven't been verified recently
    # and have requirements in the same category
    category = pattern.get("category")

    category_filter = ""
    params = []
    if category:
        category_filter = "WHERE jr.category = $1"
        params.append(category)

    query = f"""
        SELECT DISTINCT
            j.id AS jurisdiction_id,
            j.state,
            j.city,
            j.last_verified_at,
            jr.category,
            jr.current_value,
            jr.effective_date
        FROM jurisdictions j
        JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
        {category_filter}
        {"AND" if category_filter else "WHERE"} j.state NOT IN (
            SELECT UNNEST(${"2" if category else "1"}::text[])
        )
        AND (
            j.last_verified_at IS NULL
            OR j.last_verified_at < NOW() - INTERVAL '30 days'
        )
        ORDER BY j.last_verified_at NULLS FIRST
        LIMIT 20
    """

    if category:
        rows = await conn.fetch(query, category, list(changed_states))
    else:
        rows = await conn.fetch(query, list(changed_states))

    flagged = []
    for r in rows:
        flagged.append(
            {
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "state": r["state"],
                "city": r["city"],
                "category": r["category"],
                "current_value": r["current_value"],
                "last_verified_at": r["last_verified_at"].isoformat()
                if r["last_verified_at"]
                else None,
                "reason": f"Pattern '{pattern['display_name']}' detected; this jurisdiction may need review",
            }
        )

    return flagged


async def create_review_alerts(conn, pattern_detection: dict) -> int:
    """
    Create 'review_recommended' alerts for flagged jurisdictions.

    Args:
        conn: Database connection
        pattern_detection: Dict with pattern info and flagged jurisdictions

    Returns:
        Number of alerts created
    """
    flagged = pattern_detection.get("jurisdictions_flagged", [])
    if not flagged:
        return 0

    alerts_created = 0

    for jurisdiction in flagged:
        jid = jurisdiction["jurisdiction_id"]

        # Find all business locations in this jurisdiction's city/state
        locations = await conn.fetch(
            """
            SELECT DISTINCT bl.id AS location_id, bl.company_id
            FROM business_locations bl
            JOIN jurisdictions j ON j.city = bl.city AND j.state = bl.state
            WHERE j.id = $1
              AND bl.is_active = true
            """,
            UUID(jid),
        )

        if not locations:
            continue

        pattern_key = pattern_detection.get("pattern_key", "unknown")
        category = jurisdiction.get("category") or pattern_detection.get("category")

        for loc in locations:
            # Check for existing review alert for this pattern + location
            existing = await conn.fetchval(
                """
                SELECT id FROM compliance_alerts
                WHERE location_id = $1
                  AND alert_type = 'review_recommended'
                  AND metadata->>'pattern_key' = $2
                  AND created_at > NOW() - INTERVAL '30 days'
                """,
                loc["location_id"],
                pattern_key,
            )

            if existing:
                continue

            # Create review alert
            await conn.execute(
                """
                INSERT INTO compliance_alerts (
                    location_id, company_id, title, message, severity, category,
                    alert_type, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                loc["location_id"],
                loc["company_id"],
                f"Review Recommended: {pattern_detection.get('display_name', 'Compliance Pattern Detected')}",
                jurisdiction.get("reason", "This jurisdiction may have compliance updates that need review."),
                "info",
                category,
                "review_recommended",
                {
                    "pattern_key": pattern_key,
                    "pattern_display_name": pattern_detection.get("display_name"),
                    "detection_year": pattern_detection.get("detection_year"),
                    "jurisdictions_matched_count": pattern_detection.get("count", 0),
                    "source": "pattern_recognition",
                },
            )
            alerts_created += 1

    return alerts_created


def _get_known_pattern_config(pattern_key: str) -> Optional[dict]:
    """Look up pattern config from KNOWN_PATTERNS by key."""
    for p in KNOWN_PATTERNS:
        if p["pattern_key"] == pattern_key:
            return p
    return None


async def record_pattern_detection(conn, pattern: dict) -> UUID:
    """
    Record a pattern detection in the pattern_detections table.

    Args:
        conn: Database connection
        pattern: Detected pattern dict

    Returns:
        UUID of the created detection record
    """
    # Get or create the legislative pattern record
    pattern_row = await conn.fetchrow(
        """
        SELECT id FROM legislative_patterns WHERE pattern_key = $1
        """,
        pattern["pattern_key"],
    )

    if not pattern_row:
        # Pattern not in DB yet, create it using the correct config
        known_config = _get_known_pattern_config(pattern["pattern_key"])
        if known_config is None:
            # Fallback for unknown patterns - use values from the detected pattern
            known_config = {
                "trigger_month": 1,
                "trigger_day": 1,
                "lookback_days": 30,
                "min_jurisdictions": 3,
            }

        pattern_row = await conn.fetchrow(
            """
            INSERT INTO legislative_patterns (
                pattern_key, display_name, category, trigger_month, trigger_day,
                lookback_days, min_jurisdictions
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id
            """,
            pattern["pattern_key"],
            pattern["display_name"],
            pattern.get("category"),
            known_config["trigger_month"],
            known_config["trigger_day"],
            known_config["lookback_days"],
            known_config["min_jurisdictions"],
        )

    pattern_id = pattern_row["id"]
    detection_year = pattern["detection_year"]

    # Upsert pattern detection
    result = await conn.fetchrow(
        """
        INSERT INTO pattern_detections (
            pattern_id, detection_year, jurisdictions_matched
        ) VALUES ($1, $2, $3)
        ON CONFLICT (pattern_id, detection_year) DO UPDATE
        SET jurisdictions_matched = $3, detection_date = NOW()
        RETURNING id
        """,
        pattern_id,
        detection_year,
        pattern["jurisdictions_matched"],
    )

    return result["id"]


async def run_pattern_recognition_cycle(conn) -> dict:
    """
    Run one cycle of pattern recognition.

    1. Detect patterns in recent jurisdiction requirement changes
    2. Flag stale jurisdictions that may need review
    3. Create review_recommended alerts

    Args:
        conn: Database connection

    Returns:
        Dict with cycle stats
    """
    print("[Pattern Recognition] Starting cycle...")

    # Detect patterns
    detected_patterns = await detect_patterns(conn)
    print(f"[Pattern Recognition] Detected {len(detected_patterns)} patterns")

    total_alerts = 0
    patterns_processed = []

    for pattern in detected_patterns:
        # Record the detection
        detection_id = await record_pattern_detection(conn, pattern)

        # Flag jurisdictions that may need review
        flagged = await flag_stale_jurisdictions(
            conn, pattern, pattern["jurisdictions_matched"]
        )

        pattern["jurisdictions_flagged"] = flagged
        pattern["detection_id"] = str(detection_id)

        # Create review alerts
        alerts = await create_review_alerts(conn, pattern)
        total_alerts += alerts

        # Update detection record with flagged jurisdictions and alert count
        await conn.execute(
            """
            UPDATE pattern_detections
            SET jurisdictions_flagged = $1, alerts_created = $2
            WHERE id = $3
            """,
            flagged,
            alerts,
            detection_id,
        )

        patterns_processed.append(
            {
                "pattern_key": pattern["pattern_key"],
                "matched_count": pattern["count"],
                "flagged_count": len(flagged),
                "alerts_created": alerts,
            }
        )

    result = {
        "patterns_detected": len(detected_patterns),
        "total_alerts_created": total_alerts,
        "patterns": patterns_processed,
    }

    print(f"[Pattern Recognition] Cycle complete: {result}")
    return result
