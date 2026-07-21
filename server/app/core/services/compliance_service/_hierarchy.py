"""compliance_service.hierarchy — J6 split of compliance_service.py."""
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

from app.core.services.compliance_service._shared import (
    _decode_jsonb,
)
from app.core.services.compliance_service._normalize import (
    _CODE_TO_STATE_NAME,
    _base_title,
    _get_numeric_from_req,
    _normalize_category,
    _normalize_requirement_categories,
    _normalize_title_key,
    _pick_best_by_priority,
)
from app.core.services.compliance_service._industry import (
    _get_company_industry_tags,
    _requirement_applicable_industries,
)
from app.core.services.compliance_service._jurisdictions import (
    _drop_no_rule_placeholders,
    _jurisdiction_row_to_dict,
    _load_chain_requirements,
)



def is_codified_row(row: Dict[str, Any]) -> bool:
    """The trio, in Python — for callers holding CATALOG rows, not SQL.

    Mirrors `codified_sql`; kept beside the gate so the two can't drift.
    """
    return bool(
        row.get("statute_citation")
        and row.get("citation_verified_at")
        and row.get("citation_item_id")
    )




async def codified_gate_sql(alias: str = "cat", *, conn=None) -> str:
    """`AND <trio>` when tenants are gated to codified rows, else empty string.

    Every tenant-facing read of requirement CONTENT appends this. The alias is
    the joined CATALOG row (`jurisdiction_requirements`), not the per-location
    projection: codification is a property of the law we researched once, not of
    each tenant's copy. Projection rows with a NULL `jurisdiction_requirement_id`
    (~6% — written before the SSOT link existed, or by a path that never set it)
    fail a LEFT JOIN's trio and drop out, which is the honest outcome: with no
    catalog row there is nothing to have verified.

    Returns SQL with no placeholders, so callers can concatenate it into a query
    without disturbing their `$n` numbering.
    """
    from app.core.services.platform_settings import get_tenant_codified_only

    if not await get_tenant_codified_only(conn=conn):
        return ""
    return f" AND {codified_sql(alias)}"




def _filter_city_level_requirements(reqs: list, state: str) -> list:
    """Filter city-level requirements for locations without local ordinances.

    Instead of blindly stripping all city-level requirements (which can lose
    categories like minimum_wage entirely), this promotes city-level entries
    to state-level when no state-level entry exists for that category.
    A city with no local ordinance inherits state rules, so any "city-level"
    data is really the state requirement mislabeled by the research source.
    """
    state_name = _CODE_TO_STATE_NAME.get(state.upper().strip(), state)

    # Separate city-level from non-city-level
    non_city = []
    city_level = []
    for r in reqs:
        jl = (
            r.get("jurisdiction_level")
            if isinstance(r, dict)
            else getattr(r, "jurisdiction_level", None)
        )
        if jl == "city":
            city_level.append(r)
        else:
            non_city.append(r)

    if not city_level:
        return reqs

    # Find categories already covered by non-city (state/county/federal) requirements
    covered_categories = set()
    for r in non_city:
        cat = r.get("category") if isinstance(r, dict) else getattr(r, "category", None)
        norm = _normalize_category(cat) or cat
        covered_categories.add(norm)

    # Promote city-level entries for categories with no state/county fallback
    promoted = []
    for r in city_level:
        cat = r.get("category") if isinstance(r, dict) else getattr(r, "category", None)
        norm = _normalize_category(cat) or cat
        if norm not in covered_categories:
            # Promote to state-level — the city has no local ordinance so this
            # data actually represents the inherited state requirement.
            if isinstance(r, dict):
                r["jurisdiction_level"] = "state"
                r["jurisdiction_name"] = state_name
            else:
                r.jurisdiction_level = "state"
                r.jurisdiction_name = state_name
            promoted.append(r)
            covered_categories.add(norm)

    stripped = len(city_level) - len(promoted)
    if stripped:
        print(
            f"[Compliance] Stripped {stripped} city-level req(s), promoted {len(promoted)} to state-level"
        )

    return non_city + promoted




