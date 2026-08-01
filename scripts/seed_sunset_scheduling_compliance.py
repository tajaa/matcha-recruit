#!/usr/bin/env python3
"""Seed the Sunset Smile Dental Group tenant with test data for the
scheduling + workforce-compliance surfaces that shipped in the 7/31 batch:
`employee_schedule` (employee-facing swap/drop/unavailability requests),
`schedule_intelligence` (all four analytics modules), and
`workforce_compliance` (the four employment-practices registers).

The tenant already has 433 published shifts / 546 assignments / 67 employees
from an earlier seed. What it did NOT have — and what this fills — is the
data those newer read-time engines actually compute over:

  1. schedule_requests (was 0) — the whole employee-facing half of
     `employee_schedule`. Swap/drop/unavailability in every status.
  2. schedule_audit_log churn (was 10 rows, none priceable) — enriched
     employer-initiated changes to PUBLISHED shifts, which is the only
     input `fair_workweek.price_event` can cost. Includes two
     employee-initiated changes (an approved request logged within the
     120s correlation window) specifically so the exemption path is
     demonstrable, not just the priced path.
  3. ir_incidents.involved_employee_ids (was 2 of 16) — without named
     employees `build_incident_correlation` computes no fatigue flags.
     Linked to people who actually worked adjacent shifts, and shaped so
     both fatigue signals fire (short rest gap, >=6-day streak).
  4. training_requirements / training_records (was 2 / 1) — the lapse
     feed behind `build_qualified_coverage` and the roster lapse badges.
  5. workforce_compliance registers — more pay-transparency states, an
     overdue AI hiring-tool audit, a biometric collection point missing
     consent, and a pay-equity review carrying a real measured gap_pct
     distinct from the dispersion screen.

Deterministic — no Gemini, no model calls. The @huume schedule-chat path
(`schedule_chat_proposals`) is deliberately NOT seeded here: it parses via
Gemini off a real channel message, so it's exercised by sending
"@huume ..." in #Front Desk over the live WS instead of forged rows.

Dev-only. Connects directly to the local dev Postgres container
(matcha-postgres:5432/matcha) — never point DATABASE_URL at this script.

Additive only. Every row it writes is tagged (see TAG below) so the undo
below is exact and can't catch a live row.

Re-running inserts a second copy of the schedule_requests / audit-log /
training rows; the workforce-compliance registers are upserted on their
natural keys and the incident links are idempotent (set, not appended).

Run:
    cd server && ./venv/bin/python ../scripts/seed_sunset_scheduling_compliance.py

Undo:
    DELETE FROM schedule_requests WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND review_notes LIKE '%[seed:sched-compliance]%';
    DELETE FROM schedule_audit_log WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND details->>'seed_tag' = 'sched-compliance';
    DELETE FROM training_records WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND notes LIKE '%[seed:sched-compliance]%';
    DELETE FROM training_requirements WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND description LIKE '%[seed:sched-compliance]%';
    DELETE FROM hiring_ai_audits WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND notes LIKE '%[seed:sched-compliance]%';
    DELETE FROM biometric_consent_points WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND notes LIKE '%[seed:sched-compliance]%';
    DELETE FROM pay_equity_reviews WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND notes LIKE '%[seed:sched-compliance]%';
    DELETE FROM pay_transparency_status WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND note LIKE '%[seed:sched-compliance]%';
    -- (the four employees given work_state='CA' are left as-is on undo —
    --  it is the correct value for CA-clinic staff, not seed-only data)
    -- incidents this script CREATED (numbered IR-2026-SC-*) go entirely:
    DELETE FROM ir_incidents WHERE company_id = '287fffb5-ea50-40a2-bf07-6b5c2ca3c400'
        AND incident_number LIKE 'IR-2026-SC-%';
    -- pre-existing incidents were only given an involved_employee_ids link;
    -- the audit row is the marker (nothing is written to their narrative):
    UPDATE ir_incidents SET involved_employee_ids = NULL WHERE id IN (
        SELECT incident_id FROM ir_audit_log
        WHERE details->>'seed_tag' = 'sched-compliance'
          AND action = 'incident.involved_employees_set');
    DELETE FROM ir_audit_log WHERE details->>'seed_tag' = 'sched-compliance';
"""

