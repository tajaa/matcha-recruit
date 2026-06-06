"""Free-tier Handbook Gap Analyzer endpoints.

Surface:
    POST /resources/handbook-gap-analyzer/analyze
        Authed business user (any tier — surfaced as a Free-plan tool).
        Multipart upload (PDF + states + industry). Stores PDF, inserts a
        handbook_audit_reports row keyed to the user, kicks the Celery worker.

    GET /resources/handbook-gap-analyzer/report/{report_id}
        Authed business user. Owner = user_id match (or email fallback for
        legacy rows). Non-owners receive 403.

Gating to authed callers prevents anonymous abuse — running an audit always
requires a Free-tier signup at minimum.
"""

import asyncio
import html as html_lib
import json
import logging
import re
from datetime import timedelta
from io import BytesIO
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from ...database import get_connection
from ..models.auth import CurrentUser
from ..services.redis_cache import check_rate_limit, client_ip
from ..services.storage import get_storage
from ...matcha.dependencies import require_client
from ..feature_flags import merge_company_features

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_PDF_BYTES = 10 * 1024 * 1024  # 10 MiB
MAX_STATES_PER_REPORT = 1
MAX_AUDITS_PER_ACCOUNT_PER_MONTH = 7  # hard cap; resets at the start of each calendar month
IP_RATE_LIMIT_KEY = "handbook_gap_analyzer:ip"
IP_RATE_LIMIT_PER_DAY = 12  # belt-and-suspenders against one IP fanning out via many accounts
STATE_CODE_RE = re.compile(r"^[A-Z]{2}$")
SAMPLE_GAPS_LIMIT = 3  # how many gaps Free-tier callers see in full on the report page


async def _resolve_caller_tier(conn, user_id: UUID) -> str:
    """Return 'paid' when the caller is entitled to the FULL handbook audit, else 'free'.

    Entitlement = the `handbook_audit` feature (Matcha-X + Pro). Free lead-gen
    users AND Lite tenants get the teaser ('free' → sample gaps only, no PDF);
    X/Pro get the full gap list + PDF. Uses merge_company_features so the gate
    applies the exact per-tier overlay the in-app <FeatureGate> uses. The shared
    public lead-gen funnel stays open — anonymous→resources_free callers simply
    fall to the teaser. Admins/brokers/employees without a clients row default
    to 'paid'.
    """
    row = await conn.fetchrow(
        """
        SELECT comp.signup_source, comp.enabled_features
        FROM clients c
        JOIN companies comp ON comp.id = c.company_id
        WHERE c.user_id = $1
        """,
        user_id,
    )
    if not row:
        return "paid"
    merged = merge_company_features(row["enabled_features"], row["signup_source"])
    return "paid" if merged.get("handbook_audit") else "free"


def _build_hidden_by_state(
    by_state: dict[str, dict[str, int]],
    sample_gaps: list[dict[str, Any]],
) -> dict[str, int]:
    """For each state, count gaps that aren't in the sample so the UI can render
    'X more gaps hidden — upgrade to reveal' cards."""
    sample_per_state: dict[str, int] = {}
    for g in sample_gaps:
        s = g.get("state")
        if s:
            sample_per_state[s] = sample_per_state.get(s, 0) + 1
    hidden: dict[str, int] = {}
    for state, counts in (by_state or {}).items():
        total = (
            int(counts.get("critical", 0))
            + int(counts.get("important", 0))
            + int(counts.get("recommended", 0))
        )
        revealed = sample_per_state.get(state, 0)
        if total - revealed > 0:
            hidden[state] = total - revealed
    return hidden


def _parse_states(raw: str) -> list[str]:
    if not raw:
        return []
    parts = [p.strip().upper() for p in raw.replace(";", ",").split(",")]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if not p or p in seen:
            continue
        if not STATE_CODE_RE.match(p):
            raise HTTPException(status_code=400, detail=f"Invalid state code: {p}")
        seen.add(p)
        out.append(p)
    return out


_SEVERITY_ORDER = {"critical": 0, "important": 1, "recommended": 2}


