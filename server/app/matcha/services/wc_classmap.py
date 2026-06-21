"""WC class-code auto-map — derive class exposures from the company's employees
instead of broker hand-entry. Groups employees by job title (headcount +
annualized payroll from pay_rate), then Gemini maps each title to an NCCI class
from the reference table. Best-effort; unmapped titles surface for review. The
caller confirms before anything is written.
"""

import asyncio
import json
import logging
from typing import Optional
from uuid import UUID

from app.config import get_settings
from app.matcha.services.ir_analysis import IRAnalyzer
from . import wc_depth

logger = logging.getLogger(__name__)

_analyzer: Optional[IRAnalyzer] = None

# annualize pay_rate → yearly payroll (hourly × 2080; exempt/salary already annual)
_ANNUALIZE = (
    "CASE WHEN pay_classification ILIKE 'hour%' THEN pay_rate*2080 "
    "WHEN pay_classification ILIKE 'exempt' OR pay_classification ILIKE 'salar%' THEN pay_rate "
    "WHEN pay_rate < 2000 THEN pay_rate*2080 ELSE pay_rate END"
)


def _get_analyzer() -> IRAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = IRAnalyzer(api_key=get_settings().gemini_api_key)
    return _analyzer


async def employee_groups(conn, company_id: UUID) -> list[dict]:
    """Distinct job titles → headcount + annualized payroll, from employees (org_id = company)."""
    rows = await conn.fetch(
        f"""
        SELECT COALESCE(NULLIF(TRIM(job_title), ''), '(untitled)') AS title,
               COUNT(*) AS headcount,
               ROUND(COALESCE(SUM({_ANNUALIZE}), 0)::numeric, 0) AS payroll
        FROM employees
        WHERE org_id = $1
          AND COALESCE(employment_status, 'active') NOT ILIKE 'term%'
        GROUP BY title
        ORDER BY headcount DESC
        """,
        company_id,
    )
    return [{"title": r["title"], "headcount": int(r["headcount"]), "payroll": float(r["payroll"] or 0)} for r in rows]


async def _ai_map_titles(titles: list[str], codes: list[dict]) -> dict[str, str]:
    """Map each job title → an NCCI class_code from the reference list. {} on failure."""
    if not titles or not codes:
        return {}
    ref = "\n".join(f"{c['class_code']}: {c['description']}" for c in codes)
    prompt = (
        "Map each employee JOB TITLE to the single best-fitting NCCI workers'-comp CLASS CODE "
        "from the reference list. Use only codes from the list. If none fits, use null.\n\n"
        f"Reference class codes:\n{ref}\n\n"
        f"Job titles (JSON array): {json.dumps(titles)}\n\n"
        'Return ONLY valid JSON: {"<title>": "<class_code or null>", ...} covering every title.'
    )
    analyzer = _get_analyzer()
    try:
        resp = await asyncio.wait_for(
            analyzer.client.aio.models.generate_content(model=analyzer.model, contents=prompt),
            timeout=45,
        )
        payload = analyzer._parse_json_response((getattr(resp, "text", None) or "").strip()) or {}
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as exc:
        logger.warning("class-map AI failed: %s", exc)
        return {}
    valid = {c["class_code"] for c in codes}
    return {t: payload[t] for t in titles if isinstance(payload.get(t), str) and payload[t] in valid}


async def auto_map(conn, company_id: UUID) -> dict:
    """Proposed class exposures from the workforce. No write — caller confirms.
    Returns {proposed:[{class_code,description,state,payroll,headcount}], unmapped:[title], source}."""
    groups = await employee_groups(conn, company_id)
    if not groups:
        return {"proposed": [], "unmapped": [], "employee_count": 0}
    codes = await wc_depth.list_class_codes(conn)
    states = await wc_depth.resolve_company_states(conn, company_id)
    primary = states[0] if states else "US"
    mapping = await _ai_map_titles([g["title"] for g in groups], codes)
    desc = {c["class_code"]: c["description"] for c in codes}

    proposed: dict[str, dict] = {}
    unmapped: list[str] = []
    for g in groups:
        cc = mapping.get(g["title"])
        if not cc:
            unmapped.append(g["title"])
            continue
        p = proposed.setdefault(cc, {"class_code": cc, "description": desc.get(cc),
                                     "state": primary, "payroll": 0.0, "headcount": 0})
        p["payroll"] += g["payroll"]
        p["headcount"] += g["headcount"]
    out = [{**p, "payroll": round(p["payroll"])} for p in proposed.values()]
    out.sort(key=lambda r: r["payroll"], reverse=True)
    return {"proposed": out, "unmapped": unmapped, "employee_count": sum(g["headcount"] for g in groups)}
