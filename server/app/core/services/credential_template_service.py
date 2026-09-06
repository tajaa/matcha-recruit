"""Credential Requirement Template Service.

Resolves jurisdiction + role-specific credential requirements using a tiered strategy:
1. Company-specific templates
2. System-wide templates
3. Static fallback (credential_inference.py)
4. OpenAI Luna research (creates templates for future reuse)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

import httpx

from app.config import get_settings
from app.core.services.ai_usage import record_openai_response

logger = logging.getLogger(__name__)

_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_OPENAI_REQUEST_TIMEOUT_SECONDS = 55.0


def _openai_response_text(payload: dict[str, Any]) -> str:
    """Extract the assistant text from an OpenAI Responses payload."""
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"].strip()

    parts: list[str] = []
    for output in payload.get("output", []):
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for content in output.get("content", []):
            if (
                isinstance(content, dict)
                and content.get("type") == "output_text"
                and isinstance(content.get("text"), str)
            ):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _luna_credentials() -> tuple[str, str] | None:
    """Return the configured Luna API key and model, if both are available."""
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_luna_model:
        return None
    return settings.openai_api_key, settings.openai_luna_model


async def _generate_luna_text(
    prompt: str,
    *,
    api_key: str,
    model: str,
    max_output_tokens: int,
    json_output: bool,
) -> str:
    """Run one high-reasoning Luna request and record exact provider usage."""
    request_payload: dict[str, Any] = {
        "model": model,
        "input": prompt,
        "reasoning": {"effort": "high"},
        "service_tier": "default",
        "max_output_tokens": max_output_tokens,
    }
    if json_output:
        request_payload["text"] = {"format": {"type": "json_object"}}

    started = time.monotonic()
    usage_recorded = False
    try:
        async with httpx.AsyncClient(timeout=_OPENAI_REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                _OPENAI_RESPONSES_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=request_payload,
            )
            response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError("OpenAI Responses payload must be an object")
        await record_openai_response(
            model=model,
            latency_ms=int((time.monotonic() - started) * 1000),
            response=payload,
        )
        usage_recorded = True
        return _openai_response_text(payload)
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        if not usage_recorded:
            await record_openai_response(
                model=model,
                latency_ms=int((time.monotonic() - started) * 1000),
                error=str(exc),
                status="timeout" if isinstance(exc, httpx.TimeoutException) else "error",
            )
        raise


@dataclass
class ResolvedCredentialRequirement:
    credential_type_key: str
    credential_type_label: str
    credential_type_id: UUID
    is_required: bool = True
    due_days: int = 7
    priority: str = "standard"
    notes: str | None = None
    template_id: UUID | None = None
    source: str = "static_fallback"


# ── Role category matching ────────────────────────────────────────────


async def match_job_title_to_role_category(
    conn, job_title: str
) -> Optional[dict[str, Any]]:
    """Match a free-text job title to a role_category using DB patterns.

    Returns the role_category row dict, or None.
    """
    if not job_title or not job_title.strip():
        return None

    title = job_title.strip()

    rows = await conn.fetch(
        "SELECT id, key, label, match_patterns, is_clinical "
        "FROM role_categories ORDER BY sort_order"
    )

    for row in rows:
        patterns = row["match_patterns"]
        if not patterns:
            continue
        for pat in patterns:
            try:
                # DB stores Postgres-style \m/\M word boundaries — convert to Python \b
                py_pat = pat.replace(r"\m", r"\b").replace(r"\M", r"\b")
                if re.search(py_pat, title, re.IGNORECASE):
                    return dict(row)
            except re.error:
                logger.warning("Invalid regex in role_categories.key=%s: %s", row["key"], pat)
                continue

    # Luna fallback for unrecognized titles
    return await _classify_role_via_luna(conn, title, rows)


async def _classify_role_via_luna(
    conn, job_title: str, role_rows: list
) -> Optional[dict[str, Any]]:
    """Use OpenAI Luna to classify an unrecognized title into a role category."""
    try:
        credentials = _luna_credentials()
        if credentials is None:
            return None
        api_key, model = credentials

        categories = [{"key": r["key"], "label": r["label"]} for r in role_rows]
        prompt = (
            f"Given the job title \"{job_title}\", which of these role categories does it belong to?\n\n"
            f"Categories:\n{json.dumps(categories, indent=2)}\n\n"
            f"Return ONLY a JSON object with one string field named \"key\". "
            f"Use \"non_clinical\" if none fit."
        )

        response_text = await _generate_luna_text(
            prompt,
            api_key=api_key,
            model=model,
            max_output_tokens=512,
            json_output=True,
        )
        if not response_text or not response_text.strip():
            logger.warning("Luna returned no role classification for '%s'", job_title)
            return None

        try:
            data = json.loads(response_text)
        except (TypeError, json.JSONDecodeError):
            logger.warning("Luna returned invalid role classification for '%s'", job_title)
            return None
        key = data.get("key") if isinstance(data, dict) else None
        for r in role_rows:
            if r["key"] == key:
                return dict(r)

        return None
    except Exception:
        logger.exception("Luna role classification failed for '%s'", job_title)
        return None


# ── Template resolution (tiered) ─────────────────────────────────────


async def resolve_credential_requirements(
    conn,
    company_id: UUID,
    state: str | None,
    city: str | None,
    job_title: str | None,
) -> list[ResolvedCredentialRequirement]:
    """Main entry point. Resolves credential requirements for an employee.

    Tiered: company templates -> system templates -> static -> Luna research.
    """
    if not job_title:
        return []

    role_cat = await match_job_title_to_role_category(conn, job_title)
    if not role_cat:
        return []

    # Non-clinical roles: no credentials needed
    if not role_cat["is_clinical"]:
        return []

    if not state:
        # No jurisdiction info — fall back to static
        return await _resolve_from_static(conn, job_title)

    # Tier 1: Company-specific templates
    requirements = await _resolve_from_templates(conn, company_id, state, city, role_cat["id"])
    if requirements:
        return requirements

    # Tier 2: System-wide templates (company_id IS NULL)
    requirements = await _resolve_from_templates(conn, None, state, city, role_cat["id"])
    if requirements:
        return requirements

    # Tier 3: Static fallback
    static_reqs = await _resolve_from_static(conn, job_title)
    if static_reqs:
        return static_reqs

    # Tier 4: OpenAI Luna research (creates system-wide templates for reuse)
    return await _resolve_via_research(conn, state, city, role_cat)


async def _resolve_from_templates(
    conn,
    company_id: UUID | None,
    state: str,
    city: str | None,
    role_category_id: UUID,
) -> list[ResolvedCredentialRequirement]:
    """Query approved templates for a given scope."""
    if company_id is not None:
        rows = await conn.fetch(
            """
            SELECT crt.*, ct.key AS ct_key, ct.label AS ct_label
            FROM credential_requirement_templates crt
            JOIN scoped_credential_types ct ON ct.id = crt.credential_type_id
            WHERE crt.company_id = $1
              AND crt.state = $2
              AND crt.role_category_id = $3
              AND crt.is_active = true
              AND crt.review_status IN ('approved', 'auto_approved')
            ORDER BY ct.category, ct.label
            """,
            company_id, state, role_category_id,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT crt.*, ct.key AS ct_key, ct.label AS ct_label
            FROM credential_requirement_templates crt
            JOIN scoped_credential_types ct ON ct.id = crt.credential_type_id
            WHERE crt.company_id IS NULL
              AND crt.state = $1
              AND crt.role_category_id = $2
              AND crt.is_active = true
              AND crt.review_status IN ('approved', 'auto_approved')
            ORDER BY ct.category, ct.label
            """,
            state, role_category_id,
        )

    return [
        ResolvedCredentialRequirement(
            credential_type_key=r["ct_key"],
            credential_type_label=r["ct_label"],
            credential_type_id=r["credential_type_id"],
            is_required=r["is_required"],
            due_days=r["due_days"],
            priority=r["priority"],
            notes=r["notes"],
            template_id=r["id"],
            source="template",
        )
        for r in rows
    ]


