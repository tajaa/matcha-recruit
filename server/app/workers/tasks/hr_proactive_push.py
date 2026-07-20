"""Celery task: HR Pilot proactive push.

Every other HR Pilot surface waits to be asked. This one goes first: it opens a
pre-briefed HR Pilot thread ahead of the event, so a supervisor learns that Jane
comes back Monday *before* Monday, rather than after mishandling it.

Three sweeps:

  1. leave_return        — approved/active leave whose return date lands inside
                           the lookahead window.
  2. discipline_expiry   — active discipline reaching `expires_at`.
     discipline_review   — ...or its `review_date` (the improvement-plan check-in).
                           Distinct kinds: they need different briefings, and a
                           record can legitimately hit both.
  3. pending_signatures  — handbook/policy acknowledgements left unreturned past
                           the age threshold. A per-COMPANY digest, not one
                           thread per document: fifty unsigned handbooks is one
                           problem to work through, not fifty problems.

The thread opens with `hr_pilot_mode = true` and a deterministic briefing — NO
Gemini call happens here. The briefing states facts the worker already has
(names, dates, the record) plus the standing legal caution for that category;
anything the supervisor asks next runs through the normal grounded, cited HR
Pilot turn, which is where the corpus and the citation gate live. That split
keeps a cron job from spending model tokens on threads nobody opens.

Runs on the shared worker restart cadence; gated on
scheduler_settings.task_key = 'hr_proactive_push' (seeded DISABLED, migration
hrpush01). Idempotency lives in hr_proactive_push_log — see `_already_pushed`
for why the two dedupe shapes differ.
"""

import asyncio
import json
from datetime import date, timedelta

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row
from .leave_deadline_checks import FMLA_LEAVE_TYPES

# How far ahead of each deadline to open the thread. A week is long enough to
# arrange coverage or schedule a conversation, short enough that the thread is
# still relevant when it is read.
LEAVE_LOOKAHEAD_DAYS = 7
DISCIPLINE_LOOKAHEAD_DAYS = 7
# Signatures: how stale before it is worth raising, and how often to re-raise.
SIGNATURE_STALE_DAYS = 7
SIGNATURE_RENOTIFY_DAYS = 7
# Employees named in the digest body before it collapses to a count.
MAX_DIGEST_NAMES = 15

# Triggers that fire exactly ONCE per subject, ever. A return date or an expiry
# date is a single event: re-raising it every morning until it passes is how a
# notification channel teaches people to ignore it. The digest is the exception
# (below) because its subject is the company, not one dated record.
_ONE_SHOT_KINDS = ("leave_return", "discipline_expiry", "discipline_review")


class _AlreadyStamped(Exception):
    """Raised inside the open-thread transaction when the ledger row already
    exists, to roll back a thread a concurrent run already delivered."""


# --------------------------------------------------------------------------- #
# Pure helpers — no DB, unit-tested.
# --------------------------------------------------------------------------- #

def _full_name(first, last) -> str:
    return f"{first or ''} {last or ''}".strip() or "an employee"


def _fmt(d) -> str:
    if d is None:
        return "an unspecified date"
    try:
        return d.strftime("%A, %B %-d")
    except (AttributeError, ValueError):
        try:
            return d.strftime("%A, %B %d")
        except (AttributeError, ValueError):
            return str(d)


def build_leave_return_briefing(row: dict) -> tuple[str, str]:
    """Briefing for an employee coming back from leave."""
    who = _full_name(row.get("first_name"), row.get("last_name"))
    when = _fmt(row.get("return_date"))
    leave_type = str(row.get("leave_type") or "leave").replace("_", " ")
    is_fmla = str(row.get("leave_type") or "") in FMLA_LEAVE_TYPES or \
        str(row.get("leave_type") or "").startswith("fmla_")

    title = f"{who} returns from leave — {when}"
    body = [
        f"**{who}** is scheduled to return from {leave_type} on **{when}**.",
        "",
        "Before they're back:",
        "- Confirm the return date with them — it can move, and the roster should match.",
        "- Have their schedule, access, and equipment ready for day one.",
        "- Plan a short catch-up on what changed while they were out.",
    ]
    if is_fmla:
        body += [
            "",
            "**On an FMLA return specifically:** the employee is generally entitled to "
            "their same job, or an equivalent one with equivalent pay, benefits, and "
            "terms. Taking the leave cannot count against them — not in scheduling, not "
            "in evaluations, not in discipline.",
        ]
    body += [
        "",
        "Do not ask about their medical condition or diagnosis, and do not ask coworkers "
        "about it either. If they raise a medical restriction, an accommodation, or an "
        "extension, route it to corporate HR rather than deciding it on-site.",
        "",
        "Ask me anything about the return in this thread and I'll answer from your "
        "company's handbook and policies.",
    ]
    return title, "\n".join(body)


