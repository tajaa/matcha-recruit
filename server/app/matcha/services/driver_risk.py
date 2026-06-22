"""Driver-risk scoring + fleet view (gap-analysis #15).

Generalizes MVR tracking off the healthcare-only resident_care vertical into a
standalone surface for any employer with drivers — the cheapest beachhead into
commercial-auto exposure (the #1 auto underwriting input is driver/fleet risk).
Reuses the existing ``mvr_reviews`` table (now with scoring columns); resident_care
keeps its simpler currency view on the same rows.

Pure ``score_driver`` (unit-tested) + a DB ``build_fleet`` wrapper (never raises)
+ a deterministic insurer-facing PDF. Directional — driver-entered MVR data, not
a pulled motor-vehicle record (that needs a paid provider; future integration).
"""

import asyncio
import html
import logging
from uuid import UUID

from app.core.services.pdf import safe_url_fetcher

logger = logging.getLogger(__name__)

TIER_RANK = {"high_risk": 0, "marginal": 1, "clean": 2, "unknown": 3}


def score_driver(d: dict) -> dict:
    """Risk tier + points for one driver's MVR record. Pure.

    high_risk: suspended/expired license, a major violation (DUI/reckless), 2+
    at-fault accidents, or 4+ moving violations. marginal: any accident, any
    violation, a flagged review, or unknown license. else clean.
    """
    lic = (d.get("license_status") or "valid").lower()
    major = bool(d.get("major_violation"))
    viol = int(d.get("violation_count") or 0)
    acc = int(d.get("accident_count") or 0)
    status = d.get("status")

    if lic in ("suspended", "expired") or major or acc >= 2 or viol >= 4:
        tier = "high_risk"
    elif acc >= 1 or viol >= 1 or status == "flagged" or lic == "unknown":
        tier = "marginal"
    else:
        tier = "clean"

    points = viol + acc * 2 + (5 if major else 0) + (5 if lic in ("suspended", "expired") else 0)
    return {"tier": tier, "points": points}