async def _resolve_from_static(
    conn, job_title: str
) -> list[ResolvedCredentialRequirement]:
    """Fall back to the existing static mapping in credential_inference.py."""
    from .credential_inference import infer_from_static

    static = infer_from_static(job_title)
    if static is None or len(static) == 0:
        return []

    # Map static document_type keys to credential_types rows
    keys = [r.document_type for r in static]
    ct_rows = await conn.fetch(
        "SELECT id, key, label FROM scoped_credential_types WHERE key = ANY($1)",
        keys,
    )
    ct_map = {r["key"]: r for r in ct_rows}

    results = []
    for req in static:
        ct = ct_map.get(req.document_type)
        if not ct:
            continue
        results.append(
            ResolvedCredentialRequirement(
                credential_type_key=ct["key"],
                credential_type_label=ct["label"],
                credential_type_id=ct["id"],
                is_required=req.is_required,
                source="static_fallback",
            )
        )
    return results


async def _resolve_via_research(
    conn,
    state: str,
    city: str | None,
    role_cat: dict[str, Any],
) -> list[ResolvedCredentialRequirement]:
    """Research via Luna, create system-wide templates, return requirements."""
    await research_credential_requirements(
        conn, state, city, role_cat["id"], company_id=None
    )

    # Re-read the just-created templates (which have real IDs and review statuses)
    # Include auto_approved ones for immediate use; pending ones will be skipped
    # by _resolve_from_templates's filter, so we query directly here
    rows = await conn.fetch(
        """
        SELECT crt.id, crt.is_required, crt.due_days, crt.priority, crt.notes,
               ct.id AS ct_id, ct.key AS ct_key, ct.label AS ct_label
        FROM credential_requirement_templates crt
        JOIN scoped_credential_types ct ON ct.id = crt.credential_type_id
        WHERE crt.company_id IS NULL
          AND crt.state = $1
          AND crt.role_category_id = $2
          AND crt.is_active = true
          AND crt.review_status IN ('approved', 'auto_approved')
        ORDER BY ct.category, ct.label
        """,
        state, role_cat["id"],
    )

    return [
        ResolvedCredentialRequirement(
            credential_type_key=r["ct_key"],
            credential_type_label=r["ct_label"],
            credential_type_id=r["ct_id"],
            is_required=r["is_required"],
            due_days=r["due_days"],
            priority=r["priority"],
            notes=r["notes"],
            template_id=r["id"],
            source="ai_research",
        )
        for r in rows
    ]