def build_discipline_briefing(row: dict, kind: str) -> tuple[str, str]:
    """Briefing for a discipline record reaching its review or expiry date."""
    who = _full_name(row.get("first_name"), row.get("last_name"))
    dtype = str(row.get("discipline_type") or "discipline").replace("_", " ")
    is_review = kind == "discipline_review"
    when = _fmt(row.get("review_date") if is_review else row.get("expires_at"))

    if is_review:
        title = f"Discipline check-in due — {who} ({when})"
        body = [
            f"The **{dtype}** on file for **{who}** reaches its review date on **{when}**.",
            "",
            "What the review is for:",
            "- Decide whether the improvement you asked for actually happened.",
            "- Say so to the employee either way — an unspoken pass is not a record.",
            "- Write down what you observed, with dates. That contemporaneous note is "
            "what makes the decision defensible later.",
        ]
        if row.get("expected_improvement"):
            body += ["", f"The improvement this record asked for: {row['expected_improvement']}"]
    else:
        title = f"Discipline expires — {who} ({when})"
        body = [
            f"The **{dtype}** on file for **{who}** expires on **{when}**, after which "
            "it no longer counts as an active step on the ladder.",
            "",
            "Before it lapses:",
            "- If the conduct was corrected, nothing is needed — let it expire.",
            "- If it wasn't, address it now, while the record is still active.",
            "- Don't rely on an expired record as the basis for a later escalation.",
        ]

    body += [
        "",
        "If the next step here is a termination, or if the employee has raised a legal "
        "concern, a complaint, or anything involving leave or a medical condition, stop "
        "and bring in corporate HR before acting.",
        "",
        "Ask me about this record in this thread and I'll answer from your company's "
        "policies and discipline ladder.",
    ]
    return title, "\n".join(body)


def build_signature_digest_briefing(rows: list[dict], stale_days: int,
                                    total: int | None = None) -> tuple[str, str]:
    """Digest for handbook/policy acknowledgements left unreturned.

    `total` is the true backlog size, which can exceed `len(rows)` when the
    caller passes only the names it intends to list. Reporting `len(rows)` as
    the count is how a company with 30 outstanding acknowledgements gets told it
    has 4."""
    n = total if total is not None else len(rows)
    title = f"{n} unreturned acknowledgement{'s' if n != 1 else ''}"
    body = [
        f"**{n}** handbook or policy acknowledgement{'s have' if n != 1 else ' has'} been "
        f"outstanding for more than {stale_days} days.",
        "",
        "Why it matters: an unsigned acknowledgement is the gap that gets pointed at when "
        "a policy is enforced later. The signature is what shows the rule was "
        "communicated, not just published.",
        "",
        "Outstanding:",
    ]
    for r in rows[:MAX_DIGEST_NAMES]:
        who = _full_name(r.get("first_name"), r.get("last_name"))
        body.append(f"- {who} — {r.get('title') or 'document'}")
    if n > MAX_DIGEST_NAMES:
        body.append(f"- ...and {n - MAX_DIGEST_NAMES} more not listed individually.")
    body += [
        "",
        "Chase these through the employee portal rather than collecting paper. Ask me in "
        "this thread if you need the wording for a reminder.",
    ]
    return title, "\n".join(body)


def _as_date(value):
    """Normalize a DATE or TIMESTAMPTZ column to a `date` for window checks."""
    if value is None:
        return None
    return value.date() if hasattr(value, "date") else value


