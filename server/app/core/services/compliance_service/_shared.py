"""compliance_service.shared — J6 split of compliance_service.py."""
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable, Tuple
from uuid import UUID
from datetime import date, datetime, timedelta
import asyncio
import json
import logging
import re

import asyncpg
import httpx
from fastapi import HTTPException

from app.core.services.scope_registry.codify import codified_sql
from app.core.services.company_contacts import get_company_name_and_contacts
from app.core.services.jurisdiction_context import (
    get_known_sources,
    record_source,
    extract_domain,
    build_context_prompt,
    get_source_reputations,
    update_source_accuracy,
)
from app.core.models.compliance import (
    BusinessLocation,
    ComplianceRequirement,
    ComplianceAlert,
    LocationCreate,
    LocationUpdate,
    AutoCheckSettings,
    RequirementResponse,
    AlertResponse,
    CheckLogEntry,
    UpcomingLegislationResponse,
    VerificationResult,
    ComplianceSummary,
)
from app.core.compliance_registry import (
    LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES,
    HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    INDUSTRY_TAGS as MEDICAL_COMPLIANCE_INDUSTRY_TAGS,
)

logger = logging.getLogger(__name__)




def parse_date(date_str: Optional[str]) -> Optional[date]:
    """Parse ISO date string to Python date object."""
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, AttributeError):
        return None




# Library permanence (B5): stored requirements are treated as truth until a
# future diff-scheduler exists to selectively re-check them (see
# COMPLIANCE_REMEDIATION_PLAN.md B5/E6). While settings.repository_ttl_enabled
# is False, _is_jurisdiction_fresh ignores age and reports "fresh" whenever a
# jurisdiction has any data at all; gap-driven research (missing required
# categories) still fires regardless. Config-backed (REPOSITORY_TTL_ENABLED
# env var, config.py) rather than a module constant so it can flip without a
# redeploy.

# Threshold for numeric material changes (e.g. $0.25 for wages)
MATERIAL_CHANGE_THRESHOLDS = {
    "minimum_wage": 0.25,
    "default": 0.10,
}



JURISDICTION_PRIORITY = {
    "city": 1, "county": 2,
    "state": 3, "province": 3, "region": 3,
    "federal": 4, "national": 4,
}



VALID_LEGISLATION_STATUSES = {
    "proposed",
    "passed",
    "signed",
    "effective_soon",
    "effective",
    "dismissed",
}




MAX_VERIFICATIONS_PER_CHECK = 3


HEARTBEAT_INTERVAL = 8




async def _heartbeat_while(task, *, queue=None, interval=HEARTBEAT_INTERVAL):
    """Yield progress events from queue and heartbeat dicts while a task runs."""
    try:
        while not task.done():
            if queue is not None:
                while not queue.empty():
                    yield queue.get_nowait()
            done, _ = await asyncio.wait({task}, timeout=interval)
            if done:
                break
            yield {"type": "heartbeat"}
    except asyncio.CancelledError:
        if not task.done():
            task.cancel()
        raise
    # Final drain
    if queue is not None:
        while not queue.empty():
            yield queue.get_nowait()




def _parse_jsonb_list(value: Any) -> Optional[List[Dict]]:
    """asyncpg hands JSONB back as a str on this pool — the API must not leak
    strings where a list of objects belongs."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return None
    return value if isinstance(value, list) else None




def _as_jsonb(value: Any) -> Optional[str]:
    """Serialize a value for a JSONB column — WITHOUT re-encoding an encoded one.

    asyncpg hands JSONB back as a `str`. So a row that is read out of the catalog
    and written back (which is every research pass: catalog -> dict -> upsert)
    used to hit `json.dumps(already_a_json_string)` and gain another layer of
    escaping. Each pass added one:

        {"type": "entity_type", ...}
        "{\\"type\\": \\"entity_type\\", ...}"
        "\\"{\\\\\\"type\\\\\\": ...}\\""

    trigger_conditions then no longer parses as an object, the evaluator can't
    read it, and the requirement fails OPEN — which is how "SAMHSA Opioid
    Treatment Program Certification" (trigger: entity_type == behavioral_health)
    was served to a dental practice.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str):
        # Already JSON text. Trust it only if it parses; a bare string that isn't
        # JSON is a caller bug we shouldn't silently persist as garbage.
        try:
            json.loads(value)
            return value
        except (TypeError, ValueError):
            return json.dumps(value)
    return json.dumps(value)




def _decode_jsonb(value: Any) -> Any:
    """Read a JSONB value that may have been multi-encoded by the bug above."""
    seen = 0
    while isinstance(value, str) and seen < 5:
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return value
        seen += 1
    return value