# ── OpenAI Luna research ──────────────────────────────────────────────

_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


def _normalize_credential_label(value: Any) -> str:
    """Normalize labels for deterministic matching within a tenant catalog."""
    return " ".join(str(value or "").split()).casefold()


def _normalize_credential_category(value: Any) -> str:
    """Normalize the category vocabulary used by credential type rows."""
    return str(value or "").strip().casefold()


def _reconcile_tenant_credential_type(
    req: dict[str, Any],
    *,
    custom_by_key: dict[str, dict[str, Any]],
    custom_by_label: dict[str, list[dict[str, Any]]],
    visible_by_key: dict[str, dict[str, Any]],
) -> tuple[bool, dict[str, Any] | None]:
    """Resolve a model response to one of this tenant's custom types.

    The first return value tells the caller that the response was attempting to
    use a custom type (including an invalid attempt).  That distinction is
    important: an opaque ``custom_<uuid>`` key must never fall through to the
    global catalog insertion path.  Label matching is intentionally limited to
    a unique, category-matching tenant row and rejects a contradictory visible
    key, so a hallucinated label cannot bind a different tenant type.
    """
    key = str(req.get("credential_type_key") or "").strip()
    label = _normalize_credential_label(req.get("label"))
    category = _normalize_credential_category(req.get("category"))

    by_key = custom_by_key.get(key) if key else None
    if by_key is not None:
        matches_metadata = (
            bool(label)
            and bool(category)
            and label == _normalize_credential_label(by_key.get("label"))
            and category == _normalize_credential_category(by_key.get("category"))
        )
        return True, by_key if matches_metadata else None

    # A custom key is opaque and tenant-owned.  If it is not one of the
    # tenant's rows, do not create a same-key global type from model output.
    if key.startswith("custom_"):
        return True, None

    candidates = custom_by_label.get(label, []) if label else []
    if not candidates:
        return False, None

    # The database enforces this label uniqueness for tenant rows.  Treat
    # legacy duplicate data as ambiguous rather than choosing an arbitrary
    # credential type.
    if len(candidates) != 1:
        return True, None

    candidate = candidates[0]
    if not category or category != _normalize_credential_category(candidate.get("category")):
        return True, None

    # A known global key (or another visible tenant key) contradicts the
    # normalized-label match and must not be rebound to the custom row.
    keyed_visible = visible_by_key.get(key) if key else None
    if keyed_visible is not None and keyed_visible.get("id") != candidate.get("id"):
        return True, None

    return True, candidate