async def _project_chain_to_location(
    conn, company_id: UUID, location, leaf_jurisdiction_id: UUID
) -> List[Dict]:
    """The requirement set a location is actually liable for.

    Chain union -> normalize -> industry filter -> FACILITY TRIGGERS -> preemption.

    The trigger pass is what keeps "exhaustive" from becoming "everything".
    Catalog rows carry conditions like ``{"type": "entity_type", "value":
    "behavioral_health"}`` (SAMHSA opioid-treatment certification) or
    ``{"key": "payer_contracts", "operator": "contains", "value": "medicare"}``
    (Hospital IQR). Nothing in the tenant read path ever evaluated them — only
    the hierarchical view did, and the Compliance tab doesn't use it — so a
    dental practice was served hospital and opioid-clinic obligations.
    """
    requirements = await _load_chain_requirements(conn, leaf_jurisdiction_id)
    requirements = [_jurisdiction_row_to_dict(r) for r in requirements]

    _normalize_requirement_categories(requirements)
    requirements = await _filter_requirements_for_company(conn, company_id, requirements)
    requirements = _drop_no_rule_placeholders(requirements)

    facility_attributes = _decode_jsonb(getattr(location, "facility_attributes", None))
    if not isinstance(facility_attributes, dict):
        facility_attributes = {}
    kept: List[Dict] = []
    for req in requirements:
        trigger = _decode_jsonb(req.get("trigger_conditions"))
        # `isinstance(dict)`, not just truthiness. _decode_jsonb returns an
        # unparseable value AS-IS (and jsonfix01 deliberately leaves such rows in
        # the DB rather than guessing at them), so a garbage string is truthy,
        # reaches _eval_condition, and dies on `cond.get("type")` —
        # AttributeError: 'str' object has no attribute 'get'. One bad catalog row
        # would take down the projection for every tenant whose chain contains it.
        # A trigger we cannot read is not a trigger we can enforce: treat it as
        # unconditional, which is how a row with no trigger already behaves.
        if isinstance(trigger, dict) and not evaluate_trigger_conditions(
            trigger, facility_attributes
        ):
            continue
        if trigger is not None and not isinstance(trigger, dict):
            logger.warning(
                "compliance: unreadable trigger_conditions on requirement %s — "
                "serving it unconditionally",
                req.get("jurisdiction_requirement_id"),
            )
        kept.append(req)
    requirements = kept

    requirements = await _filter_with_preemption(conn, requirements, location.state)
    return requirements




async def _filter_requirements_for_company(
    conn, company_id: UUID, requirements: List[Dict]
) -> List[Dict]:
    """Filter out industry-specific requirements that don't apply to this company."""
    if not any(_requirement_applicable_industries(r) for r in requirements):
        return requirements

    company_tags = await _get_company_industry_tags(conn, company_id)

    filtered = []
    for req in requirements:
        req_industries = _requirement_applicable_industries(req)
        if not req_industries:
            filtered.append(req)  # Generic requirement — always include
        elif not company_tags:
            continue  # Company has no industry — skip industry-specific reqs
        elif req_industries & company_tags:
            filtered.append(req)  # Direct match (set intersection)
    return filtered




def _filter_by_jurisdiction_priority(requirements):
    """For each distinct requirement key, keep only the most local jurisdiction.

    For minimum_wage, requirements are grouped by rate_type (general, tipped, etc.)
    allowing multiple wage entries per jurisdiction when they have different rate types.

    For other categories, titles are compared after stripping jurisdiction-name prefixes
    so that e.g. "California Overtime" (state) and "San Francisco Overtime" (city)
    are recognized as the same rule, while genuinely different requirements
    (e.g. separate meal / rest break entries) within one category are preserved.
    """
    by_key = {}

    for req in requirements:
        cat = req["category"] if isinstance(req, dict) else req.category
        rate_type = (
            req.get("rate_type")
            if isinstance(req, dict)
            else getattr(req, "rate_type", None)
        )
        cat_key = _normalize_category(cat)

        # For minimum_wage, group by rate_type to allow multiple entries
        if cat_key == "minimum_wage":
            key = ("minimum_wage", rate_type or "general")
        else:
            # For other categories, use existing logic based on title
            title = req["title"] if isinstance(req, dict) else req.title
            jname = (
                req["jurisdiction_name"]
                if isinstance(req, dict)
                else getattr(req, "jurisdiction_name", None)
            )
            base = _base_title(title, jname)
            base_key = _normalize_title_key(base)
            key = (cat_key, base_key)

        by_key.setdefault(key, []).append(req)

    # For each key, keep the most local jurisdiction
    filtered = []
    for reqs in by_key.values():
        best = _pick_best_by_priority(reqs)
        if best:
            filtered.append(best)

    return filtered




