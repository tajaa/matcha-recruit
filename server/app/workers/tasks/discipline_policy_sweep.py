"""Celery task: incident policy-check sweep.

Scans recently-closed incidents, checks each against the company's handbook
+ active policies (`discipline_policy_check.check_incident_against_handbook`),
and on a finding opens a pre-briefed Huume thread — modeled directly on
`hr_proactive_push.py`'s source-table-scan + SQL `NOT EXISTS` ledger +
one-transaction-per-delivery shape, not a separate queue table. No request-path
code exists for this anywhere: the two incident-close sites
(`ir_copilot_flow.py`, `ir_incidents/crud.py`) do NOT call into this module —
this sweep finds its own work by scanning `ir_incidents` directly, so a policy
check can never fail (or even slow down) an incident close.

The briefing is a DETERMINISTIC template over the stored check result — no
Gemini call happens in the thread-opening transaction; the (already-completed)
Gemini call is the check itself, run once per incident, per the ledger below.
The grounded, cited turn happens when the admin replies in the thread.

Dedupe: `discipline_policy_sweep_log`, UNIQUE on `incident_id` alone (a single
subject dimension, unlike hr_proactive_push_log's polymorphic subject_id) —
one row per incident, ever. A row with `thread_id IS NULL` means "checked,
found nothing" and must ALSO be stamped, or a clean incident gets re-Gemini'd
every cycle; a `available=False` result (Gemini outage) does NOT stamp, so a
transient failure gets retried on the next sweep instead of being permanently
marked "checked".

Gated on scheduler_settings.task_key = 'discipline_policy_sweep' (seeded
DISABLED, migration discipapp01).
"""

import asyncio
import json

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

# Only incidents closed within this window are candidates — an incident
# closed a year ago isn't worth a fresh Gemini call today, and bounding the
# scan keeps the query cheap as ir_incidents grows.
LOOKBACK_DAYS = 14


class _AlreadyStamped(Exception):
    """Raised inside the open-thread transaction when the ledger row already
    exists, to roll back a thread a concurrent run already delivered."""


def discipline_policy_sweep_enabled(enabled_features, signup_source) -> bool:
    """Whether a company has the flags this sweep needs: huume (the thread
    surface), matcha_work (threads at all), discipline (what gets drafted),
    incidents (the source data), handbooks (the corpus the check grounds on).
    Resolved through the shared merge, not a raw JSONB lookup — see
    hr_proactive_push.hr_pilot_enabled for why that distinction matters."""
    from app.core.feature_flags import merge_company_features
    merged = merge_company_features(enabled_features, signup_source)
    return bool(
        merged.get("huume") and merged.get("matcha_work")
        and merged.get("discipline") and merged.get("incidents")
        and merged.get("handbooks")
    )


def build_finding_briefing(incident: dict, result: dict) -> tuple[str, str]:
    """(title, body) — pure, DB-free, unit-tested. `result` is the return
    shape of `discipline_policy_check.check_incident_against_handbook`."""
    incident_number = incident.get("incident_number") or "an incident"
    title = f"Policy check: {incident_number}"
    violations = result.get("violations") or []
    lines = [
        f"Huume checked the closed incident **{incident_number}** "
        f"(\"{incident.get('title') or 'untitled'}\") against your handbook and active "
        f"policies, and found {len(violations)} possible match"
        f"{'es' if len(violations) != 1 else ''}:",
        "",
    ]
    for v in violations[:5]:
        conf_pct = round(float(v.get("confidence") or 0) * 100)
        lines.append(f"- **{v.get('policy_title')}** ({v.get('relevance')}, {conf_pct}% confidence)")
    if len(violations) > 5:
        lines.append(f"- …and {len(violations) - 5} more")
    lines.append("")
    if result.get("summary"):
        lines.append(result["summary"])
        lines.append("")
    lines.append(
        "Reply here to draft a disciplinary action from this incident — I'll route it "
        "for HR approval before anything is issued."
    )
    return title, "\n".join(lines)


