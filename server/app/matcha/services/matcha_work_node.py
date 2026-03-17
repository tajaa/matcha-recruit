"""Node mode — builds rich internal-data context for Matcha Work threads."""

import logging
import time
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

# TTL cache keyed by company_id — same pattern as _company_profile_cache
_node_context_cache: dict[str, tuple[float, str]] = {}
_NODE_CACHE_TTL = 120  # 2 minutes


async def build_node_context(company_id: UUID) -> str:
    """Fetch internal company data and format as AI context string."""
    cache_key = str(company_id)
    now = time.time()
    cached = _node_context_cache.get(cache_key)
    if cached and (now - cached[0]) < _NODE_CACHE_TTL:
        return cached[1]

    async with get_connection() as conn:
        employees = await conn.fetch(
            """
            SELECT first_name, last_name, job_title, department, work_state,
                   employment_type, start_date
            FROM employees
            WHERE org_id=$1 AND termination_date IS NULL
            LIMIT 50
            """,
            company_id,
        )
        policies = await conn.fetch(
            """
            SELECT title, description, LEFT(content, 500) AS content
            FROM policies
            WHERE company_id=$1 AND status='active'
            LIMIT 20
            """,
            company_id,
        )
        handbooks = await conn.fetch(
            """
            SELECT title, status, mode
            FROM handbooks
            WHERE company_id=$1
            LIMIT 10
            """,
            company_id,
        )
        er_cases = await conn.fetch(
            """
            SELECT case_number, title, status, category
            FROM er_cases
            WHERE company_id=$1
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            company_id,
        )
        ir_incidents = await conn.fetch(
            """
            SELECT incident_number, title, incident_type, severity, status
            FROM ir_incidents
            WHERE company_id=$1
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
            company_id,
        )

    sections: list[str] = []

    # Instruction block
    sections.append(
        "=== NODE MODE: INTERNAL DATA CONTEXT ===\n"
        "You have access to the company's real internal data below. "
        "Reference this data when answering questions. "
        "Do NOT fabricate employee names, policy details, case numbers, or incident data. "
        "If the data below does not contain what the user asks about, say so."
    )

    # Employees
    if employees:
        dept_counts: dict[str, int] = {}
        state_counts: dict[str, int] = {}
        lines = []
        for e in employees:
            name = f"{e['first_name'] or ''} {e['last_name'] or ''}".strip()
            title = e["job_title"] or "N/A"
            dept = e["department"] or "N/A"
            state = e["work_state"] or "N/A"
            emp_type = e["employment_type"] or "N/A"
            start = str(e["start_date"]) if e["start_date"] else "N/A"
            lines.append(f"- {name} | {title} | {dept} | {state} | {emp_type} | Started {start}")
            if dept != "N/A":
                dept_counts[dept] = dept_counts.get(dept, 0) + 1
            if state != "N/A":
                state_counts[state] = state_counts.get(state, 0) + 1

        agg_parts = [f"Total active: {len(employees)}"]
        if dept_counts:
            dept_str = ", ".join(f"{k}: {v}" for k, v in sorted(dept_counts.items(), key=lambda x: -x[1])[:10])
            agg_parts.append(f"By department: {dept_str}")
        if state_counts:
            state_str = ", ".join(f"{k}: {v}" for k, v in sorted(state_counts.items(), key=lambda x: -x[1])[:10])
            agg_parts.append(f"By state: {state_str}")

        sections.append(
            "\n--- EMPLOYEES ---\n"
            + " | ".join(agg_parts) + "\n"
            + "\n".join(lines)
        )

    # Policies
    if policies:
        lines = []
        for p in policies:
            title = p["title"] or "Untitled"
            desc = p["description"] or ""
            content = p["content"] or ""
            preview = (desc + " " + content).strip()[:300]
            lines.append(f"- {title}: {preview}")
        sections.append("\n--- ACTIVE POLICIES ---\n" + "\n".join(lines))

    # Handbooks
    if handbooks:
        lines = []
        for h in handbooks:
            title = h["title"] or "Untitled"
            st = h["status"] or "N/A"
            mode = h["mode"] or "N/A"
            lines.append(f"- {title} | status: {st} | mode: {mode}")
        sections.append("\n--- HANDBOOKS ---\n" + "\n".join(lines))

    # ER Cases
    if er_cases:
        lines = []
        for c in er_cases:
            num = c["case_number"] or "N/A"
            title = c["title"] or "Untitled"
            st = c["status"] or "N/A"
            cat = c["category"] or "N/A"
            lines.append(f"- {num}: {title} | {cat} | {st}")
        sections.append("\n--- ER CASES ---\n" + "\n".join(lines))

    # IR Incidents
    if ir_incidents:
        lines = []
        for i in ir_incidents:
            num = i["incident_number"] or "N/A"
            title = i["title"] or "Untitled"
            itype = i["incident_type"] or "N/A"
            sev = i["severity"] or "N/A"
            st = i["status"] or "N/A"
            lines.append(f"- {num}: {title} | {itype} | severity: {sev} | {st}")
        sections.append("\n--- IR INCIDENTS ---\n" + "\n".join(lines))

    result = "\n".join(sections)
    _node_context_cache[cache_key] = (now, result)
    return result