async def _filter_with_preemption(conn, requirements, state: Optional[str]):
    """Preemption-aware jurisdiction filter.

    For each category group:
    1. Check state_preemption_rules to see if local override is allowed.
    2. If preempted: keep only state-level requirements.
    3. If allowed (or no rule): apply most-beneficial-to-employee for wage
       categories, or most-local for others (existing behavior).
    """
    # A location with no state (10 live rows on dev) reached `state.upper()` and
    # 500'd the whole compliance page. Preemption is a state-law question — with
    # no state there is no rule to apply, so pass the requirements through
    # unfiltered rather than taking the tenant's page down.
    if not state:
        logger.warning(
            "preemption skipped: location has no state — returning requirements unfiltered"
        )
        return requirements

    norm_state = state.upper().strip()
    state_name = _CODE_TO_STATE_NAME.get(norm_state, norm_state)

    # Load all preemption rules for this state in one query
    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            norm_state,
        )
        preemption_map = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_map = {}

    # Group requirements the same way as _filter_by_jurisdiction_priority
    by_key = {}
    for req in requirements:
        cat = req["category"] if isinstance(req, dict) else req.category
        rate_type = (
            req.get("rate_type")
            if isinstance(req, dict)
            else getattr(req, "rate_type", None)
        )
        cat_key = _normalize_category(cat)

        if cat_key == "minimum_wage":
            key = ("minimum_wage", rate_type or "general")
        else:
            title = req["title"] if isinstance(req, dict) else req.title
            jname = (
                req["jurisdiction_name"]
                if isinstance(req, dict)
                else getattr(req, "jurisdiction_name", None)
            )
            base = _base_title(title, jname)
            base_key = _normalize_title_key(base)
            key = (cat_key, base_key)

        by_key.setdefault(key, []).append(req)

    filtered = []
    for key, reqs in by_key.items():
        category = key[0]
        allows_local = preemption_map.get(category)

        if allows_local is False:
            # State preempts local: only keep state-level requirements
            state_reqs = [
                r
                for r in reqs
                if (
                    r["jurisdiction_level"]
                    if isinstance(r, dict)
                    else r.jurisdiction_level
                )
                == "state"
            ]
            if state_reqs:
                best = _pick_best_by_priority(state_reqs)
                if best:
                    filtered.append(best)
            else:
                # If preempted categories only have local-level rows, treat this as
                # a labeling issue from research and promote the strongest row to state.
                fallback = _pick_best_by_priority(reqs)
                if fallback:
                    original_level = (
                        fallback["jurisdiction_level"]
                        if isinstance(fallback, dict)
                        else getattr(fallback, "jurisdiction_level", None)
                    )
                    if isinstance(fallback, dict):
                        fallback["jurisdiction_level"] = "state"
                        fallback["jurisdiction_name"] = state_name
                        fallback["promoted_from_level"] = original_level
                        fallback["promotion_reason"] = "state_preemption_no_state_row"
                    else:
                        fallback.jurisdiction_level = "state"
                        fallback.jurisdiction_name = state_name
                        fallback.promoted_from_level = original_level
                        fallback.promotion_reason = "state_preemption_no_state_row"
                    filtered.append(fallback)
                    logger.warning(
                        "Category '%s' is preempted in %s but had no state-level "
                        "requirement — promoting local fallback (from '%s') to state.",
                        category, norm_state, original_level,
                    )
            continue

        # Not preempted (allows_local is True or None/unknown)
        # For wage categories: most-beneficial-to-employee (highest numeric value)
        if category == "minimum_wage":
            # Among all jurisdiction levels, pick the one with the highest rate
            reqs_with_num = [(r, _get_numeric_from_req(r)) for r in reqs]
            reqs_with_num_valid = [
                pair for pair in reqs_with_num if pair[1] is not None
            ]
            if reqs_with_num_valid:
                best = max(reqs_with_num_valid, key=lambda x: x[1])[0]
            else:
                best = _pick_best_by_priority(reqs)
            if best:
                filtered.append(best)
        else:
            # Non-wage: most local wins (existing behavior)
            best = _pick_best_by_priority(reqs)
            if best:
                filtered.append(best)

    return filtered




