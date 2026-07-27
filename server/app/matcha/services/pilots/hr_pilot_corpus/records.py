"""Pure record builders (no DB) that turn the fetched rows into cid-keyed corpus
records, the corpus assembly itself, and the two gates that ride on it:
redact_for_employee (strips the supervisor-only groups from BOTH `sources` and
`index`, so a guessed cid resolves in neither) and audit_citations.
"""
import logging
import re
from app.matcha.services.pilots.handbook_pilot import build_corpus

from ._config import _CITATION_RE, _INCIDENT_LOOKBACK_DAYS, _LADDER_STEPS, _MAX_BENEFIT_PLANS, _MAX_RECENT_INCIDENTS, _MAX_SCHEDINT_COVERAGE_RECORDS, _MAX_SCHEDLAW_RECORDS, _MAX_SCHEDULE_SHIFTS, _MAX_TRAINING_DETAIL, _MAX_TRAINING_PROGRAMS, _SCHEDLAW_RULE_KEY_TO_CHECK, _SCHEDLAW_RULE_LABELS, _SCHEDULE_LOOKAHEAD_DAYS, _SUPERVISOR_ONLY_SOURCES
from app.matcha.services._shared.text import _hum

logger = logging.getLogger(__name__)


def _ladder_records() -> list[dict]:
    return [
        {
            "cid": f"ladder:{slug}",
            "ref": f"Discipline ladder — {label}",
            "summary": summary,
            "when": "company procedure",
            "step": i + 1,
        }
        for i, (slug, label, summary) in enumerate(_LADDER_STEPS)
    ]


def _fmt_dt(value) -> str:
    """Weekday-bearing timestamp. A supervisor asks "who's on Saturday", so the
    day name has to survive into the record — an ISO date alone makes the model
    do calendar arithmetic, which it does badly."""
    if value is None:
        return "unscheduled"
    try:
        return value.strftime("%a %Y-%m-%d %H:%M")
    except (AttributeError, ValueError):
        return str(value)


def _fmt_d(value) -> str:
    if value is None:
        return "no date"
    try:
        return value.strftime("%Y-%m-%d")
    except (AttributeError, ValueError):
        return str(value)


def _schedule_records(shifts: list | None) -> list[dict]:
    """One record per published upcoming shift, naming its assignees.

    The shift id is the cid: it is a real stable UUID, so a citation survives the
    shift being retimed (the fact it points at is still that shift)."""
    recs: list[dict] = []
    for s in shifts or []:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        assignees = s.get("assignees")
        if isinstance(assignees, str):
            import json as _json
            try:
                assignees = _json.loads(assignees)
            except (ValueError, TypeError):
                assignees = []
        # Declined assignments are already excluded by the fetch; re-filter here
        # so the pure minter is correct on any input. Counting a declined person
        # as staffed answers "is Saturday covered?" with a confident yes.
        assignees = [
            a for a in (assignees or [])
            if isinstance(a, dict) and a.get("status") != "declined"
        ]

        names = [str(a.get("name") or "").strip() for a in assignees]
        names = [n for n in names if n]
        required = s.get("required_staff")
        role = s.get("role") or s.get("department") or "shift"

        bits = [f"{_fmt_dt(s.get('starts_at'))} → {_fmt_dt(s.get('ends_at'))}"]
        if names:
            bits.append("assigned: " + ", ".join(names))
        else:
            bits.append("nobody assigned")
        if required is not None:
            # Staffing shortfall is a deterministic fact, computed here rather
            # than left for the model to infer from two numbers.
            short = int(required) - len(names)
            bits.append(
                f"needs {required}"
                + (f" — SHORT BY {short}" if short > 0 else " — fully staffed")
            )
        recs.append({
            "cid": f"schedule:{s['id']}",
            "ref": f"Shift — {role} {_fmt_dt(s.get('starts_at'))}",
            "summary": "; ".join(bits) + ".",
            "when": _fmt_dt(s.get("starts_at")),
            "role": str(role),
            "assignee_names": names,
        })
    return recs


