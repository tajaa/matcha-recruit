"""HR Pilot citation corpus — traceable grounding for supervisor guidance.

HR Pilot mode grounds answers in the company's own written material, but until
now it did so as *uncitable prose*: the model was told to answer from the
handbook, and nothing checked that the rule it quoted actually existed. This
module gives that same source material a flat citation index (`{sources, index,
notes}` — the shape `legal_defense.validate_citations` consumes) so every
enforceable claim carries a bracketed corpus id, and any id the model invents is
dropped before the answer is persisted.

Corpus cid scheme (one flat index; the audit gate keys on it):
- ``profile``                        — company handbook profile          (via handbook_pilot)
- ``law:<state>-<cat>-<title-slug>`` — applicable jurisdiction requirement (via handbook_pilot)
- ``handbook:<uuid>``                — active handbook section            (via handbook_pilot)
- ``policy:<uuid>``                  — active policy                      (via handbook_pilot)
- ``playbook:<slug>``                — industry baseline section          (via handbook_pilot)
- ``floor:<level>-<juris>-<cat>``    — governing compliance requirement   (this module)
- ``ladder:<step-slug>``             — progressive-discipline step        (this module)

The first five are minted by `handbook_pilot.build_corpus` — reused wholesale,
not reimplemented, because HR Pilot fetches the same four sources Handbook Pilot
does (compare `handbook_pilot.gather_grounding`). Its law cids are derived from
requirement *content* rather than fetch position, for reasons documented at
length in that module's docstring; do not re-mint them here.

`floor:` records are a separate namespace on purpose. They come from
`matcha_work_node.build_compliance_context`'s reasoning chains — the
precedence-resolved *governing* requirement per category — which overlaps the
same statutes `law:` records cover but at a different resolution. Minting them
as `law:` would collide two different views of one statute onto one cid and the
index (keyed by cid) would silently drop one.

A floor cell is a **governing requirement**, not a location: two offices in the
same state share one California meal-break obligation. Keying on the location
would mint it once per office, and the model would cite whichever copy it saw
first — three cids naming one rule. The location labels merge into `applies_to`
instead.

Pure functions here are unit-tested (`tests/matcha_work/test_hr_pilot_corpus.py`);
only `gather_hr_pilot_grounding` touches the DB.
"""

import logging
import re

from .handbook_pilot import _slug, _floor_records, build_corpus

logger = logging.getLogger(__name__)

_MAX_HR_PILOT_SECTIONS = 60
_MAX_HR_PILOT_POLICIES = 60

# Operational-fact caps (Supervisor Copilot groups). These read live tables that
# change daily, unlike the policy corpus above — the caps keep the prompt bounded
# and every cap that bites emits a truncation note, so the model can never read a
# clipped list as the complete picture.
_SCHEDULE_LOOKAHEAD_DAYS = 7
_MAX_SCHEDULE_SHIFTS = 40
# Jurisdiction research can generate per-state training requirements, so a
# company's program list is not inherently small — it needs a cap like every
# other fetch here.
_MAX_TRAINING_PROGRAMS = 40
_MAX_TRAINING_DETAIL = 15
_MAX_RECENT_INCIDENTS = 15
_INCIDENT_LOOKBACK_DAYS = 90
_MAX_BENEFIT_PLANS = 20
_MAX_SCHEDINT_COVERAGE_RECORDS = 10
_MAX_SCHEDLAW_RECORDS = 30

# rule_key -> (label, unit) — mirrors client/src/components/employees/ScheduleLawPanel.tsx's
# RULE_LABELS so the HR Pilot answer and the admin-facing law panel describe
# the same eleven fields the same way.
_SCHEDLAW_RULE_LABELS: dict[str, tuple[str, str]] = {
    "meal_break_after_hours": ("meal break required after", "h shift"),
    "meal_break_minutes": ("meal break duration", "min"),
    "second_meal_after_hours": ("second meal break after", "h shift"),
    "daily_ot_hours": ("daily overtime after", "h"),
    "daily_doubletime_hours": ("daily double-time after", "h"),
    "weekly_ot_hours": ("weekly overtime after", "h"),
    "min_rest_between_shifts_hours": ("minimum rest between shifts", "h"),
    "minor_u16_day_hours": ("under-16 daily cap", "h"),
    "minor_u16_week_hours": ("under-16 weekly cap", "h"),
    "minor_16_17_day_hours": ("16-17yo daily cap", "h"),
    "minor_16_17_week_hours": ("16-17yo weekly cap", "h"),
}

# rule_key -> the citation-lookup name `schedule_compliance._cite` reads
# (`rules["citations"][name]`) — duplicated from
# `routes/employee_schedule/_compliance.py:_RULE_KEY_TO_CHECK` rather than
# imported, since that lives in a route package and services must not reach
# into routes.
_SCHEDLAW_RULE_KEY_TO_CHECK = {
    "meal_break_after_hours": "meal_break",
    "meal_break_minutes": "meal_break",
    "second_meal_after_hours": "meal_break",
    "daily_ot_hours": "daily_overtime",
    "daily_doubletime_hours": "daily_overtime",
    "weekly_ot_hours": "weekly_overtime",
    "min_rest_between_shifts_hours": "min_rest",
    "minor_u16_day_hours": "minor_hours",
    "minor_u16_week_hours": "minor_hours",
    "minor_16_17_day_hours": "minor_hours",
    "minor_16_17_week_hours": "minor_hours",
}

# Namespaces the audit gate will recognise inside brackets. Deliberately a
# closed list: a bare `[...]` regex also matches markdown link text and the
# `[Handbook — Title]` headers this corpus renders, so unknown brackets must be
# left alone rather than treated as a citation that failed to resolve.
_CID_NAMESPACES = (
    "profile", "law", "handbook", "policy", "playbook", "floor", "ladder",
    # Supervisor Copilot — operational facts, not policy. See the order-of-
    # authority note in matcha_work_mode_contexts: these say who/when/status,
    # they never establish a rule.
    "schedule", "training", "incident",
    # Schedule Intelligence — analytics over the scheduling data (understaffing
    # x incident correlation, Fair Workweek exposure, qualified-coverage gaps).
    # Supervisor-only: see _SUPERVISOR_ONLY_SOURCES.
    "schedint",
    # Benefits enrollment — plan offerings + the open-enrollment window.
    # Company-level and nameless by construction, so (unlike the three above)
    # it is served to BOTH surfaces: "when does open enrollment close?" is a
    # core Ask HR question.
    "benefit",
    # Enforced scheduling-law thresholds (meal break/OT/rest/minor caps) +
    # Fair Workweek ordinances — state-level law, no employee data, served to
    # BOTH surfaces like benefit. See services/schedule_compliance.py.
    "schedlaw",
)
_CITATION_RE = re.compile(
    r"\[(" + "|".join(_CID_NAMESPACES) + r")(:[^\]\s]+)?\]"
)