def _pick_samples_distributed(gaps: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """Pick up to N sample gaps. Prefer state diversity (one per state first),
    then fall back to severity-ranked picks until N is reached."""
    if not gaps or n <= 0:
        return []
    ranked = sorted(
        gaps,
        key=lambda g: (
            _SEVERITY_ORDER.get((g.get("severity") or "").lower(), 9),
            (g.get("requirement_title") or ""),
        ),
    )
    picked: list[dict[str, Any]] = []
    seen_states: set[str] = set()
    # Pass 1: one-per-state, severity-first.
    for g in ranked:
        state = g.get("state")
        if state and state not in seen_states:
            picked.append(g)
            seen_states.add(state)
            if len(picked) >= n:
                return picked
    # Pass 2: top up by severity regardless of state.
    for g in ranked:
        if g in picked:
            continue
        picked.append(g)
        if len(picked) >= n:
            break
    return picked


def _summarize_gaps(report: dict[str, Any]) -> dict[str, Any]:
    counts = report.get("gap_counts") or {}
    if isinstance(counts, str):
        try:
            counts = json.loads(counts)
        except json.JSONDecodeError:
            counts = {}
    if isinstance(counts, dict):
        # Worker stashes a sample list in here; we re-derive at response time.
        counts.pop("sample_gaps", None)
    return {
        "status": report.get("status"),
        "states": report.get("states") or [],
        "industry": report.get("industry"),
        "gap_counts": {
            "critical": int(counts.get("critical", 0)),
            "important": int(counts.get("important", 0)),
            "recommended": int(counts.get("recommended", 0)),
            "total_gaps": int(counts.get("total_gaps", 0)),
            "total_states": int(counts.get("total_states", len(report.get("states") or []))),
            "by_state": counts.get("by_state") or {},
        },
        "created_at": report["created_at"].isoformat() if report.get("created_at") else None,
        "completed_at": report["completed_at"].isoformat() if report.get("completed_at") else None,
    }


def _coerce_jsonb(value: Any, fallback: Any) -> Any:
    """asyncpg may hand back JSONB as a str; normalize to a Python object."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value if value is not None else fallback


async def _load_owned_report(conn, report_id: UUID, current_user: CurrentUser) -> dict[str, Any]:
    """Fetch a report and enforce owner-only access (user_id match, or email
    fallback for legacy rows). Shared by the JSON report endpoint and the PDF
    export so the ownership rule never drifts between them. Raises 404/403."""
    row = await conn.fetchrow(
        """
        SELECT id, email, user_id, states, industry, status,
               gap_counts, gaps_jsonb, error_text,
               created_at, completed_at
        FROM handbook_audit_reports
        WHERE id = $1
        """,
        report_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    report = dict(row)
    user_email = (current_user.email or "").lower() or None
    is_owner = bool(
        (report.get("user_id") and str(report["user_id"]) == str(current_user.id))
        or (user_email and report.get("email") and user_email == report["email"].lower())
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="This report belongs to another account")

    report["gap_counts"] = _coerce_jsonb(report.get("gap_counts"), {})
    return report


def _build_audit_report_html(report: dict[str, Any]) -> str:
    """Render a handbook-audit report (full gap list) to a self-contained HTML
    document for WeasyPrint. Pure function — no DB/IO — so it's unit-testable."""
    esc = html_lib.escape
    counts = _coerce_jsonb(report.get("gap_counts"), {}) or {}
    states = report.get("states") or []
    industry = report.get("industry")
    completed_at = report.get("completed_at")
    gaps = list(_coerce_jsonb(report.get("gaps_jsonb"), []) or [])

    total_gaps = int(counts.get("total_gaps", len(gaps)))

    # Group gaps by state, severity-ranked, mirroring the on-screen results.
    by_state: dict[str, list[dict[str, Any]]] = {}
    for g in gaps:
        by_state.setdefault(g.get("state") or "—", []).append(g)
    for lst in by_state.values():
        lst.sort(key=lambda g: _SEVERITY_ORDER.get((g.get("severity") or "").lower(), 9))

    sev_colors = {"critical": "#8a4a3a", "important": "#a47c2c", "recommended": "#5b6f7c"}

    sections: list[str] = []
    for state in sorted(by_state.keys()):
        rows: list[str] = []
        for g in by_state[state]:
            sev = (g.get("severity") or "").lower()
            color = sev_colors.get(sev, "#5b6f7c")
            meta_bits = []
            if g.get("citation"):
                meta_bits.append(f"cite · {esc(str(g['citation']))}")
            if g.get("matched_section_title"):
                meta_bits.append(f"matched · {esc(str(g['matched_section_title']))}")
            meta = (
                f"<div class='meta'>{' &nbsp;·&nbsp; '.join(meta_bits)}</div>" if meta_bits else ""
            )
            good = (
                f"<p class='good'>{esc(str(g['what_good_looks_like']))}</p>"
                if g.get("what_good_looks_like")
                else ""
            )
            rows.append(
                f"<div class='gap' style='border-left:3px solid {color}'>"
                f"<div class='gap-head'><span class='title'>{esc(str(g.get('requirement_title') or 'Requirement'))}</span>"
                f"<span class='sev' style='color:{color};border-color:{color}'>{esc(sev or 'gap')}</span></div>"
                f"{good}{meta}</div>"
            )
        sections.append(
            f"<section><h2>{esc(state)}</h2>{''.join(rows) or '<p class=\"empty\">No gaps flagged.</p>'}</section>"
        )

    completed_str = ""
    if completed_at is not None:
        try:
            completed_str = completed_at.strftime("%B %-d, %Y")
        except Exception:
            completed_str = str(completed_at)

    industry_str = f" · {esc(str(industry))}" if industry else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 40px; }}
  body {{ font-family: 'Helvetica Neue', Arial, sans-serif; color: #1f1d1a; font-size: 12px; line-height: 1.5; }}
  h1 {{ font-size: 26px; font-weight: 600; margin: 0 0 6px; }}
  .sub {{ color: #6b6862; font-size: 12px; margin: 0 0 4px; }}
  .summary {{ margin: 18px 0 24px; font-size: 13px; }}
  section {{ page-break-inside: avoid; margin-bottom: 22px; }}
  h2 {{ font-size: 16px; font-weight: 600; border-bottom: 1px solid #e4e0d8; padding-bottom: 4px; margin: 0 0 10px; }}
  .gap {{ padding: 8px 12px; margin-bottom: 8px; background: #faf8f4; border-radius: 6px; page-break-inside: avoid; }}
  .gap-head {{ display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }}
  .title {{ font-weight: 600; font-size: 13px; }}
  .sev {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.12em; border: 1px solid; border-radius: 4px; padding: 1px 6px; white-space: nowrap; }}
  .good {{ color: #4b4842; margin: 6px 0 0; }}
  .meta {{ color: #8a877f; font-size: 10.5px; margin-top: 6px; }}
  .empty {{ color: #8a877f; }}
  footer {{ margin-top: 28px; color: #8a877f; font-size: 10px; }}
</style></head><body>
  <h1>Handbook Audit Report</h1>
  <p class="sub">{esc(' · '.join(states))}{industry_str}</p>
  <p class="summary"><strong>{total_gaps}</strong> gap{'' if total_gaps == 1 else 's'} found
    — Critical {int(counts.get('critical', 0))} · Important {int(counts.get('important', 0))} · Recommended {int(counts.get('recommended', 0))}.</p>
  {''.join(sections)}
  <footer>{('Completed ' + completed_str + '. ') if completed_str else ''}Informational only — not legal advice.</footer>
</body></html>"""


@router.get("/quota")
async def get_audit_quota(
    current_user: CurrentUser = Depends(require_client),
):
    """Returns how many audits the caller has run this calendar month and the
    remaining allowance. Lets the UI render a quota chip before upload."""
    from datetime import datetime, timezone

    async with get_connection() as conn:
        used = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM handbook_audit_reports
            WHERE user_id = $1
              AND created_at >= date_trunc('month', NOW())
            """,
            current_user.id,
        )
    used = int(used or 0)
    now = datetime.now(timezone.utc)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    return {
        "used": used,
        "limit": MAX_AUDITS_PER_ACCOUNT_PER_MONTH,
        "remaining": max(0, MAX_AUDITS_PER_ACCOUNT_PER_MONTH - used),
        "resets_at": next_month.isoformat(),
    }


@router.post("/analyze")
async def submit_handbook_for_analysis(
    request: Request,
    background_tasks: BackgroundTasks,
    pdf: UploadFile = File(...),
    states: str = Form(...),
    industry: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(require_client),
):
    """Authed handbook upload. Returns a report_id the client polls."""
    state_list = _parse_states(states)
    if not state_list:
        raise HTTPException(status_code=400, detail="At least one state is required")
    if len(state_list) > MAX_STATES_PER_REPORT:
        raise HTTPException(
            status_code=400,
            detail="Pick exactly one state per audit",
        )

    content_type = (pdf.content_type or "").lower()
    filename = (pdf.filename or "").lower()
    if "pdf" not in content_type and not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Upload must be a PDF")

    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="PDF is empty")
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be 10MB or smaller")

    # Hard per-account cap (MAX_AUDITS_PER_ACCOUNT_PER_MONTH) per calendar
    # month. Counts every attempt (success or failure) so a user gets retry
    # headroom if a run errored. Resets at the first of the next month.
    async with get_connection() as conn:
        used_this_month = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM handbook_audit_reports
            WHERE user_id = $1
              AND created_at >= date_trunc('month', NOW())
            """,
            current_user.id,
        )
    used_this_month = int(used_this_month or 0)
    if used_this_month >= MAX_AUDITS_PER_ACCOUNT_PER_MONTH:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've used your {MAX_AUDITS_PER_ACCOUNT_PER_MONTH} handbook audits "
                f"for this month. Quota resets {next_month.strftime('%B %-d, %Y')}."
            ),
        )

    # Belt-and-suspenders IP guard against one network spinning up many accounts.
    ip = client_ip(request) or "unknown"
    try:
        await check_rate_limit(
            ip,
            IP_RATE_LIMIT_KEY,
            IP_RATE_LIMIT_PER_DAY,
            24 * 60 * 60,
        )
    except HTTPException:
        raise
    except Exception:
        pass

    try:
        storage_path = await get_storage().upload_private_file(
            pdf_bytes,
            filename or "handbook.pdf",
            prefix="handbook-audits",
            content_type="application/pdf",
        )
    except Exception as exc:
        logger.exception("Handbook PDF upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not store the uploaded PDF")

    industry_clean = (industry or "").strip().lower()[:64] or None
    user_email = (current_user.email or "").strip().lower() or None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO handbook_audit_reports
                (email, user_id, states, industry, pdf_storage_path, status)
            VALUES ($1, $2, $3::text[], $4, $5, 'processing')
            RETURNING id
            """,
            user_email,
            current_user.id,
            state_list,
            industry_clean,
            storage_path,
        )
    report_id = str(row["id"])

    # Run inline via FastAPI's BackgroundTasks instead of dispatching to a
    # Celery worker. The handbook audit is interactive (frontend polls the
    # report row every 2.5s while the user waits on the result page) so the
    # same-event-loop + same-process model avoids a whole class of bugs:
    # no per-worker load_settings() bootstrap, no asyncpg-pool-per-loop
    # plumbing, no get_storage() singleton drift, no worker-unavailable
    # 503 surface area. A stalled run (uvicorn restart, OOM, unhandled
    # exception) is detected by the frontend after 5 minutes of no
    # progress and surfaces a Retry banner.
    from app.core.services.handbook_audit_service import run_handbook_audit
    background_tasks.add_task(run_handbook_audit, report_id)

    return {"report_id": report_id, "status": "processing"}


@router.get("/report/{report_id}")
async def get_handbook_audit_report(
    report_id: UUID,
    current_user: CurrentUser = Depends(require_client),
):
    """Polling endpoint. Returns the full report when the caller owns it."""
    async with get_connection() as conn:
        report = await _load_owned_report(conn, report_id, current_user)

    summary = _summarize_gaps(report)
    summary["report_id"] = str(report["id"])
    summary["is_owner"] = True
    if report["status"] == "failed":
        summary["error"] = (report.get("error_text") or "Audit failed")[:400]

    # Backfill user_id on legacy/email-matched rows so future GETs are fast.
    if not report.get("user_id"):
        try:
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE handbook_audit_reports SET user_id = $2 WHERE id = $1",
                    report["id"],
                    current_user.id,
                )
        except Exception as exc:
            logger.warning("Could not backfill user_id on report %s: %s", report["id"], exc)

    gaps_raw = report.get("gaps_jsonb")
    if isinstance(gaps_raw, str):
        try:
            gaps_raw = json.loads(gaps_raw)
        except json.JSONDecodeError:
            gaps_raw = []
    full_gaps: list[dict[str, Any]] = list(gaps_raw or [])

    async with get_connection() as conn:
        tier = await _resolve_caller_tier(conn, current_user.id)
    summary["tier"] = tier

    samples = _pick_samples_distributed(full_gaps, SAMPLE_GAPS_LIMIT)
    summary["sample_gaps"] = samples

    if tier == "paid":
        summary["gaps"] = full_gaps
    else:
        # Free tier: hide the full list, expose how much is locked per state.
        summary["gaps"] = None
        summary["hidden_by_state"] = _build_hidden_by_state(
            summary["gap_counts"]["by_state"],
            samples,
        )
    return summary


@router.get("/report/{report_id}/pdf")
async def export_handbook_audit_pdf(
    report_id: UUID,
    current_user: CurrentUser = Depends(require_client),
):
    """Download the full audit report as a PDF. Paid-tier only — free callers
    get a 403 upsell. The full gap list is the value being gated (free tier
    only ever sees sample gaps on the report page)."""
    async with get_connection() as conn:
        report = await _load_owned_report(conn, report_id, current_user)
        tier = await _resolve_caller_tier(conn, current_user.id)

    if report.get("status") != "ready":
        raise HTTPException(status_code=409, detail="Audit hasn't finished yet")
    if tier == "free":
        raise HTTPException(
            status_code=403,
            detail="Saving the full report is a Matcha Lite feature",
        )

    html = _build_audit_report_html(report)
    try:
        from weasyprint import HTML  # local import: heavy native dep
        from ..services.pdf import safe_url_fetcher
        pdf_bytes = await asyncio.to_thread(lambda: HTML(string=html, url_fetcher=safe_url_fetcher).write_pdf())
    except Exception as exc:
        logger.exception("Handbook audit PDF render failed for report %s: %s", report_id, exc)
        raise HTTPException(status_code=500, detail="Could not generate the report PDF")

    states = report.get("states") or []
    state_part = "-".join(states) if states else "report"
    filename = f"handbook-audit-{state_part}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