def _training_records(training: dict | None) -> list[dict]:
    """Per-program completion aggregates plus overdue/expiring detail rows.

    Two cid shapes in one namespace, kept disjoint by construction: aggregates
    are `training:program-<requirement_uuid>`, detail rows are
    `training:<record_uuid>`. A raw UUID can never collide with a `program-`
    prefix, so the flat index stays sound."""
    training = training or {}
    recs: list[dict] = []

    for p in training.get("programs") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        total = int(p.get("total_assigned") or 0)
        done = int(p.get("completed") or 0)
        overdue = int(p.get("overdue") or 0)
        pct = round(done * 100 / total) if total else 0
        bits = [f"{done}/{total} complete ({pct}%)"]
        if overdue:
            bits.append(f"{overdue} OVERDUE")
        if p.get("frequency_months"):
            bits.append(f"repeats every {p['frequency_months']} months")
        recs.append({
            "cid": f"training:program-{p['id']}",
            "ref": f"Training program — {p.get('title')}",
            "summary": "; ".join(bits) + ".",
            "when": "current",
            "training_type": p.get("training_type"),
        })

    for r in training.get("overdue") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        who = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "employee"
        remedial = r.get("source_type") in ("incident", "discipline")
        recs.append({
            "cid": f"training:{r['id']}",
            "ref": f"Overdue training — {who}",
            "summary": f"{who} has not completed {r.get('title')}; was due {_fmt_d(r.get('due_date'))}."
                       + (" (remedial — assigned after an incident/discipline record)" if remedial else ""),
            "when": _fmt_d(r.get("due_date")),
            "status": "overdue",
        })

    for r in training.get("expiring") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        who = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "employee"
        remedial = r.get("source_type") in ("incident", "discipline")
        recs.append({
            "cid": f"training:{r['id']}",
            "ref": f"Expiring training — {who}",
            "summary": (f"{who} completed {r.get('title')}, but it expires "
                        f"{_fmt_d(r.get('expiration_date'))}.")
                       + (" (remedial — assigned after an incident/discipline record)" if remedial else ""),
            "when": _fmt_d(r.get("expiration_date")),
            "status": "expiring",
        })

    return recs


def _incident_records(incidents: list | None) -> list[dict]:
    """Recent incidents — pattern awareness, no persons named."""
    recs: list[dict] = []
    for i in incidents or []:
        if not isinstance(i, dict) or not i.get("id"):
            continue
        bits = [str(i.get("title") or "incident")]
        if i.get("incident_type"):
            bits.append(_hum(i["incident_type"]))
        if i.get("severity"):
            bits.append(f"severity {i['severity']}")
        if i.get("status"):
            bits.append(f"status {i['status']}")
        if i.get("location"):
            bits.append(f"at {i['location']}")
        recs.append({
            "cid": f"incident:{i['id']}",
            "ref": f"Incident {i.get('incident_number') or ''} — {i.get('title')}".strip(),
            "summary": "; ".join(bits) + ".",
            "when": _fmt_d(i.get("occurred_at")),
            "severity": i.get("severity"),
            "incident_type": i.get("incident_type"),
        })
    return recs


def _fmt_cost(value, cost_period) -> str:
    try:
        amount = f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "cost n/a"
    return amount + ("/pay period" if cost_period == "per_pay_period" else "/mo")