# Progressive-discipline ladder — static company procedure, cited like any other
# record so "the next step is a written warning" is traceable rather than
# asserted. Replaces the prose _DISCIPLINE_LADDER_SUMMARY this module took over
# from matcha_work_mode_contexts.
_LADDER_STEPS = [
    ("verbal-warning", "Verbal warning",
     "First documented step. Supervisor discusses the issue with the employee and "
     "records that the conversation happened."),
    ("written-warning", "Written warning",
     "Second step. A written record the employee acknowledges, stating the conduct, "
     "the expectation, and the timeframe for improvement."),
    ("final-warning", "Final warning",
     "Third step. States plainly that the next step is a termination review."),
    ("termination-review", "Termination review",
     "Final step. NOT drafted or advised here — a final warning already on file means "
     "the supervisor must be routed to corporate HR."),
]


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


# --------------------------------------------------------------------------- #
# Grounding — DB-touching. Mirrors handbook_pilot.gather_grounding, but reads
# only what is ACTUALLY IN FORCE (active handbook + active policies, no drafts):
# a supervisor acting today needs the rule in force today, not a proposal.
# --------------------------------------------------------------------------- #

async def gather_hr_pilot_grounding(conn, company_id) -> dict:
    """Fetch the raw grounding material HR Pilot cites. Best-effort at every
    level — a dead source degrades to empty and the rest still grounds."""
    from app.core.services import handbook_service as hb

    sections: list = []
    try:
        sections = await conn.fetch(
            """
            SELECT hs.id, hs.title, hs.section_type, hs.content,
                   h.title AS handbook_title
            FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1 AND h.status = 'active'
              AND hv.version_number = h.active_version
            ORDER BY hs.section_order
            LIMIT $2
            """,
            company_id, _MAX_HR_PILOT_SECTIONS,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: handbook-section fetch failed for %s", company_id)

    policies: list = []
    try:
        policies = await conn.fetch(
            """
            SELECT id, title, category, status, content, description
            FROM policies
            WHERE company_id = $1 AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            company_id, _MAX_HR_PILOT_POLICIES,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: policy fetch failed for %s", company_id)

    scopes: list = []
    requirements: dict = {}
    try:
        scopes = await hb.derive_handbook_scopes_from_employees(conn, str(company_id))
        if scopes:
            requirements = await hb._fetch_state_requirements(conn, scopes)
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: requirement fetch failed for %s", company_id)

    # One row carries both the industry (playbook selection) and the feature
    # set. Features are resolved through the PURE `merge_company_features` rather
    # than read straight off the JSONB: a tier overlay (Matcha-X grants
    # `training` without storing it) is invisible to `enabled_features ->> …`,
    # so a SQL-side check would hide a module the company actually has.
    industry = None
    features: dict = {}
    # Whether we actually LEARNED the feature set. A failed fetch leaves
    # `features` empty, which is indistinguishable from "every module off" —
    # and reporting that to the supervisor tells a paying customer they don't
    # have a module they bought, cached for the context TTL. Tracked separately
    # so the corpus can say "temporarily unavailable" instead.
    features_known = False
    try:
        row = await conn.fetchrow(
            "SELECT industry, enabled_features, signup_source FROM companies WHERE id = $1",
            company_id,
        )
        if row:
            industry = row["industry"]
            # merge_company_features parses a JSON string itself and applies the
            # tier overlay — pass the raw column straight through.
            from app.core.feature_flags import merge_company_features
            features = merge_company_features(row["enabled_features"], row["signup_source"])
            features_known = True
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: company/feature fetch failed for %s", company_id)

    profile = None
    try:
        profile = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: profile fetch failed for %s", company_id)

    # --- Operational facts (Supervisor Copilot) ---------------------------------
    # Each rides its own product's feature flag. Three states, not two:
    #   [] / {...}  → module on (empty means nothing in the window)
    #   None        → module off for this company
    #   unset key   → we could not determine it (feature fetch failed)
    # The corpus renders a different note for each; conflating the last two is
    # how a transient DB error becomes "you don't have scheduling".
    out = {
        "scopes": scopes,
        "profile": dict(profile) if profile else None,
        "requirements": requirements,
        "sections": [dict(r) for r in sections],
        "policies": [dict(r) for r in policies],
        "industry": industry,
        "features": features,
        "features_known": features_known,
    }
    if features_known:
        out["shifts"] = (
            await _fetch_shifts(conn, company_id) if features.get("employee_schedule") else None
        )
        out["training"] = (
            await _fetch_training(conn, company_id) if features.get("training") else None
        )
        out["incidents"] = (
            await _fetch_incidents(conn, company_id) if features.get("incidents") else None
        )
        out["benefits"] = (
            await _fetch_benefits(conn, company_id) if features.get("benefits_admin") else None
        )
        out["schedule_intelligence"] = (
            await _fetch_schedule_intelligence(conn, company_id, features)
            if features.get("schedule_intelligence") and features.get("employee_schedule")
            else None
        )
        out["schedule_law"] = (
            await _fetch_schedule_law(conn, company_id, features)
            if features.get("employee_schedule") else None
        )
    return out


async def _fetch_shifts(conn, company_id) -> list[dict]:
    """Published shifts OVERLAPPING the next `_SCHEDULE_LOOKAHEAD_DAYS`, each with
    its assignees.

    Deliberately does NOT import `routes/employee_schedule/_shared.fetch_shifts`
    — a service reaching into a route package inverts the layering every other
    service here respects. The query is small enough to own, but it uses that
    module's OVERLAP predicate (`ends_at > now AND starts_at < horizon`) rather
    than a start-time window: "who is on right now?" is a core supervisor
    question, and a shift that started two hours ago and runs another six is the
    answer to it. Filtering on `starts_at >= NOW()` drops exactly the shift being
    asked about.

    Only PUBLISHED shifts: a draft schedule is not something a supervisor should
    be told is happening. Declined assignments are excluded from the roster —
    counting them as staffed is how "is Saturday covered?" gets a confident wrong
    answer."""
    try:
        rows = await conn.fetch(
            """
            SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
                   s.required_staff, s.location_id,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'name', TRIM(COALESCE(e.first_name,'') || ' ' || COALESCE(e.last_name,'')),
                               'job_title', e.job_title,
                               'status', a.status
                           ) ORDER BY e.last_name, e.first_name
                       ) FILTER (WHERE e.id IS NOT NULL),
                       '[]'::json
                   ) AS assignees
            FROM schedule_shifts s
            LEFT JOIN schedule_shift_assignments a
                   ON a.shift_id = s.id AND a.status <> 'declined'
            LEFT JOIN employees e
                   ON e.id = a.employee_id AND e.termination_date IS NULL
            WHERE s.company_id = $1 AND s.status = 'published'
              AND s.ends_at > NOW()
              AND s.starts_at < NOW() + ($2 || ' days')::interval
            GROUP BY s.id
            ORDER BY s.starts_at
            LIMIT $3
            """,
            company_id, str(_SCHEDULE_LOOKAHEAD_DAYS), _MAX_SCHEDULE_SHIFTS,
        )
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: shift fetch failed for %s", company_id)
        return []


async def _fetch_training(conn, company_id) -> dict:
    """Per-program completion aggregates + the overdue and expiring detail rows.

    Same SQL shapes as the `training` thread mode's builder, with the row ids
    added so each fact gets a stable cid. Status and dates only — scores and
    certificate numbers are never selected, following the credential precedent
    in that builder."""
    out: dict = {"programs": [], "overdue": [], "expiring": []}
    try:
        out["programs"] = [dict(r) for r in await conn.fetch(
            """
            SELECT r.id, r.title, r.training_type, r.frequency_months,
                   COUNT(tr.id) AS total_assigned,
                   COUNT(tr.id) FILTER (WHERE tr.status='completed') AS completed,
                   COUNT(tr.id) FILTER (WHERE tr.status IN ('assigned','in_progress')
                                          AND tr.due_date < CURRENT_DATE) AS overdue
            FROM training_requirements r
            LEFT JOIN training_records tr ON tr.requirement_id = r.id
            WHERE r.company_id=$1 AND r.is_active
            GROUP BY r.id
            ORDER BY overdue DESC, r.title
            LIMIT $2
            """,
            company_id, _MAX_TRAINING_PROGRAMS,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: training-program fetch failed for %s", company_id)

    try:
        # `tr.title`, not `tr.course_name` — the latter is referenced in
        # dashboard.py:1636 but does not exist on this table.
        out["overdue"] = [dict(r) for r in await conn.fetch(
            """
            SELECT tr.id, tr.title, tr.due_date, e.first_name, e.last_name, e.job_title
            FROM training_records tr
            JOIN employees e ON e.id = tr.employee_id
            WHERE tr.company_id=$1 AND tr.status IN ('assigned','in_progress')
              AND e.termination_date IS NULL
              AND tr.due_date < CURRENT_DATE
            ORDER BY tr.due_date ASC
            LIMIT $2
            """,
            company_id, _MAX_TRAINING_DETAIL,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: training-overdue fetch failed for %s", company_id)

    try:
        out["expiring"] = [dict(r) for r in await conn.fetch(
            """
            SELECT tr.id, tr.title, tr.expiration_date, e.first_name, e.last_name, e.job_title
            FROM training_records tr
            JOIN employees e ON e.id = tr.employee_id
            WHERE tr.company_id=$1 AND tr.status='completed'
              AND e.termination_date IS NULL
              AND tr.expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
            ORDER BY tr.expiration_date ASC
            LIMIT $2
            """,
            company_id, _MAX_TRAINING_DETAIL,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: training-expiring fetch failed for %s", company_id)

    return out


async def _fetch_incidents(conn, company_id) -> list[dict]:
    """Recent incidents, for situational awareness only.

    Names no people: `involved_employee_ids` is deliberately not selected. A
    supervisor asking "has anything happened at this site lately?" needs the
    pattern, not a list of who was hurt — and the IR product is where a named
    record is read, with its own access controls."""
    try:
        rows = await conn.fetch(
            """
            SELECT id, incident_number, title, incident_type, severity, status,
                   occurred_at, location
            FROM ir_incidents
            WHERE company_id = $1
              AND occurred_at >= NOW() - ($2 || ' days')::interval
            ORDER BY occurred_at DESC
            LIMIT $3
            """,
            company_id, str(_INCIDENT_LOOKBACK_DAYS), _MAX_RECENT_INCIDENTS,
        )
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: incident fetch failed for %s", company_id)
        return []


async def _fetch_benefits(conn, company_id) -> dict:
    """Active benefit plans + the open OE window + aggregate election progress.

    Deliberately NAMELESS — no employee is selected anywhere here. That is what
    lets this group skip `_SUPERVISOR_ONLY_SOURCES` and reach Ask HR: "what does
    the family tier cost?" and "when does open enrollment close?" are questions
    every employee is entitled to ask, and a plan's tier price names nobody.
    Per-employee election status stays in the benefits product (admin review
    dashboard) with its own access controls."""
    out: dict = {"plans": [], "open_period": None, "submitted_employees": None,
                 "active_employees": None, "pending_life_events": 0}
    try:
        out["plans"] = [dict(r) for r in await conn.fetch(
            """
            SELECT p.id, p.plan_type, p.name, p.carrier_name, p.waivable,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'coverage_tier', t.coverage_tier,
                               'employee_cost', t.employee_cost,
                               'cost_period', t.cost_period
                           ) ORDER BY t.coverage_tier
                       ) FILTER (WHERE t.id IS NOT NULL),
                       '[]'::json
                   ) AS tiers
            FROM benefit_plans p
            LEFT JOIN benefit_plan_tiers t ON t.plan_id = p.id
            WHERE p.company_id = $1 AND p.status = 'active'
            GROUP BY p.id
            ORDER BY p.plan_type, p.name
            LIMIT $2
            """,
            company_id, _MAX_BENEFIT_PLANS,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: benefit-plan fetch failed for %s", company_id)

    try:
        # Partial unique index guarantees at most one open period per company.
        period = await conn.fetchrow(
            """
            SELECT id, name, starts_on, ends_on, plan_year_start
            FROM open_enrollment_periods
            WHERE company_id = $1 AND status = 'open'
            """,
            company_id,
        )
        if period:
            out["open_period"] = dict(period)
            out["submitted_employees"] = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT employee_id) FROM benefit_elections
                WHERE open_enrollment_period_id = $1 AND status IN ('submitted', 'approved')
                """,
                period["id"],
            )
            out["active_employees"] = await conn.fetchval(
                """
                SELECT COUNT(*) FROM employees
                WHERE org_id = $1 AND employment_status NOT IN ('terminated', 'offboarded')
                """,
                company_id,
            )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: OE-period fetch failed for %s", company_id)

    try:
        out["pending_life_events"] = await conn.fetchval(
            "SELECT COUNT(*) FROM life_event_changes WHERE company_id = $1 AND status = 'pending'",
            company_id,
        ) or 0
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: life-event fetch failed for %s", company_id)

    return out


