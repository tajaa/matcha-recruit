"""Node mode & compliance mode — builds rich internal-data context for Matcha Work threads."""

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID

from ...database import get_connection
from ...core.compliance_registry import get_activated_profiles
from ...core.services.compliance_service import (
    determine_governing_requirement,
    resolve_jurisdiction_stacks,
)
from ...core.services.redis_cache import cache_get, cache_set, get_redis_cache

logger = logging.getLogger(__name__)


@dataclass
class ComplianceContextResult:
    """Holds both the text prompt for Gemini and the structured reasoning chains for storage."""
    context_text: str
    reasoning_chains: list[dict] | None = field(default=None)
    truncated: bool = False
    has_legacy_locations: bool = False


# ---------------------------------------------------------------------------
# Context cache — Redis-backed (shared across workers, TTL-bounded), with an
# in-process fallback when Redis is unavailable (tests, workers without it).
# Per-key locks prevent concurrent turns for one company from both rebuilding.
# ---------------------------------------------------------------------------

_CACHE_TTL = 120  # 2 minutes
_MAX_LOCAL_CACHE_ENTRIES = 256
_local_cache: dict[str, tuple[float, Any]] = {}
_build_locks: dict[str, asyncio.Lock] = {}

# Context size caps — compliance context is otherwise unbounded (M2).
_MAX_COMPLIANCE_LOCATIONS = 20
_MAX_COMPLIANCE_CONTEXT_CHARS = 60_000
_MAX_LEGACY_ROWS = 200


def _get_build_lock(key: str) -> asyncio.Lock:
    lock = _build_locks.get(key)
    if lock is None:
        lock = _build_locks.setdefault(key, asyncio.Lock())
    return lock


async def _ctx_cache_get(key: str) -> Any | None:
    redis = get_redis_cache()
    if redis is not None:
        return await cache_get(redis, key)
    entry = _local_cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


async def _ctx_cache_set(key: str, value: Any) -> None:
    redis = get_redis_cache()
    if redis is not None:
        await cache_set(redis, key, value, ttl=_CACHE_TTL)
        return
    if len(_local_cache) >= _MAX_LOCAL_CACHE_ENTRIES:
        oldest = min(_local_cache, key=lambda k: _local_cache[k][0])
        _local_cache.pop(oldest, None)
    _local_cache[key] = (time.time(), value)


async def build_node_context(company_id: UUID) -> str:
    """Fetch internal company data and format as AI context string."""
    cache_key = f"mw:node_ctx:{company_id}"
    cached = await _ctx_cache_get(cache_key)
    if isinstance(cached, str):
        return cached
    async with _get_build_lock(cache_key):
        cached = await _ctx_cache_get(cache_key)
        if isinstance(cached, str):
            return cached
        result = await _build_node_context_uncached(company_id)
        await _ctx_cache_set(cache_key, result)
        return result


