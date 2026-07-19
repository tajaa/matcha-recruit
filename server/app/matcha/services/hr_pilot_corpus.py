"""HR Pilot citation corpus — traceable grounding for supervisor guidance.

HR Pilot mode grounds answers in the company's own written material, but until
now it did so as *uncitable prose*: the model was told to answer from the
handbook, and nothing checked that the rule it quoted actually existed. This
module gives that same source material a flat citation index (`{sources, index,
notes}` — the shape `legal_defense.validate_citations` consumes) so every
enforceable claim carries a bracketed corpus id, and any id the model invents is
dropped before the answer is persisted.

Corpus cid scheme (one flat index; the audit gate keys on it):
- ``profile``                        — company handbook profile          (via handbook_pilot)
- ``law:<state>-<cat>-<title-slug>`` — applicable jurisdiction requirement (via handbook_pilot)
- ``handbook:<uuid>``                — active handbook section            (via handbook_pilot)
- ``policy:<uuid>``                  — active policy                      (via handbook_pilot)
- ``playbook:<slug>``                — industry baseline section          (via handbook_pilot)
- ``floor:<level>-<juris>-<cat>``    — governing compliance requirement   (this module)
- ``ladder:<step-slug>``             — progressive-discipline step        (this module)

The first five are minted by `handbook_pilot.build_corpus` — reused wholesale,
not reimplemented, because HR Pilot fetches the same four sources Handbook Pilot
does (compare `handbook_pilot.gather_grounding`). Its law cids are derived from
requirement *content* rather than fetch position, for reasons documented at
length in that module's docstring; do not re-mint them here.

`floor:` records are a separate namespace on purpose. They come from
`matcha_work_node.build_compliance_context`'s reasoning chains — the
precedence-resolved *governing* requirement per category — which overlaps the
same statutes `law:` records cover but at a different resolution. Minting them
as `law:` would collide two different views of one statute onto one cid and the
index (keyed by cid) would silently drop one.

A floor cell is a **governing requirement**, not a location: two offices in the
same state share one California meal-break obligation. Keying on the location
would mint it once per office, and the model would cite whichever copy it saw
first — three cids naming one rule. The location labels merge into `applies_to`
instead.

Pure functions here are unit-tested (`tests/matcha_work/test_hr_pilot_corpus.py`);
only `gather_hr_pilot_grounding` touches the DB.
"""

import logging
import re

from .handbook_pilot import _slug, build_corpus

logger = logging.getLogger(__name__)

_MAX_HR_PILOT_SECTIONS = 60
_MAX_HR_PILOT_POLICIES = 60

# Operational-fact caps (Supervisor Copilot groups). These read live tables that
# change daily, unlike the policy corpus above — the caps keep the prompt bounded
# and every cap that bites emits a truncation note, so the model can never read a
# clipped list as the complete picture.
_SCHEDULE_LOOKAHEAD_DAYS = 7
_MAX_SCHEDULE_SHIFTS = 40
_MAX_TRAINING_DETAIL = 15
_MAX_RECENT_INCIDENTS = 15
_INCIDENT_LOOKBACK_DAYS = 90

# Namespaces the audit gate will recognise inside brackets. Deliberately a
# closed list: a bare `[...]` regex also matches markdown link text and the
# `[Handbook — Title]` headers this corpus renders, so unknown brackets must be
# left alone rather than treated as a citation that failed to resolve.
_CID_NAMESPACES = (
    "profile", "law", "handbook", "policy", "playbook", "floor", "ladder",
    # Supervisor Copilot — operational facts, not policy. See the order-of-
    # authority note in matcha_work_mode_contexts: these say who/when/status,
    # they never establish a rule.
    "schedule", "training", "incident",
)
_CITATION_RE = re.compile(
    r"\[(" + "|".join(_CID_NAMESPACES) + r")(:[^\]\s]+)?\]"
)

# Progressive-discipline ladder — static company procedure, cited like any other
# record so "the next step is a written warning" is traceable rather than
# asserted. Replaces the prose _DISCIPLINE_LADDER_SUMMARY this module took over
# from matcha_work_mode_contexts.
_LADDER_STEPS = [
    ("verbal-warning", "Verbal warning",
     "First documented step. Supervisor discusses the issue with the employee and "
     "records that the conversation happened."),
    ("written-warning", "Written warning",
     "Second step. A written record the employee acknowledges, stating the conduct, "
     "the expectation, and the timeframe for improvement."),
    ("final-warning", "Final warning",
     "Third step. States plainly that the next step is a termination review."),
    ("termination-review", "Termination review",
     "Final step. NOT drafted or advised here — a final warning already on file means "
     "the supervisor must be routed to corporate HR."),
]


