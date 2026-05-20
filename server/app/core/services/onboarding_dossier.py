"""Onboarding gap-analysis dossier — assemble + render.

The admin onboarding wizard captures everything needed to onboard a
compliance-complex company across several JSONB columns on
``onboarding_sessions``. This module assembles those scattered fields
into one durable, reviewable dossier and renders it to HTML (for the
PDF export) and markdown.

``build_gap_analysis_dossier`` is pure: it takes a session dict whose
JSONB fields are ALREADY parsed to dict/list (the caller resolves them
via ``_safe_jsonb`` first). No I/O, no json.loads — keeps it trivially
testable.
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timezone
from typing import Any


def _jurisdiction_label(item: dict[str, Any]) -> str:
    """Human label for a {state, county, city} tuple. 'Federal' when bare."""
    city = (item.get("city") or "").strip()
    county = (item.get("county") or "").strip()
    state = (item.get("state") or "").strip()
    parts = [p for p in (city, county, state) if p]
    return ", ".join(parts) if parts else "Federal"


def build_gap_analysis_dossier(session: dict[str, Any]) -> dict[str, Any]:
    """Assemble the full onboarding dossier from a pre-parsed session dict.

    Expects ``session`` keys: id, status, basics, size, locations,
    ai_scope, resolved_scope — with the JSONB ones already parsed to
    dict/list. Missing/None fields degrade to empty.
    """
    basics = session.get("basics") or {}
    size = session.get("size") or {}
    locations = session.get("locations") or []
    ai_scope = session.get("ai_scope") or {}
    resolved = session.get("resolved_scope") or {}

    covered = resolved.get("existing") or []
    gaps = resolved.get("missing") or []
    ambiguous = resolved.get("ambiguous") or []
    gap_check = resolved.get("gap_check") or {}

    certifications = ai_scope.get("required_certifications") or []
    licenses = ai_scope.get("required_licenses") or []

    suggestions_count = (
        len(gap_check.get("suggested_compliance_categories") or [])
        + len(gap_check.get("suggested_certifications") or [])
        + len(gap_check.get("suggested_licenses") or [])
        + len(gap_check.get("suggested_jurisdictions") or [])
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session_id": str(session.get("id")) if session.get("id") else None,
        "status": session.get("status"),
        "company": {
            "name": basics.get("business_name"),
            "industry": basics.get("industry"),
            "specialty": basics.get("specialty"),
            "description": basics.get("description"),
            "entity_type": basics.get("entity_type"),
            "owner_name": basics.get("owner_name"),
            "owner_email": basics.get("owner_email"),
        },
        "headcount": {
            "full_time": size.get("full_time", 0),
            "part_time": size.get("part_time", 0),
            "contractor": size.get("contractor", 0),
            "unknown": size.get("unknown", 0),
            "source": size.get("source"),
        },
        "locations": locations,
        "scope": {
            "naics_sector": ai_scope.get("naics_sector"),
            "compliance_categories": ai_scope.get("compliance_categories") or [],
            "required_certifications": certifications,
            "required_licenses": licenses,
            "applicable_jurisdictions": ai_scope.get("applicable_jurisdictions") or [],
        },
        "coverage": {
            "covered": covered,
            "gaps": gaps,
            "ambiguous": ambiguous,
        },
        "ai_suggestions": gap_check,
        "counts": {
            "covered": len(covered),
            "gaps": len(gaps),
            "ambiguous": len(ambiguous),
            "certifications": len(certifications),
            "licenses": len(licenses),
            "suggestions": suggestions_count,
        },
    }


# ── Markdown render ─────────────────────────────────────────────────────


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "_None_\n"
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        out.append("| " + " | ".join((c or "").replace("|", "\\|") for c in r) + " |")
    return "\n".join(out) + "\n"


def _dossier_to_markdown(d: dict[str, Any]) -> str:
    co = d.get("company") or {}
    hc = d.get("headcount") or {}
    cov = d.get("coverage") or {}
    counts = d.get("counts") or {}
    sug = d.get("ai_suggestions") or {}

    lines: list[str] = []
    lines.append(f"# Onboarding Gap Analysis — {co.get('name') or 'Untitled'}")
    lines.append("")
    lines.append(f"_Generated {d.get('generated_at', '')[:19]} · status: {d.get('status') or 'in progress'}_")
    lines.append("")
    lines.append(
        f"**Covered:** {counts.get('covered', 0)} · "
        f"**Gaps (need research):** {counts.get('gaps', 0)} · "
        f"**Ambiguous:** {counts.get('ambiguous', 0)} · "
        f"**AI suggestions:** {counts.get('suggestions', 0)}"
    )
    lines.append("")

    # Gaps first — the actionable deliverable.
    lines.append("## Gaps — need research")
    lines.append(_md_table(
        ["Category", "Scope", "Jurisdiction", "Why"],
        [[g.get("category_slug") or "", g.get("scope_level") or "",
          _jurisdiction_label(g), g.get("reason") or ""] for g in (cov.get("gaps") or [])],
    ))

    lines.append("## Ambiguous — need disambiguation")
    lines.append(_md_table(
        ["Why", "Candidates"],
        [[a.get("why") or "", str(len(a.get("candidates") or []))]
         for a in (cov.get("ambiguous") or [])],
    ))

    # AI safety-net suggestions.
    lines.append("## AI suggestions (safety-net pass)")
    if sug.get("summary"):
        lines.append(sug["summary"])
        lines.append("")
    lines.append("**Categories**")
    lines.append(_md_table(
        ["Category", "Scope", "Why"],
        [[s.get("category_slug") or "", s.get("scope") or "", s.get("reason") or ""]
         for s in (sug.get("suggested_compliance_categories") or [])],
    ))
    lines.append("**Certifications**")
    lines.append(_md_table(
        ["Slug", "Name", "Why"],
        [[s.get("slug") or "", s.get("name") or "", s.get("reason") or ""]
         for s in (sug.get("suggested_certifications") or [])],
    ))
    lines.append("**Licenses**")
    lines.append(_md_table(
        ["Slug", "Name", "Why"],
        [[s.get("slug") or "", s.get("name") or "", s.get("reason") or ""]
         for s in (sug.get("suggested_licenses") or [])],
    ))

    lines.append("## Covered — already in the compliance bank")
    lines.append(_md_table(
        ["Title", "Category", "Scope", "Jurisdiction"],
        [[c.get("title") or "", c.get("category_slug") or "", c.get("scope_level") or "",
          _jurisdiction_label(c)] for c in (cov.get("covered") or [])],
    ))

    scope = d.get("scope") or {}
    lines.append("## Certifications")
    lines.append(_md_table(
        ["Name", "Authority", "Scope", "Renewal (mo)"],
        [[c.get("name") or "", c.get("issuing_authority") or "", c.get("scope_level") or "",
          str(c.get("renewal_period_months") or "")] for c in (scope.get("required_certifications") or [])],
    ))
    lines.append("## Licenses")
    lines.append(_md_table(
        ["Name", "Authority", "Scope", "Renewal (mo)"],
        [[l.get("name") or "", l.get("issuing_authority") or "", l.get("scope_level") or "",
          str(l.get("renewal_period_months") or "")] for l in (scope.get("required_licenses") or [])],
    ))

    lines.append("## Jurisdictions in scope")
    lines.append(_md_table(
        ["Jurisdiction"],
        [[_jurisdiction_label(j)] for j in (scope.get("applicable_jurisdictions") or [])],
    ))

    lines.append("## Company profile")
    lines.append(f"- **Industry:** {co.get('industry') or '—'} / {co.get('specialty') or '—'}")
    lines.append(f"- **Entity type:** {co.get('entity_type') or '—'}")
    lines.append(f"- **Owner:** {co.get('owner_name') or '—'} ({co.get('owner_email') or '—'})")
    lines.append(
        f"- **Headcount:** FT {hc.get('full_time', 0)} · PT {hc.get('part_time', 0)} · "
        f"Contractor {hc.get('contractor', 0)} · Unknown {hc.get('unknown', 0)}"
    )
    if co.get("description"):
        lines.append(f"- **Description:** {co['description']}")
    lines.append("")
    lines.append("**Locations**")
    lines.append(_md_table(
        ["Name", "City", "County", "State"],
        [[loc.get("name") or "", loc.get("city") or "", loc.get("county") or "", loc.get("state") or ""]
         for loc in (d.get("locations") or [])],
    ))

    return "\n".join(lines)


# ── HTML render (for WeasyPrint PDF) ────────────────────────────────────


_PDF_STYLE = """
  @page { size: A4; margin: 50px 60px; }
  * { box-sizing: border-box; }
  body { font-family: 'Helvetica Neue', Arial, sans-serif; font-size: 10.5pt; line-height: 1.55; color: #1a1a1a; margin: 0; }
  h1 { font-size: 22pt; font-weight: 700; color: #0f172a; margin: 0 0 4px 0; }
  .meta { color: #64748b; font-size: 9pt; margin-bottom: 4px; }
  .title-rule { border: none; border-top: 3px solid #22c55e; margin: 10px 0 24px 0; }
  h2 { font-size: 13pt; font-weight: 600; color: #0f172a; margin: 26px 0 8px 0; padding-bottom: 5px; border-bottom: 1px solid #e2e8f0; }
  h3 { font-size: 10.5pt; font-weight: 600; color: #334155; margin: 14px 0 4px 0; }
  .counts { font-size: 10pt; color: #334155; margin: 6px 0 0 0; }
  .counts .gap { color: #b45309; font-weight: 700; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0 4px 0; font-size: 9pt; }
  th, td { border: 1px solid #e2e8f0; padding: 5px 8px; text-align: left; vertical-align: top; }
  th { background: #f8fafc; font-weight: 600; color: #0f172a; }
  .empty { color: #94a3b8; font-style: italic; font-size: 9pt; }
  ul { margin: 4px 0; padding-left: 18px; }
  .footer { margin-top: 36px; padding-top: 10px; border-top: 1px solid #e2e8f0; font-size: 8pt; color: #94a3b8; text-align: center; }
"""


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<div class="empty">None</div>'
    head = "".join(f"<th>{_html.escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_html.escape(c or '')}</td>" for c in r) + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _dossier_to_html(d: dict[str, Any]) -> str:
    co = d.get("company") or {}
    hc = d.get("headcount") or {}
    cov = d.get("coverage") or {}
    counts = d.get("counts") or {}
    sug = d.get("ai_suggestions") or {}
    scope = d.get("scope") or {}

    sections: list[str] = []

    sections.append("<h2>Gaps — need research</h2>")
    sections.append(_html_table(
        ["Category", "Scope", "Jurisdiction", "Why"],
        [[g.get("category_slug") or "", g.get("scope_level") or "",
          _jurisdiction_label(g), g.get("reason") or ""] for g in (cov.get("gaps") or [])],
    ))

    sections.append("<h2>Ambiguous — need disambiguation</h2>")
    sections.append(_html_table(
        ["Why", "Candidates"],
        [[a.get("why") or "", str(len(a.get("candidates") or []))]
         for a in (cov.get("ambiguous") or [])],
    ))

    sections.append("<h2>AI suggestions (safety-net pass)</h2>")
    if sug.get("summary"):
        sections.append(f"<p>{_html.escape(sug['summary'])}</p>")
    sections.append("<h3>Categories</h3>")
    sections.append(_html_table(
        ["Category", "Scope", "Why"],
        [[s.get("category_slug") or "", s.get("scope") or "", s.get("reason") or ""]
         for s in (sug.get("suggested_compliance_categories") or [])],
    ))
    sections.append("<h3>Certifications</h3>")
    sections.append(_html_table(
        ["Slug", "Name", "Why"],
        [[s.get("slug") or "", s.get("name") or "", s.get("reason") or ""]
         for s in (sug.get("suggested_certifications") or [])],
    ))
    sections.append("<h3>Licenses</h3>")
    sections.append(_html_table(
        ["Slug", "Name", "Why"],
        [[s.get("slug") or "", s.get("name") or "", s.get("reason") or ""]
         for s in (sug.get("suggested_licenses") or [])],
    ))

    sections.append("<h2>Covered — already in the compliance bank</h2>")
    sections.append(_html_table(
        ["Title", "Category", "Scope", "Jurisdiction"],
        [[c.get("title") or "", c.get("category_slug") or "", c.get("scope_level") or "",
          _jurisdiction_label(c)] for c in (cov.get("covered") or [])],
    ))

    sections.append("<h2>Certifications</h2>")
    sections.append(_html_table(
        ["Name", "Authority", "Scope", "Renewal (mo)"],
        [[c.get("name") or "", c.get("issuing_authority") or "", c.get("scope_level") or "",
          str(c.get("renewal_period_months") or "")] for c in (scope.get("required_certifications") or [])],
    ))
    sections.append("<h2>Licenses</h2>")
    sections.append(_html_table(
        ["Name", "Authority", "Scope", "Renewal (mo)"],
        [[l.get("name") or "", l.get("issuing_authority") or "", l.get("scope_level") or "",
          str(l.get("renewal_period_months") or "")] for l in (scope.get("required_licenses") or [])],
    ))

    sections.append("<h2>Jurisdictions in scope</h2>")
    sections.append(_html_table(
        ["Jurisdiction"],
        [[_jurisdiction_label(j)] for j in (scope.get("applicable_jurisdictions") or [])],
    ))

    sections.append("<h2>Company profile</h2>")
    profile = (
        f"<ul>"
        f"<li><strong>Industry:</strong> {_html.escape(co.get('industry') or '—')} / {_html.escape(co.get('specialty') or '—')}</li>"
        f"<li><strong>Entity type:</strong> {_html.escape(co.get('entity_type') or '—')}</li>"
        f"<li><strong>Owner:</strong> {_html.escape(co.get('owner_name') or '—')} ({_html.escape(co.get('owner_email') or '—')})</li>"
        f"<li><strong>Headcount:</strong> FT {hc.get('full_time', 0)} · PT {hc.get('part_time', 0)} · "
        f"Contractor {hc.get('contractor', 0)} · Unknown {hc.get('unknown', 0)}</li>"
        + (f"<li><strong>Description:</strong> {_html.escape(co['description'])}</li>" if co.get("description") else "")
        + "</ul>"
    )
    sections.append(profile)
    sections.append(_html_table(
        ["Name", "City", "County", "State"],
        [[loc.get("name") or "", loc.get("city") or "", loc.get("county") or "", loc.get("state") or ""]
         for loc in (d.get("locations") or [])],
    ))

    name = _html.escape(co.get("name") or "Untitled")
    counts_line = (
        f'Covered {counts.get("covered", 0)} · '
        f'<span class="gap">Gaps {counts.get("gaps", 0)}</span> · '
        f'Ambiguous {counts.get("ambiguous", 0)} · '
        f'AI suggestions {counts.get("suggestions", 0)}'
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>{_PDF_STYLE}</style></head><body>
<h1>Onboarding Gap Analysis — {name}</h1>
<div class="meta">Generated {_html.escape((d.get('generated_at') or '')[:19])} · status: {_html.escape(d.get('status') or 'in progress')}</div>
<div class="counts">{counts_line}</div>
<hr class="title-rule">
{''.join(sections)}
<div class="footer">Matcha — Onboarding Gap Analysis</div>
</body></html>"""