async def _build_node_context_uncached(company_id: UUID) -> str:
    async with get_connection() as conn:
        # Aggregates over the FULL roster — totals and breakdowns must never
        # come from the display sample (a 500-employee company was being told
        # it has 50). One GROUPING SETS query: grand total + by-state + by-dept.
        emp_stats = await conn.fetch(
            """
            SELECT work_state, department, COUNT(*) AS n,
                   GROUPING(work_state) AS g_state, GROUPING(department) AS g_dept
            FROM employees
            WHERE org_id=$1 AND termination_date IS NULL
            GROUP BY GROUPING SETS ((work_state), (department), ())
            """,
            company_id,
        )
        employees = await conn.fetch(
            """
            SELECT first_name, last_name, job_title, department, work_state,
                   employment_type, start_date
            FROM employees
            WHERE org_id=$1 AND termination_date IS NULL
            ORDER BY start_date DESC NULLS LAST, last_name NULLS LAST, first_name NULLS LAST
            LIMIT 50
            """,
            company_id,
        )
        policies = await conn.fetch(
            """
            SELECT title, description, LEFT(content, 500) AS content,
                   COUNT(*) OVER () AS total_n
            FROM policies
            WHERE company_id=$1 AND status='active'
            ORDER BY title
            LIMIT 20
            """,
            company_id,
        )
        handbooks = await conn.fetch(
            """
            SELECT title, status, mode, COUNT(*) OVER () AS total_n
            FROM handbooks
            WHERE company_id=$1
            ORDER BY title
            LIMIT 10
            """,
            company_id,
        )
        er_cases = await conn.fetch(
            """
            SELECT case_number, title, status, category, COUNT(*) OVER () AS total_n
            FROM er_cases
            WHERE company_id=$1
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            company_id,
        )
        ir_incidents = await conn.fetch(
            """
            SELECT incident_number, title, incident_type, severity, status,
                   COUNT(*) OVER () AS total_n
            FROM ir_incidents
            WHERE company_id=$1
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
            company_id,
        )

    total_active = 0
    dept_counts: dict[str, int] = {}
    state_counts: dict[str, int] = {}
    for row in emp_stats:
        if row["g_state"] == 1 and row["g_dept"] == 1:
            total_active = row["n"]
        elif row["g_state"] == 0 and row["work_state"]:
            state_counts[row["work_state"]] = row["n"]
        elif row["g_dept"] == 0 and row["department"]:
            dept_counts[row["department"]] = row["n"]

    sections: list[str] = []

    # Instruction block
    sections.append(
        "=== NODE MODE: INTERNAL DATA CONTEXT ===\n"
        "You have access to the company's real internal data below. "
        "Reference this data when answering questions. "
        "Do NOT fabricate employee names, policy details, case numbers, or incident data. "
        "If the data below does not contain what the user asks about, say so."
    )

    # Employees — aggregates cover the full roster; the name listing is a sample.
    if total_active or employees:
        agg_parts = [f"Total active employees: {total_active}"]
        if dept_counts:
            dept_str = ", ".join(
                f"{k}: {v}" for k, v in sorted(dept_counts.items(), key=lambda x: -x[1])[:10]
            )
            agg_parts.append(f"By department: {dept_str}")
        if state_counts:
            # Every work state matters for compliance reasoning — list all.
            state_str = ", ".join(
                f"{k}: {v}" for k, v in sorted(state_counts.items(), key=lambda x: -x[1])
            )
            agg_parts.append(f"By work state: {state_str}")

        lines = []
        for e in employees:
            name = f"{e['first_name'] or ''} {e['last_name'] or ''}".strip()
            title = e["job_title"] or "N/A"
            dept = e["department"] or "N/A"
            state = e["work_state"] or "N/A"
            emp_type = e["employment_type"] or "N/A"
            start = str(e["start_date"]) if e["start_date"] else "N/A"
            lines.append(f"- {name} | {title} | {dept} | {state} | {emp_type} | Started {start}")

        emp_section = "\n--- EMPLOYEES ---\n" + " | ".join(agg_parts)
        if lines:
            if total_active > len(lines):
                emp_section += (
                    f"\nRoster sample (newest {len(lines)} of {total_active} — "
                    "the aggregates above cover everyone):"
                )
            emp_section += "\n" + "\n".join(lines)
        sections.append(emp_section)

    # Policies
    if policies:
        total_n = policies[0]["total_n"]
        lines = []
        for p in policies:
            title = p["title"] or "Untitled"
            desc = p["description"] or ""
            content = p["content"] or ""
            preview = (desc + " " + content).strip()[:300]
            lines.append(f"- {title}: {preview}")
        header = "\n--- ACTIVE POLICIES ---"
        if total_n > len(policies):
            header += f" (showing {len(policies)} of {total_n})"
        sections.append(header + "\n" + "\n".join(lines))

    # Handbooks
    if handbooks:
        total_n = handbooks[0]["total_n"]
        lines = []
        for h in handbooks:
            title = h["title"] or "Untitled"
            st = h["status"] or "N/A"
            mode = h["mode"] or "N/A"
            lines.append(f"- {title} | status: {st} | mode: {mode}")
        header = "\n--- HANDBOOKS ---"
        if total_n > len(handbooks):
            header += f" (showing {len(handbooks)} of {total_n})"
        sections.append(header + "\n" + "\n".join(lines))

    # ER Cases
    if er_cases:
        total_n = er_cases[0]["total_n"]
        lines = []
        for c in er_cases:
            num = c["case_number"] or "N/A"
            title = c["title"] or "Untitled"
            st = c["status"] or "N/A"
            cat = c["category"] or "N/A"
            lines.append(f"- {num}: {title} | {cat} | {st}")
        header = "\n--- ER CASES ---"
        if total_n > len(er_cases):
            header += f" (showing {len(er_cases)} most recent of {total_n})"
        sections.append(header + "\n" + "\n".join(lines))

    # IR Incidents
    if ir_incidents:
        total_n = ir_incidents[0]["total_n"]
        lines = []
        for i in ir_incidents:
            num = i["incident_number"] or "N/A"
            title = i["title"] or "Untitled"
            itype = i["incident_type"] or "N/A"
            sev = i["severity"] or "N/A"
            st = i["status"] or "N/A"
            lines.append(f"- {num}: {title} | {itype} | severity: {sev} | {st}")
        header = "\n--- IR INCIDENTS ---"
        if total_n > len(ir_incidents):
            header += f" (showing {len(ir_incidents)} most recent of {total_n})"
        sections.append(header + "\n" + "\n".join(lines))

    return "\n".join(sections)