async def research_credential_requirements(
    conn,
    state: str,
    city: str | None,
    role_category_id: UUID,
    company_id: UUID | None = None,
    triggered_by: UUID | None = None,
) -> list[dict[str, Any]]:
    """Call OpenAI Luna to research jurisdiction-specific requirements.

    Creates credential_requirement_templates and returns the raw result list.
    """
    credentials = _luna_credentials()
    if credentials is None:
        logger.warning("OpenAI Luna is not configured; cannot research credentials")
        return []
    api_key, model = credentials

    role_cat = await conn.fetchrow(
        "SELECT key, label, is_clinical FROM role_categories WHERE id = $1",
        role_category_id,
    )
    if not role_cat:
        return []

    # Create research log
    log_id = await conn.fetchval(
        """
        INSERT INTO credential_research_logs
            (company_id, state, city, role_category_id, status, ai_model, triggered_by)
        VALUES ($1, $2, $3, $4, 'running', $5, $6)
        RETURNING id
        """,
        company_id, state, city, role_category_id, model, triggered_by,
    )

    try:
        # Tenant research may reuse that tenant's custom options, but must not
        # disclose or attach another company's catalog rows.
        ct_rows = [dict(row) for row in await conn.fetch(
            """SELECT id, key, label, category, company_id
               FROM scoped_credential_types
               WHERE company_id IS NULL OR company_id = $1
               ORDER BY company_id NULLS FIRST, key""",
            company_id,
        )]
        known_keys = {r["key"] for r in ct_rows}
        visible_by_key = {r["key"]: r for r in ct_rows}
        custom_rows = [
            row for row in ct_rows
            if company_id is not None and row.get("company_id") == company_id
        ]
        custom_by_key = {row["key"]: row for row in custom_rows}
        custom_by_label: dict[str, list[dict[str, Any]]] = {}
        for row in custom_rows:
            custom_by_label.setdefault(
                _normalize_credential_label(row.get("label")), []
            ).append(row)

        state_name = _STATE_NAMES.get(state, state)
        city_context = f"City: {city}" if city else ""
        custom_context = ""
        if custom_rows:
            custom_context = f"""
TENANT CUSTOM CREDENTIAL OPTIONS (only these options belong to this tenant):
{json.dumps([
    {"key": row["key"], "label": row["label"], "category": row["category"]}
    for row in custom_rows
], sort_keys=True)}
When using one of these options, return its exact key, its label, and its category.
Do not invent or alter a tenant custom key."""

        prompt = f"""You are a healthcare HR compliance expert specializing in credentialing requirements.

For the following jurisdiction and role, determine ALL credentials, licenses, certifications, clearances, and background checks that are REQUIRED or RECOMMENDED for employment.

JURISDICTION: {state_name} ({state})
{city_context}
ROLE: {role_cat['label']}
CLINICAL: {role_cat['is_clinical']}
{custom_context}

Research and return the COMPLETE list of credentialing requirements including:
1. State professional licenses (specific license type for this role in this state)
2. Federal registrations (DEA, NPI) — only if applicable to this role
3. Board certifications — only if typically required
4. Training certifications (BLS, ACLS, PALS, CPI) — be specific about which ones
5. Health clearances (TB test, Hepatitis B, flu vaccine, COVID vaccine, drug screening)
6. Background checks (state-specific: e.g., PA Act 33/34, CA LiveScan, NY fingerprinting)
7. Child/elder abuse clearances (if applicable in this state)
8. Malpractice insurance (if individually required)
9. Any STATE-SPECIFIC requirements unique to {state} (e.g., CA requires fingerprint LiveScan for healthcare workers; PA requires Act 33/34 clearances; NY requires infection control training)

For EACH requirement, return:
- credential_type_key: use one of these existing keys if it matches: {json.dumps(sorted(known_keys))}
  Otherwise, use a new snake_case identifier.
- label: human-readable name
- category: for a tenant custom option, return its exact category; otherwise use one of "clinical", "training", "clearance", "insurance", "federal", "background"
- is_required: true if legally mandatory, false if recommended/common
- priority: "blocking" (cannot start without), "standard" (must complete within onboarding), "optional"
- due_days: typical days from hire date to complete
- confidence: 0.0-1.0 how confident you are this is required
- notes: any jurisdiction-specific detail or statute citation

Return ONLY a JSON object: {{"requirements": [...]}}
Do NOT include requirements that don't apply to this role.
Do NOT fabricate requirements — if unsure, omit."""

        text = await _generate_luna_text(
            prompt,
            api_key=api_key,
            model=model,
            max_output_tokens=8192,
            json_output=True,
        )
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

        data = json.loads(text)
        requirements = data.get("requirements", [])

        # Store templates
        template_count = 0
        persisted_requirements: list[dict[str, Any]] = []
        for req in requirements:
            if not isinstance(req, dict):
                continue
            ct_key = req.get("credential_type_key", "")

            custom_attempt, custom_type = _reconcile_tenant_credential_type(
                req,
                custom_by_key=custom_by_key,
                custom_by_label=custom_by_label,
                visible_by_key=visible_by_key,
            )
            if custom_attempt and custom_type is None:
                logger.warning(
                    "Ignoring invalid or inaccessible tenant custom credential response: key=%r label=%r",
                    ct_key,
                    req.get("label"),
                )
                continue

            # A tenant custom type may be identified by its normalized label
            # even if Luna omitted the optional key field.  All global types
            # still require a key, as they did before tenant custom types.
            if custom_type is None and not ct_key:
                continue

            # Ensure credential_type exists.  Tenant custom types are resolved
            # from the scoped catalog above; this query preserves the existing
            # global/system lookup and insertion behavior for other keys.
            ct_id = custom_type["id"] if custom_type is not None else await conn.fetchval(
                """SELECT id FROM scoped_credential_types
                   WHERE key = $1 AND (company_id IS NULL OR company_id = $2)""",
                ct_key.strip() if isinstance(ct_key, str) else ct_key,
                company_id,
            )
            if not ct_id:
                # Create new credential type from AI result
                ct_id = await conn.fetchval(
                    """
                    INSERT INTO credential_types (key, label, category, is_system)
                    VALUES ($1, $2, $3, false)
                    ON CONFLICT (key) DO UPDATE SET label = EXCLUDED.label
                    RETURNING id
                    """,
                    ct_key,
                    req.get("label", ct_key),
                    req.get("category", "clearance"),
                )

            # Upsert template
            review_status = "auto_approved" if req.get("confidence", 0) >= 0.85 else "pending"
            await conn.execute(
                """
                INSERT INTO credential_requirement_templates
                    (company_id, state, city, role_category_id, credential_type_id,
                     is_required, due_days, priority, notes, source,
                     ai_research_id, ai_confidence, review_status)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'ai_research', $10, $11, $12)
                ON CONFLICT (company_id, state, city, role_category_id, credential_type_id)
                DO UPDATE SET
                    is_required = EXCLUDED.is_required,
                    due_days = EXCLUDED.due_days,
                    priority = EXCLUDED.priority,
                    notes = EXCLUDED.notes,
                    ai_research_id = EXCLUDED.ai_research_id,
                    ai_confidence = EXCLUDED.ai_confidence,
                    review_status = EXCLUDED.review_status,
                    updated_at = NOW()
                """,
                company_id, state, city, role_category_id, ct_id,
                req.get("is_required", True),
                req.get("due_days", 7),
                req.get("priority", "standard"),
                req.get("notes"),
                log_id,
                req.get("confidence"),
                review_status,
            )
            if custom_type is not None:
                req = {
                    **req,
                    "credential_type_key": custom_type["key"],
                    "label": custom_type["label"],
                    "category": custom_type["category"],
                }
            persisted_requirements.append(req)
            template_count += 1

        # Update research log
        await conn.execute(
            """
            UPDATE credential_research_logs
            SET status = 'completed', template_count = $1, completed_at = NOW()
            WHERE id = $2
            """,
            template_count, log_id,
        )

        return persisted_requirements

    except Exception as e:
        logger.exception("Credential research failed for %s/%s", state, role_cat["key"])
        await conn.execute(
            """
            UPDATE credential_research_logs
            SET status = 'failed', error_message = $1, completed_at = NOW()
            WHERE id = $2
            """,
            str(e), log_id,
        )
        return []