def _benefit_records(benefits: dict | None) -> list[dict]:
    """Plan offerings + the open OE window + a pending-life-event count.

    Nameless by construction (see `_fetch_benefits`) — this is the one
    operational group that reaches Ask HR unredacted. Cids: `benefit:plan-<id>`
    per active plan, `benefit:oe-<id>` for the open window, and the fixed
    `benefit:life-events-pending` aggregate (a count, not a row — like
    `profile`, its stability comes from being a singleton)."""
    benefits = benefits or {}
    recs: list[dict] = []

    for p in benefits.get("plans") or []:
        if not isinstance(p, dict) or not p.get("id"):
            continue
        tiers = p.get("tiers")
        if isinstance(tiers, str):
            import json as _json
            try:
                tiers = _json.loads(tiers)
            except (ValueError, TypeError):
                tiers = []
        tier_bits = [
            f"{_hum(t.get('coverage_tier'))} {_fmt_cost(t.get('employee_cost'), t.get('cost_period'))} employee cost"
            for t in (tiers or []) if isinstance(t, dict)
        ]
        bits = [f"{_hum(p.get('plan_type'))} plan"]
        if p.get("carrier_name"):
            bits.append(f"carrier {p['carrier_name']}")
        if tier_bits:
            bits.append("tiers: " + ", ".join(tier_bits))
        bits.append("can be waived" if p.get("waivable") else "cannot be waived")
        recs.append({
            "cid": f"benefit:plan-{p['id']}",
            "ref": f"Benefit plan — {p.get('name')} ({_hum(p.get('plan_type'))})",
            "summary": "; ".join(bits) + ".",
            "when": "current offering",
            "plan_type": p.get("plan_type"),
        })

    period = benefits.get("open_period")
    if isinstance(period, dict) and period.get("id"):
        bits = [f"OPEN now, {_fmt_d(period.get('starts_on'))} → {_fmt_d(period.get('ends_on'))}"]
        if period.get("plan_year_start"):
            bits.append(f"coverage effective {_fmt_d(period['plan_year_start'])}")
        submitted = benefits.get("submitted_employees")
        active = benefits.get("active_employees")
        if submitted is not None and active is not None:
            bits.append(f"{submitted} of {active} active employees have submitted elections")
        recs.append({
            "cid": f"benefit:oe-{period['id']}",
            "ref": f"Open enrollment — {period.get('name')}",
            "summary": "; ".join(bits) + ".",
            "when": f"closes {_fmt_d(period.get('ends_on'))}",
            "ends_on": _fmt_d(period.get("ends_on")),
        })

    pending = int(benefits.get("pending_life_events") or 0)
    if pending:
        recs.append({
            "cid": "benefit:life-events-pending",
            "ref": "Qualifying life events — pending review",
            "summary": (f"{pending} qualifying life-event request(s) await HR review; "
                        "an approved event opens a personal election window."),
            "when": "current",
        })

    return recs


def _schedlaw_records(data: list[dict] | None) -> list[dict]:
    """Enforced scheduling-law thresholds + Fair Workweek ordinances, one
    record per determined fact. Iterates the FIXED `_SCHEDLAW_RULE_LABELS`
    map — never the summary dict's own keys — so meta fields the summary
    carries (`citations`, `source`) can never mint a garbage record."""
    recs: list[dict] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        if item.get("kind") == "state_rules":
            state = item.get("state")
            summary = item.get("summary") or {}
            citations = summary.get("citations") or {}
            for rule_key, (label, unit) in _SCHEDLAW_RULE_LABELS.items():
                value = summary.get(rule_key)
                if value is None:
                    continue
                display = "no limit under law" if value == "no_cap" else f"{value}{unit}"
                citation = citations.get(_SCHEDLAW_RULE_KEY_TO_CHECK.get(rule_key, ""))
                cite_clause = f", cites {citation}" if citation else ""
                recs.append({
                    "cid": f"schedlaw:{state}-{rule_key}",
                    "ref": f"Scheduling law — {state} {label}",
                    "summary": f"{state}: {label} {display}{cite_clause}.",
                    "when": "current law",
                })
        elif item.get("kind") == "fair_workweek":
            state = item.get("state")
            city_slug = str(item.get("city") or "").strip().lower().replace(" ", "-")
            prefix = "" if item.get("applicability") == "covered" else "may apply (verify industry) — "
            bits = [f"{prefix}{item.get('ordinance_name')} requires {item.get('notice_days')}-day schedule notice"]
            if item.get("clopening_rest_hours"):
                bits.append(f'{item["clopening_rest_hours"]}h rest between shifts ("clopening")')
            recs.append({
                "cid": f"schedlaw:fw-{state}-{city_slug}",
                "ref": f"Fair Workweek — {item.get('location_name') or item.get('city')}",
                "summary": "; ".join(bits) + f", cites {item.get('citation')}.",
                "when": "current law",
            })
        if len(recs) >= _MAX_SCHEDLAW_RECORDS:
            break
    return recs