import asyncio
import json
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import asyncpg  # noqa: E402

DATABASE_URL = "postgresql://matcha:matcha_dev@localhost:5432/matcha"

COMPANY_ID = UUID("287fffb5-ea50-40a2-bf07-6b5c2ca3c400")  # Sunset Smile Dental Group
LA_LOCATION = UUID("59bf0bdc-558f-4530-8917-a792eb7f5d98")  # Wilshire (Los Angeles)

TAG = "[seed:sched-compliance]"
SEED_TAG = "sched-compliance"

# Deterministic run-to-run so a re-seed produces the same narrative.
RNG = random.Random(20260731)


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── 1. schedule_requests ─────────────────────────────────────────────────

async def seed_schedule_requests(conn, admin_user_id) -> int:
    """Swap / drop / unavailability in every status.

    Requests are filed against UPCOMING published shifts by the employee
    actually assigned to them — a swap request naming someone who isn't on
    the shift is not a shape the real UI can produce, and the approval path
    reads the assignment row.
    """
    shifts = await conn.fetch(
        """
        SELECT s.id, s.starts_at, s.role, a.employee_id
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id AND a.status <> 'declined'
        JOIN employees e ON e.id = a.employee_id
        WHERE s.company_id = $1 AND s.status = 'published'
          AND s.starts_at >= NOW() AND s.starts_at < NOW() + INTERVAL '21 days'
          AND e.employment_status = 'active'
        ORDER BY s.starts_at
        LIMIT 40
        """,
        COMPANY_ID,
    )
    if not shifts:
        print("  ! no upcoming published+assigned shifts — skipping schedule_requests")
        return 0

    # Coworkers in the same role are the plausible swap targets.
    coworkers = await conn.fetch(
        """
        SELECT id, job_title FROM employees
        WHERE org_id = $1 AND employment_status = 'active' AND pay_rate IS NOT NULL
        """,
        COMPANY_ID,
    )
    coworker_ids = [r["id"] for r in coworkers]

    plan = [
        ("swap", "pending", "Dentist appt for my kid that morning — Miguel said he can take it."),
        ("swap", "pending", "Family thing out of town, already squared it with Bea."),
        ("drop", "pending", "Double-booked with a class I can't move."),
        ("unavailable", "pending", "Night classes Tues/Thurs through the end of the term."),
        ("swap", "approved", "Swapping with Kai so I can cover my sister's move."),
        ("drop", "approved", "Called out — food poisoning, sorry for the short notice."),
        ("unavailable", "approved", "Pre-approved PTO, flights already booked."),
        ("swap", "denied", "Wanted to trade but we'd both be off the floor that morning."),
        ("drop", "denied", "Too close to the date and nobody picked it up."),
    ]

    inserted = 0
    for i, (rtype, status, reason) in enumerate(plan):
        row = shifts[i % len(shifts)]
        employee_id = row["employee_id"]
        shift_id = row["id"] if rtype != "unavailable" else None

        target = None
        if rtype == "swap":
            candidates = [c for c in coworker_ids if c != employee_id]
            target = RNG.choice(candidates) if candidates else None

        unavailable_start = unavailable_end = None
        if rtype == "unavailable":
            start = date.today() + timedelta(days=10 + i)
            unavailable_start, unavailable_end = start, start + timedelta(days=3)

        reviewed_by = admin_user_id if status in ("approved", "denied") else None
        reviewed_at = (
            datetime.now(timezone.utc) - timedelta(days=RNG.randint(1, 5))
            if status in ("approved", "denied") else None
        )
        review_note = {
            "approved": f"Approved — coverage confirmed. {TAG}",
            "denied": f"Denied — would leave the front desk short. {TAG}",
        }.get(status, TAG)

        await conn.execute(
            """
            INSERT INTO schedule_requests
                (company_id, employee_id, request_type, shift_id, target_employee_id,
                 unavailable_start, unavailable_end, reason, status,
                 reviewed_by, reviewed_at, review_notes, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            """,
            COMPANY_ID, employee_id, rtype, shift_id, target,
            unavailable_start, unavailable_end, reason, status,
            reviewed_by, reviewed_at, review_note,
            datetime.now(timezone.utc) - timedelta(days=RNG.randint(2, 9)),
        )
        inserted += 1
    return inserted