def evaluate_trigger_conditions(
    trigger_json: Optional[Dict[str, Any]],
    facility_attributes: Optional[Dict[str, Any]],
) -> bool:
    """Evaluate a trigger_conditions JSONB document against facility_attributes.

    Returns True if the trigger conditions are met, False otherwise.
    If trigger_json is None, the requirement has no trigger → always applies.
    If facility_attributes is None, treat all attribute checks as False.

    Supports: attribute, entity_type, and/or/not compounds.
    requirement_active / category_active are v2 — passthrough (return True).
    """
    if trigger_json is None:
        return True
    # Not every read path decodes JSONB: the hierarchical resolver's recursive
    # CTE hands `trigger_conditions` back as a str, and indexing it below raised
    # TypeError ("string indices must be integers") — a 500 for the whole view.
    if isinstance(trigger_json, str):
        try:
            trigger_json = json.loads(trigger_json)
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                "Trigger condition is unparseable JSON — treating as not matched."
            )
            return False
        if trigger_json is None:
            return True
    if not isinstance(trigger_json, dict):
        logger.warning(
            "Trigger condition is %s, expected an object — treating as not matched.",
            type(trigger_json).__name__,
        )
        return False
    if facility_attributes is None:
        facility_attributes = {}

    return _eval_condition(trigger_json, facility_attributes)




def _eval_condition(cond: Dict[str, Any], attrs: Dict[str, Any]) -> bool:
    """Recursively evaluate a single trigger condition node."""
    # Compound conditions
    if "op" in cond:
        op = cond["op"]
        children = cond.get("conditions", [])
        if op == "and":
            return all(_eval_condition(c, attrs) for c in children)
        elif op == "or":
            return any(_eval_condition(c, attrs) for c in children)
        elif op == "not":
            if children:
                return not _eval_condition(children[0], attrs)
            # `not` with nothing to negate is malformed — and it was the last
            # shape still failing OPEN, i.e. silently universalizing a
            # conditional obligation. _condition_shape_error rejects it at write
            # time on the scope-registry side; nothing gates it on the research
            # side, so fail closed here too.
            logger.warning(
                "Trigger condition has an empty 'not' — treating as not matched."
            )
            return False
        # An unrecognized op used to return True — which silently turned a
        # CONDITIONAL obligation into a universal one: every company got it.
        # `trigger_conditions` on jurisdiction_requirements are written by Gemini
        # research with NO shape gate (unlike scope-registry classifications,
        # which validate_proposal rejects), so a plausible model typo
        # ({"op": "greater_than"}, a leaf that says "op" where it means
        # "operator") is enough to serve e.g. the PSM standard to a bakery.
        # Fail closed and say so — the same convention this function already
        # uses for an unevaluable numeric comparison below.
        logger.warning(
            "Trigger condition has unknown op %r — treating as not matched. "
            "This requirement will NOT apply; fix the trigger_conditions JSON.",
            op,
        )
        return False

    # Leaf conditions
    ctype = cond.get("type")

    if ctype == "attribute":
        key = cond.get("key", "")
        operator = cond.get("operator", "eq")
        expected = cond.get("value")
        actual = attrs.get(key)

        if operator == "exists":
            return key in attrs
        if actual is None:
            return False
        if operator == "eq":
            return actual == expected
        if operator == "neq":
            return actual != expected
        if operator in ("gt", "gte", "lt", "lte"):
            # facility_attributes is user-edited JSONB — a numeric trigger vs a
            # string attr ("120" vs 100) must degrade to False, not TypeError
            # the whole compliance context.
            try:
                a = float(actual) if isinstance(actual, str) else actual
                e = float(expected) if isinstance(expected, str) else expected
                if operator == "gt":
                    return a > e
                if operator == "gte":
                    return a >= e
                if operator == "lt":
                    return a < e
                return a <= e
            except (TypeError, ValueError):
                logger.warning(
                    "Trigger comparison failed: %r %s %r (key=%s) — treating as not matched",
                    actual, operator, expected, key,
                )
                return False
        if operator == "in":
            return actual in (expected or [])
        if operator == "contains":
            if isinstance(actual, (list, set)):
                return expected in actual
            return False
        return False

    if ctype == "entity_type":
        value = cond.get("value")
        operator = cond.get("operator", "eq")
        entity = attrs.get("entity_type")
        if operator == "eq":
            return entity == value
        if operator == "in":
            return entity in (value if isinstance(value, list) else [value])
        return False

    # v2 chaining predicates — passthrough for now
    if ctype in ("requirement_active", "category_active"):
        return True

    # Unrecognized node shape. Same reasoning as the unknown-op branch above:
    # returning True here would universalize a conditional obligation on the
    # strength of malformed JSON.
    logger.warning(
        "Trigger condition has unknown type %r — treating as not matched. "
        "This requirement will NOT apply; fix the trigger_conditions JSON.",
        ctype,
    )
    return False