def _fleet_grade(clean_pct: float, high_risk: int, total: int) -> str:
    """A–D fleet grade from clean share + high-risk presence."""
    if total == 0:
        return "n/a"
    if high_risk == 0 and clean_pct >= 85:
        return "A"
    if clean_pct >= 70 and high_risk <= max(1, total // 20):
        return "B"
    if clean_pct >= 50:
        return "C"
    return "D"


def summarize(drivers: list[dict]) -> dict:
    """Fleet rollup over scored driver rows."""
    total = len(drivers)
    counts = {"clean": 0, "marginal": 0, "high_risk": 0}
    overdue = 0
    for d in drivers:
        counts[d["tier"]] = counts.get(d["tier"], 0) + 1
        if d.get("overdue"):
            overdue += 1
    clean_pct = round(100 * counts["clean"] / total, 1) if total else 0.0
    return {
        "total_drivers": total,
        "clean": counts["clean"], "marginal": counts["marginal"], "high_risk": counts["high_risk"],
        "overdue_reviews": overdue,
        "clean_pct": clean_pct,
        "grade": _fleet_grade(clean_pct, counts["high_risk"], total),
    }


async def build_fleet(conn, company_id: UUID) -> dict:
    """Scored driver list + fleet summary for a company. Never raises."""
    company_name = "Client"
    rows: list[dict] = []
    try:
        company = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
        company_name = company["name"] if company else "Client"
        rows = [dict(r) for r in await conn.fetch(
            """SELECT id, driver_name, employee_id, review_type, review_date, status,
                      next_due_date, notes, violation_count, accident_count,
                      major_violation, license_status,
                      (next_due_date IS NOT NULL AND next_due_date < CURRENT_DATE) AS overdue
               FROM mvr_reviews WHERE company_id = $1
               ORDER BY driver_name""",
            company_id,
        )]
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("driver_risk.build_fleet fetch failed: %s", exc)

    drivers = []
    for r in rows:
        r["id"] = str(r["id"])
        if r.get("employee_id"):
            r["employee_id"] = str(r["employee_id"])
        for k in ("review_date", "next_due_date"):
            if r.get(k):
                r[k] = str(r[k])
        r.update(score_driver(r))
        drivers.append(r)
    drivers.sort(key=lambda d: (TIER_RANK.get(d["tier"], 3), -d["points"], d["driver_name"]))
    return {"company_id": str(company_id), "company_name": company_name,
            "drivers": drivers, "summary": summarize(drivers)}


# --- insurer-facing PDF -----------------------------------------------------

def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else "—"


_TIER_LABEL = {"clean": "CLEAN", "marginal": "MARGINAL", "high_risk": "HIGH RISK"}
_TIER_CLASS = {"clean": "good", "marginal": "warn", "high_risk": "bad"}


def _fleet_html(company_name: str, fleet: dict) -> str:
    s = fleet["summary"]
    rows = "".join(
        f"<tr><td>{_esc(d['driver_name'])}</td>"
        f"<td class='t {_TIER_CLASS.get(d['tier'], 'muted')}'>{_TIER_LABEL.get(d['tier'], d['tier'].upper())}</td>"
        f"<td>{_esc(d.get('license_status'))}</td>"
        f"<td class='r'>{_esc(d.get('violation_count'))}</td>"
        f"<td class='r'>{_esc(d.get('accident_count'))}</td>"
        f"<td>{'major' if d.get('major_violation') else ''}</td>"
        f"<td>{_esc(d.get('review_date') or '—')}</td>"
        f"<td>{'OVERDUE' if d.get('overdue') else _esc(d.get('next_due_date') or '—')}</td></tr>"
        for d in fleet["drivers"]
    ) or "<tr><td colspan='8'>No drivers on file.</td></tr>"
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
      body {{ font-family: -apple-system, Helvetica, sans-serif; color:#1a1a2e; padding:30px; font-size:11px; }}
      h1 {{ color:#1f8a5b; margin:0 0 2px; font-size:22px; }}
      .sub {{ color:#666; margin:0 0 16px; }}
      h2 {{ font-size:13px; border-bottom:2px solid #1f8a5b; padding-bottom:4px; margin:18px 0 8px; }}
      .grid {{ display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px; }}
      .cell {{ border:1px solid #e5e7eb; border-radius:8px; padding:8px 12px; min-width:90px; }}
      .cell .l {{ font-size:8px; text-transform:uppercase; letter-spacing:.6px; color:#888; }}
      .cell .v {{ font-size:18px; font-weight:300; font-family:monospace; margin-top:3px; }}
      table {{ width:100%; border-collapse:collapse; margin-top:4px; }}
      th {{ text-align:left; font-size:8px; text-transform:uppercase; color:#888; border-bottom:1px solid #ddd; padding:4px 6px; }}
      td {{ padding:4px 6px; border-bottom:1px solid #f0f0f0; }} td.r {{ text-align:right; font-family:monospace; }}
      .t {{ font-size:8px; font-weight:700; }} .t.good{{color:#1f8a5b}} .t.warn{{color:#b8902f}} .t.bad{{color:#b23b3b}} .t.muted{{color:#999}}
      .foot {{ margin-top:24px; color:#999; font-size:8px; border-top:1px solid #eee; padding-top:6px; }}
    </style></head><body>
      <h1>Driver Risk &amp; MVR Summary</h1>
      <p class="sub">{_esc(company_name)} — fleet driver-risk profile</p>
      <h2>Fleet — grade {_esc(s['grade'])}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Drivers</div><div class="v">{_esc(s['total_drivers'])}</div></div>
        <div class="cell"><div class="l">Clean</div><div class="v">{_esc(s['clean'])}</div></div>
        <div class="cell"><div class="l">Marginal</div><div class="v">{_esc(s['marginal'])}</div></div>
        <div class="cell"><div class="l">High risk</div><div class="v">{_esc(s['high_risk'])}</div></div>
        <div class="cell"><div class="l">Overdue MVR</div><div class="v">{_esc(s['overdue_reviews'])}</div></div>
      </div>
      <h2>Drivers</h2>
      <table><thead><tr><th>Driver</th><th>Tier</th><th>License</th><th class="r">Viol.</th><th class="r">Acc.</th>
        <th>Major</th><th>Last MVR</th><th>Next due</th></tr></thead><tbody>{rows}</tbody></table>
      <div class="foot">Prepared by Matcha. Driver-risk tiers are derived from employer-recorded MVR reviews
      (license status, moving violations, at-fault accidents, major violations) — directional, not a pulled
      motor-vehicle record. Present alongside the commercial-auto application.</div>
    </body></html>"""


async def render_fleet_pdf(company_name: str, fleet: dict) -> bytes:
    def _render() -> bytes:
        from weasyprint import HTML

        return HTML(string=_fleet_html(company_name, fleet), url_fetcher=safe_url_fetcher).write_pdf()

    return await asyncio.to_thread(_render)