# ── 2. schedule_audit_log churn (Fair Workweek + pretext shield) ─────────

async def seed_audit_churn(conn, admin_user_id) -> tuple[int, int]:
    """Employer-initiated changes to PUBLISHED shifts at the LA location.

    Only published shifts are priceable (`classify_change` returns None on
    `was_published: false`), and only hourly employees can be costed — the
    LA bracket is `hours_at_rate`, so a salaried dentist's 205000 "rate"
    would price one shift change at $205k. Restricting to the hourly Front
    Office Coordinators is both the realistic Fair Workweek population and
    the only one that yields sane dollars.

    Two of the events are logged alongside a `request.approved` row for the
    same shift within the 120s correlation window, which is how
    `classify_audit_row` recognises an employee-initiated change and drops
    it from exposure — the exemption is worth demoing, not just the charge.
    """
    shifts = await conn.fetch(
        """
        SELECT DISTINCT ON (s.id)
               s.id, s.starts_at, s.ends_at, s.location_id, a.employee_id, e.pay_rate
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id AND a.status <> 'declined'
        JOIN employees e ON e.id = a.employee_id
        WHERE s.company_id = $1 AND s.location_id = $2 AND s.status = 'published'
          AND s.starts_at >= NOW() - INTERVAL '85 days' AND s.starts_at < NOW()
          AND e.pay_rate BETWEEN 15 AND 60
        ORDER BY s.id, s.starts_at
        LIMIT 30
        """,
        COMPANY_ID, LA_LOCATION,
    )
    if not shifts:
        print("  ! no LA published shifts with hourly assignees — skipping audit churn")
        return 0, 0

    priced_rows = 0
    exempt_rows = 0

    for i, s in enumerate(shifts[:24]):
        starts_at = _utc(s["starts_at"])
        ends_at = _utc(s["ends_at"])
        # Notice window drives the bracket: spread across the 14-day range
        # so the exposure list isn't all one tier.
        notice_days = [0.4, 1.5, 3.0, 6.0, 9.0, 12.0][i % 6]
        logged_at = starts_at - timedelta(days=notice_days)

        # Cycle the four priceable change kinds.
        kind = i % 4
        if kind == 0:
            # time_change — same duration, later start
            before = {
                "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(),
                "status": "published", "location_id": str(s["location_id"]),
            }
            after = {
                "starts_at": (starts_at + timedelta(hours=2)).isoformat(),
                "ends_at": (ends_at + timedelta(hours=2)).isoformat(),
                "status": "published", "location_id": str(s["location_id"]),
            }
            action, details = "shift.update", {
                "before": before, "after": after,
                "fields": ["starts_at", "ends_at"], "was_published": True,
            }
        elif kind == 1:
            # reduced_hours — shortened shift
            before = {
                "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(),
                "status": "published", "location_id": str(s["location_id"]),
            }
            after = {
                "starts_at": starts_at.isoformat(),
                "ends_at": (ends_at - timedelta(hours=3)).isoformat(),
                "status": "published", "location_id": str(s["location_id"]),
            }
            action, details = "shift.update", {
                "before": before, "after": after,
                "fields": ["ends_at"], "was_published": True,
            }
        elif kind == 2:
            # added_hours — an assignee added to an already-posted shift
            action, details = "assignment.create", {
                "employee_id": str(s["employee_id"]),
                "shift_status": "published",
                "shift_starts_at": starts_at.isoformat(),
            }
        else:
            # reduced_hours — an assignee pulled off a posted shift
            action, details = "assignment.delete", {
                "employee_id": str(s["employee_id"]),
                "shift_status": "published",
                "shift_starts_at": starts_at.isoformat(),
            }

        details["seed_tag"] = SEED_TAG
        await conn.execute(
            """
            INSERT INTO schedule_audit_log
                (company_id, entity_type, entity_id, actor_user_id, action, details, created_at)
            VALUES ($1,'shift',$2,$3,$4,$5,$6)
            """,
            COMPANY_ID, s["id"], admin_user_id, action, json.dumps(details), logged_at,
        )
        priced_rows += 1

        # Two employee-initiated changes: an approval logged at the same
        # instant marks the change as the consequence of the employee's own
        # request, which every FW ordinance exempts.
        if i in (5, 11):
            await conn.execute(
                """
                INSERT INTO schedule_audit_log
                    (company_id, entity_type, entity_id, actor_user_id, action, details, created_at)
                VALUES ($1,'shift',$2,$3,'request.approved',$4,$5)
                """,
                COMPANY_ID, s["id"], admin_user_id,
                json.dumps({
                    "employee_id": str(s["employee_id"]),
                    "employee_initiated": True,
                    "request_type": "swap",
                    "seed_tag": SEED_TAG,
                }),
                logged_at + timedelta(seconds=20),
            )
            priced_rows -= 1
            exempt_rows += 1

    return priced_rows, exempt_rows