# ── Employee assignment ───────────────────────────────────────────────


async def materialize_uploaded_schedule_blocking_requirement(
    conn,
    *,
    company_id: UUID,
    employee_id: UUID,
    credential_type_key: str,
):
    """Create the evidence row implied by an uploaded blocking credential.

    Food-service employees do not necessarily pass through the clinical-role
    template resolver or a configured schedule job. An explicit upload of a
    curated schedule-blocking credential is therefore its own materialization
    signal. Preserve any existing verification evidence while making the
    requirement company-wide so scheduling cannot fail open.
    """
    return await conn.fetchrow(
        """
        WITH blocking_type AS (
            SELECT id, has_expiration
              FROM scoped_credential_types
             WHERE key = $3 AND COALESCE(schedule_blocking, false) = true
        ), upserted AS (
            INSERT INTO employee_credential_requirements
                (employee_id, credential_type_id, status, is_required,
                 priority, applies_company_wide)
            SELECT e.id, bt.id, 'pending', true, 'blocking', true
              FROM employees e CROSS JOIN blocking_type bt
             WHERE e.id = $1 AND e.org_id = $2
            ON CONFLICT (employee_id, credential_type_id) DO UPDATE SET
                is_required = true,
                priority = 'blocking',
                applies_company_wide = true,
                updated_at = NOW()
            RETURNING id, credential_type_id
        )
        SELECT u.id, bt.has_expiration
          FROM upserted u JOIN blocking_type bt ON bt.id=u.credential_type_id
        """,
        employee_id, company_id, credential_type_key,
    )