def _hum(s) -> str:
    if not s:
        return ""
    return str(s).replace("_", " ").replace("-", " ").strip().title()


# --------------------------------------------------------------------------- #
# Grounding — DB-touching. Mirrors handbook_pilot.gather_grounding, but reads
# only what is ACTUALLY IN FORCE (active handbook + active policies, no drafts):
# a supervisor acting today needs the rule in force today, not a proposal.
# --------------------------------------------------------------------------- #

async def gather_hr_pilot_grounding(conn, company_id) -> dict:
    """Fetch the raw grounding material HR Pilot cites. Best-effort at every
    level — a dead source degrades to empty and the rest still grounds."""
    from app.core.services import handbook_service as hb

    sections: list = []
    try:
        sections = await conn.fetch(
            """
            SELECT hs.id, hs.title, hs.section_type, hs.content,
                   h.title AS handbook_title
            FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1 AND h.status = 'active'
              AND hv.version_number = h.active_version
            ORDER BY hs.section_order
            LIMIT $2
            """,
            company_id, _MAX_HR_PILOT_SECTIONS,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: handbook-section fetch failed for %s", company_id)

    policies: list = []
    try:
        policies = await conn.fetch(
            """
            SELECT id, title, category, status, content, description
            FROM policies
            WHERE company_id = $1 AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT $2
            """,
            company_id, _MAX_HR_PILOT_POLICIES,
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: policy fetch failed for %s", company_id)

    scopes: list = []
    requirements: dict = {}
    try:
        scopes = await hb.derive_handbook_scopes_from_employees(conn, str(company_id))
        if scopes:
            requirements = await hb._fetch_state_requirements(conn, scopes)
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: requirement fetch failed for %s", company_id)

    # One row carries both the industry (playbook selection) and the feature
    # set. Features are resolved through the PURE `merge_company_features` rather
    # than read straight off the JSONB: a tier overlay (Matcha-X grants
    # `training` without storing it) is invisible to `enabled_features ->> …`,
    # so a SQL-side check would hide a module the company actually has.
    industry = None
    features: dict = {}
    try:
        row = await conn.fetchrow(
            "SELECT industry, enabled_features, signup_source FROM companies WHERE id = $1",
            company_id,
        )
        if row:
            industry = row["industry"]
            # merge_company_features parses a JSON string itself and applies the
            # tier overlay — pass the raw column straight through.
            from app.core.feature_flags import merge_company_features
            features = merge_company_features(row["enabled_features"], row["signup_source"])
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: company/feature fetch failed for %s", company_id)

    profile = None
    try:
        profile = await conn.fetchrow(
            "SELECT * FROM company_handbook_profiles WHERE company_id = $1", company_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: profile fetch failed for %s", company_id)

    # --- Operational facts (Supervisor Copilot) ---------------------------------
    # Each rides its own product's feature flag, and the distinction between
    # "off" and "on but empty" is load-bearing: `None` means the company doesn't
    # have the module (the corpus emits a note so the model says so plainly
    # instead of implying nobody is scheduled), `[]` means it has it and there is
    # genuinely nothing in the window.
    shifts = await _fetch_shifts(conn, company_id) if features.get("employee_schedule") else None
    training = await _fetch_training(conn, company_id) if features.get("training") else None
    incidents = await _fetch_incidents(conn, company_id) if features.get("incidents") else None

    return {
        "scopes": scopes,
        "profile": dict(profile) if profile else None,
        "requirements": requirements,
        "sections": [dict(r) for r in sections],
        "policies": [dict(r) for r in policies],
        "industry": industry,
        "features": features,
        "shifts": shifts,
        "training": training,
        "incidents": incidents,
    }


async def _fetch_shifts(conn, company_id) -> list[dict]:
    """Published shifts starting in the next `_SCHEDULE_LOOKAHEAD_DAYS`, each with
    its assignees.

    Deliberately does NOT import `routes/employee_schedule/_shared.fetch_shifts`
    — a service reaching into a route package inverts the layering every other
    service here respects. The query is small enough to own.

    Only PUBLISHED shifts: a draft schedule is not something a supervisor should
    be told is happening."""
    try:
        rows = await conn.fetch(
            """
            SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
                   s.required_staff, s.location_id,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'name', TRIM(COALESCE(e.first_name,'') || ' ' || COALESCE(e.last_name,'')),
                               'job_title', e.job_title,
                               'status', a.status
                           ) ORDER BY e.last_name, e.first_name
                       ) FILTER (WHERE e.id IS NOT NULL),
                       '[]'::json
                   ) AS assignees
            FROM schedule_shifts s
            LEFT JOIN schedule_shift_assignments a ON a.shift_id = s.id
            LEFT JOIN employees e ON e.id = a.employee_id
            WHERE s.company_id = $1 AND s.status = 'published'
              AND s.starts_at >= NOW()
              AND s.starts_at < NOW() + ($2 || ' days')::interval
            GROUP BY s.id
            ORDER BY s.starts_at
            LIMIT $3
            """,
            company_id, str(_SCHEDULE_LOOKAHEAD_DAYS), _MAX_SCHEDULE_SHIFTS,
        )
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: shift fetch failed for %s", company_id)
        return []


async def _fetch_training(conn, company_id) -> dict:
    """Per-program completion aggregates + the overdue and expiring detail rows.

    Same SQL shapes as the `training` thread mode's builder, with the row ids
    added so each fact gets a stable cid. Status and dates only — scores and
    certificate numbers are never selected, following the credential precedent
    in that builder."""
    out: dict = {"programs": [], "overdue": [], "expiring": []}
    try:
        out["programs"] = [dict(r) for r in await conn.fetch(
            """
            SELECT r.id, r.title, r.training_type, r.frequency_months,
                   COUNT(tr.id) AS total_assigned,
                   COUNT(tr.id) FILTER (WHERE tr.status='completed') AS completed,
                   COUNT(tr.id) FILTER (WHERE tr.status IN ('assigned','in_progress')
                                          AND tr.due_date < CURRENT_DATE) AS overdue
            FROM training_requirements r
            LEFT JOIN training_records tr ON tr.requirement_id = r.id
            WHERE r.company_id=$1 AND r.is_active
            GROUP BY r.id
            ORDER BY overdue DESC, r.title
            """,
            company_id,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: training-program fetch failed for %s", company_id)

    try:
        # `tr.title`, not `tr.course_name` — the latter is referenced in
        # dashboard.py:1636 but does not exist on this table.
        out["overdue"] = [dict(r) for r in await conn.fetch(
            """
            SELECT tr.id, tr.title, tr.due_date, e.first_name, e.last_name, e.job_title
            FROM training_records tr
            JOIN employees e ON e.id = tr.employee_id
            WHERE tr.company_id=$1 AND tr.status IN ('assigned','in_progress')
              AND tr.due_date < CURRENT_DATE
            ORDER BY tr.due_date ASC
            LIMIT $2
            """,
            company_id, _MAX_TRAINING_DETAIL,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: training-overdue fetch failed for %s", company_id)

    try:
        out["expiring"] = [dict(r) for r in await conn.fetch(
            """
            SELECT tr.id, tr.title, tr.expiration_date, e.first_name, e.last_name, e.job_title
            FROM training_records tr
            JOIN employees e ON e.id = tr.employee_id
            WHERE tr.company_id=$1 AND tr.status='completed'
              AND tr.expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
            ORDER BY tr.expiration_date ASC
            LIMIT $2
            """,
            company_id, _MAX_TRAINING_DETAIL,
        )]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: training-expiring fetch failed for %s", company_id)

    return out


async def _fetch_incidents(conn, company_id) -> list[dict]:
    """Recent incidents, for situational awareness only.

    Names no people: `involved_employee_ids` is deliberately not selected. A
    supervisor asking "has anything happened at this site lately?" needs the
    pattern, not a list of who was hurt — and the IR product is where a named
    record is read, with its own access controls."""
    try:
        rows = await conn.fetch(
            """
            SELECT id, incident_number, title, incident_type, severity, status,
                   occurred_at, location
            FROM ir_incidents
            WHERE company_id = $1
              AND occurred_at >= NOW() - ($2 || ' days')::interval
            ORDER BY occurred_at DESC
            LIMIT $3
            """,
            company_id, str(_INCIDENT_LOOKBACK_DAYS), _MAX_RECENT_INCIDENTS,
        )
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001
        logger.warning("hr_pilot_corpus: incident fetch failed for %s", company_id)
        return []


# --------------------------------------------------------------------------- #
# Corpus build — pure. Extends handbook_pilot's five source groups with two.
# --------------------------------------------------------------------------- #

def _floor_records(reasoning_chains: list | None) -> list[dict]:
    """One record per GOVERNING compliance requirement, deduped across
    locations. `reasoning_chains` is the structured list from
    `matcha_work_node.build_compliance_context`.

    The cid keys on what makes the obligation unique — governing level,
    jurisdiction, category — never on the location that surfaced it, so the same
    state rule reached from three offices is one citable record whose
    `applies_to` names all three."""
    by_cid: dict[str, dict] = {}
    for chain in reasoning_chains or []:
        if not isinstance(chain, dict):
            continue
        label = str(chain.get("location_label") or "").strip()
        for cat in chain.get("categories") or []:
            if not isinstance(cat, dict) or not cat.get("category"):
                continue
            category = str(cat["category"])
            level = str(cat.get("governing_level") or "unknown")

            governing = next(
                (lv for lv in (cat.get("all_levels") or [])
                 if isinstance(lv, dict) and lv.get("is_governing")),
                None,
            )
            juris = str((governing or {}).get("jurisdiction_name") or level)
            cid = f"floor:{_slug(level)}-{_slug(juris)}-{_slug(category)}"

            existing = by_cid.get(cid)
            if existing is not None:
                # Same obligation reached from another location — widen the
                # scope note, don't mint a second cid.
                if label and label not in existing["applies_to"]:
                    existing["applies_to"].append(label)
                continue

            title = str((governing or {}).get("title") or _hum(category))
            bits = [title]
            value = (governing or {}).get("current_value")
            if value:
                bits.append(f"requirement: {value}")
            if cat.get("precedence_type"):
                bits.append(f"precedence {cat['precedence_type']}")
            citation = cat.get("legal_citation") or (governing or {}).get("statute_citation")
            if citation:
                bits.append(f"cite {citation}")
            if cat.get("reasoning_text"):
                bits.append(str(cat["reasoning_text"])[:280])

            by_cid[cid] = {
                "cid": cid,
                "ref": f"{_hum(level)} · {juris}: {title}",
                "summary": " — ".join(bits) + ".",
                "when": str((governing or {}).get("effective_date") or "current"),
                # Structured fields so the client can group without parsing `ref`.
                "category": category,
                "governing_level": level,
                "jurisdiction": juris,
                "source_url": (governing or {}).get("source_url"),
                "applies_to": [label] if label else [],
            }
    return list(by_cid.values())


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
        assignees = [a for a in (assignees or []) if isinstance(a, dict)]

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
        recs.append({
            "cid": f"training:{r['id']}",
            "ref": f"Overdue training — {who}",
            "summary": f"{who} has not completed {r.get('title')}; was due {_fmt_d(r.get('due_date'))}.",
            "when": _fmt_d(r.get("due_date")),
            "status": "overdue",
        })

    for r in training.get("expiring") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        who = f"{r.get('first_name') or ''} {r.get('last_name') or ''}".strip() or "employee"
        recs.append({
            "cid": f"training:{r['id']}",
            "ref": f"Expiring training — {who}",
            "summary": (f"{who} completed {r.get('title')}, but it expires "
                        f"{_fmt_d(r.get('expiration_date'))}."),
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
    corpus = build_corpus(grounding)
    sources = corpus["sources"]

    sources["compliance_floor"] = {
        "label": "Governing compliance requirements",
        "records": _floor_records(reasoning_chains),
    }
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

    # Rebuild the flat index over ALL groups. A cid appearing in two groups
    # would silently lose one here — the namespaces are disjoint by
    # construction, and test_no_cid_collisions_across_groups holds them so.
    index: dict = {}
    for key, source in sources.items():
        for record in source["records"]:
            index[record["cid"]] = {**record, "source": key, "source_label": source["label"]}

    notes = list(corpus.get("notes") or [])
    if not sources["compliance_floor"]["records"]:
        notes.append(
            "No precedence-resolved compliance floor available — answers ground on "
            "the flat per-state requirement list only."
        )

    # Module-off notes. Absence of data and absence of the module are different
    # answers to "who's on Saturday?" — one is "nobody", the other is "this
    # company doesn't schedule here".
    if grounding.get("shifts") is None:
        notes.append(
            "Shift scheduling is not enabled for this company — no schedule data is "
            "available. Say so if asked about shifts; do not infer who is working."
        )
    if grounding.get("training") is None:
        notes.append(
            "Training records are not enabled for this company — say so if asked "
            "whether someone is trained or current."
        )
    if grounding.get("incidents") is None:
        notes.append(
            "Incident reporting is not enabled for this company — say so if asked "
            "about past incidents."
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
    _training = grounding.get("training") or {}
    if (len(_training.get("overdue") or []) >= _MAX_TRAINING_DETAIL
            or len(_training.get("expiring") or []) >= _MAX_TRAINING_DETAIL):
        notes.append(
            f"Training detail is capped at {_MAX_TRAINING_DETAIL} rows per list — "
            "the per-program counts above are the complete figures."
        )

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
