"""Every DB read behind the HR Pilot corpus: the grounding gatherer plus one
fetcher per operational-fact group (shifts, training, incidents, benefits,
schedule intelligence, scheduling law). Each rides its own product's feature
flag; `None` (module off) and `[]` (on but empty) are kept distinct, because
silence would otherwise read as "nobody is scheduled".
"""
import logging

from ._config import _INCIDENT_LOOKBACK_DAYS, _MAX_BENEFIT_PLANS, _MAX_HR_PILOT_POLICIES, _MAX_HR_PILOT_SECTIONS, _MAX_RECENT_INCIDENTS, _MAX_SCHEDULE_SHIFTS, _MAX_TRAINING_DETAIL, _MAX_TRAINING_PROGRAMS, _SCHEDLAW_RULE_KEY_TO_CHECK, _SCHEDULE_LOOKAHEAD_DAYS

logger = logging.getLogger(__name__)


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
            SELECT tr.id, tr.title, tr.due_date, tr.source_type, e.first_name, e.last_name, e.job_title
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
            SELECT tr.id, tr.title, tr.expiration_date, tr.source_type, e.first_name, e.last_name, e.job_title
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
    from app.matcha.services.scheduling import schedule_intelligence as si

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
    from app.matcha.services.scheduling import schedule_compliance
    from app.matcha.services.scheduling import fair_workweek

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