async def _stamp_clean(conn, *, company_id, incident_id) -> None:
    await conn.execute(
        """
        INSERT INTO discipline_policy_sweep_log (company_id, incident_id, thread_id, finding_count)
        VALUES ($1, $2, NULL, 0)
        ON CONFLICT (incident_id) DO NOTHING
        """,
        company_id, incident_id,
    )


async def _stamp_ineligible(conn, *, company_id, incident_id) -> None:
    """A company without the huume/discipline/etc. flag combo this sweep
    needs. finding_count = -1 distinguishes this from `_stamp_clean`'s 0
    (checked, genuinely nothing found) — this incident was never checked at
    all. Without stamping it, the `NOT EXISTS` prefilter re-selects it every
    cycle forever; at 100+ closed incidents from non-huume companies (the
    common case, since huume defaults off) that fills the whole `limit * 4`
    scan window and an eligible company's incident is never reached."""
    await conn.execute(
        """
        INSERT INTO discipline_policy_sweep_log (company_id, incident_id, thread_id, finding_count)
        VALUES ($1, $2, NULL, -1)
        ON CONFLICT (incident_id) DO NOTHING
        """,
        company_id, incident_id,
    )


async def _stamp_undelivered(conn, *, company_id, incident_id, finding_count) -> None:
    """A real finding that couldn't be delivered because the company has no
    active client user to own the thread. Distinct from `_stamp_clean`
    (finding_count 0) — stamped here so the incident isn't re-Gemini'd on
    every sweep forever once a company reaches this state."""
    await conn.execute(
        """
        INSERT INTO discipline_policy_sweep_log (company_id, incident_id, thread_id, finding_count)
        VALUES ($1, $2, NULL, $3)
        ON CONFLICT (incident_id) DO NOTHING
        """,
        company_id, incident_id, finding_count,
    )


async def _company_client_users(conn, company_id, cache: dict) -> list:
    if company_id in cache:
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
    cache[company_id] = users
    return users


async def _hr_notify_user_ids(conn, company_id, all_clients: list) -> list:
    """Who gets told a policy match was found: the company's DESIGNATED HR
    approvers (clients.is_hr_approver), falling back to every client user when
    nobody is designated. Same resolution rule as
    discipline_notifications._designated_approver_user_ids — a finding is an
    approval-queue event, so it must not be broadcast wider than the approval
    request that follows it."""
    rows = await conn.fetch(
        """
        SELECT u.id
        FROM clients c JOIN users u ON u.id = c.user_id
        WHERE c.company_id = $1 AND u.role = 'client' AND u.is_active = true
          AND c.is_hr_approver = true
        """,
        company_id,
    )
    designated = [r["id"] for r in rows]
    return designated or all_clients


