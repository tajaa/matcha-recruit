"""Full-detail fetchers + deterministic appendix sections — one query per
cited record, rendered from DB rows, never from model text. Includes the
chain-of-custody trails and the appendix-section registry."""

import json

from ...claims_readiness import _esc, _fmt_dt
from ._shared import _emp_name, _hum


_AUDIT_ACTION_LABELS = {
    "create": "Matter created",
    "update": "Matter updated",
    "message": "Chat message ({role})",
    "generate_packet": "Packet generated ({kind})",
    "export": "Packet downloaded",
    "share": "Share link created",
    "shared_download": "Downloaded via share link",
    "research": "External legal research run",
}


def _describe_audit(row: dict, labels: dict | None = _AUDIT_ACTION_LABELS) -> str:
    """Human phrase for one audit row. ``labels`` is the MATTER vocabulary by
    default; pass None for a foreign trail (ER, discipline), whose action names
    are its own — 'update' there means the record was updated, and rendering it
    through this map would assert 'Matter updated' in an attorney packet."""
    if labels is None:
        return _hum(row.get("action")) or "—"
    action = row.get("action") or ""
    details = row.get("details") or {}
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except Exception:
            details = {}
    label = labels.get(action, _hum(action))
    if action == "message":
        return label.format(role=_hum(details.get("role", "")) or "—")
    if action == "generate_packet":
        return label.format(kind=(details.get("kind") or "").upper() or "—")
    return label
def _hd(v) -> str:
    """Humanized-or-dash: same "—" convention as ``_esc`` for empty values."""
    return _esc(_hum(v)) if v else "—"


def _incident_section(cid: str, data: dict) -> str:
    inc = data.get("incident", {})
    tl = "".join(
        f"<tr><td>{_fmt_dt(t['created_at'])}</td><td>{_hd(t['action'])}</td></tr>"
        for t in data.get("timeline", [])
    ) or "<tr><td colspan='2'>No audit-trail entries.</td></tr>"
    return f"""
      <h2>Appendix — Incident {_esc(inc.get('incident_number'))}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Type</div><div class="v">{_hd(inc.get('incident_type'))}</div></div>
        <div class="cell"><div class="l">Severity</div><div class="v">{_hd(inc.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(inc.get('status'))}</div></div>
        <div class="cell"><div class="l">Occurred</div><div class="v">{_fmt_dt(inc.get('occurred_at'))}</div></div>
      </div>
      <div class="narr">{_esc(inc.get('description'))}</div>
      <table><thead><tr><th>When</th><th>Audit action</th></tr></thead><tbody>{tl}</tbody></table>
    """


def _er_section(cid: str, data: dict) -> str:
    case = data.get("case", {})
    notes = "".join(
        f"<tr><td>{_fmt_dt(n['created_at'])}</td><td>{_hd(n['note_type'])}</td><td>{_esc(n['content'])}</td></tr>"
        for n in data.get("notes", [])
    ) or "<tr><td colspan='3'>No case notes on file.</td></tr>"
    return f"""
      <h2>Appendix — ER case {_esc(case.get('case_number'))}</h2>
      <div class="grid">
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(case.get('category'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(case.get('status'))}</div></div>
        <div class="cell"><div class="l">Outcome</div><div class="v">{_hd(case.get('outcome'))}</div></div>
      </div>
      <div class="narr">{_esc(case.get('description'))}</div>
      <table><thead><tr><th>When</th><th>Type</th><th>Entry</th></tr></thead><tbody>{notes}</tbody></table>
      <h3 style="font-size:11px;margin:10px 0 2px">Chain of custody</h3>
      {_custody_table(data.get('audit_trail'), 'No audit-trail entries recorded for this case.')}
    """
# --------------------------------------------------------------------------- #
# Full-detail fetchers for the appendix — one query per cited record, run only
# for records the memo actually cites (never the whole corpus). Mirrors the
# incident/ER-case pattern (claims_readiness.build_incident_packet /
# build_er_packet) for the source types owned directly by this module.
# --------------------------------------------------------------------------- #