async def build_compliance_context(company_id: UUID) -> ComplianceContextResult:
    """Build compliance context with full reasoning chains from jurisdiction_requirements.

    Uses the jurisdiction hierarchy (federal→state→city), trigger evaluation, and
    precedence resolution to produce an annotated context that Gemini can synthesize
    into layered compliance explanations.

    Returns a ComplianceContextResult with both the text prompt and structured reasoning chains.
    Locations without a jurisdiction_id fall back to the legacy compliance_requirements table.
    """
    cache_key = f"mw:compliance_ctx:{company_id}"
    cached = await _ctx_cache_get(cache_key)
    if isinstance(cached, dict) and "context_text" in cached:
        return ComplianceContextResult(
            context_text=cached["context_text"],
            reasoning_chains=cached.get("reasoning_chains"),
            truncated=bool(cached.get("truncated")),
            has_legacy_locations=bool(cached.get("has_legacy_locations")),
        )
    async with _get_build_lock(cache_key):
        cached = await _ctx_cache_get(cache_key)
        if isinstance(cached, dict) and "context_text" in cached:
            return ComplianceContextResult(
                context_text=cached["context_text"],
                reasoning_chains=cached.get("reasoning_chains"),
                truncated=bool(cached.get("truncated")),
                has_legacy_locations=bool(cached.get("has_legacy_locations")),
            )
        result = await _build_compliance_context_uncached(company_id)
        await _ctx_cache_set(cache_key, {
            "context_text": result.context_text,
            "reasoning_chains": result.reasoning_chains,
            "truncated": result.truncated,
            "has_legacy_locations": result.has_legacy_locations,
        })
        return result