async def assign_credential_requirements_to_employee(
    conn,
    employee_id: UUID,
    company_id: UUID,
    requirements: list[ResolvedCredentialRequirement],
    start_date: date | None = None,
) -> int:
    """Create employee_credential_requirements and linked onboarding tasks.

    Returns the number of requirements created.
    """
    if not requirements:
        return 0

    base_date = start_date or date.today()
    count = 0

    for req in requirements:
        due = base_date + timedelta(days=req.due_days)

        # An employee can move into a role or jurisdiction with an existing
        # credential type. Reuse that requirement rather than creating an
        # orphan onboarding task, while updating the template that governs it.
        existing_id = await conn.fetchval(
            """SELECT id FROM employee_credential_requirements
               WHERE employee_id = $1 AND credential_type_id = $2
               FOR UPDATE""",
            employee_id, req.credential_type_id,
        )
        if existing_id:
            await conn.execute(
                """UPDATE employee_credential_requirements
                   SET template_id = $1, is_required = $2, priority = $3,
                       notes = $4, applies_company_wide = true, updated_at = NOW()
                   WHERE id = $5""",
                req.template_id, req.is_required, req.priority, req.notes, existing_id,
            )
            count += 1
            continue

        # Create onboarding task first (backward compat)
        task_id = await conn.fetchval(
            """
            INSERT INTO employee_onboarding_tasks
                (id, employee_id, title, description, category, is_employee_task,
                 due_date, status, document_type)
            VALUES (gen_random_uuid(), $1, $2, $3, 'credentials', TRUE, $4, 'pending', $5)
            RETURNING id
            """,
            employee_id,
            f"Upload {req.credential_type_label}",
            f"Upload your {req.credential_type_label.lower()} document for verification",
            due,
            req.credential_type_key,
        )

        # Create the credential requirement
        ecr_id = await conn.fetchval(
            """
            INSERT INTO employee_credential_requirements
                (employee_id, credential_type_id, template_id, status,
                 is_required, priority, due_date, onboarding_task_id, notes)
            VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7, $8)
            ON CONFLICT (employee_id, credential_type_id) DO NOTHING
            RETURNING id
            """,
            employee_id, req.credential_type_id, req.template_id,
            req.is_required, req.priority, due, task_id, req.notes,
        )

        # Link onboarding task back to credential requirement
        if ecr_id and task_id:
            await conn.execute(
                """
                UPDATE employee_onboarding_tasks
                SET credential_requirement_id = $1
                WHERE id = $2
                """,
                ecr_id, task_id,
            )

        count += 1

    return count