def discipline_kinds_in_window(row: dict, today, horizon) -> list[str]:
    """Which discipline triggers this row fires.

    One record can hit both dates in the same window — a review check-in and an
    expiry are different conversations, so each gets its own thread and its own
    dedupe key. And because the SQL matches on `review_date OR expires_at`, a row
    can arrive having matched on only one of them: each date is re-checked here,
    or a record whose review lands next week would also push an expiry briefing
    for a date six months out."""
    kinds = []
    review = _as_date(row.get("review_date"))
    expires = _as_date(row.get("expires_at"))
    if review is not None and today <= review <= horizon:
        kinds.append("discipline_review")
    if expires is not None and today <= expires <= horizon:
        kinds.append("discipline_expiry")
    return kinds


def hr_pilot_enabled(enabled_features, signup_source) -> bool:
    """Whether a company has HR Pilot.

    Resolved in Python through the shared merge rather than a SQL
    `enabled_features ->> 'hr_pilot'`. `hr_pilot` is not in any tier overlay
    today, so the two agree — but merge_company_features is the definition of
    "does this company have X" (defaults + stored + overlay), and a SQL
    shortcut that happens to be equivalent now silently stops being equivalent
    the day the flag gets bundled."""
    from app.core.feature_flags import merge_company_features
    return bool(merge_company_features(enabled_features, signup_source).get("hr_pilot"))


# --------------------------------------------------------------------------- #
# Ledger
# --------------------------------------------------------------------------- #

async def _already_pushed(conn, company_id, trigger_kind: str, subject_id, today) -> bool:
    """Has this subject already been pushed?

    Two shapes, because the triggers mean different things. A dated deadline
    (`_ONE_SHOT_KINDS`) is asked about WITHOUT a date bound — once we have told
    someone that Jane returns Monday, telling them again on Tuesday, Wednesday
    and Thursday is noise, not diligence. The company-scoped digest asks with a
    date floor instead, so it can recur on a slower cadence."""
    if trigger_kind in _ONE_SHOT_KINDS:
        return bool(await conn.fetchval(
            """SELECT EXISTS (SELECT 1 FROM hr_proactive_push_log
                              WHERE trigger_kind = $1 AND subject_id = $2)""",
            trigger_kind, subject_id,
        ))
    return bool(await conn.fetchval(
        """SELECT EXISTS (SELECT 1 FROM hr_proactive_push_log
                          WHERE company_id = $1 AND trigger_kind = $2 AND subject_id = $3
                            AND sent_on > $4)""",
        company_id, trigger_kind, subject_id, today - timedelta(days=SIGNATURE_RENOTIFY_DAYS),
    ))


# --------------------------------------------------------------------------- #
# Recipients + thread creation
# --------------------------------------------------------------------------- #

async def _company_client_users(conn, company_id, cache: dict | None = None) -> list:
    """Every active business-admin user for the company, oldest first.

    Deterministic ORDER BY so `created_by` doesn't shuffle between runs.
    `cache` is a per-run dict: without it this is an N+1, re-running the same
    join for every event in a company."""
    if cache is not None and company_id in cache:
        return cache[company_id]
    rows = await conn.fetch(
        """
        SELECT DISTINCT u.id, u.created_at
        FROM clients c JOIN users u ON u.id = c.user_id
        WHERE c.company_id = $1 AND u.is_active = true
        ORDER BY u.created_at, u.id
        """,
        company_id,
    )
    users = [r["id"] for r in rows]
    if cache is not None:
        cache[company_id] = users
    return users


async def _resolve_recipients(conn, company_id, employee_id, cache: dict | None = None) -> tuple:
    """(owner_user_id, [notify_user_ids]).

    Prefers the employee's own manager, who is the person actually holding the
    situation. `manager_id` is only populated by bulk upload today, so the
    fallback — every business admin — is the common path rather than the edge
    case. The thread is company-visible either way (`list_threads` scopes by
    company, not creator), so a wrong-but-plausible owner is a cosmetic problem,
    not an access one."""
    manager_user_id = None
    if employee_id:
        try:
            manager_user_id = await conn.fetchval(
                """
                SELECT mu.id
                FROM employees e
                JOIN employees m ON m.id = e.manager_id
                JOIN users mu ON mu.id = m.user_id
                WHERE e.id = $1 AND mu.is_active = true
                """,
                employee_id,
            )
        except Exception:  # noqa: BLE001
            manager_user_id = None

    clients = await _company_client_users(conn, company_id, cache)
    if manager_user_id:
        notify = [manager_user_id] + [c for c in clients if c != manager_user_id]
        return manager_user_id, notify
    if clients:
        return clients[0], clients
    return None, []