def _schedint_records(data: dict | None) -> list[dict]:
    """Schedule Intelligence headlines: incident-correlation, Fair Workweek
    exposure per location, and per-shift qualified-coverage gaps.

    Every summary repeats the directional/estimate framing in-line — these are
    the same figures a business admin sees on the Schedule Intelligence page,
    and the model must not present them as more certain out of context."""
    recs: list[dict] = []
    data = data or {}

    incidents = data.get("incidents") or {}
    if incidents:
        if incidents.get("suppressed"):
            summary = (
                f"Too few incidents/shifts in the last {incidents.get('days')} days for a "
                f"reliable comparison — {incidents.get('n_incidents')} incidents across "
                f"{incidents.get('n_shifts')} shifts (counts only)."
            )
        else:
            under = (incidents.get("by_staffing") or {}).get("understaffed") or {}
            ok = (incidents.get("by_staffing") or {}).get("adequate") or {}
            summary = (
                f"Understaffed shifts: {under.get('incidents', 0)} incidents / "
                f"{under.get('shifts', 0)} shifts (rate {under.get('incident_rate')}); "
                f"adequately staffed: {ok.get('incidents', 0)} incidents / {ok.get('shifts', 0)} "
                f"shifts (rate {ok.get('incident_rate')}). Directional, not a causal claim."
            )
        recs.append({
            "cid": "schedint:incidents",
            "ref": "Schedule Intelligence — incident correlation",
            "summary": summary,
            "when": "current",
        })

    for loc in (data.get("fair_workweek") or {}).get("locations") or []:
        if loc.get("applicability") == "unmapped" or not loc.get("event_count"):
            continue
        ordinance = loc.get("ordinance") or {}
        estimate = loc.get("exposure_estimate")
        summary = (
            f"{loc.get('event_count')} schedule-change event(s) under {ordinance.get('name')} "
            f"({ordinance.get('citation')})"
            + (f" — estimated exposure ${estimate:,.2f}" if estimate is not None
               else " — dollar estimate unavailable (no pay-rate data)")
            + f". Applicability: {loc.get('applicability')}. Directional estimate, not legal advice."
        )
        recs.append({
            "cid": f"schedint:fair-workweek.{loc['location_id']}",
            "ref": f"Fair Workweek exposure — {loc.get('name')}",
            "summary": summary,
            "when": "current",
        })

    coverage_shifts = (data.get("coverage") or {}).get("shifts") or []
    gap_shifts = [s for s in coverage_shifts if s.get("qualified", 0) < s.get("assigned", 0)]
    for s in gap_shifts[:_MAX_SCHEDINT_COVERAGE_RECORDS]:
        recs.append({
            "cid": f"schedint:coverage.{s['shift_id']}",
            "ref": f"Qualified-coverage gap — {_fmt_dt(s.get('starts_at'))}",
            "summary": (
                f"{s.get('qualified')}/{s.get('assigned')} assigned staff are currently "
                f"qualified for this shift (needs {s.get('required_staff')}) — a credential "
                "or training item has lapsed for at least one assignee."
            ),
            "when": _fmt_dt(s.get("starts_at")),
        })
    return recs