async def _build_compliance_context_uncached(company_id: UUID) -> ComplianceContextResult:
    truncated = False
    async with get_connection() as conn:
        locations = await conn.fetch(
            """
            SELECT id, name, city, state, jurisdiction_id, facility_attributes
            FROM business_locations WHERE company_id = $1 AND is_active = true
            ORDER BY name NULLS LAST, city NULLS LAST
            """,
            company_id,
        )

        sections: list[str] = []
        sections.append(
            "=== COMPLIANCE MODE: JURISDICTION REQUIREMENTS WITH REASONING ===\n"
            "You have access to the company's compliance requirements organized by jurisdiction "
            "hierarchy with reasoning chains. When answering compliance questions:\n"
            "- Use the REGULATORY LAYERS to show which jurisdiction levels apply.\n"
            "- Explain WHY triggered requirements apply using the trigger explanations.\n"
            "- Show PRECEDENCE: floor=highest value wins, ceiling=state caps local, "
            "supersede=local replaces higher, additive=all levels stack.\n"
            "- CITE SOURCES with URLs and statute citations inline.\n"
            "- Distinguish baseline requirements (no trigger) from triggered additions.\n"
            "If the data below does not cover what the user asks about, suggest they run "
            "a compliance check to pull in the latest requirements."
        )

        reasoning_chains: list[dict] = []

        if not locations:
            sections.append(
                "\nNo active business locations found. "
                "Suggest the user add business locations and run a compliance check."
            )
        else:
            jurisdiction_locations = []
            legacy_locations = []
            for loc in locations:
                if loc["jurisdiction_id"]:
                    jurisdiction_locations.append(loc)
                else:
                    legacy_locations.append(loc)

            if len(jurisdiction_locations) > _MAX_COMPLIANCE_LOCATIONS:
                truncated = True
                sections.append(
                    f"\n(Context budget: showing {_MAX_COMPLIANCE_LOCATIONS} of "
                    f"{len(jurisdiction_locations)} locations — run per-location "
                    "compliance checks for the rest.)"
                )
                jurisdiction_locations = jurisdiction_locations[:_MAX_COMPLIANCE_LOCATIONS]

            # One round trip for every location's jurisdiction chain (was an
            # N+1 with duplicate queries for co-located sites).
            stacks_by_jurisdiction = await resolve_jurisdiction_stacks(
                conn, [loc["jurisdiction_id"] for loc in jurisdiction_locations]
            )

            # Process locations with jurisdiction hierarchy
            chars_used = 0
            for loc_idx, loc in enumerate(jurisdiction_locations):
                if chars_used > _MAX_COMPLIANCE_CONTEXT_CHARS:
                    truncated = True
                    remaining = len(jurisdiction_locations) - loc_idx
                    sections.append(
                        f"\n(Context budget reached — {remaining} more location"
                        f"{'s' if remaining != 1 else ''} omitted. Run per-location "
                        "compliance checks for details.)"
                    )
                    break
                facility_attrs = _parse_facility_attrs(loc["facility_attributes"])
                loc_label = f"{loc['name'] or 'Unknown'} ({loc['city'] or 'N/A'}, {loc['state'] or 'N/A'})"

                # Facility profile
                activated = get_activated_profiles(facility_attrs)
                profile_section = _format_facility_profile(loc_label, facility_attrs, activated)
                sections.append(profile_section)
                chars_used += len(profile_section)

                stack_rows = stacks_by_jurisdiction.get(loc["jurisdiction_id"], [])
                if not stack_rows:
                    sections.append(
                        f"\n--- REGULATORY LAYERS: {loc_label} ---\n"
                        "No jurisdiction requirements found. Suggest running a compliance check."
                    )
                    continue

                # Group by category and determine governing requirement
                # Parse JSON string trigger_conditions — asyncpg may return
                # JSONB as str depending on column type / driver config.
                by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
                for row in stack_rows:
                    tc = row.get("trigger_conditions")
                    if isinstance(tc, str):
                        try:
                            row["trigger_conditions"] = json.loads(tc)
                        except (json.JSONDecodeError, TypeError):
                            row["trigger_conditions"] = None
                    rtc = row.get("rule_trigger_condition")
                    if isinstance(rtc, str):
                        try:
                            row["rule_trigger_condition"] = json.loads(rtc)
                        except (json.JSONDecodeError, TypeError):
                            row["rule_trigger_condition"] = None
                    cat = row.get("category") or "uncategorized"
                    by_cat[cat].append(row)

                governed = determine_governing_requirement(by_cat, facility_attrs)

                # Format regulatory layers (limit 30 categories)
                if len(governed) > 30:
                    truncated = True
                lines = [f"\n--- REGULATORY LAYERS: {loc_label} ---"]
                for cat_result in governed[:30]:
                    lines.append(_format_category_reasoning(cat_result, facility_attrs))

                layers_section = "\n".join(lines)
                sections.append(layers_section)
                chars_used += len(layers_section)

                # Build structured reasoning chain for this location
                loc_chain = _build_location_reasoning_chain(
                    loc, loc_label, facility_attrs, activated, governed,
                )
                reasoning_chains.append(loc_chain)

            # Fallback: locations without jurisdiction_id use legacy table
            if legacy_locations:
                legacy_ids = [loc["id"] for loc in legacy_locations]
                legacy_rows = await conn.fetch(
                    """
                    SELECT cr.category, cr.title, cr.current_value,
                           cr.jurisdiction_name, cr.jurisdiction_level,
                           cr.effective_date, cr.source_url,
                           bl.city, bl.state, bl.name AS location_name,
                           COUNT(*) OVER () AS total_n
                    FROM compliance_requirements cr
                    JOIN business_locations bl ON cr.location_id = bl.id
                    WHERE bl.id = ANY($1)
                    ORDER BY bl.city, cr.category, cr.jurisdiction_level
                    LIMIT $2
                    """,
                    legacy_ids,
                    _MAX_LEGACY_ROWS,
                )
                if legacy_rows and legacy_rows[0]["total_n"] > len(legacy_rows):
                    truncated = True
                    sections.append(
                        f"\n(Legacy requirements capped at {len(legacy_rows)} of "
                        f"{legacy_rows[0]['total_n']}.)"
                    )

                if legacy_rows:
                    by_loc: Dict[str, list] = defaultdict(list)
                    for r in legacy_rows:
                        loc_key = f"{r['location_name'] or 'Unknown'} ({r['city'] or 'N/A'}, {r['state'] or 'N/A'})"
                        by_loc[loc_key].append(r)

                    for loc_name, reqs in by_loc.items():
                        loc_lines = [f"\n--- {loc_name} (legacy format) ---"]
                        by_lcat: Dict[str, list] = defaultdict(list)
                        for r in reqs:
                            by_lcat[r["category"] or "uncategorized"].append(r)

                        for cat, cat_reqs in by_lcat.items():
                            loc_lines.append(f"\n  [{cat}]")
                            for r in cat_reqs:
                                title = r["title"] or "Untitled"
                                value = r["current_value"] or "N/A"
                                level = r["jurisdiction_level"] or "N/A"
                                eff = str(r["effective_date"]) if r["effective_date"] else "N/A"
                                source = r["source_url"] or ""
                                entry = f"  - {title}: {value} (level: {level}, effective: {eff})"
                                if source:
                                    entry += f" [source: {source}]"
                                loc_lines.append(entry)

                        sections.append("\n".join(loc_lines))

    context_text = "\n".join(sections)
    return ComplianceContextResult(
        context_text=context_text,
        reasoning_chains=reasoning_chains if reasoning_chains else None,
        truncated=truncated,
        has_legacy_locations=bool(legacy_locations) if locations else False,
    )