# ── 3. incidents in-window (clears the small-n guard) + employee links ───

# Realistic dental-practice safety/near-miss events. `occurred_at` is set
# relative to today so the set always sits inside the correlation window.
_INCIDENTS = [
    (12, "safety", "medium", "Sharps container overfilled in operatory 3",
     "RDA flagged the sharps container past the fill line during turnover. Replaced immediately; "
     "no injury. Noted the pickup schedule had slipped a week."),
    (26, "near_miss", "medium", "Slip on wet floor near sterilization sink",
     "Front office coordinator slipped on standing water by the sterilization sink but caught the "
     "counter. No fall, no injury. Floor mat had been moved during a supply delivery."),
    (39, "safety", "high", "Handpiece burn — assistant's forearm during procedure",
     "Assistant contacted a hot handpiece head immediately after autoclave cycle. Minor first-degree "
     "burn, first aid on site, declined further care. Cooling interval not observed."),
    (54, "near_miss", "low", "Nitrous line fitting found loose during morning check",
     "Morning equipment check found the nitrous line fitting on chair 2 finger-loose. Tightened and "
     "leak-tested before first patient. No exposure."),
    (68, "other", "medium", "Patient verbally aggressive toward front desk over billing",
     "Patient raised voice and refused to leave the reception area for roughly ten minutes over a "
     "billing dispute. De-escalated by the office manager. No contact, no threat of harm."),
    (81, "safety", "medium", "Chemical splash — disinfectant during dilution",
     "Disinfectant concentrate splashed onto an assistant's safety glasses while diluting. Eyewear "
     "worked as intended; no eye contact. Dilution station lacks a splash guard."),
]