async def _fetch_schedule_intelligence(conn, company_id, features: dict) -> dict:
    """Schedule Intelligence headlines: incident correlation, Fair Workweek
    exposure, qualified-coverage gaps. Reuses `services/schedule_intelligence.py`
    wholesale (same builders the /schedule-intelligence endpoints call) rather
    than re-querying — this IS the analytics engine, not a re-derivation of it.
    Each of the three sub-fetches degrades independently so one failing query
    doesn't blank the whole group."""
    from . import schedule_intelligence as si

    out: dict = {"incidents": None, "fair_workweek": None, "coverage": None}
    try:
        out["incidents"] = await si.build_incident_correlation(conn, company_id)
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: schedule-intelligence incident fetch failed for %s", company_id)
    try:
        out["fair_workweek"] = await si.build_fair_workweek_exposure(conn, company_id)
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: schedule-intelligence fair-workweek fetch failed for %s", company_id)
    try:
        out["coverage"] = await si.build_qualified_coverage(
            conn, company_id,
            credential_templates_enabled=bool(features.get("credential_templates")),
            training_enabled=bool(features.get("training")),
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: schedule-intelligence coverage fetch failed for %s", company_id)
    return out


async def _fetch_schedule_law(conn, company_id, features: dict) -> list[dict]:
    """Per-state ENFORCED scheduling-law thresholds — the same merged
    curated + catalog-extraction source `schedule_compliance.rules_for_state`
    feeds the write-path gate, plus any Fair Workweek ordinance covering the
    company's locations (`fair_workweek.ordinance_for_location`).

    This is deliberately a SEPARATE pipeline from the `floor:` group (which
    reads the raw jurisdiction catalog via precedence resolution): a state in
    the hand-curated `_SCHEDULING_RULES` table ignores catalog/db_rules
    entirely (`rules_for_state`'s per-state precedence), so `floor:` and the
    gate can disagree. Grounding here instead guarantees HR Pilot's citation
    always matches what the scheduling system will actually enforce.

    Company-wide, not per-thread-location — same aggregation level every
    other HR Pilot group uses."""
    from . import schedule_compliance
    from . import fair_workweek

    out: list[dict] = []
    try:
        loc_rows = await conn.fetch(
            "SELECT DISTINCT state, city, name FROM business_locations "
            "WHERE company_id = $1 AND state IS NOT NULL",
            company_id,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: schedule-law location fetch failed for %s", company_id)
        return out

    industry = None
    try:
        company = await conn.fetchrow("SELECT industry FROM companies WHERE id = $1", company_id)
        industry = company["industry"] if company else None
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: schedule-law industry fetch failed for %s", company_id)

    seen_states: set[str] = set()
    for loc in loc_rows:
        state = (loc["state"] or "").strip().upper()
        if not state:
            continue
        if state not in seen_states:
            seen_states.add(state)
            db_rules = None
            if not schedule_compliance.is_curated_state(state):
                try:
                    rows = await conn.fetch(
                        """
                        SELECT rule_key, rule_value, no_rule, citation
                        FROM schedule_rule_extractions
                        WHERE state = $1 AND review_status = 'approved' AND is_active = true
                        """,
                        state,
                    )
                    if rows:
                        db_rules = {"citations": {}}
                        for r in rows:
                            db_rules[r["rule_key"]] = (
                                schedule_compliance.NO_CAP if r["no_rule"] else float(r["rule_value"])
                            )
                            check_name = _SCHEDLAW_RULE_KEY_TO_CHECK.get(r["rule_key"])
                            if check_name:
                                db_rules["citations"][check_name] = r["citation"]
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "hr_pilot_corpus: schedule-law catalog fetch failed for %s/%s", company_id, state,
                    )
            summary = schedule_compliance.rules_summary(state, db_rules)
            out.append({"kind": "state_rules", "state": state, "summary": summary})

        ordinance, applicability = fair_workweek.ordinance_for_location(loc["state"], loc["city"], industry)
        if ordinance is not None:
            out.append({
                "kind": "fair_workweek", "state": state, "city": loc["city"],
                "location_name": loc["name"], "applicability": applicability,
                "ordinance_name": ordinance["name"], "citation": ordinance["citation"],
                "notice_days": ordinance["notice_days"],
                "clopening_rest_hours": (ordinance.get("clopening") or {}).get("rest_hours"),
            })
    return out


# --------------------------------------------------------------------------- #
# Corpus build — pure. Extends handbook_pilot's five source groups with two.
# --------------------------------------------------------------------------- #

# NOTE: `_floor_records` now lives in `handbook_pilot` and is imported at the top
# of this module. It moved DOWN the dependency arrow (this module already imports
# handbook_pilot; the reverse would be circular) once Handbook Pilot needed the
# same precedence-resolved floor. It stays importable from here — callers and
# tests that reach for `hr_pilot_corpus._floor_records` are unaffected.


def _ladder_records() -> list[dict]:
    return [
        {
            "cid": f"ladder:{slug}",
            "ref": f"Discipline ladder — {label}",
            "summary": summary,
            "when": "company procedure",
            "step": i + 1,
        }
        for i, (slug, label, summary) in enumerate(_LADDER_STEPS)
    ]


def _fmt_dt(value) -> str:
    """Weekday-bearing timestamp. A supervisor asks "who's on Saturday", so the
    day name has to survive into the record — an ISO date alone makes the model
    do calendar arithmetic, which it does badly."""
    if value is None:
        return "unscheduled"
    try:
        return value.strftime("%a %Y-%m-%d %H:%M")
    except (AttributeError, ValueError):
        return str(value)


def _fmt_d(value) -> str:
    if value is None:
        return "no date"
    try:
        return value.strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return str(value)


def _schedule_records(shifts: list | None) -> list[dict]:
    """One record per published upcoming shift, naming its assignees.

    The shift id is the cid: it is a real stable UUID, so a citation survives the
    shift being retimed (the fact it points at is still that shift)."""
    recs: list[dict] = []
    for s in shifts or []:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        assignees = s.get("assignees")
        if isinstance(assignees, str):
            import json as _json
            try:
                assignees = _json.loads(assignees)
            except (ValueError, TypeError):
                assignees = []
        # Declined assignments are already excluded by the fetch; re-filter here
        # so the pure minter is correct on any input. Counting a declined person
        # as staffed answers "is Saturday covered?" with a confident yes.
        assignees = [
            a for a in (assignees or [])
            if isinstance(a, dict) and a.get("status") != "declined"
        ]

        names = [str(a.get("name") or "").strip() for a in assignees]
        names = [n for n in names if n]
        required = s.get("required_staff")
        role = s.get("role") or s.get("department") or "shift"

        bits = [f"{_fmt_dt(s.get('starts_at'))} → {_fmt_dt(s.get('ends_at'))}"]
        if names:
            bits.append("assigned: " + ", ".join(names))
        else:
            bits.append("nobody assigned")
        if required is not None:
            # Staffing shortfall is a deterministic fact, computed here rather
            # than left for the model to infer from two numbers.
            short = int(required) - len(names)
            bits.append(
                f"needs {required}"
                + (f" — SHORT BY {short}" if short > 0 else " — fully staffed")
            )
        recs.append({
            "cid": f"schedule:{s['id']}",
            "ref": f"Shift — {role} {_fmt_dt(s.get('starts_at'))}",
            "summary": "; ".join(bits) + ".",
            "when": _fmt_dt(s.get("starts_at")),
            "role": str(role),
            "assignee_names": names,
        })
    return recs


def _training_records(training: dict | None) -> list[dict]:
    """Per-program completion aggregates plus overdue/expiring detail rows.

    Two cid shapes in one namespace, kept disjoint by construction: aggregates
    are `training:program-<requirement_uuid>`, detail rows are
    `training:<record_uuid>`. A raw UUID can never collide with a `program-`
    prefix, so the flat index stays sound."""
    training = training or {}
    recs: list[dict] = []

    for p in training.get("programs") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        total = int(p.get("total_assigned") or 0)
        done = int(p.get("completed") or 0)
        overdue = int(p.get("overdue") or 0)
        pct = round(done * 100 / total) if total else 0
        bits = [f"{done}/{total} complete ({pct}%)"]
        if overdue:
            bits.append(f"{overdue} OVERDUE")
        if p.get("frequency_months"):
            bits.append(f"repeats every {p['frequency_months']} months")
        recs.append({
            "cid": f"training:program-{p['id']}",
            "ref": f"Training program — {p.get('title')}",
            "summary": "; ".join(bits) + ".",
            "when": "current",
            "training_type": p.get("training_type"),
        })

    for r in training.get("overdue") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        who = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "employee"
        recs.append({
            "cid": f"training:{r['id']}",
            "ref": f"Overdue training — {who}",
            "summary": f"{who} has not completed {r.get('title')}; was due {_fmt_d(r.get('due_date'))}.",
            "when": _fmt_d(r.get("due_date")),
            "status": "overdue",
        })

    for r in training.get("expiring") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        who = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "employee"
        recs.append({
            "cid": f"training:{r['id']}",
            "ref": f"Expiring training — {who}",
            "summary": (f"{who} completed {r.get('title')}, but it expires "
                        f"{_fmt_d(r.get('expiration_date'))}."),
            "when": _fmt_d(r.get("expiration_date")),
            "status": "expiring",
        })

    return recs


def _incident_records(incidents: list | None) -> list[dict]:
    """Recent incidents — pattern awareness, no persons named."""
    recs: list[dict] = []
    for i in incidents or []:
        if not isinstance(i, dict) or not i.get("id"):
            continue
        bits = [str(i.get("title") or "incident")]
        if i.get("incident_type"):
            bits.append(_hum(i["incident_type"]))
        if i.get("severity"):
            bits.append(f"severity {i['severity']}")
        if i.get("status"):
            bits.append(f"status {i['status']}")
        if i.get("location"):
            bits.append(f"at {i['location']}")
        recs.append({
            "cid": f"incident:{i['id']}",
            "ref": f"Incident {i.get('incident_number') or ''} — {i.get('title')}".strip(),
            "summary": "; ".join(bits) + ".",
            "when": _fmt_d(i.get("occurred_at")),
            "severity": i.get("severity"),
            "incident_type": i.get("incident_type"),
        })
    return recs


def _fmt_cost(value, cost_period) -> str:
    try:
        amount = f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "cost n/a"
    return amount + ("/pay period" if cost_period == "per_pay_period" else "/mo")


def _benefit_records(benefits: dict | None) -> list[dict]:
    """Plan offerings + the open OE window + a pending-life-event count.

    Nameless by construction (see `_fetch_benefits`) — this is the one
    operational group that reaches Ask HR unredacted. Cids: `benefit:plan-<id>`
    per active plan, `benefit:oe-<id>` for the open window, and the fixed
    `benefit:life-events-pending` aggregate (a count, not a row — like
    `profile`, its stability comes from being a singleton)."""
    benefits = benefits or {}
    recs: list[dict] = []

    for p in benefits.get("plans") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        tiers = p.get("tiers")
        if isinstance(tiers, str):
            import json as _json
            try:
                tiers = _json.loads(tiers)
            except (ValueError, TypeError):
                tiers = []
        tier_bits = [
            f"{_hum(t.get('coverage_tier'))} {_fmt_cost(t.get('employee_cost'), t.get('cost_period'))} employee cost"
            for t in (tiers or []) if isinstance(t, dict)
        ]
        bits = [f"{_hum(p.get('plan_type'))} plan"]
        if p.get("carrier_name"):
            bits.append(f"carrier {p['carrier_name']}")
        if tier_bits:
            bits.append("tiers: " + ", ".join(tier_bits))
        bits.append("can be waived" if p.get("waivable") else "cannot be waived")
        recs.append({
            "cid": f"benefit:plan-{p['id']}",
            "ref": f"Benefit plan — {p.get('name')} ({_hum(p.get('plan_type'))})",
            "summary": "; ".join(bits) + ".",
            "when": "current offering",
            "plan_type": p.get("plan_type"),
        })

    period = benefits.get("open_period")
    if isinstance(period, dict) and period.get("id"):
        bits = [f"OPEN now, {_fmt_d(period.get('starts_on'))} → {_fmt_d(period.get('ends_on'))}"]
        if period.get("plan_year_start"):
            bits.append(f"coverage effective {_fmt_d(period['plan_year_start'])}")
        submitted = benefits.get("submitted_employees")
        active = benefits.get("active_employees")
        if submitted is not None and active is not None:
            bits.append(f"{submitted} of {active} active employees have submitted elections")
        recs.append({
            "cid": f"benefit:oe-{period['id']}",
            "ref": f"Open enrollment — {period.get('name')}",
            "summary": "; ".join(bits) + ".",
            "when": f"closes {_fmt_d(period.get('ends_on'))}",
            "ends_on": _fmt_d(period.get("ends_on")),
        })

    pending = int(benefits.get("pending_life_events") or 0)
    if pending:
        recs.append({
            "cid": "benefit:life-events-pending",
            "ref": "Qualifying life events — pending review",
            "summary": (f"{pending} qualifying life-event request(s) await HR review; "
                        "an approved event opens a personal election window."),
            "when": "current",
        })

    return recs


def _schedlaw_records(data: list[dict] | None) -> list[dict]:
    """Enforced scheduling-law thresholds + Fair Workweek ordinances, one
    record per determined fact. Iterates the FIXED `_SCHEDLAW_RULE_LABELS`
    map — never the summary dict's own keys — so meta fields the summary
    carries (`citations`, `source`) can never mint a garbage record."""
    recs: list[dict] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "state_rules":
            state = item.get("state")
            summary = item.get("summary") or {}
            citations = summary.get("citations") or {}
            for rule_key, (label, unit) in _SCHEDLAW_RULE_LABELS.items():
                value = summary.get(rule_key)
                if value is None:
                    continue
                display = "no limit under law" if value == "no_cap" else f"{value}{unit}"
                citation = citations.get(_SCHEDLAW_RULE_KEY_TO_CHECK.get(rule_key, ""))
                cite_clause = f", cites {citation}" if citation else ""
                recs.append({
                    "cid": f"schedlaw:{state}-{rule_key}",
                    "ref": f"Scheduling law — {state} {label}",
                    "summary": f"{state}: {label} {display}{cite_clause}.",
                    "when": "current law",
                })
        elif item.get("kind") == "fair_workweek":
            state = item.get("state")
            city_slug = str(item.get("city") or "").strip().lower().replace(" ", "-")
            prefix = "" if item.get("applicability") == "covered" else "may apply (verify industry) — "
            bits = [f"{prefix}{item.get('ordinance_name')} requires {item.get('notice_days')}-day schedule notice"]
            if item.get("clopening_rest_hours"):
                bits.append(f'{item["clopening_rest_hours"]}h rest between shifts ("clopening")')
            recs.append({
                "cid": f"schedlaw:fw-{state}-{city_slug}",
                "ref": f"Fair Workweek — {item.get('location_name') or item.get('city')}",
                "summary": "; ".join(bits) + f", cites {item.get('citation')}.",
                "when": "current law",
            })
        if len(recs) >= _MAX_SCHEDLAW_RECORDS:
            break
    return recs


def _schedint_records(data: dict | None) -> list[dict]:
    """Schedule Intelligence headlines: incident-correlation, Fair Workweek
    exposure per location, and per-shift qualified-coverage gaps.

    Every summary repeats the directional/estimate framing in-line — these are
    the same figures a business admin sees on the Schedule Intelligence page,
    and the model must not present them as more certain out of context."""
    recs: list[dict] = []
    data = data or {}

    incidents = data.get("incidents") or {}
    if incidents:
        if incidents.get("suppressed"):
            summary = (
                f"Too few incidents/shifts in the last {incidents.get('days')} days for a "
                f"reliable comparison — {incidents.get('n_incidents')} incidents across "
                f"{incidents.get('n_shifts')} shifts (counts only)."
            )
        else:
            under = (incidents.get("by_staffing") or {}).get("understaffed") or {}
            ok = (incidents.get("by_staffing") or {}).get("adequate") or {}
            summary = (
                f"Understaffed shifts: {under.get('incidents', 0)} incidents / "
                f"{under.get('shifts', 0)} shifts (rate {under.get('incident_rate')}); "
                f"adequately staffed: {ok.get('incidents', 0)} incidents / {ok.get('shifts', 0)} "
                f"shifts (rate {ok.get('incident_rate')}). Directional, not a causal claim."
            )
        recs.append({
            "cid": "schedint:incidents",
            "ref": "Schedule Intelligence — incident correlation",
            "summary": summary,
            "when": "current",
        })

    for loc in (data.get("fair_workweek") or {}).get("locations") or []:
        if loc.get("applicability") == "unmapped" or not loc.get("event_count"):
            continue
        ordinance = loc.get("ordinance") or {}
        estimate = loc.get("exposure_estimate")
        summary = (
            f"{loc.get('event_count')} schedule-change event(s) under {ordinance.get('name')} "
            f"({ordinance.get('citation')})"
            + (f" — estimated exposure ${estimate:,.2f}" if estimate is not None
               else " — dollar estimate unavailable (no pay-rate data)")
            + f". Applicability: {loc.get('applicability')}. Directional estimate, not legal advice."
        )
        recs.append({
            "cid": f"schedint:fair-workweek.{loc['location_id']}",
            "ref": f"Fair Workweek exposure — {loc.get('name')}",
            "summary": summary,
            "when": "current",
        })

    coverage_shifts = (data.get("coverage") or {}).get("shifts") or []
    gap_shifts = [s for s in coverage_shifts if s.get("qualified", 0) < s.get("assigned", 0)]
    for s in gap_shifts[:_MAX_SCHEDINT_COVERAGE_RECORDS]:
        recs.append({
            "cid": f"schedint:coverage.{s['shift_id']}",
            "ref": f"Qualified-coverage gap — {_fmt_dt(s.get('starts_at'))}",
            "summary": (
                f"{s.get('qualified')}/{s.get('assigned')} assigned staff are currently "
                f"qualified for this shift (needs {s.get('required_staff')}) — a credential "
                "or training item has lapsed for at least one assignee."
            ),
            "when": _fmt_dt(s.get("starts_at")),
        })
    return recs


def build_hr_pilot_corpus(grounding: dict, reasoning_chains: list | None = None) -> dict:
    """Assemble the HR Pilot citation corpus `{sources, index, notes}`. Pure.

    Delegates the five shared source groups to `handbook_pilot.build_corpus`
    (identical source material, already-hardened cid minting), appends the two
    policy-side HR Pilot groups, then the three operational-fact groups
    (Supervisor Copilot).

    The operational groups distinguish "module off" (`None`) from "module on,
    nothing there" (`[]`) — an absent module gets a note telling the model to
    say so, because silence would otherwise read as "nobody is scheduled"."""
    grounding = grounding or {}
    if reasoning_chains is not None:
        # `build_corpus` mints the compliance_floor group itself now, off
        # `grounding["reasoning_chains"]`. The explicit parameter stays for the
        # existing callers (and their tests) and simply feeds that key; minting
        # the group again here would render every floor record twice in the
        # prompt block (the index dedupes on cid, the prompt does not).
        grounding = {**grounding, "reasoning_chains": reasoning_chains}
    corpus = build_corpus(grounding)
    sources = corpus["sources"]

    sources["discipline_ladder"] = {
        "label": "Progressive discipline ladder",
        "records": _ladder_records(),
    }
    sources["schedule"] = {
        "label": f"Published shifts — next {_SCHEDULE_LOOKAHEAD_DAYS} days",
        "records": _schedule_records(grounding.get("shifts")),
    }
    sources["training_status"] = {
        "label": "Training compliance status",
        "records": _training_records(grounding.get("training")),
    }
    sources["recent_incidents"] = {
        "label": f"Incidents — last {_INCIDENT_LOOKBACK_DAYS} days",
        "records": _incident_records(grounding.get("incidents")),
    }
    # Nameless (plans/window/aggregates only) — the one operational group NOT in
    # _SUPERVISOR_ONLY_SOURCES, so Ask HR employees see it too.
    sources["benefits"] = {
        "label": "Benefit plans & open enrollment",
        "records": _benefit_records(grounding.get("benefits")),
    }
    sources["schedint"] = {
        "label": "Schedule Intelligence — analytics",
        "records": _schedint_records(grounding.get("schedule_intelligence")),
    }
    # Nameless (state-level law + ordinances, no employee data) — like
    # benefits, NOT in _SUPERVISOR_ONLY_SOURCES, so Ask HR employees keep it.
    sources["schedlaw"] = {
        "label": "Scheduling law — enforced thresholds",
        "records": _schedlaw_records(grounding.get("schedule_law")),
    }

    # Rebuild the flat index over ALL groups. A cid appearing in two groups
    # would silently lose one here — the namespaces are disjoint by
    # construction, and test_no_cid_collisions_across_groups holds them so.
    index: dict = {}
    for key, source in sources.items():
        for record in source["records"]:
            index[record["cid"]] = {**record, "source": key, "source_label": source["label"]}

    # The "no compliance floor" note now comes from `build_corpus` with the
    # group itself — appending it again here would state it twice.
    notes = list(corpus.get("notes") or [])

    # Module-off notes. Absence of data and absence of the module are different
    # answers to "who's on Saturday?" — one is "nobody", the other is "this
    # company doesn't schedule here".
    if "shifts" in grounding and grounding.get("shifts") is None:
        notes.append(
            "Shift scheduling is not enabled for this company — no schedule data is "
            "available. Say so if asked about shifts; do not infer who is working."
        )
    if "training" in grounding and grounding.get("training") is None:
        notes.append(
            "Training records are not enabled for this company — say so if asked "
            "whether someone is trained or current."
        )
    if "incidents" in grounding and grounding.get("incidents") is None:
        notes.append(
            "Incident reporting is not enabled for this company — say so if asked "
            "about past incidents."
        )
    # NB: worded to survive redact_for_employee's note filter — benefits is the
    # one operational group employees keep, so its notes must not contain the
    # supervisor-only trigger words ("shifts", "incidents", "training programs").
    if "benefits" in grounding and grounding.get("benefits") is None:
        notes.append(
            "Benefits enrollment is not enabled for this company — say so if asked "
            "about benefit plans or open enrollment; do not infer plan offerings."
        )
    if "schedule_intelligence" in grounding and grounding.get("schedule_intelligence") is None:
        notes.append(
            "Schedule Intelligence analytics are not enabled for this company — say so "
            "if asked about staffing/incident correlation, Fair Workweek exposure, or "
            "qualified-coverage gaps; do not infer any of it."
        )
    # Worded to survive redact_for_employee's note filter (schedlaw stays for
    # employees) — must not contain "shifts"/"incidents"/"training programs".
    if "schedule_law" in grounding and grounding.get("schedule_law") is None:
        notes.append(
            "Scheduling-law data is not enabled for this company — say so if asked "
            "about break, overtime, or rest requirements; do not infer them."
        )

    # Cap-hit notes. A clipped list the model reads as complete is how "nobody
    # else is overdue" gets asserted from a LIMIT.
    if len(sources["schedule"]["records"]) >= _MAX_SCHEDULE_SHIFTS:
        notes.append(
            f"Only the first {_MAX_SCHEDULE_SHIFTS} upcoming shifts are listed — "
            "there may be more; do not treat the list as complete."
        )
    if len(sources["recent_incidents"]["records"]) >= _MAX_RECENT_INCIDENTS:
        notes.append(
            f"Only the {_MAX_RECENT_INCIDENTS} most recent incidents are listed — "
            "there may be more."
        )
    if len(sources["schedlaw"]["records"]) >= _MAX_SCHEDLAW_RECORDS:
        notes.append(
            f"Only the first {_MAX_SCHEDLAW_RECORDS} scheduling-law records are listed — "
            "there may be more; do not treat the list as complete."
        )
    _training = grounding.get("training") or {}
    if (len(_training.get("overdue") or []) >= _MAX_TRAINING_DETAIL
            or len(_training.get("expiring") or []) >= _MAX_TRAINING_DETAIL):
        notes.append(
            f"Training detail is capped at {_MAX_TRAINING_DETAIL} rows per list — "
            "the per-program counts above are the complete figures."
        )
    if len(_training.get("programs") or []) >= _MAX_TRAINING_PROGRAMS:
        notes.append(
            f"Only {_MAX_TRAINING_PROGRAMS} training programs are listed — there may "
            "be more; do not treat the list as the company's full program set."
        )
    _benefits = grounding.get("benefits") or {}
    if len(_benefits.get("plans") or []) >= _MAX_BENEFIT_PLANS:
        notes.append(
            f"Only the first {_MAX_BENEFIT_PLANS} benefit plans are listed — there "
            "may be more; do not treat the plan list as complete."
        )
    _schedint_coverage_shifts = ((grounding.get("schedule_intelligence") or {}).get("coverage") or {}).get("shifts") or []
    _schedint_gap_count = sum(1 for s in _schedint_coverage_shifts if s.get("qualified", 0) < s.get("assigned", 0))
    if _schedint_gap_count > _MAX_SCHEDINT_COVERAGE_RECORDS:
        notes.append(
            f"Schedule Intelligence coverage-gap list is capped at {_MAX_SCHEDINT_COVERAGE_RECORDS} "
            "shifts — there may be more gaps than shown."
        )

    # Could-not-determine. Distinct from "off": the keys are absent entirely
    # because the feature lookup itself failed, and reporting that as "you don't
    # have this module" would tell a paying customer they lost a product.
    if not grounding.get("features_known", True):
        notes.append(
            "Operational data (shifts, training, incidents, benefits, Schedule "
            "Intelligence, scheduling law) could not be loaded just now — this is a "
            "temporary system issue, NOT a statement that the company lacks those "
            "modules. If asked about them, say the data is briefly unavailable and to "
            "try again shortly."
        )

    return {"sources": sources, "index": index, "notes": notes}


# Source groups an employee must not see. The first three describe OTHER PEOPLE
# rather than company policy — a supervisor is entitled to them (knowing who is
# on shift and who is overdue on training is the job), an employee is not: they
# name coworkers, their training failures, and incidents at their site.
#
# `handbook_audit`/`handbook_freshness` describe the EMPLOYER's own shortfalls:
# a graded handbook gap and a section the law has moved under.
# `gather_hr_pilot_grounding` doesn't fetch them today (only Handbook Pilot
# does), so both groups are empty here — they are listed anyway because
# `build_corpus` is shared, and the day anyone wires them in, the default must
# not be that an employee's "what's the PTO policy?" comes back with a list of
# where the company's handbook is non-compliant.
#
# `schedint` (Schedule Intelligence) is supervisor-only for the same
# other-people reason as the first three: its records name understaffed
# shifts, per-location Fair Workweek exposure, and which specific employees
# have a lapsed credential/training item blocking a shift.
_SUPERVISOR_ONLY_SOURCES = ("schedule", "training_status", "recent_incidents",
                            "handbook_audit", "handbook_freshness", "schedint")


def redact_for_employee(corpus: dict) -> dict:
    """Strip supervisor-only source groups from a corpus. Pure.

    Employee Ask HR (`routes/portal_ask_hr.py`) reuses this exact corpus by
    design — same build, same cache, zero extra cost. That sharing is safe only
    while every group is company-policy material. The Supervisor Copilot groups
    are not: `schedule:` names who works when, `training:` names individuals who
    have not completed a requirement, `incident:` describes site events. Serving
    those to an employee turns "what's the PTO policy?" into a roster and a list
    of coworkers' compliance failures.

    The `benefits` group deliberately stays: `_fetch_benefits` selects no
    employee anywhere (plans, the OE window, aggregate counts), and "when does
    open enrollment close?" is a core Ask HR question. If a per-employee
    election detail is ever added to that fetch, the group moves into
    `_SUPERVISOR_ONLY_SOURCES` with it.

    Both the group AND its records' cids leave the index, so the citation gate
    drops any attempt to cite them — the model cannot reference what it was
    never shown, and could not smuggle a cid through if it guessed one."""
    corpus = corpus or {}
    sources = {
        key: group for key, group in (corpus.get("sources") or {}).items()
        if key not in _SUPERVISOR_ONLY_SOURCES
    }
    index = {
        cid: rec for cid, rec in (corpus.get("index") or {}).items()
        if rec.get("source") not in _SUPERVISOR_ONLY_SOURCES
    }
    # The dropped groups' notes ("shift scheduling is not enabled…") describe
    # modules the employee was never going to be told about; keeping them would
    # invite the model to volunteer that the company lacks scheduling.
    notes = [
        n for n in (corpus.get("notes") or [])
        if not any(w in n for w in ("Shift scheduling", "Training records",
                                    "Incident reporting", "shifts", "incidents",
                                    "training programs", "Training detail",
                                    "Schedule Intelligence"))
    ]
    return {"sources": sources, "index": index, "notes": notes}


# --------------------------------------------------------------------------- #
# The gate — pure. Runs on the finished answer, before it is persisted.
# --------------------------------------------------------------------------- #

def audit_citations(text: str, index: dict) -> tuple[str, list[dict], list[str]]:
    """Strip unresolvable citations from a finished HR Pilot answer.

    Returns `(clean_text, citations, dropped)`:
    - `clean_text` — the answer with unresolvable `[cid]` markers removed
      (resolvable ones stay in place so the client can render them as chips).
    - `citations`  — the corpus records actually cited, in first-use order.
    - `dropped`    — the invented ids, for logging and a client-side notice.

    Exact-match only, deliberately. `handbook_pilot.lookup_record` recovers
    legacy cids by prefix, but that is a READ path over already-stored
    citations; routing new model output through it would launder an invented id
    into a real requirement.

    A dropped citation removes the bracket, not the sentence around it — the
    claim survives uncited, visibly ungrounded, rather than the answer
    developing a hole mid-sentence. The count is surfaced to the user so an
    answer leaning on invented sources is legible as such.
    """
    if not text:
        return "", [], []
    index = index or {}

    citations: list[dict] = []
    seen: set[str] = set()
    dropped: list[str] = []

    def _replace(match: re.Match) -> str:
        cid = match.group(0)[1:-1]
        record = index.get(cid)
        if record is None:
            if cid not in dropped:
                dropped.append(cid)
            return ""
        if cid not in seen:
            seen.add(cid)
            citations.append(record)
        return match.group(0)

    clean = _CITATION_RE.sub(_replace, text)
    # Dropping a marker can leave doubled spaces or a space before punctuation.
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r" ([.,;:!?])", r"\1", clean)
    return clean.strip(), citations, dropped