# ---------------------------------------------------------------------------
# Compliance context formatting helpers
# ---------------------------------------------------------------------------

_MAX_DESC_LEN = 200


def _parse_facility_attrs(raw: Any) -> Dict[str, Any]:
    """Parse facility_attributes from DB (may be dict, JSON string, or None)."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _format_facility_profile(
    loc_label: str,
    facility_attrs: Dict[str, Any],
    activated_profiles: list,
) -> str:
    """Render the facility profile block showing entity type, payers, and active triggers."""
    lines = [f"\n--- FACILITY PROFILE: {loc_label} ---"]

    entity_type = facility_attrs.get("entity_type")
    if entity_type:
        lines.append(f"Entity Type: {entity_type}")

    payer_contracts = facility_attrs.get("payer_contracts")
    if payer_contracts and isinstance(payer_contracts, list):
        lines.append(f"Payer Contracts: {', '.join(payer_contracts)}")

    # Show other notable attributes
    for key, val in facility_attrs.items():
        if key not in ("entity_type", "payer_contracts") and val:
            val_str = ", ".join(val) if isinstance(val, list) else str(val)
            lines.append(f"{key}: {_truncate(val_str, 120)}")

    if activated_profiles:
        lines.append("Active Triggers:")
        for profile in activated_profiles:
            cats = ", ".join(profile.applicable_categories)
            lines.append(f"  - {profile.label}: {_explain_trigger(profile.trigger_condition, facility_attrs)} → activates: {cats}")
    else:
        lines.append("Active Triggers: none (baseline requirements only)")

    return "\n".join(lines)


def _format_category_reasoning(
    result: Dict[str, Any],
    facility_attrs: Dict[str, Any],
) -> str:
    """Render one category's decision path from determine_governing_requirement() output."""
    category = result["category"]
    all_levels = result["all_levels"]
    precedence_type = result.get("precedence_type")
    reasoning = result.get("reasoning_text")
    gov_level = result.get("governing_level") or "unknown"

    # Single-level categories: render flat (save tokens)
    if len(all_levels) == 1:
        row = all_levels[0]
        desc = _truncate(row.get("description") or row.get("current_value") or "", _MAX_DESC_LEN)
        trigger_str = _explain_trigger(row.get("trigger_conditions"), facility_attrs)
        source = _format_source(row)
        line = f"\n  [{category}] {row.get('title', 'Untitled')}: {desc}"
        if source:
            line += f" {source}"
        if trigger_str != "no trigger":
            line += f"\n    [trigger: {trigger_str}]"
        return line

    # Multi-level: full decision path
    lines = []
    prec_label = f" (precedence: {precedence_type})" if precedence_type else ""
    lines.append(f"\n  [{category}] Governing: {gov_level} level{prec_label}")
    if reasoning:
        lines.append(f"  Precedence reasoning: \"{reasoning}\"")
    lines.append("  Decision path:")

    for row in all_levels:
        level = row.get("jur_level") or row.get("jurisdiction_level") or "unknown"
        jur_name = row.get("jur_display_name") or row.get("jurisdiction_name") or ""
        title = row.get("title") or "Untitled"
        desc = _truncate(row.get("description") or row.get("current_value") or "", _MAX_DESC_LEN)
        statute = row.get("statute_citation") or ""
        source = _format_source(row)

        level_label = level.capitalize()
        if jur_name and jur_name.lower() != level.lower():
            level_label = f"{level.capitalize()} ({jur_name})"

        entry = f"    {level_label}: {title}"
        if desc:
            entry += f" — {desc}"
        if statute:
            entry += f" — {statute}"
        if source:
            entry += f" {source}"

        lines.append(entry)

        # Show trigger if this row has one
        trigger = row.get("trigger_conditions")
        if trigger is not None:
            trigger_str = _explain_trigger(trigger, facility_attrs)
            lines.append(f"      [trigger: {trigger_str}]")

    # Note if no triggers on any row
    has_any_trigger = any(r.get("trigger_conditions") is not None for r in all_levels)
    if not has_any_trigger:
        lines.append("  (No trigger — applies to all entity types)")

    # Surface change/expiry context for the governing requirement
    gov_row = next((r for r in all_levels if (r.get("jur_level") or r.get("jurisdiction_level")) == gov_level), None)
    if gov_row:
        prev = gov_row.get("previous_value")
        lca = gov_row.get("last_changed_at")
        if lca and prev:
            lca_str = lca.strftime("%Y-%m-%d") if hasattr(lca, "strftime") else str(lca)[:10]
            lines.append(f"  ⚠ RECENT CHANGE: Updated {lca_str} (was: {prev})")
        exp = gov_row.get("expiration_date")
        if exp:
            exp_str = exp.strftime("%Y-%m-%d") if hasattr(exp, "strftime") else str(exp)[:10]
            lines.append(f"  ⚠ EXPIRING: This requirement expires on {exp_str}")
        if gov_row.get("requires_written_policy"):
            lines.append("  📋 REQUIRES WRITTEN POLICY: Governing jurisdiction mandates a documented policy for this category")
        raw_meta = gov_row.get("metadata")
        if isinstance(raw_meta, str):
            try:
                raw_meta = json.loads(raw_meta)
            except Exception:
                raw_meta = None
        if isinstance(raw_meta, dict):
            pen = raw_meta.get("penalties") or {}
            if pen.get("summary"):
                agency = pen.get("enforcing_agency", "N/A")
                lines.append(f"  ⚖️ PENALTY: {pen['summary']} (enforced by {agency})")

    return "\n".join(lines)


