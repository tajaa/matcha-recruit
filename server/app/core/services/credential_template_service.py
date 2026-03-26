"""Credential Requirement Template Service.

Resolves jurisdiction + role-specific credential requirements using a tiered strategy:
1. Company-specific templates
2. System-wide templates
3. Static fallback (credential_inference.py)
4. Gemini AI research (creates templates for future reuse)
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


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

    # Gemini fallback for unrecognized titles
    return await _classify_role_via_gemini(conn, title, rows)


async def _classify_role_via_gemini(
    conn, job_title: str, role_rows: list
) -> Optional[dict[str, Any]]:
    """Use Gemini to classify an unrecognized job title into a role category."""
    try:
        from google import genai
        from google.genai import types

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None

        categories = [{"key": r["key"], "label": r["label"]} for r in role_rows]
        prompt = (
            f"Given the job title \"{job_title}\", which of these role categories does it belong to?\n\n"
            f"Categories:\n{json.dumps(categories, indent=2)}\n\n"
            f"Return ONLY the category key as a plain string. "
            f"If none fit, return \"non_clinical\"."
        )

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=64),
        )

        key = response.text.strip().strip('"').strip("'")
        for r in role_rows:
            if r["key"] == key:
                return dict(r)

        return None
    except Exception:
        logger.exception("Gemini role classification failed for '%s'", job_title)
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

    Tiered: company templates -> system templates -> static -> Gemini research.
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

    # Tier 4: Gemini AI research (creates system-wide templates for reuse)
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
            JOIN credential_types ct ON ct.id = crt.credential_type_id
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
            JOIN credential_types ct ON ct.id = crt.credential_type_id
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
        "SELECT id, key, label FROM credential_types WHERE key = ANY($1)",
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
    """Research via Gemini, create system-wide templates, return requirements."""
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
        JOIN credential_types ct ON ct.id = crt.credential_type_id
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


# ── Gemini AI research ────────────────────────────────────────────────

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


async def research_credential_requirements(
    conn,
    state: str,
    city: str | None,
    role_category_id: UUID,
    company_id: UUID | None = None,
    triggered_by: UUID | None = None,
) -> list[dict[str, Any]]:
    """Call Gemini to research jurisdiction-specific credential requirements.

    Creates credential_requirement_templates and returns the raw result list.
    """
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set, cannot research credentials")
        return []

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
        VALUES ($1, $2, $3, $4, 'running', 'gemini-2.0-flash', $5)
        RETURNING id
        """,
        company_id, state, city, role_category_id, triggered_by,
    )

    try:
        # Load existing credential type keys for normalization
        ct_rows = await conn.fetch("SELECT key FROM credential_types")
        known_keys = {r["key"] for r in ct_rows}

        state_name = _STATE_NAMES.get(state, state)
        city_context = f"City: {city}" if city else ""

        prompt = f"""You are a healthcare HR compliance expert specializing in credentialing requirements.

For the following jurisdiction and role, determine ALL credentials, licenses, certifications, clearances, and background checks that are REQUIRED or RECOMMENDED for employment.

JURISDICTION: {state_name} ({state})
{city_context}
ROLE: {role_cat['label']}
CLINICAL: {role_cat['is_clinical']}

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
- category: one of "clinical", "training", "clearance", "insurance", "federal", "background"
- is_required: true if legally mandatory, false if recommended/common
- priority: "blocking" (cannot start without), "standard" (must complete within onboarding), "optional"
- due_days: typical days from hire date to complete
- confidence: 0.0-1.0 how confident you are this is required
- notes: any jurisdiction-specific detail or statute citation

Return ONLY a JSON object: {{"requirements": [...]}}
Do NOT include requirements that don't apply to this role.
Do NOT fabricate requirements — if unsure, omit."""

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[types.Content(parts=[types.Part.from_text(text=prompt)])],
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=4096),
        )

        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[: text.rfind("```")]
        text = text.strip()

        data = json.loads(text)
        requirements = data.get("requirements", [])

        # Store templates
        template_count = 0
        for req in requirements:
            ct_key = req.get("credential_type_key", "")
            if not ct_key:
                continue

            # Ensure credential_type exists
            ct_id = await conn.fetchval(
                "SELECT id FROM credential_types WHERE key = $1", ct_key
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

        return requirements

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


# ── Query helpers ─────────────────────────────────────────────────────


async def get_employee_credential_requirements(
    conn, employee_id: UUID
) -> list[dict[str, Any]]:
    """Fetch all credential requirements for an employee with type info."""
    rows = await conn.fetch(
        """
        SELECT ecr.*, ct.key AS credential_type_key, ct.label AS credential_type_label,
               ct.category AS credential_type_category, ct.has_expiration, ct.has_number, ct.has_state
        FROM employee_credential_requirements ecr
        JOIN credential_types ct ON ct.id = ecr.credential_type_id
        WHERE ecr.employee_id = $1
        ORDER BY ct.category, ct.label
        """,
        employee_id,
    )
    return [dict(r) for r in rows]


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
        JOIN credential_types ct ON ct.id = crt.credential_type_id
        JOIN role_categories rc ON rc.id = crt.role_category_id
        WHERE {where}
        ORDER BY rc.sort_order, ct.category, ct.label
        """,
        *params,
    )
    return [dict(r) for r in rows]