def build_hr_pilot_corpus(grounding: dict, reasoning_chains: list | None = None) -> dict:
    """Assemble the HR Pilot citation corpus `{sources, index, notes}`. Pure.

    Delegates the five shared source groups to `handbook_pilot.build_corpus`
    (identical source material, already-hardened cid minting), appends the two
    policy-side HR Pilot groups, then the three operational-fact groups
    (Supervisor Copilot).

    The operational groups distinguish "module off" (`None`) from "module on,
    nothing there" (`[]`) — an absent module gets a note telling the model to
    say so, because silence would otherwise read as "nobody is scheduled"."""
    grounding = grounding or {}
    if reasoning_chains is not None:
        # `build_corpus` mints the compliance_floor group itself now, off
        # `grounding["reasoning_chains"]`. The explicit parameter stays for the
        # existing callers (and their tests) and simply feeds that key; minting
        # the group again here would render every floor record twice in the
        # prompt block (the index dedupes on cid, the prompt does not).
        grounding = {**grounding, "reasoning_chains": reasoning_chains}
    corpus = build_corpus(grounding)
    sources = corpus["sources"]

    sources["discipline_ladder"] = {
        "label": "Progressive discipline ladder",
        "records": _ladder_records(),
    }
    sources["schedule"] = {
        "label": f"Published shifts — next {_SCHEDULE_LOOKAHEAD_DAYS} days",
        "records": _schedule_records(grounding.get("shifts")),
    }
    sources["training_status"] = {
        "label": "Training compliance status",
        "records": _training_records(grounding.get("training")),
    }
    sources["recent_incidents"] = {
        "label": f"Incidents — last {_INCIDENT_LOOKBACK_DAYS} days",
        "records": _incident_records(grounding.get("incidents")),
    }
    # Nameless (plans/window/aggregates only) — the one operational group NOT in
    # _SUPERVISOR_ONLY_SOURCES, so Ask HR employees see it too.
    sources["benefits"] = {
        "label": "Benefit plans & open enrollment",
        "records": _benefit_records(grounding.get("benefits")),
    }
    sources["schedint"] = {
        "label": "Schedule Intelligence — analytics",
        "records": _schedint_records(grounding.get("schedule_intelligence")),
    }
    # Nameless (state-level law + ordinances, no employee data) — like
    # benefits, NOT in _SUPERVISOR_ONLY_SOURCES, so Ask HR employees keep it.
    sources["schedlaw"] = {
        "label": "Scheduling law — enforced thresholds",
        "records": _schedlaw_records(grounding.get("schedule_law")),
    }

    # Rebuild the flat index over ALL groups. A cid appearing in two groups
    # would silently lose one here — the namespaces are disjoint by
    # construction, and test_no_cid_collisions_across_groups holds them so.
    index: dict = {}
    for key, source in sources.items():
        for record in source["records"]:
            index[record["cid"]] = {**record, "source": key, "source_label": source["label"]}

    # The "no compliance floor" note now comes from `build_corpus` with the
    # group itself — appending it again here would state it twice.
    notes = list(corpus.get("notes") or [])

    # Module-off notes. Absence of data and absence of the module are different
    # answers to "who's on Saturday?" — one is "nobody", the other is "this
    # company doesn't schedule here".
    if "shifts" in grounding and grounding.get("shifts") is None:
        notes.append(
            "Shift scheduling is not enabled for this company — no schedule data is "
            "available. Say so if asked about shifts; do not infer who is working."
        )
    if "training" in grounding and grounding.get("training") is None:
        notes.append(
            "Training records are not enabled for this company — say so if asked "
            "whether someone is trained or current."
        )
    if "incidents" in grounding and grounding.get("incidents") is None:
        notes.append(
            "Incident reporting is not enabled for this company — say so if asked "
            "about past incidents."
        )
    # NB: worded to survive redact_for_employee's note filter — benefits is the
    # one operational group employees keep, so its notes must not contain the
    # supervisor-only trigger words ("shifts", "incidents", "training programs").
    if "benefits" in grounding and grounding.get("benefits") is None:
        notes.append(
            "Benefits enrollment is not enabled for this company — say so if asked "
            "about benefit plans or open enrollment; do not infer plan offerings."
        )
    if "schedule_intelligence" in grounding and grounding.get("schedule_intelligence") is None:
        notes.append(
            "Schedule Intelligence analytics are not enabled for this company — say so "
            "if asked about staffing/incident correlation, Fair Workweek exposure, or "
            "qualified-coverage gaps; do not infer any of it."
        )
    # Worded to survive redact_for_employee's note filter (schedlaw stays for
    # employees) — must not contain "shifts"/"incidents"/"training programs".
    if "schedule_law" in grounding and grounding.get("schedule_law") is None:
        notes.append(
            "Scheduling-law data is not enabled for this company — say so if asked "
            "about break, overtime, or rest requirements; do not infer them."
        )

    # Cap-hit notes. A clipped list the model reads as complete is how "nobody
    # else is overdue" gets asserted from a LIMIT.
    if len(sources["schedule"]["records"]) >= _MAX_SCHEDULE_SHIFTS:
        notes.append(
            f"Only the first {_MAX_SCHEDULE_SHIFTS} upcoming shifts are listed — "
            "there may be more; do not treat the list as complete."
        )
    if len(sources["recent_incidents"]["records"]) >= _MAX_RECENT_INCIDENTS:
        notes.append(
            f"Only the {_MAX_RECENT_INCIDENTS} most recent incidents are listed — "
            "there may be more."
        )
    if len(sources["schedlaw"]["records"]) >= _MAX_SCHEDLAW_RECORDS:
        notes.append(
            f"Only the first {_MAX_SCHEDLAW_RECORDS} scheduling-law records are listed — "
            "there may be more; do not treat the list as complete."
        )
    _training = grounding.get("training") or {}
    if (len(_training.get("overdue") or []) >= _MAX_TRAINING_DETAIL
            or len(_training.get("expiring") or []) >= _MAX_TRAINING_DETAIL):
        notes.append(
            f"Training detail is capped at {_MAX_TRAINING_DETAIL} rows per list — "
            "the per-program counts above are the complete figures."
        )
    if len(_training.get("programs") or []) >= _MAX_TRAINING_PROGRAMS:
        notes.append(
            f"Only {_MAX_TRAINING_PROGRAMS} training programs are listed — there may "
            "be more; do not treat the list as the company's full program set."
        )
    _benefits = grounding.get("benefits") or {}
    if len(_benefits.get("plans") or []) >= _MAX_BENEFIT_PLANS:
        notes.append(
            f"Only the first {_MAX_BENEFIT_PLANS} benefit plans are listed — there "
            "may be more; do not treat the plan list as complete."
        )
    _schedint_coverage_shifts = ((grounding.get("schedule_intelligence") or {}).get("coverage") or {}).get("shifts") or []
    _schedint_gap_count = sum(1 for s in _schedint_coverage_shifts if s.get("qualified", 0) < s.get("assigned", 0))
    if _schedint_gap_count > _MAX_SCHEDINT_COVERAGE_RECORDS:
        notes.append(
            f"Schedule Intelligence coverage-gap list is capped at {_MAX_SCHEDINT_COVERAGE_RECORDS} "
            "shifts — there may be more gaps than shown."
        )

    # Could-not-determine. Distinct from "off": the keys are absent entirely
    # because the feature lookup itself failed, and reporting that as "you don't
    # have this module" would tell a paying customer they lost a product.
    if not grounding.get("features_known", True):
        notes.append(
            "Operational data (shifts, training, incidents, benefits, Schedule "
            "Intelligence, scheduling law) could not be loaded just now — this is a "
            "temporary system issue, NOT a statement that the company lacks those "
            "modules. If asked about them, say the data is briefly unavailable and to "
            "try again shortly."
        )

    return {"sources": sources, "index": index, "notes": notes}