def _explain_trigger(
    trigger_json: Optional[Dict[str, Any]],
    facility_attrs: Dict[str, Any],
) -> str:
    """Produce human-readable trigger explanation from compound trigger JSON."""
    if trigger_json is None:
        return "no trigger"

    return _explain_condition(trigger_json, facility_attrs)


def _explain_condition(cond: Dict[str, Any], attrs: Dict[str, Any]) -> str:
    """Recursively explain a trigger condition node."""
    # Compound conditions
    if "op" in cond:
        op = cond["op"]
        children = cond.get("conditions", [])
        if not children:
            return f"{op}()"
        parts = [_explain_condition(c, attrs) for c in children]
        if op == "not":
            return f"NOT ({parts[0]})"
        joiner = " AND " if op == "and" else " OR "
        return joiner.join(parts)

    ctype = cond.get("type")

    if ctype == "entity_type":
        value = cond.get("value")
        return f"entity_type is '{value}'"

    if ctype == "attribute":
        key = cond.get("key", "?")
        operator = cond.get("operator", "eq")
        expected = cond.get("value")

        if operator == "contains":
            return f"{key} includes '{expected}'"
        if operator == "eq":
            return f"{key} = '{expected}'"
        if operator == "neq":
            return f"{key} != '{expected}'"
        if operator == "in":
            return f"{key} in {expected}"
        if operator == "exists":
            return f"{key} is set"
        if operator in ("gt", "gte", "lt", "lte"):
            op_symbol = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[operator]
            return f"{key} {op_symbol} {expected}"
        return f"{key} {operator} {expected}"

    return str(cond)