async def _detail_discipline(conn, disc_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT pd.*, e.first_name, e.last_name
             FROM progressive_discipline pd
             LEFT JOIN employees e ON e.id = pd.employee_id
            WHERE pd.id = $1 AND pd.company_id = $2""",
        disc_id, company_id,
    )
    return dict(row) if row else None


async def _detail_compliance(conn, req_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT cr.*, bl.name AS location_name, jr.statute_citation
             FROM compliance_requirements cr
             JOIN business_locations bl ON bl.id = cr.location_id
             LEFT JOIN jurisdiction_requirements jr
                 ON jr.id = cr.jurisdiction_requirement_id AND jr.status = 'active'
            WHERE cr.id = $1 AND bl.company_id = $2""",
        req_id, company_id,
    )
    return dict(row) if row else None


async def _detail_law(conn, req_id: str) -> dict | None:
    # jurisdiction_requirements is a global repository table (no company_id) —
    # every company can see the same governing-law text; tenant scoping isn't
    # meaningful here the way it is for the company's own compliance rows.
    # status='active' — a Legal Pilot packet must never cite admin-staged
    # research still awaiting review as settled law.
    row = await conn.fetchrow(
        "SELECT * FROM jurisdiction_requirements WHERE id = $1 AND status = 'active'", req_id
    )
    return dict(row) if row else None


async def _detail_alert(conn, alert_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT ca.*, bl.name AS location_name
             FROM compliance_alerts ca
             JOIN business_locations bl ON bl.id = ca.location_id
            WHERE ca.id = $1 AND ca.company_id = $2""",
        alert_id, company_id,
    )
    return dict(row) if row else None


async def _detail_training(conn, tr_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT tr.*, e.first_name, e.last_name
             FROM training_records tr
             LEFT JOIN employees e ON e.id = tr.employee_id
            WHERE tr.id = $1 AND tr.company_id = $2""",
        tr_id, company_id,
    )
    return dict(row) if row else None


async def _detail_accommodation(conn, acc_id: str, company_id) -> dict | None:
    row = await conn.fetchrow(
        """SELECT ac.*, e.first_name, e.last_name
             FROM accommodation_cases ac
             LEFT JOIN employees e ON e.id = ac.employee_id
            WHERE ac.id = $1 AND ac.org_id = $2""",
        acc_id, company_id,
    )
    return dict(row) if row else None


# Chain-of-custody trails for cited records. Incidents already carry theirs
# (claims_readiness.build_incident_packet selects ir_audit_log as `timeline`);
# ER cases and discipline records did not, so the module docstring's promise of
# "the immutable *_audit_log trails" was only two-thirds true.
#
# Packet-time only: audit rows are high-volume and low-semantic-density, so they
# are worth nothing in the corpus and everything in the appendix — they show a
# record was created contemporaneously and never retro-edited. No new cids, no
# gate interaction, and they run only for records the packet already renders.
_AUDIT_ROW_CAP = 30


def _group_audit(rows, key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r[key]), []).append(dict(r))
    return out


async def _er_audit_by_case(conn, case_ids: list[str]) -> dict[str, list[dict]]:
    """One query for the whole packet, not one per case. The appendix covers
    every in-scope ER case (the deliberate case-file dump), so per-record fetches
    would add up to _PER_SOURCE_CAP sequential round-trips to an already-slow
    packet build."""
    if not case_ids:
        return {}
    rows = await conn.fetch(
        """SELECT al.case_id, al.action, al.details, al.created_at, u.email AS user_email
             FROM er_audit_log al
             LEFT JOIN users u ON u.id = al.user_id
            WHERE al.case_id = ANY($1::uuid[])
            ORDER BY al.created_at""",
        case_ids,
    )
    return _group_audit(rows, "case_id")


async def _discipline_audit_by_record(conn, disc_ids: list[str]) -> dict[str, list[dict]]:
    if not disc_ids:
        return {}
    rows = await conn.fetch(
        """SELECT al.discipline_id, al.action, al.details, al.created_at,
                  u.email AS user_email
             FROM discipline_audit_log al
             LEFT JOIN users u ON u.id = al.actor_user_id
            WHERE al.discipline_id = ANY($1::uuid[])
            ORDER BY al.created_at""",
        disc_ids,
    )
    return _group_audit(rows, "discipline_id")