async def seed_incidents(conn) -> int:
    """Top up the correlation window so the rate comparison isn't
    suppressed. `build_incident_correlation` needs >= 10 incidents (with a
    location) in its 180-day window before it will show anything beyond raw
    counts — the tenant had 8, so the module rendered as counts-only and
    the whole point of the engine was invisible.

    Deliberately spread across both severities and both fatigue-relevant
    windows rather than clustered, so the staffing/day-night splits have
    something to actually differentiate.
    """
    existing = await conn.fetchval(
        """
        SELECT COUNT(*) FROM ir_incidents
        WHERE company_id = $1 AND location_id IS NOT NULL
          AND occurred_at >= (NOW() - INTERVAL '180 days')::timestamp
        """,
        COMPANY_ID,
    )
    if existing >= 12:
        return 0

    reporter = await conn.fetchrow(
        """
        SELECT first_name || ' ' || last_name AS name FROM employees
        WHERE org_id = $1 AND employment_status = 'active' AND job_title ILIKE '%coordinator%'
        ORDER BY last_name LIMIT 1
        """,
        COMPANY_ID,
    )
    reporter_name = reporter["name"] if reporter else "Front Office"

    # Anchor each incident inside a REAL staffed shift rather than guessing
    # a clock hour: `match_incidents_to_shifts` only counts an incident that
    # falls within a shift's window, and the fatigue pass only looks at
    # employees actually assigned to the matched shift. A hardcoded hour
    # silently lands outside the 08:00-18:00 coverage (or on a day with no
    # shift at all) and the incident matches nothing.
    candidate_shifts = await conn.fetch(
        """
        SELECT DISTINCT ON (s.id) s.id, s.starts_at, s.ends_at
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id AND a.status <> 'declined'
        JOIN employees e ON e.id = a.employee_id
        WHERE s.company_id = $1 AND s.location_id = $2 AND s.status <> 'cancelled'
          AND s.starts_at >= NOW() - INTERVAL '170 days' AND s.starts_at < NOW()
          AND e.employment_status = 'active'
        ORDER BY s.id, s.starts_at
        """,
        COMPANY_ID, LA_LOCATION,
    )
    if not candidate_shifts:
        print("  ! no staffed LA shifts in window — skipping incident top-up")
        return 0
    # Spread across the window so the day/night and staffing splits differ.
    candidate_shifts = sorted(candidate_shifts, key=lambda r: r["starts_at"])

    created = 0
    for idx, (days_ago, itype, severity, title, description) in enumerate(_INCIDENTS):
        shift = candidate_shifts[(idx * max(1, len(candidate_shifts) // len(_INCIDENTS)))
                                 % len(candidate_shifts)]
        starts, ends = _utc(shift["starts_at"]), _utc(shift["ends_at"])
        span = max(int((ends - starts).total_seconds()) - 1800, 1800)
        occurred = (starts + timedelta(seconds=RNG.randint(900, span))).replace(tzinfo=None)
        suffix = f"{days_ago:03d}"
        await conn.execute(
            """
            INSERT INTO ir_incidents
                (company_id, incident_number, title, description, incident_type, severity,
                 status, occurred_at, location_id, reported_by_name, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'reported',$7,$8,$9,$10)
            """,
            COMPANY_ID, f"IR-2026-SC-{suffix}", title, description, itype, severity,
            occurred, LA_LOCATION, reporter_name,
            # ir_incidents.occurred_at/created_at are `timestamp WITHOUT
            # time zone` — asyncpg rejects a tz-aware value for them.
            occurred + timedelta(hours=RNG.randint(1, 20)),
        )
        # Marker lives in the audit trail, not the narrative — see
        # link_incidents_to_employees for why.
        await conn.execute(
            """
            INSERT INTO ir_audit_log (incident_id, action, entity_type, details)
            SELECT id, 'incident.created', 'incident', $2
            FROM ir_incidents WHERE company_id = $1 AND incident_number = $3
            """,
            COMPANY_ID, json.dumps({"seed_tag": SEED_TAG, "source": "scheduling-compliance seed"}),
            f"IR-2026-SC-{suffix}",
        )
        created += 1
    return created


async def link_incidents_to_employees(conn) -> int:
    """Name employees on in-window incidents so the fatigue analysis has
    someone to compute a rest gap / consecutive-day streak for.

    Each incident is linked to an employee who actually worked a shift
    overlapping it — a name with no adjacent schedule history produces no
    fatigue signal at all, which would make the module look broken rather
    than clean.
    """
    incidents = await conn.fetch(
        """
        SELECT id, occurred_at, location_id
        FROM ir_incidents
        WHERE company_id = $1 AND location_id IS NOT NULL
          AND occurred_at >= (NOW() - INTERVAL '175 days')::timestamp
          AND (involved_employee_ids IS NULL OR array_length(involved_employee_ids, 1) IS NULL)
        ORDER BY occurred_at DESC
        """,
        COMPANY_ID,
    )
    linked = 0
    for inc in incidents:
        occurred = inc["occurred_at"]
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        worker = await conn.fetchrow(
            """
            SELECT a.employee_id
            FROM schedule_shifts s
            JOIN schedule_shift_assignments a ON a.shift_id = s.id AND a.status <> 'declined'
            JOIN employees e ON e.id = a.employee_id
            WHERE s.company_id = $1 AND s.location_id = $2 AND s.status <> 'cancelled'
              AND s.starts_at <= $3 AND s.ends_at >= $3
              AND e.employment_status = 'active'
            ORDER BY s.starts_at
            LIMIT 1
            """,
            COMPANY_ID, inc["location_id"], occurred,
        )
        if not worker:
            continue
        await conn.execute(
            "UPDATE ir_incidents SET involved_employee_ids = ARRAY[$2::uuid] WHERE id = $1",
            inc["id"], worker["employee_id"],
        )
        # The marker goes in the audit trail, NOT on the incident row —
        # ir_incidents has no notes column and `description` is the
        # reporter's narrative on a legal record, which a seed script has
        # no business appending to. The audit row is also what the undo
        # in this module's docstring joins against.
        await conn.execute(
            """
            INSERT INTO ir_audit_log (incident_id, action, entity_type, details)
            VALUES ($1, 'incident.involved_employees_set', 'incident', $2)
            """,
            inc["id"],
            json.dumps({
                "seed_tag": SEED_TAG,
                "employee_id": str(worker["employee_id"]),
                "reason": "schedule-correlation fatigue analysis demo data",
            }),
        )
        linked += 1
    return linked


# ── 4. training (qualified coverage + lapse badges) ──────────────────────

_TRAINING = [
    ("Bloodborne Pathogens (OSHA 1910.1030)", "safety", 12, "all"),
    ("HIPAA Privacy & Security Refresher", "compliance", 12, "all"),
    ("BLS / CPR Certification", "safety", 24, "all"),
    ("Radiation Safety — Dental X-Ray Operator", "safety", 24, "all"),
]


async def seed_training(conn) -> tuple[int, int]:
    """A handful of dental-realistic requirements plus records in every
    state qualified-coverage cares about: current, expiring-soon, overdue,
    and not-yet-started."""
    req_ids = []
    for title, ttype, months, applies in _TRAINING:
        rid = await conn.fetchval(
            """
            INSERT INTO training_requirements
                (company_id, title, description, training_type, jurisdiction,
                 frequency_months, applies_to, is_active)
            VALUES ($1,$2,$3,$4,'CA',$5,$6,true)
            RETURNING id
            """,
            COMPANY_ID, title,
            f"Recurring requirement for clinical and front-office staff. {TAG}",
            ttype, months, applies,
        )
        req_ids.append((rid, title, ttype, months))

    employees = await conn.fetch(
        """
        SELECT id, job_title FROM employees
        WHERE org_id = $1 AND employment_status = 'active'
        ORDER BY last_name LIMIT 24
        """,
        COMPANY_ID,
    )

    today = date.today()
    # (status, completed offset days, expiration offset days) — negative
    # expiration = already lapsed, small positive = expiring soon.
    shapes = [
        ("completed", -200, 165),    # current
        ("completed", -320, 20),     # expiring within the month
        ("completed", -400, -35),    # lapsed
        ("assigned", None, None),    # never started
        ("in_progress", None, None),
    ]

    records = 0
    for i, emp in enumerate(employees):
        rid, title, ttype, months = req_ids[i % len(req_ids)]
        status, done_off, exp_off = shapes[i % len(shapes)]
        completed = today + timedelta(days=done_off) if done_off is not None else None
        expiration = today + timedelta(days=exp_off) if exp_off is not None else None
        due = (
            completed + timedelta(days=30) if completed
            else today + timedelta(days=RNG.choice([-14, -3, 12, 30]))
        )
        await conn.execute(
            """
            INSERT INTO training_records
                (company_id, employee_id, requirement_id, title, training_type, status,
                 assigned_date, due_date, completed_date, expiration_date,
                 provider, score, source_type, notes)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'manual',$13)
            """,
            COMPANY_ID, emp["id"], rid, title, ttype, status,
            (completed or today) - timedelta(days=30), due, completed, expiration,
            "CE Zone Dental" if completed else None,
            round(RNG.uniform(84, 99), 2) if completed else None,
            f"Seeded for schedule-intelligence qualified-coverage demo. {TAG}",
        )
        records += 1
    return len(req_ids), records


# ── 5. workforce_compliance registers ────────────────────────────────────

async def seed_workforce_compliance(conn, admin_user_id) -> dict:
    counts = {}
    today = date.today()

    # Fill in the four active employees carrying NO work_state. They are
    # front-desk staff at the two CA clinics, so CA is simply the correct
    # value; `employees.work_state` is what `discipline_compliance` keys its
    # state sick-leave table on, and a NULL there reads as "unmapped state"
    # rather than "California".
    #
    # NOTE: this does NOT affect the pay-transparency register. A row's
    # `required` flag comes from `business_locations.state`
    # (workforce_compliance._company_states), not from the roster — so the
    # NY/CO rows seeded below stay `required: false` and the summary keeps
    # reporting `action_needed: 0`. Making another state *required* means
    # giving the company a business location there, which is a much larger
    # change (locations feed scheduling, jurisdiction scoping, and property)
    # and is deliberately not done here.
    filled = await conn.execute(
        """
        UPDATE employees SET work_state = 'CA'
        WHERE org_id = $1 AND employment_status = 'active' AND work_state IS NULL
        """,
        COMPANY_ID,
    )
    counts["employees_work_state_filled"] = int(filled.split()[-1]) if filled else 0

    # Pay transparency — CA already present and compliant. The rest are
    # non-required states the register still lists (a company can track a
    # state it doesn't operate in); see the note above about `required`.
    pt = [
        ("NY", "action_needed", False, "Job board postings still omit ranges for the NY telehealth roles."),
        ("CO", "action_needed", False, "No ranges on the two remote coordinator reqs."),
        ("WA", "compliant", True, "All postings carry ranges + benefits summary."),
        ("NV", "na", False, "No employees or postings in this state."),
    ]
    for state, status, ranges, note in pt:
        await conn.execute(
            """
            INSERT INTO pay_transparency_status
                (company_id, state, status, postings_include_ranges, note, updated_by)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (company_id, state) DO UPDATE
            SET status = EXCLUDED.status,
                postings_include_ranges = EXCLUDED.postings_include_ranges,
                note = EXCLUDED.note, updated_at = NOW()
            """,
            COMPANY_ID, state, status, ranges, f"{note} {TAG}", admin_user_id,
        )
    counts["pay_transparency"] = len(pt)

    # AI hiring tools — one current, one overdue (the register's whole point).
    tools = [
        ("SmileHire Resume Ranker", "SmileHire Inc.", "Ranks applicants for front-office reqs",
         today - timedelta(days=120), 365, False),
        ("ChairsideFit Assessment", "Chairside Analytics", "Scores clinical-aptitude assessment",
         today - timedelta(days=520), 365, True),
        ("AutoSchedule Screener", "Vendor TBD", "Auto-screens availability on applications",
         None, 365, True),
    ]
    for name, vendor, purpose, last_audit, cadence, overdue in tools:
        next_due = last_audit + timedelta(days=cadence) if last_audit else today - timedelta(days=30)
        await conn.execute(
            """
            INSERT INTO hiring_ai_audits
                (company_id, tool_name, vendor, purpose, last_audit_date,
                 cadence_days, next_due_date, is_overdue, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (company_id, tool_name) DO UPDATE
            SET vendor = EXCLUDED.vendor, purpose = EXCLUDED.purpose,
                last_audit_date = EXCLUDED.last_audit_date,
                next_due_date = EXCLUDED.next_due_date,
                is_overdue = EXCLUDED.is_overdue, notes = EXCLUDED.notes, updated_at = NOW()
            """,
            COMPANY_ID, name, vendor, purpose, last_audit, cadence, next_due, overdue,
            f"Bias-audit register entry. {TAG}", admin_user_id,
        )
    counts["hiring_ai_audits"] = len(tools)

    # Biometric collection points — one consented, one collecting WITHOUT
    # consent (the BIPA exposure the register exists to surface).
    points = [
        (LA_LOCATION, "hand_geometry", "Sterilization-room access control", True,
         today - timedelta(days=210), "written", "Retained 12 months after separation."),
        (LA_LOCATION, "voice", "Phone-system voice authentication for PHI lookups", False,
         None, None, "No retention policy on file — vendor default."),
    ]
    for loc, ctype, purpose, consented, cdate, method, retention in points:
        await conn.execute(
            """
            INSERT INTO biometric_consent_points
                (company_id, location_id, collection_type, purpose, consent_obtained,
                 consent_obtained_date, consent_method, retention_policy, is_active, notes, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,true,$9,$10)
            """,
            COMPANY_ID, loc, ctype, purpose, consented, cdate, method, retention,
            f"Biometric inventory entry. {TAG}", admin_user_id,
        )
    counts["biometric_points"] = len(points)

    # Pay equity — a review carrying a MEASURED protected-class gap, which
    # is a different column from the dispersion screen the existing auto row
    # reports (payequity02 exists to keep the two from being conflated).
    await conn.execute(
        """
        INSERT INTO pay_equity_reviews
            (company_id, review_date, scope, methodology, gap_pct, dispersion_pct,
             remediation, cadence_days, next_due_date, notes, created_by)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        COMPANY_ID, today - timedelta(days=45),
        "All CA employees, by role family and tenure band",
        "Regression on base pay controlling for role, tenure, licensure",
        3.10, 11.40,
        "Two front-office coordinators adjusted effective next pay period; "
        "hiring-range guardrails added to the offer template.",
        365, today + timedelta(days=320),
        f"Counsel-reviewed study with HRIS demographics. {TAG}", admin_user_id,
    )
    counts["pay_equity_reviews"] = 1
    return counts


# ── main ─────────────────────────────────────────────────────────────────

async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            "SELECT name, enabled_features FROM companies WHERE id = $1", COMPANY_ID,
        )
        if not row:
            print("Sunset Smile Dental Group not found in this database — aborting.")
            return
        features = row["enabled_features"]
        features = json.loads(features) if isinstance(features, str) else (features or {})
        missing = [
            f for f in ("employee_schedule", "schedule_intelligence", "workforce_compliance")
            if not features.get(f)
        ]
        if missing:
            print(f"Company is missing required flags {missing} — aborting so nothing silently no-ops.")
            return
        print(f"Seeding {row['name']}...")

        admin_user_id = await conn.fetchval(
            """
            SELECT u.id FROM users u
            JOIN clients c ON c.user_id = u.id
            WHERE c.company_id = $1 AND u.is_active = true
            ORDER BY u.created_at LIMIT 1
            """,
            COMPANY_ID,
        )

        async with conn.transaction():
            n = await seed_schedule_requests(conn, admin_user_id)
            print(f"  schedule_requests:        +{n}")

            priced, exempt = await seed_audit_churn(conn, admin_user_id)
            print(f"  schedule_audit_log:       +{priced} employer-initiated, +{exempt} employee-initiated (exempt)")

            new_incidents = await seed_incidents(conn)
            print(f"  ir_incidents:             +{new_incidents}")

            linked = await link_incidents_to_employees(conn)
            print(f"  ir_incidents linked:      {linked}")

            reqs, recs = await seed_training(conn)
            print(f"  training:                 +{reqs} requirements, +{recs} records")

            wc = await seed_workforce_compliance(conn, admin_user_id)
            print(f"  workforce_compliance:     {wc}")

        print("\nDone. Verify at /app/employee-schedule, /app/schedule-intelligence, "
              "/app/workforce-compliance.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
