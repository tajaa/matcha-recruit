"""Policy Suggestion Service.

Scans ER case policy_check and IR incident policy_mapping analyses to identify
policy gaps — topics referenced in cases/incidents but not covered by the
company's active policies or handbook.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


@dataclass
class PolicyGap:
    topic: str
    frequency: int = 0
    max_severity: str = "low"
    source_cases: list[dict] = field(default_factory=list)
    existing_match: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize_topic(topic: str) -> str:
    """Normalize policy topic for dedup."""
    return topic.strip().lower().replace("_", " ").replace("-", " ")


def _best_severity(a: str, b: str) -> str:
    return a if SEVERITY_RANK.get(a, 0) >= SEVERITY_RANK.get(b, 0) else b


async def get_policy_gaps(company_id: UUID) -> list[dict]:
    """Aggregate policy gaps from ER and IR analyses for a company."""
    async with get_connection() as conn:
        # Get existing active policy titles
        active_policies = await conn.fetch(
            "SELECT title FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        )
        active_titles = {_normalize_topic(r["title"]) for r in active_policies}

        # Get active handbook section titles
        handbook_sections = await conn.fetch(
            """
            SELECT hs.title FROM handbook_sections hs
            JOIN handbooks h ON hs.handbook_id = h.id
            WHERE h.company_id = $1 AND h.status = 'active'
            """,
            company_id,
        )
        active_titles |= {_normalize_topic(r["title"]) for r in handbook_sections}

        # Dismissed suggestions
        dismissed_raw = await conn.fetchval(
            "SELECT policy_suggestions_dismissed FROM companies WHERE id = $1",
            company_id,
        )
        dismissed: set[str] = set()
        if dismissed_raw:
            if isinstance(dismissed_raw, str):
                try:
                    dismissed_raw = json.loads(dismissed_raw)
                except (json.JSONDecodeError, TypeError):
                    dismissed_raw = []
            if isinstance(dismissed_raw, list):
                dismissed = {_normalize_topic(t) for t in dismissed_raw}

        # --- ER case policy_check analyses ---
        er_rows = await conn.fetch(
            """
            SELECT a.analysis_data, c.title AS case_title, c.id AS case_id
            FROM er_case_analysis a
            JOIN er_cases c ON a.case_id = c.id
            WHERE c.company_id = $1 AND a.analysis_type = 'policy_check'
            """,
            company_id,
        )

        gaps: dict[str, PolicyGap] = {}

        for row in er_rows:
            data = row["analysis_data"]
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(data, dict):
                continue

            applicable = data.get("policies_potentially_applicable", [])
            if not isinstance(applicable, list):
                continue

            for topic in applicable:
                if not isinstance(topic, str) or not topic.strip():
                    continue
                norm = _normalize_topic(topic)
                if norm in active_titles or norm in dismissed:
                    continue

                if norm not in gaps:
                    gaps[norm] = PolicyGap(topic=topic.strip())
                gap = gaps[norm]
                gap.frequency += 1
                gap.source_cases.append({
                    "type": "er_case",
                    "id": str(row["case_id"]),
                    "title": row["case_title"],
                })

        # --- IR incident policy_mapping analyses ---
        ir_rows = await conn.fetch(
            """
            SELECT a.analysis_data, i.title AS incident_title, i.id AS incident_id,
                   i.severity
            FROM ir_incident_analysis a
            JOIN ir_incidents i ON a.incident_id = i.id
            WHERE i.company_id = $1 AND a.analysis_type = 'policy_mapping'
            """,
            company_id,
        )

        for row in ir_rows:
            data = row["analysis_data"]
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(data, dict):
                continue

            # Check no_matching_policies flag — if the incident couldn't be mapped
            # to ANY policy, that's a strong signal for a gap
            if data.get("no_matching_policies"):
                topic = f"{row['incident_title'] or 'Incident'} — No Matching Policy"
                norm = _normalize_topic(topic)
                if norm not in active_titles and norm not in dismissed:
                    if norm not in gaps:
                        gaps[norm] = PolicyGap(topic=topic)
                    gap = gaps[norm]
                    gap.frequency += 1
                    gap.max_severity = _best_severity(gap.max_severity, row["severity"] or "low")
                    gap.source_cases.append({
                        "type": "ir_incident",
                        "id": str(row["incident_id"]),
                        "title": row["incident_title"],
                    })

        # Sort by frequency desc, then severity desc
        sorted_gaps = sorted(
            gaps.values(),
            key=lambda g: (g.frequency, SEVERITY_RANK.get(g.max_severity, 0)),
            reverse=True,
        )

        return [g.to_dict() for g in sorted_gaps]


async def dismiss_suggestion(company_id: UUID, topic: str) -> None:
    """Mark a suggestion as dismissed so it doesn't reappear.

    Uses an atomic append to avoid TOCTOU race conditions.
    """
    async with get_connection() as conn:
        topic_json = json.dumps(topic)  # e.g. '"Anti-Retaliation Policy"'
        await conn.execute(
            """
            UPDATE companies
            SET policy_suggestions_dismissed =
                CASE WHEN policy_suggestions_dismissed @> $1::jsonb
                     THEN policy_suggestions_dismissed
                     ELSE COALESCE(policy_suggestions_dismissed, '[]'::jsonb) || $1::jsonb
                END
            WHERE id = $2
            """,
            topic_json,
            company_id,
        )