def _custody_table(rows: list[dict] | None, empty: str) -> str:
    """Compact chain-of-custody table for one record. Long trails are elided in
    the middle — the first and last entries are the evidentiary ones (when it was
    created, when it was last touched); the middle is edit noise."""
    rows = rows or []
    if not rows:
        return (f"<table><thead><tr><th>When</th><th>Who</th><th>Action</th></tr></thead>"
                f"<tbody><tr><td colspan='3'>{_esc(empty)}</td></tr></tbody></table>")
    elided = 0
    if len(rows) > _AUDIT_ROW_CAP:
        head, tail = _AUDIT_ROW_CAP // 2, _AUDIT_ROW_CAP - _AUDIT_ROW_CAP // 2
        elided = len(rows) - _AUDIT_ROW_CAP
        rows = rows[:head] + rows[-tail:]
    body = "".join(
        f"<tr><td>{_fmt_dt(r.get('created_at'))}</td>"
        f"<td>{_esc(r.get('user_email') or 'System')}</td>"
        f"<td>{_esc(_describe_audit(r, labels=None))}</td></tr>"
        for r in rows
    )
    if elided:
        body += (f"<tr><td colspan='3' style='color:#888'>… {elided} further entr"
                 f"{'y' if elided == 1 else 'ies'} omitted for length …</td></tr>")
    return ("<table><thead><tr><th>When</th><th>Who</th><th>Action</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")