def _format_source(row: Dict[str, Any]) -> str:
    """Format source URL and statute citation into a compact reference."""
    source_url = row.get("source_url") or ""
    source_name = row.get("source_name") or ""
    if source_url:
        if source_name:
            label = source_name
        else:
            parts = source_url.split("/")
            label = parts[2] if len(parts) > 2 else source_url
        return f"[source: {label}]"
    return ""


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _build_location_reasoning_chain(
    loc: dict,
    loc_label: str,
    facility_attrs: Dict[str, Any],
    activated_profiles: list,
    governed: List[Dict[str, Any]],
) -> dict:
    """Build structured reasoning chain for a single location."""
    categories = []
    for cat_result in governed[:30]:
        all_levels_structured = []
        for row in cat_result.get("all_levels", []):
            level = row.get("jur_level") or row.get("jurisdiction_level") or "unknown"
            jur_name = row.get("jur_display_name") or row.get("jurisdiction_name") or ""
            eff = row.get("effective_date")
            lva = row.get("last_verified_at")
            lca = row.get("last_changed_at")
            exp = row.get("expiration_date")
            all_levels_structured.append({
                "jurisdiction_level": level,
                "jurisdiction_name": jur_name if jur_name else level.capitalize(),
                "title": row.get("title") or "Untitled",
                "current_value": row.get("current_value") or row.get("description") or None,
                "numeric_value": _safe_float(row.get("numeric_value")),
                "source_url": row.get("source_url"),
                "statute_citation": row.get("statute_citation"),
                "trigger_condition": row.get("trigger_conditions"),
                "is_governing": (
                    (row.get("jur_level") or row.get("jurisdiction_level"))
                    == cat_result.get("governing_level")
                ),
                "effective_date": eff.isoformat() if hasattr(eff, "isoformat") else None,
                "last_verified_at": lva.isoformat() if hasattr(lva, "isoformat") else None,
                "previous_value": row.get("previous_value"),
                "last_changed_at": lca.isoformat() if hasattr(lca, "isoformat") else None,
                "expiration_date": exp.isoformat() if hasattr(exp, "isoformat") else None,
                "requires_written_policy": bool(row.get("requires_written_policy")),
                "penalty_summary": None,
                "enforcing_agency": None,
            })
            # Extract penalty data from metadata JSONB
            raw_meta = row.get("metadata")
            if isinstance(raw_meta, str):
                try:
                    raw_meta = json.loads(raw_meta)
                except Exception:
                    raw_meta = None
            if isinstance(raw_meta, dict):
                pen = raw_meta.get("penalties") or {}
                if pen.get("summary"):
                    all_levels_structured[-1]["penalty_summary"] = pen["summary"]
                if pen.get("enforcing_agency"):
                    all_levels_structured[-1]["enforcing_agency"] = pen["enforcing_agency"]

        gov_req = cat_result.get("governing_requirement") or {}
        categories.append({
            "category": cat_result["category"],
            "governing_level": cat_result.get("governing_level") or "unknown",
            "precedence_type": cat_result.get("precedence_type"),
            "reasoning_text": cat_result.get("reasoning_text"),
            "legal_citation": cat_result.get("legal_citation") or gov_req.get("statute_citation"),
            "all_levels": all_levels_structured,
        })

    return {
        "location_id": str(loc["id"]),
        "location_label": loc_label,
        "facility_attributes": facility_attrs if facility_attrs else None,
        "activated_profiles": [
            {"label": p.label, "categories": list(p.applicable_categories)}
            for p in activated_profiles
        ],
        "categories": categories,
    }


def _safe_float(val: Any) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