async def _open_thread(conn, *, company_id, owner_user_id, notify_user_ids, title, body,
                       trigger_kind, subject_id, today) -> str | None:
    """Create the thread + briefing + notifications + ledger stamp atomically.

    One transaction on purpose: a thread with no ledger row is pushed again
    tomorrow, and a ledger row with no thread silently suppresses the push
    forever. Unlike the email workers there is no external send to sequence
    around, so there is no reason to split it."""
    async with conn.transaction():
        thread_id = await conn.fetchval(
            """
            INSERT INTO mw_threads (company_id, created_by, title, current_state, hr_pilot_mode)
            VALUES ($1, $2, $3, '{}'::jsonb, true)
            RETURNING id
            """,
            company_id, owner_user_id, title[:255],
        )
        await conn.execute(
            """
            INSERT INTO mw_messages (thread_id, role, content, metadata)
            VALUES ($1, 'assistant', $2, $3::jsonb)
            """,
            thread_id, body,
            json.dumps({
                "source": "proactive_push",
                "trigger": trigger_kind,
                "subject_id": str(subject_id),
            }),
        )
        await conn.execute(
            "UPDATE mw_threads SET updated_at = NOW() WHERE id = $1", thread_id
        )
        for user_id in notify_user_ids:
            await conn.execute(
                """
                INSERT INTO mw_notifications (user_id, company_id, type, title, body, link, metadata)
                VALUES ($1, $2, 'hr_proactive', $3, $4, $5, $6::jsonb)
                """,
                user_id, company_id, title[:255],
                "HR Pilot opened a thread with what you need to know.",
                f"/work/{thread_id}",
                json.dumps({"thread_id": str(thread_id), "trigger": trigger_kind}),
            )
        stamped = await conn.fetchval(
            """
            INSERT INTO hr_proactive_push_log
                (company_id, trigger_kind, subject_id, thread_id, sent_on)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (company_id, trigger_kind, subject_id, sent_on) DO NOTHING
            RETURNING id
            """,
            company_id, trigger_kind, subject_id, thread_id, today,
        )
        if stamped is None:
            # Another run beat us to this subject between our _already_pushed
            # check and here. DO NOTHING would otherwise leave the thread and
            # its notifications committed with no ledger row to suppress the
            # next run — a duplicate thread every cycle. Roll the whole unit
            # back instead; the winning run already delivered it.
            raise _AlreadyStamped(trigger_kind, subject_id)
    return str(thread_id)


# --------------------------------------------------------------------------- #
# Sweeps
#
# Each sweep shares one `budget` (max_per_cycle) counting THREADS OPENED, not
# rows scanned: a discipline row can fire two triggers, so a row-based cap would
# let one sweep write twice its stated limit. Each event is also isolated — a
# single bad row must not abort the run and strand every event behind it, which
# a retry would then re-attempt in the same order, forever.
# --------------------------------------------------------------------------- #

async def _deliver(conn, *, company_id, employee_id, trigger_kind, subject_id,
                   title, body, today, budget, clients_cache) -> bool:
    """Dedupe-check, resolve recipients, open the thread. Best-effort.

    Returns True if a thread was opened. Every failure mode is contained here:
    a row that raises is logged and skipped, and the sweep continues."""
    if budget["remaining"] <= 0:
        return False
    try:
        if await _already_pushed(conn, company_id, trigger_kind, subject_id, today):
            return False
        owner, notify = await _resolve_recipients(conn, company_id, employee_id, clients_cache)
        if not owner:
            return False
        await _open_thread(
            conn, company_id=company_id, owner_user_id=owner, notify_user_ids=notify,
            title=title, body=body, trigger_kind=trigger_kind, subject_id=subject_id,
            today=today,
        )
    except _AlreadyStamped:
        # Concurrent run delivered it; its transaction rolled back cleanly.
        return False
    except Exception:  # noqa: BLE001
        print(f"[HR Proactive Push] {trigger_kind} failed for subject {subject_id}")
        return False
    budget["remaining"] -= 1
    return True