async def materialize_schedule_blocking_template(
    conn, *, company_id: UUID, template_id: UUID,
) -> int:
    """Attach an enabled schedule-blocking template to matching active staff.

    Requirement rows are normally created when an employee is onboarded. A
    blocking rule must also cover people already on the roster; otherwise the
    scheduler would treat their absence as an all-clear. Existing records keep
    their verification history while being associated with the newly activated
    template.
    """
    template = await conn.fetchrow(
        """
        SELECT crt.id, crt.state, crt.city, crt.role_category_id,
               crt.credential_type_id, crt.is_required, crt.priority, crt.due_days
        FROM credential_requirement_templates crt
        WHERE crt.id = $1 AND crt.is_active = true
          AND crt.schedule_blocking = true
          AND crt.review_status IN ('approved', 'auto_approved')
        """,
        template_id,
    )
    if not template:
        return 0

    employees = await conn.fetch(
        """
        SELECT e.id, e.start_date
        FROM employees e
        JOIN role_categories rc ON rc.id = $4
        WHERE e.org_id = $1 AND e.work_state = $2
          AND ($3::text IS NULL OR lower(e.work_city) = lower($3))
          AND COALESCE(e.employment_status, 'active') NOT IN ('terminated', 'offboarded', 'inactive')
          AND e.job_title IS NOT NULL
          AND e.job_title ~* ANY(rc.match_patterns)
        """,
        company_id, template["state"], template["city"], template["role_category_id"],
    )
    materialized = 0
    for employee in employees:
        due_date = (employee["start_date"] or date.today()) + timedelta(days=template["due_days"])
        await conn.execute(
            """
            INSERT INTO employee_credential_requirements
                (employee_id, credential_type_id, template_id, status, is_required, priority, due_date)
            VALUES ($1, $2, $3, 'pending', $4, $5, $6)
            ON CONFLICT (employee_id, credential_type_id) DO UPDATE SET
                template_id = EXCLUDED.template_id,
                is_required = EXCLUDED.is_required,
                priority = EXCLUDED.priority,
                applies_company_wide = true,
                updated_at = NOW()
            """,
            employee["id"], template["credential_type_id"], template["id"],
            template["is_required"], template["priority"], due_date,
        )
        materialized += 1
    return materialized