def redact_for_employee(corpus: dict) -> dict:
    """Strip supervisor-only source groups from a corpus. Pure.

    Employee Ask HR (`routes/portal_ask_hr.py`) reuses this exact corpus by
    design — same build, same cache, zero extra cost. That sharing is safe only
    while every group is company-policy material. The Supervisor Copilot groups
    are not: `schedule:` names who works when, `training:` names individuals who
    have not completed a requirement, `incident:` describes site events. Serving
    those to an employee turns "what's the PTO policy?" into a roster and a list
    of coworkers' compliance failures.

    The `benefits` group deliberately stays: `_fetch_benefits` selects no
    employee anywhere (plans, the OE window, aggregate counts), and "when does
    open enrollment close?" is a core Ask HR question. If a per-employee
    election detail is ever added to that fetch, the group moves into
    `_SUPERVISOR_ONLY_SOURCES` with it.

    Both the group AND its records' cids leave the index, so the citation gate
    drops any attempt to cite them — the model cannot reference what it was
    never shown, and could not smuggle a cid through if it guessed one."""
    corpus = corpus or {}
    sources = {
        key: group for key, group in (corpus.get("sources") or {}).items()
        if key not in _SUPERVISOR_ONLY_SOURCES
    }
    index = {
        cid: rec for cid, rec in (corpus.get("index") or {}).items()
        if rec.get("source") not in _SUPERVISOR_ONLY_SOURCES
    }
    # The dropped groups' notes ("shift scheduling is not enabled…") describe
    # modules the employee was never going to be told about; keeping them would
    # invite the model to volunteer that the company lacks scheduling.
    notes = [
        n for n in (corpus.get("notes") or [])
        if not any(w in n for w in ("Shift scheduling", "Training records",
                                    "Incident reporting", "shifts", "incidents",
                                    "training programs", "Training detail",
                                    "Schedule Intelligence"))
    ]
    return {"sources": sources, "index": index, "notes": notes}


