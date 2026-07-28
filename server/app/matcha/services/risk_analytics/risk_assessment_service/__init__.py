"""Risk Assessment Service.

Computes a live risk score across 5 dimensions for a company:
- Compliance (30%)
- Incidents (25%)
- ER Cases (25%)
- Workforce (15%)
- Legislative (5%)

Facade package (refactor round 2, stage 6) over a 1,439-line flat module.
Everything is re-exported here, so the 7 callers (the route, the Celery task,
employees/_shared, monte_carlo_service, and the tests) are unchanged.

Flat, not the nested `dimensions/{compliance,incident,er,workforce,legislative}.py`
the plan sketched: the five dimension functions total ~490 lines, so five files
averaging 98 lines each would be more navigation than the split saves. They
share `_shared.DimensionResult` and read as one family.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.database import get_connection

from ._config import (  # noqa: F401
    COMPLIANCE_CRITICAL_ALERT_POINTS,
    COMPLIANCE_CRITICAL_ALERT_CAP,
    COMPLIANCE_WARNING_ALERT_POINTS,
    COMPLIANCE_WARNING_ALERT_CAP,
    COMPLIANCE_WAGE_VIOLATION_POINTS,
    COMPLIANCE_WAGE_VIOLATION_CAP,
    COMPLIANCE_WAGE_LOCATION_POINTS,
    COMPLIANCE_WAGE_LOCATION_CAP,
    ER_PENDING_POINTS,
    ER_PENDING_CAP,
    ER_IN_REVIEW_POINTS,
    ER_IN_REVIEW_CAP,
    ER_OPEN_POINTS,
    ER_OPEN_CAP,
    ER_MAJOR_POLICY_POINTS,
    ER_HIGH_DISCREPANCY_POINTS,
    _UNSOURCED_REASONS,
    FALLBACK_MODELS,
    DEFAULT_WEIGHTS,
    _WEIGHT_KEYS,
)
from ._shared import (  # noqa: F401
    _stamp_sourcing,
    _exempt_threshold_sentence,
    _band,
    DimensionResult,
    RiskAssessmentResult,
)
from .cost_of_risk import (  # noqa: F401
    compute_compliance_cost_of_risk,
    compute_er_cost_of_risk,
    compute_incident_cost_of_risk,
)
from .dimensions import (  # noqa: F401
    _collect_minimum_wage_violation_metrics,
    compute_compliance_dimension,
    compute_incident_dimension,
    compute_er_dimension,
    compute_workforce_dimension,
    compute_legislative_dimension,
)
from .recommendations import (  # noqa: F401
    RISK_RECOMMENDATION_PROMPT,
    _parse_json_response,
    generate_recommendations,
)

logger = logging.getLogger(__name__)


# Byte-identical to services/_shared/gemini.is_model_unavailable_error.
# Aliased rather than redefined; the old private name stays exported for
# anything importing it from this module.
from app.matcha.services._shared.gemini import (  # noqa: F401
    is_model_unavailable_error as _is_model_unavailable_error,
)


async def load_risk_weights(conn) -> dict[str, float]:
    """Load admin-configured dimension weights overlaid on DEFAULT_WEIGHTS.

    Single source of truth for every snapshot writer (route, Celery task,
    and the wage-change background refresh) so they can't drift apart.
    """
    row = await conn.fetchval(
        "SELECT value FROM platform_settings WHERE key = 'risk_assessment_weights'"
    )
    if row:
        raw = json.loads(row) if isinstance(row, str) else row
        if isinstance(raw, dict):
            return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in raw.items() if k in _WEIGHT_KEYS}}
    return dict(DEFAULT_WEIGHTS)


async def write_risk_history(
    conn,
    company_id: UUID,
    *,
    overall_score,
    overall_band,
    dims_json: str,
    weights_json: str,
    computed_at,
    source: str,
) -> None:
    """Append one row to risk_assessment_history — the trend/anomaly/correlation feed.

    Single writer shared by the manual route, the scheduled Celery task, and the
    wage-change background refresh, differing only by ``source``
    ('manual'/'scheduled'/'auto') so the three can't drift on columns.
    """
    await conn.execute(
        """
        INSERT INTO risk_assessment_history
            (company_id, overall_score, overall_band, dimensions, weights, computed_at, source)
        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7)
        """,
        company_id,
        overall_score,
        overall_band,
        dims_json,
        weights_json,
        computed_at,
        source,
    )


async def compute_risk_assessment(
    company_id: UUID,
    weights: Optional[dict[str, float]] = None,
) -> RiskAssessmentResult:
    """Compute full risk assessment for a company across all 5 dimensions."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}

    async with get_connection() as conn:
        compliance = await compute_compliance_dimension(company_id, conn)
        incidents = await compute_incident_dimension(company_id, conn)
        er = await compute_er_dimension(company_id, conn)
        workforce = await compute_workforce_dimension(company_id, conn)
        legislative = await compute_legislative_dimension(company_id, conn)

    overall = int(
        compliance.score * w["compliance"]
        + incidents.score * w["incidents"]
        + er.score * w["er_cases"]
        + workforce.score * w["workforce"]
        + legislative.score * w["legislative"]
    )
    overall = min(overall, 100)

    return RiskAssessmentResult(
        overall_score=overall,
        overall_band=_band(overall),
        dimensions={
            "compliance": compliance,
            "incidents": incidents,
            "er_cases": er,
            "workforce": workforce,
            "legislative": legislative,
        },
        computed_at=datetime.now(timezone.utc),
    )