async def _sweep_leave_returns(conn, enabled_companies, today, budget, clients_cache) -> dict:
    """Employees returning from leave inside the lookahead window.

    `NOT EXISTS` against the ledger lives in the SQL, not just in `_deliver`:
    one-shot triggers keep matching the WHERE clause after they have been
    pushed, so filtering them only in Python would let already-delivered rows
    consume the whole LIMIT and starve everything behind them."""
    rows = await conn.fetch(
        """
        SELECT lr.id, lr.org_id AS company_id, lr.employee_id, lr.leave_type,
               COALESCE(lr.expected_return_date, lr.end_date) AS return_date,
               e.first_name, e.last_name
        FROM leave_requests lr
        JOIN employees e ON e.id = lr.employee_id
        WHERE lr.status IN ('approved', 'active')
          AND lr.actual_return_date IS NULL
          AND e.termination_date IS NULL
          AND COALESCE(lr.expected_return_date, lr.end_date)
              BETWEEN $1 AND $1 + ($2 || ' days')::interval
          AND lr.org_id = ANY($3::uuid[])
          AND NOT EXISTS (
                SELECT 1 FROM hr_proactive_push_log l
                WHERE l.trigger_kind = 'leave_return' AND l.subject_id = lr.id
          )
        ORDER BY COALESCE(lr.expected_return_date, lr.end_date)
        LIMIT $4
        """,
        today, str(LEAVE_LOOKAHEAD_DAYS), enabled_companies, budget["remaining"],
    )
    opened = 0
    for r in rows:
        title, body = build_leave_return_briefing(dict(r))
        if await _deliver(conn, company_id=r["company_id"], employee_id=r["employee_id"],
                          trigger_kind="leave_return", subject_id=r["id"],
                          title=title, body=body, today=today,
                          budget=budget, clients_cache=clients_cache):
            opened += 1
    return {"leave_returns_checked": len(rows), "leave_returns_opened": opened}


async def _sweep_discipline(conn, enabled_companies, today, budget, clients_cache) -> dict:
    horizon = today + timedelta(days=DISCIPLINE_LOOKAHEAD_DAYS)
    rows = await conn.fetch(
        """
        SELECT pd.id, pd.company_id, pd.employee_id, pd.discipline_type,
               pd.expires_at, pd.review_date, pd.expected_improvement,
               e.first_name, e.last_name
        FROM progressive_discipline pd
        JOIN employees e ON e.id = pd.employee_id
        WHERE pd.status = 'active'
          AND pd.company_id = ANY($3::uuid[])
          AND e.termination_date IS NULL
          AND (
                (pd.expires_at IS NOT NULL AND pd.expires_at::date BETWEEN $1 AND $2)
             OR (pd.review_date IS NOT NULL AND pd.review_date::date BETWEEN $1 AND $2)
          )
          AND NOT (
                EXISTS (SELECT 1 FROM hr_proactive_push_log l
                        WHERE l.trigger_kind = 'discipline_review' AND l.subject_id = pd.id)
            AND EXISTS (SELECT 1 FROM hr_proactive_push_log l
                        WHERE l.trigger_kind = 'discipline_expiry' AND l.subject_id = pd.id)
          )
        ORDER BY COALESCE(pd.review_date::date, pd.expires_at::date)
        LIMIT $4
        """,
        today, horizon, enabled_companies, budget["remaining"],
    )
    opened = 0
    for r in rows:
        for kind in discipline_kinds_in_window(dict(r), today, horizon):
            title, body = build_discipline_briefing(dict(r), kind)
            if await _deliver(conn, company_id=r["company_id"], employee_id=r["employee_id"],
                              trigger_kind=kind, subject_id=r["id"],
                              title=title, body=body, today=today,
                              budget=budget, clients_cache=clients_cache):
                opened += 1
    return {"discipline_checked": len(rows), "discipline_opened": opened}