async def resolve_jurisdiction_stacks(
    conn: asyncpg.Connection, jurisdiction_ids: List[UUID]
) -> Dict[UUID, List[Dict[str, Any]]]:
    """Batched variant of resolve_jurisdiction_stack — one round trip for N leaves.

    Walks every hierarchy in one recursive CTE, carrying the leaf id through the
    recursion as root_id so results group cleanly. Precedence rules are scoped
    per-chain (a rule from one leaf's chain never leaks into another's).
    Returns {leaf_jurisdiction_id: rows ordered by category + depth (leaf first)}.
    """
    if not jurisdiction_ids:
        return {}
    # Dedupe while preserving order
    unique_ids = list(dict.fromkeys(jurisdiction_ids))
    query = """
        WITH RECURSIVE jurisdiction_chain AS (
            SELECT id, city, state, country_code, level::text AS level, display_name,
                   parent_id, authority_type, 0 AS depth, id AS root_id
            FROM jurisdictions WHERE id = ANY($1::uuid[])
            UNION ALL
            SELECT j.id, j.city, j.state, j.country_code, j.level::text, j.display_name,
                   j.parent_id, j.authority_type, jc.depth + 1, jc.root_id
            FROM jurisdictions j
            JOIN jurisdiction_chain jc ON j.id = jc.parent_id
            WHERE j.country_code = jc.country_code
        ),
        chain_requirements AS (
            SELECT jr.id, jr.jurisdiction_id, jr.requirement_key, jr.category,
                   jr.jurisdiction_level, jr.jurisdiction_name, jr.title,
                   jr.description, jr.current_value, jr.numeric_value,
                   jr.source_url, jr.source_url_status, jr.source_name, jr.effective_date,
                   jr.last_verified_at, jr.previous_value,
                   jr.previous_description, jr.change_status,
                   jr.last_changed_at, jr.expiration_date,
                   jr.requires_written_policy, jr.metadata,
                   jr.rate_type, jr.canonical_key, jr.statute_citation,
                   -- The other two thirds of the codified trio, so tenant-facing
                   -- callers can apply `is_codified_row` without a second query.
                   jr.citation_verified_at, jr.citation_item_id,
                   jr.status::text AS req_status, jr.category_id,
                   jr.trigger_conditions, jr.applicable_entity_types,
                   jc.level AS jur_level, jc.display_name AS jur_display_name,
                   jc.depth, jc.root_id
            FROM jurisdiction_requirements jr
            JOIN jurisdiction_chain jc ON jr.jurisdiction_id = jc.id
            -- Same world-time read as the flat path (_load_chain_requirements):
            -- an expired row is not law. Kept in step deliberately — the two
            -- paths render the same tab, so a row dropped from one and served by
            -- the other is a tab that disagrees with itself.
            WHERE jr.status = 'active'
              AND (jr.expiration_date IS NULL OR jr.expiration_date >= CURRENT_DATE)
        ),
        chain_precedence AS (
            SELECT jc_h.root_id, pr.id AS rule_id, pr.category_id AS rule_category_id,
                   pr.precedence_type::text AS precedence_type,
                   pr.reasoning_text, pr.legal_citation,
                   pr.trigger_condition, pr.applies_to_all_children,
                   pr.higher_jurisdiction_id, pr.lower_jurisdiction_id
            FROM precedence_rules pr
            JOIN jurisdiction_chain jc_h ON jc_h.id = pr.higher_jurisdiction_id
            WHERE pr.status = 'active'
              AND (
                  pr.applies_to_all_children = true
                  OR pr.lower_jurisdiction_id IN (
                      SELECT jc_l.id FROM jurisdiction_chain jc_l
                      WHERE jc_l.root_id = jc_h.root_id
                  )
              )
        )
        SELECT cr.*,
               cp.rule_id, cp.precedence_type,
               cp.reasoning_text AS rule_reasoning_text,
               cp.legal_citation AS rule_legal_citation,
               cp.trigger_condition AS rule_trigger_condition,
               cp.applies_to_all_children,
               cp.higher_jurisdiction_id AS rule_higher_jurisdiction_id,
               cp.lower_jurisdiction_id AS rule_lower_jurisdiction_id
        FROM chain_requirements cr
        LEFT JOIN chain_precedence cp
            ON cp.rule_category_id = cr.category_id
           AND cp.root_id = cr.root_id
        ORDER BY cr.root_id, cr.category, cr.depth ASC
    """
    rows = await conn.fetch(query, unique_ids)
    grouped: Dict[UUID, List[Dict[str, Any]]] = {jid: [] for jid in unique_ids}
    for row in rows:
        out = dict(row)
        # The pool sets no JSONB codec, so asyncpg hands every JSONB column back
        # as a str. Decode the two trigger columns HERE, at the single producer
        # of these rows, rather than at each consumer: the downstream readers
        # (evaluate_trigger_conditions, _compute_triggered_by) index them as
        # mappings, and raised on the string. `rule_trigger_condition` also goes
        # out verbatim on the hierarchical response, where a JSON-encoded string
        # is not what the shape promises.
        for col in ("trigger_conditions", "rule_trigger_condition"):
            value = out.get(col)
            if not isinstance(value, str):
                continue
            try:
                out[col] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Unparseable trigger — leave the raw value. Callers fail CLOSED
                # on a non-object (the requirement does not apply), which is the
                # convention for a malformed trigger everywhere else here.
                logger.warning(
                    "Requirement %s has unparseable %s.", out.get("id"), col
                )
        grouped[row["root_id"]].append(out)
    return grouped