def render_corpus_block(corpus: dict, full_text: dict | None = None) -> str:
    """Render the corpus as the citable source block injected into the prompt.

    Every record is emitted with its own `[cid]` so the model has something
    exact to cite; the instruction block at the end is what makes the citation
    obligation explicit.

    `full_text` maps cid → the record's FULL body, and exists because the corpus
    record `summary` is an index entry, not the source. `handbook_pilot`'s
    section/policy records cap their summary at 280 characters (and policy
    records carry only title/category/description, never the policy body) —
    fine for a citation footer, useless for answering from. Feeding those to the
    model would leave HR Pilot quoting the company's handbook from a 280-char
    preview of it. Callers pass the real text here; the stored records stay
    index-sized so message metadata doesn't balloon."""
    corpus = corpus or {}
    full_text = full_text or {}
    sources = corpus.get("sources") or {}
    lines: list[str] = []
    for source in sources.values():
        records = source.get("records") or []
        if not records:
            continue
        lines.append(f"\n--- {str(source.get('label') or 'Records').upper()} ({len(records)}) ---")
        for record in records:
            body = full_text.get(record["cid"]) or record.get("summary") or ""
            lines.append(f"[{record['cid']}] {record.get('ref') or ''}\n{body}")
    return "\n".join(lines)