async def _sweep_pending_signatures(conn, enabled_companies, today, budget,
                                    clients_cache) -> dict:
    """One digest per company with a signature backlog.

    Aggregated in SQL rather than by LIMITing rows and grouping in Python: a row
    cap truncates mid-company, so the digest would report "4 outstanding" for a
    company that has 30, and companies sorting after the cutoff would get no
    digest at all while their dedupe stayed cold. The count here is the true
    count; only the NAMES are capped, and the briefing says so."""
    rows = await conn.fetch(
        """
        SELECT ed.org_id AS company_id,
               -- COUNT is the true backlog size the briefing reports; the agg
               -- only supplies the names it lists, and is sliced in Python to
               -- MAX_DIGEST_NAMES before rendering.
               COUNT(*) AS total,
               json_agg(
                    json_build_object(
                        'first_name', e.first_name,
                        'last_name', e.last_name,
                        'title', ed.title
                    ) ORDER BY ed.created_at
               ) AS docs
        FROM employee_documents ed
        JOIN employees e ON e.id = ed.employee_id
        WHERE ed.status = 'pending_signature'
          AND ed.created_at < NOW() - ($1 || ' days')::interval
          AND e.termination_date IS NULL
          AND ed.org_id = ANY($2::uuid[])
          AND NOT EXISTS (
                SELECT 1 FROM hr_proactive_push_log l
                WHERE l.company_id = ed.org_id
                  AND l.trigger_kind = 'pending_signatures'
                  AND l.subject_id = ed.org_id
                  AND l.sent_on > CURRENT_DATE - ($3 || ' days')::interval
          )
        GROUP BY ed.org_id
        ORDER BY ed.org_id
        LIMIT $4
        """,
        str(SIGNATURE_STALE_DAYS), enabled_companies,
        str(SIGNATURE_RENOTIFY_DAYS), budget["remaining"],
    )
    opened = 0
    for r in rows:
        docs = r["docs"]
        if isinstance(docs, str):
            docs = json.loads(docs)
        title, body = build_signature_digest_briefing(
            docs or [], SIGNATURE_STALE_DAYS, total=r["total"],
        )
        if await _deliver(conn, company_id=r["company_id"], employee_id=None,
                          trigger_kind="pending_signatures", subject_id=r["company_id"],
                          title=title, body=body, today=today,
                          budget=budget, clients_cache=clients_cache):
            opened += 1
    return {"signature_companies_checked": len(rows), "signature_digests_opened": opened}


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #

async def _run_hr_proactive_push() -> dict:
    conn = await get_db_connection()
    try:
        sched_row = await scheduler_settings_row(conn, "hr_proactive_push")

        if not sched_row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched_row["enabled"]:
            print("[HR Proactive Push] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        limit = sched_row["max_per_cycle"] or 100
        today = date.today()

        company_rows = await conn.fetch(
            "SELECT id, enabled_features, signup_source FROM companies WHERE status IS NULL OR status = 'approved'"
        )
        enabled = [
            r["id"] for r in company_rows
            if hr_pilot_enabled(r["enabled_features"], r["signup_source"])
        ]
        if not enabled:
            return {"skipped": True, "reason": "no_hr_pilot_companies"}

        # One budget across all three sweeps, counting threads opened. Each
        # sweep also uses the remaining budget as its LIMIT, so a run can never
        # write more than max_per_cycle threads no matter how the events split.
        budget = {"remaining": limit}
        clients_cache: dict = {}

        result = {"hr_pilot_companies": len(enabled)}
        result.update(await _sweep_leave_returns(conn, enabled, today, budget, clients_cache))
        result.update(await _sweep_discipline(conn, enabled, today, budget, clients_cache))
        result.update(await _sweep_pending_signatures(conn, enabled, today, budget, clients_cache))
        result["threads_opened"] = limit - budget["remaining"]
        return result
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_hr_proactive_push(self) -> dict:
    """Open pre-briefed HR Pilot threads ahead of upcoming HR events."""
    print("[HR Proactive Push] Running...")
    try:
        result = asyncio.run(_run_hr_proactive_push())
        print(f"[HR Proactive Push] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[HR Proactive Push] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