# --------------------------------------------------------------------------- #
# The gate — pure. Runs on the finished answer, before it is persisted.
# --------------------------------------------------------------------------- #

def audit_citations(text: str, index: dict) -> tuple[str, list[dict], list[str]]:
    """Strip unresolvable citations from a finished HR Pilot answer.

    Returns `(clean_text, citations, dropped)`:
    - `clean_text` — the answer with unresolvable `[cid]` markers removed
      (resolvable ones stay in place so the client can render them as chips).
    - `citations`  — the corpus records actually cited, in first-use order.
    - `dropped`    — the invented ids, for logging and a client-side notice.

    Exact-match only, deliberately. `handbook_pilot.lookup_record` recovers
    legacy cids by prefix, but that is a READ path over already-stored
    citations; routing new model output through it would launder an invented id
    into a real requirement.

    A dropped citation removes the bracket, not the sentence around it — the
    claim survives uncited, visibly ungrounded, rather than the answer
    developing a hole mid-sentence. The count is surfaced to the user so an
    answer leaning on invented sources is legible as such.
    """
    if not text:
        return "", [], []
    index = index or {}

    citations: list[dict] = []
    seen: set[str] = set()
    dropped: list[str] = []

    def _replace(match: re.Match) -> str:
        cid = match.group(0)[1:-1]
        record = index.get(cid)
        if record is None:
            if cid not in dropped:
                dropped.append(cid)
            return ""
        if cid not in seen:
            seen.add(cid)
            citations.append(record)
        return match.group(0)

    clean = _CITATION_RE.sub(_replace, text)
    # Dropping a marker can leave doubled spaces or a space before punctuation.
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    clean = re.sub(r" ([.,;:!?])", r"\1", clean)
    return clean.strip(), citations, dropped


def render_corpus_block(corpus: dict, full_text: dict | None = None) -> str:
    """Render the corpus as the citable source block injected into the prompt.

    Every record is emitted with its own `[cid]` so the model has something
    exact to cite; the instruction block at the end is what makes the citation
    obligation explicit.

    `full_text` maps cid → the record's FULL body, and exists because the corpus
    record `summary` is an index entry, not the source. `handbook_pilot`'s
    section/policy records cap their summary at 280 characters (and policy
    records carry only title/category/description, never the policy body) —
    fine for a citation footer, useless for answering from. Feeding those to the
    model would leave HR Pilot quoting the company's handbook from a 280-char
    preview of it. Callers pass the real text here; the stored records stay
    index-sized so message metadata doesn't balloon."""
    corpus = corpus or {}
    full_text = full_text or {}
    sources = corpus.get("sources") or {}
    lines: list[str] = []
    for source in sources.values():
        records = source.get("records") or []
        if not records:
            continue
        lines.append(f"\n--- {str(source.get('label') or 'Records').upper()} ({len(records)}) ---")
        for record in records:
            body = full_text.get(record["cid"]) or record.get("summary") or ""
            lines.append(f"[{record['cid']}] {record.get('ref') or ''}\n{body}")
    return "\n".join(lines)
