"""Scheduling-compliance route glue.

The actual orchestration (`check_shift_compliance` + its I/O helpers) was
lifted to `services/scheduling/shift_compliance.py` on 2026-07-31 so services
outside this route package — `services/scheduling/schedule_chat.py`, the
@huume channel-scheduling flow — can call it without a services→routes
import. Everything below is re-exported under its historical name so every
route module in this package (and every existing test) is unaffected.

  - any BLOCK-severity violation  → 422 (non-overridable, even with force=true)
  - advisories + not force         → 409 (force=true proceeds + audit-logs)

`raise_for_violations` turns a violation list into the right HTTP response —
it's the one piece that's a genuine route concern (HTTPException), so it
stayed here rather than moving with the rest.
"""

from __future__ import annotations

from fastapi import HTTPException

from ...services.scheduling import schedule_compliance
from ...services.scheduling.schedule_rules import compliance_block_detail, compliance_warning_detail
from ...services.scheduling.shift_compliance import (  # noqa: F401 — re-exported for route modules + tests
    _approved_db_rules,
    _DB_RULES_CACHE,
    _DB_RULES_CACHE_TTL,
    _employee_age,
    _fair_workweek_advisories,
    _hours,
    _location_state,
    _min_rest_gap,
    _training_lapse_advisories,
    _week_hours,
    _week_window,
    check_shift_compliance,
    shape_lapse_advisories,
)


def raise_for_violations(violations: list[dict], *, force: bool) -> None:
    """Turn violations into the right HTTP error, or return quietly.

    BLOCK ⇒ 422 always (force can't override a bright-line minor-hour cap).
    Advisories ⇒ 409 unless force. Force on advisories returns quietly; the
    caller is responsible for audit-logging the override.
    """
    if not violations:
        return
    if schedule_compliance.has_block(violations):
        raise HTTPException(status_code=422, detail=compliance_block_detail(violations))
    if not force:
        raise HTTPException(status_code=409, detail=compliance_warning_detail(violations))