def _discipline_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Discipline record ({_hd(d.get('discipline_type'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Employee</div><div class="v">{_esc(_emp_name(d))}</div></div>
        <div class="cell"><div class="l">Infraction</div><div class="v">{_hd(d.get('infraction_type'))}</div></div>
        <div class="cell"><div class="l">Severity</div><div class="v">{_hd(d.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Issued</div><div class="v">{_fmt_dt(d.get('issued_date'))}</div></div>
        <div class="cell"><div class="l">Review date</div><div class="v">{_fmt_dt(d.get('review_date'))}</div></div>
      </div>
      <div class="narr">{_esc(d.get('description'))}</div>
      {f"<div class='narr'><b>Expected improvement.</b> {_esc(d.get('expected_improvement'))}</div>" if d.get('expected_improvement') else ""}
      {f"<div class='narr'><b>Outcome.</b> {_esc(d.get('outcome_notes'))}</div>" if d.get('outcome_notes') else ""}
      <h3 style="font-size:11px;margin:10px 0 2px">Chain of custody</h3>
      {_custody_table(d.get('audit_trail'), 'No audit-trail entries recorded for this record.')}
    """


def _compliance_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Compliance requirement ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('category'))}</div></div>
        <div class="cell"><div class="l">Jurisdiction</div><div class="v">{_esc(d.get('jurisdiction_name'))}</div></div>
        <div class="cell"><div class="l">Location</div><div class="v">{_esc(d.get('location_name'))}</div></div>
        <div class="cell"><div class="l">Current value</div><div class="v">{_esc(d.get('current_value'))}</div></div>
        <div class="cell"><div class="l">Effective</div><div class="v">{_fmt_dt(d.get('effective_date'))}</div></div>
        <div class="cell"><div class="l">Source</div><div class="v">{_esc(d.get('source_name'))}</div></div>
        <div class="cell"><div class="l">Statute citation</div><div class="v">{_esc(d.get('statute_citation'))}</div></div>
      </div>
      {f"<div class='narr'>{_esc(d.get('description'))}</div>" if d.get('description') else ""}
    """


def _law_section(cid: str, d: dict) -> str:
    penalties_note = ""
    meta = d.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = None
    if isinstance(meta, dict):
        penalties = meta.get("penalties")
        if isinstance(penalties, dict) and penalties.get("summary"):
            penalties_note = f"<div class='narr'><b>Penalties.</b> {_esc(penalties['summary'])}</div>"
    return f"""
      <h2>Appendix — Governing requirement ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Statute citation</div><div class="v">{_esc(d.get('statute_citation'))}</div></div>
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('category'))}</div></div>
        <div class="cell"><div class="l">Jurisdiction</div><div class="v">{_esc(d.get('jurisdiction_name'))} ({_hd(d.get('jurisdiction_level'))})</div></div>
        <div class="cell"><div class="l">Current value</div><div class="v">{_esc(d.get('current_value'))}</div></div>
        <div class="cell"><div class="l">Effective</div><div class="v">{_fmt_dt(d.get('effective_date'))}</div></div>
        <div class="cell"><div class="l">Source</div><div class="v">{_esc(d.get('source_name'))}</div></div>
      </div>
      {f"<div class='narr'>{_esc(d.get('description'))}</div>" if d.get('description') else ""}
      {penalties_note}
    """


def _alert_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Compliance alert ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Severity</div><div class="v">{_hd(d.get('severity'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('category'))}</div></div>
        <div class="cell"><div class="l">Deadline</div><div class="v">{_fmt_dt(d.get('deadline'))}</div></div>
        <div class="cell"><div class="l">Location</div><div class="v">{_esc(d.get('location_name'))}</div></div>
      </div>
      <div class="narr">{_esc(d.get('message'))}</div>
      {f"<div class='narr'><b>Action required.</b> {_esc(d.get('action_required'))}</div>" if d.get('action_required') else ""}
    """


def _training_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Training ({_esc(d.get('title'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Employee</div><div class="v">{_esc(_emp_name(d))}</div></div>
        <div class="cell"><div class="l">Type</div><div class="v">{_hd(d.get('training_type'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Assigned</div><div class="v">{_fmt_dt(d.get('assigned_date'))}</div></div>
        <div class="cell"><div class="l">Due</div><div class="v">{_fmt_dt(d.get('due_date'))}</div></div>
        <div class="cell"><div class="l">Completed</div><div class="v">{_fmt_dt(d.get('completed_date'))}</div></div>
        <div class="cell"><div class="l">Expires</div><div class="v">{_fmt_dt(d.get('expiration_date'))}</div></div>
        <div class="cell"><div class="l">Score</div><div class="v">{_esc(d.get('score'))}</div></div>
      </div>
      {f"<div class='narr'>{_esc(d.get('notes'))}</div>" if d.get('notes') else ""}
    """


def _accommodation_section(cid: str, d: dict) -> str:
    return f"""
      <h2>Appendix — Accommodation case ({_esc(d.get('case_number'))})</h2>
      <div class="grid">
        <div class="cell"><div class="l">Employee</div><div class="v">{_esc(_emp_name(d))}</div></div>
        <div class="cell"><div class="l">Category</div><div class="v">{_hd(d.get('disability_category'))}</div></div>
        <div class="cell"><div class="l">Status</div><div class="v">{_hd(d.get('status'))}</div></div>
        <div class="cell"><div class="l">Closed</div><div class="v">{_fmt_dt(d.get('closed_at'))}</div></div>
      </div>
      <div class="narr">{_esc(d.get('description'))}</div>
      {f"<div class='narr'><b>Requested accommodation.</b> {_esc(d.get('requested_accommodation'))}</div>" if d.get('requested_accommodation') else ""}
      {f"<div class='narr'><b>Approved accommodation.</b> {_esc(d.get('approved_accommodation'))}</div>" if d.get('approved_accommodation') else ""}
      {f"<div class='narr'><b>Denial reason.</b> {_esc(d.get('denial_reason'))}</div>" if d.get('denial_reason') else ""}
    """


_APPENDIX_SECTIONS = {
    "incident": lambda c, d: _incident_section(c, d),
    "er_case": lambda c, d: _er_section(c, d),
    "discipline": _discipline_section,
    "compliance_req": _compliance_section,
    "training": _training_section,
    "accommodation": _accommodation_section,
    "law": _law_section,
    "compliance_alert": _alert_section,
}