async def resolve_jurisdiction_stack(
    conn: asyncpg.Connection, jurisdiction_id: UUID
) -> List[Dict[str, Any]]:
    """Walk the jurisdiction hierarchy from leaf to federal via recursive CTE.

    Returns all active requirements at each level in the chain, joined with
    matching precedence rules. Results ordered by category + depth (leaf first).
    Thin wrapper over resolve_jurisdiction_stacks for a single leaf.
    """
    grouped = await resolve_jurisdiction_stacks(conn, [jurisdiction_id])
    return grouped.get(jurisdiction_id, [])




def determine_governing_requirement(
    rows_by_category: Dict[str, List[Dict[str, Any]]],
    facility_attributes: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """For each category, determine the governing requirement based on precedence.

    Returns a list of dicts, one per category, each containing:
    - governing_requirement: the winning row
    - all_levels: all rows for this category
    - precedence_type: floor/ceiling/supersede/additive or None
    - governance_source: precedence_rule / default_local
    - reasoning_text, legal_citation from the matched rule

    ALL compliance intelligence is computed here. Frontend just renders results.
    """
    results = []

    for category, rows in rows_by_category.items():
        if not rows:
            continue

        # Filter by trigger conditions (evaluate against facility attributes).
        # The precedence LEFT JOIN fans out: a requirement matched by N rules
        # appears N times, differing only in rule_* columns. Dedupe requirement
        # rows by id (else all_levels carries duplicates and the single-level
        # render path is defeated), but keep every (row × rule) pairing as a
        # rule candidate so no matching rule is lost.
        active_rows: List[Dict[str, Any]] = []
        rule_candidates: List[Dict[str, Any]] = []
        seen_req_ids: set = set()
        depth_by_jur: Dict[Any, int] = {}
        for row in rows:
            trigger = row.get("trigger_conditions")
            if not evaluate_trigger_conditions(trigger, facility_attributes):
                continue
            if row.get("rule_id") is not None:
                rule_candidates.append(row)
            req_id = row.get("id")
            if req_id is None or req_id not in seen_req_ids:
                if req_id is not None:
                    seen_req_ids.add(req_id)
                active_rows.append(row)
            jur_id = row.get("jurisdiction_id")
            if jur_id is not None:
                depth_by_jur[jur_id] = row.get("depth", 0)

        if not active_rows:
            continue

        # Find the governing precedence rule. Specific (non-blanket) beats
        # blanket; among specific rules, the one pinned to the most local
        # lower jurisdiction (lowest depth) wins; ties resolve to the first
        # candidate in SQL order (deterministic).
        rule_row = None
        precedence_type = None
        best_score = None
        for row in rule_candidates:
            # Check trigger condition on the precedence rule itself
            rule_trigger = row.get("rule_trigger_condition")
            if not evaluate_trigger_conditions(rule_trigger, facility_attributes):
                continue
            is_specific = not row.get("applies_to_all_children")
            lower_depth = depth_by_jur.get(row.get("rule_lower_jurisdiction_id"), 999)
            score = (1 if is_specific else 0, -lower_depth)
            if best_score is None or score > best_score:
                best_score = score
                rule_row = row
                precedence_type = row.get("precedence_type")

        # Sort by depth (0 = leaf/local, higher = more general)
        sorted_rows = sorted(active_rows, key=lambda r: r.get("depth", 0))

        if precedence_type == "floor":
            # Highest value wins (most beneficial — typically min wage)
            rows_with_num = [
                (r, float(r["numeric_value"]))
                for r in sorted_rows
                if r.get("numeric_value") is not None
            ]
            if rows_with_num:
                governing = max(rows_with_num, key=lambda x: x[1])[0]
            else:
                governing = sorted_rows[0]  # most local
            governance_source = "precedence_rule"

        elif precedence_type == "ceiling":
            # The rule's higher jurisdiction caps the lower one — pick the row
            # belonging to that jurisdiction, not blindly the most general row
            # in the chain (a "state caps city" rule must not surface federal).
            target_jur = rule_row.get("rule_higher_jurisdiction_id") if rule_row else None
            governing = next(
                (r for r in sorted_rows if target_jur is not None
                 and r.get("jurisdiction_id") == target_jur),
                None,
            ) or sorted_rows[-1]
            governance_source = "precedence_rule"

        elif precedence_type == "supersede":
            # Lower jurisdiction completely replaces (most local)
            governing = sorted_rows[0]
            governance_source = "precedence_rule"

        elif precedence_type == "additive":
            # All levels apply — use most local as "governing" for display
            # but mark all as active
            governing = sorted_rows[0]
            governance_source = "precedence_rule"

        else:
            # No precedence rule — default to most local
            governing = sorted_rows[0]
            governance_source = "default_local"

        results.append({
            "category": category,
            "category_id": governing.get("category_id"),
            "governing_requirement": governing,
            "governing_level": governing.get("jur_level") or governing.get("jurisdiction_level"),
            "all_levels": sorted_rows,
            "precedence_type": precedence_type,
            "governance_source": governance_source,
            "reasoning_text": rule_row.get("rule_reasoning_text") if rule_row else None,
            "legal_citation": rule_row.get("rule_legal_citation") if rule_row else None,
            "rule_trigger_condition": rule_row.get("rule_trigger_condition") if rule_row else None,
            "rule_id": rule_row.get("rule_id") if rule_row else None,
        })

    return results




def _compute_triggered_by(
    trigger_conditions: Optional[Dict[str, Any]],
    facility_attributes: Optional[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Walk trigger condition tree and return activation dicts for the response.

    Returns None for universal requirements (no trigger), or a list of
    TriggerActivation-shaped dicts showing which conditions matched.
    """
    if trigger_conditions is None:
        return None

    activations: List[Dict[str, Any]] = []
    _collect_activations(trigger_conditions, facility_attributes or {}, activations)
    return activations or None




def _collect_activations(
    cond: Dict[str, Any],
    attrs: Dict[str, Any],
    out: List[Dict[str, Any]],
) -> None:
    """Recursively collect trigger activation results from a condition tree."""
    # Compound conditions — recurse into children
    if "op" in cond:
        for child in cond.get("conditions", []):
            _collect_activations(child, attrs, out)
        return

    ctype = cond.get("type")

    if ctype == "entity_type":
        value = cond.get("value")
        entity = attrs.get("entity_type")
        out.append({
            "trigger_type": "entity_type",
            "trigger_key": None,
            "trigger_value": value,
            "matched": entity == value,
        })

    elif ctype == "attribute":
        key = cond.get("key", "")
        operator = cond.get("operator", "eq")
        expected = cond.get("value")
        actual = attrs.get(key)
        matched = _eval_condition(cond, attrs)
        out.append({
            "trigger_type": "attribute",
            "trigger_key": key,
            "trigger_value": expected,
            "matched": matched,
        })