# ── Query helpers ─────────────────────────────────────────────────────


async def get_employee_credential_requirements(
    conn, employee_id: UUID, company_id: UUID
) -> list[dict[str, Any]]:
    """Fetch one tenant's credential requirements for one employee."""
    rows = await conn.fetch(
        """
        SELECT ecr.*, ct.key AS credential_type_key, ct.label AS credential_type_label,
               ct.category AS credential_type_category, ct.has_expiration, ct.has_number, ct.has_state
        FROM employee_credential_requirements ecr
        JOIN employees e ON e.id = ecr.employee_id AND e.org_id = $2
        JOIN scoped_credential_types ct ON ct.id = ecr.credential_type_id
        WHERE ecr.employee_id = $1
          AND (
              ecr.applies_company_wide = true
              OR EXISTS (
                  SELECT 1
                  FROM schedule_job_employees sje
                  JOIN schedule_job_credential_requirements jr
                    ON jr.job_id=sje.job_id AND jr.company_id=sje.company_id
                  WHERE sje.company_id=$2 AND sje.employee_id=ecr.employee_id
                    AND jr.credential_type_id=ecr.credential_type_id
                    AND jr.is_required
              )
          )
        ORDER BY ct.category, ct.label
        """,
        employee_id, company_id,
    )
    return [dict(r) for r in rows]


async def find_hidden_credential_types(
    conn, *, company_id: UUID, credential_type_ids: list[UUID]
) -> list[UUID]:
    """Return types unavailable because they are hidden or owned by another tenant.

    A company with no filter row has not configured one, so nothing is hidden.
    Callers pass only the ids they are *adding*: rules that predate the filter
    stay editable and removable, which is the whole point of hiding a type
    rather than deleting it.
    """
    if not credential_type_ids:
        return []
    rows = await conn.fetch(
        """
        SELECT ct.id
        FROM scoped_credential_types ct
        WHERE ct.id = ANY($2::uuid[])
          AND (
              (ct.company_id IS NOT NULL AND ct.company_id <> $1)
              OR (
                  (ct.company_id IS NULL OR ct.company_id = $1)
                  AND EXISTS (
                      SELECT 1 FROM company_credential_type_filters f WHERE f.company_id = $1
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM company_credential_type_filter_items item
                      WHERE item.company_id = $1 AND item.credential_type_id = ct.id
                  )
              )
          )
        """,
        company_id,
        list(credential_type_ids),
    )
    return [row["id"] for row in rows]


async def get_templates_for_scope(
    conn,
    state: str,
    role_category_id: UUID | None = None,
    company_id: UUID | None = None,
    include_pending: bool = False,
) -> list[dict[str, Any]]:
    """Fetch templates for a jurisdiction, optionally filtered by role and company."""
    status_filter = "('approved', 'auto_approved', 'pending')" if include_pending else "('approved', 'auto_approved')"

    conditions = ["crt.state = $1", "crt.is_active = true", f"crt.review_status IN {status_filter}"]
    params: list[Any] = [state]
    idx = 2

    if company_id is not None:
        conditions.append(f"(crt.company_id = ${idx} OR crt.company_id IS NULL)")
        params.append(company_id)
        idx += 1
    else:
        conditions.append("crt.company_id IS NULL")

    if role_category_id is not None:
        conditions.append(f"crt.role_category_id = ${idx}")
        params.append(role_category_id)
        idx += 1

    where = " AND ".join(conditions)

    rows = await conn.fetch(
        f"""
        SELECT crt.*, ct.key AS ct_key, ct.label AS ct_label, ct.category AS ct_category,
               rc.key AS role_key, rc.label AS role_label
        FROM credential_requirement_templates crt
        JOIN scoped_credential_types ct ON ct.id = crt.credential_type_id
        JOIN role_categories rc ON rc.id = crt.role_category_id
        WHERE {where}
        ORDER BY rc.sort_order, ct.category, ct.label
        """,
        *params,
    )
    return [dict(r) for r in rows]