async def _open_thread(conn, *, company_id, incident, result, clients_cache) -> bool:
    """Open a pre-briefed Huume thread for this finding, in one transaction
    with the ledger stamp. Returns True if a thread was opened."""
    clients = await _company_client_users(conn, company_id, clients_cache)
    if not clients:
        return False
    owner_user_id = clients[0]
    recipients = await _hr_notify_user_ids(conn, company_id, clients)

    title, body = build_finding_briefing(incident, result)
    violations = result.get("violations") or []

    async with conn.transaction():
        thread_id = await conn.fetchval(
            """
            INSERT INTO mw_threads (company_id, created_by, title, current_state, huume_mode)
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
                "source": "discipline_policy_sweep",
                "incident_id": str(incident["id"]),
            }),
        )
        await conn.execute("UPDATE mw_threads SET updated_at = NOW() WHERE id = $1", thread_id)

        for user_id in recipients:
            await conn.execute(
                """
                INSERT INTO mw_notifications (user_id, company_id, type, title, body, link, metadata)
                VALUES ($1, $2, 'hr_proactive', $3, $4, $5, $6::jsonb)
                """,
                user_id, company_id, title[:255],
                "Huume found a possible policy match on a closed incident.",
                f"/work/{thread_id}",
                json.dumps({"thread_id": str(thread_id), "trigger": "discipline_policy_sweep"}),
            )

        stamped = await conn.fetchval(
            """
            INSERT INTO discipline_policy_sweep_log (company_id, incident_id, thread_id, finding_count)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (incident_id) DO NOTHING
            RETURNING id
            """,
            company_id, incident["id"], thread_id, len(violations),
        )
        if stamped is None:
            # A concurrent run beat us to this incident between the scan's
            # NOT EXISTS prefilter and here — roll the whole unit back rather
            # than leave a duplicate thread with no ledger row to suppress the
            # next run.
            raise _AlreadyStamped(str(incident["id"]))
    return True


async def _run_discipline_policy_sweep() -> dict:
    from ...matcha.services.discipline.discipline_policy_check import (
        check_incident_against_handbook,
        persist_policy_check,
    )

    conn = await get_db_connection()
    try:
        sched_row = await scheduler_settings_row(conn, "discipline_policy_sweep")
        if not sched_row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched_row["enabled"]:
            print("[Discipline Policy Sweep] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        limit = sched_row["max_per_cycle"] or 25

        rows = await conn.fetch(
            f"""
            SELECT i.id, i.company_id, i.title, i.incident_number, i.description,
                   i.incident_type, i.severity, c.enabled_features, c.signup_source
            FROM ir_incidents i
            JOIN companies c ON c.id = i.company_id
            WHERE i.status = 'closed'
              AND i.updated_at > NOW() - INTERVAL '{LOOKBACK_DAYS} days'
              AND NOT EXISTS (
                  SELECT 1 FROM discipline_policy_sweep_log l WHERE l.incident_id = i.id
              )
            ORDER BY i.updated_at ASC
            LIMIT $1
            """,
            # Scan wider than the thread budget: most incidents won't have
            # huume+discipline enabled, and every non-eligible one gets
            # stamped ineligible below so it drops out of next cycle's scan —
            # this window is only ever wide on the very first sweep.
            limit * 4,
        )

        checked = 0
        findings = 0
        opened = 0
        clients_cache: dict = {}

        for row in rows:
            if opened >= limit:
                break
            if not discipline_policy_sweep_enabled(row["enabled_features"], row["signup_source"]):
                await _stamp_ineligible(conn, company_id=row["company_id"], incident_id=row["id"])
                continue

            incident = dict(row)
            try:
                result = await check_incident_against_handbook(
                    conn, company_id=incident["company_id"], incident=incident,
                )
            except Exception:  # noqa: BLE001
                print(f"[Discipline Policy Sweep] check failed for incident {incident['id']}")
                continue

            if not result.get("available"):
                # Gemini outage or grounding failure — do NOT stamp, so this
                # incident is retried on the next sweep instead of being
                # permanently marked "checked".
                continue

            checked += 1
            try:
                await persist_policy_check(conn, incident_id=incident["id"], result=result)
            except Exception:  # noqa: BLE001
                print(f"[Discipline Policy Sweep] persist failed for incident {incident['id']}")

            violations = result.get("violations") or []
            if not violations:
                await _stamp_clean(conn, company_id=incident["company_id"], incident_id=incident["id"])
                continue

            findings += 1
            try:
                if await _open_thread(
                    conn, company_id=incident["company_id"], incident=incident,
                    result=result, clients_cache=clients_cache,
                ):
                    opened += 1
                else:
                    # No active client user to own the thread — stamp so this
                    # incident isn't re-Gemini'd every sweep forever.
                    await _stamp_undelivered(
                        conn, company_id=incident["company_id"], incident_id=incident["id"],
                        finding_count=len(violations),
                    )
            except _AlreadyStamped:
                pass
            except Exception:  # noqa: BLE001
                print(f"[Discipline Policy Sweep] thread open failed for incident {incident['id']}")

        return {
            "scanned": len(rows), "checked": checked, "findings": findings, "threads_opened": opened,
        }
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_discipline_policy_sweep(self) -> dict:
    """Check recently-closed incidents against the company handbook."""
    print("[Discipline Policy Sweep] Running...")
    try:
        result = asyncio.run(_run_discipline_policy_sweep())
        print(f"[Discipline Policy Sweep] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Discipline Policy Sweep] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
