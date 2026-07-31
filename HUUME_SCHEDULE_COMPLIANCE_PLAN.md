# @huume channel scheduling — codified-compliance shift proposals from chat

## Context

Managers in a werk channel say `@huume I need an opener and a closer for our La Jolla store next
week` → Huume parses (Gemini, PARSE ONLY), resolves everything deterministically, validates every
(shift, candidate) against the codified scheduling-compliance engine, posts a proposal pill with
advisories + verbatim statute citations, manager replies **confirm** → shifts created + published.

**Hard constraint (user's words): "no grounding via Gemini—can only reference our compliance
system. Our codified policies."** Honored structurally: Gemini appears in exactly ONE call (Stage A
parse of the request into structured fields). It never sees compliance data, never produces a
verdict. Every compliance line in a pill is `violation['message']` + `(violation['statute'])`
verbatim from `services/scheduling/schedule_compliance.py` — the curated US+CA table (§512 meal,
§510 daily OT, FLSA §207(a) weekly, §1391 minor caps; `min_rest=None` = explicitly no CA statute)
that `routes/employee_schedule/_compliance.py:check_shift_compliance` already enforces on every
schedule write. Fair Workweek table = NYC + LA only; San Diego (La Jolla's city) is unmapped → pill
says nothing where the codified data says nothing.

**User decisions:** names optional (named person pinned as preferred assignee, else Huume proposes
candidates deterministically) · **publish immediately on confirm**.

**Architecture:** channels have no `mw_threads` row → Huume agent loop structurally unreachable
(`store._locked_state_update` requires one) → one-shot service like `services/ems/event_intake.py`.
Confirm rides the reply-to-system-pill dispatch that already exists (`_bg_ems_dispatch`), with a
new arming table + atomic claim (the `ems01` idiom). Zero frontend changes.

---

## Part 1 — Services lifts (mechanical, behavior-identical)

### 1a. `server/app/matcha/services/scheduling/shift_compliance.py` (new)

Move from `routes/employee_schedule/_compliance.py` (module is already routes-import-free — its
imports are `services.scheduling.schedule_compliance/schedule_rules/fair_workweek/
schedule_intelligence` + `app.core.feature_flags`), with UNCHANGED bodies:

- `_DB_RULES_CACHE: dict[str, tuple[float, Optional[dict]]]`, `_DB_RULES_CACHE_TTL = 60.0`
- `_RULE_KEY_TO_CHECK: dict[str, str]`
- `async def _approved_db_rules(conn, state: str) -> tuple[Optional[dict[str, Any]], bool]`
- `def _hours(starts_at, ends_at, break_minutes=0) -> float`
- `def _week_window(d: datetime) -> tuple[datetime, datetime]`
- `def _age_on(dob, on) -> Optional[int]`
- `async def _location_state(conn, company_id, location_id) -> tuple[Optional[str], Optional[str]]`
- `async def _employee_age(conn, company_id, employee_id, on) -> tuple[Optional[int], bool]`
- `async def _week_hours(conn, company_id, employee_id, shift_start, this_shift_hours, exclude_shift_id) -> float`
- `async def _min_rest_gap(conn, company_id, employee_id, starts_at, ends_at, exclude_shift_id) -> Optional[float]`
- `async def _fair_workweek_advisories(conn, company_id, *, location_id, starts_at, ends_at, event, shift_published, min_rest_gap_hours, state=None, city=None) -> list[dict]`
- `async def _training_lapse_advisories(conn, company_id, employee_id, *, shift_date, exclude_requirement_id=None) -> list[dict]`
- `def shape_lapse_advisories(items, *, shift_date, exclude_requirement_id=None) -> list[dict]`
- `async def check_shift_compliance(conn, company_id, *, location_id, starts_at, ends_at, break_minutes, employee_id=None, exclude_shift_id=None, fw_event=None, fw_shift_published=False, shift_kind="work", training_requirement_id=None, lapse_items=None) -> list[dict]`

`routes/employee_schedule/_compliance.py` becomes:

```python
from fastapi import HTTPException
from ...services.scheduling import schedule_compliance
from ...services.scheduling.schedule_rules import compliance_warning_detail, compliance_block_detail
from ...services.scheduling.shift_compliance import (  # noqa: F401 — re-exported for route modules + tests
    check_shift_compliance, shape_lapse_advisories, _approved_db_rules,
    _fair_workweek_advisories, _training_lapse_advisories, _week_window, _hours,
)

def raise_for_violations(violations: list[dict], *, force: bool) -> None:
    ...  # unchanged (HTTPException 422 on has_block, 409 on advisories unless force)
```

Cache stays a single instance (all importers share the one module object). Verify:
`grep -rn "_compliance import\|from ._compliance\|_compliance\." server/app server/tests` — every
hit resolves through the shim or new module.

### 1b. `server/app/matcha/services/scheduling/shift_writes.py` (new)

Move from `routes/employee_schedule/_shared.py` UNCHANGED: `async def log_audit(conn, company_id,
entity_type, entity_id, actor_user_id, action, details=None)` and `async def find_conflicts(conn,
company_id, employee_id, starts_at, ends_at, *, exclude_shift_id=None) -> list[dict]` (both plain
SQL, no FastAPI). `_shared.py` re-imports both under old names (`# noqa: F401` shim, same as 1a).
`find_conflicts`'s `_iso` dependency: give `shift_writes.py` its own tiny `_iso` copy or move it too
and shim it — prefer moving `_iso` (it's 5 lines, `_shared.py` re-imports).

New shared writer — the lift of `shifts.py:199–253` (precedent
`employees/_shared.decide_pto_request_core`):

```python
async def create_shift_core(
    conn, company_id: UUID, *,
    location_id: Optional[UUID], role: Optional[str], department: Optional[str],
    starts_at: datetime, ends_at: datetime, break_minutes: int, required_staff: int,
    color: Optional[str] = None, notes: Optional[str] = None,
    kind: str = "work", training_requirement: Optional[dict] = None,
    training_requirement_id: Optional[UUID] = None,
    employee_ids: list[UUID], created_by: UUID,
    status: str = "draft",                      # 'published' also stamps published_at = NOW()
    audit_details: Optional[dict] = None,       # merged over the default shift.create details
) -> UUID
```

Body = current route block verbatim, except the INSERT gains `status, published_at`:

```sql
INSERT INTO schedule_shifts
    (company_id, location_id, role, department, starts_at, ends_at, break_minutes,
     required_staff, color, notes, kind, training_requirement_id, created_by,
     status, published_at)
VALUES ($1,…,$13, $14, CASE WHEN $14 = 'published' THEN NOW() END)
RETURNING id
```

then per-employee assignment INSERT `ON CONFLICT (shift_id, employee_id) DO NOTHING`, the
`kind == "training"` → `assign_training(...)` hook, the `kind == "work"` →
`evaluate_scheduled_role_rules(...)` try/except-logged hook, and
`log_audit(conn, company_id, "shift", shift_id, created_by, "shift.create", {starts_at, ends_at,
location_id, status, **(audit_details or {})})`. Caller owns the transaction (route already wraps
in `async with conn.transaction():`; `schedule_chat` will too).

Route `create_shift` keeps ALL gates (location assert, training feature check, lapse-map hoist,
per-employee conflicts + compliance + `raise_for_violations`, forced-override audit) and swaps only
the write block for `shift_id = await create_shift_core(...)` with `status="draft"`,
`training_requirement=dict(training_requirement) if training_requirement else None`.

---

## Part 2 — Intent: `SCHEDULE` in `server/app/matcha/services/ems/intent.py`

```python
SCHEDULE = "schedule"

# Bias-to-LOG stands: start-anchored, present/future tense, request verb AND a
# shift-noun both required. \bneed\b does not match "needed" — "we needed more
# staff last night and someone got hurt" still LOGs. The lookahead keeps
# "I need to report an incident" / "we need to talk about what happened" in LOG.
_SHIFT_NOUN = (
    r"(?:opener|closer|opening|closing|shift|shifts|cover(?:age)?|"
    r"schedule|scheduled|staff(?:ed|ing)?|on the schedule)"
)
_SCHEDULE_PATTERNS = (
    rf"^(?:i|we)(?:'ll|'d| will| would)? (?:need|want|gotta|have to|need to get)\b"
    rf"(?:(?!\bto (?:report|log|file|talk|discuss|flag)\b).)*?\b{_SHIFT_NOUN}\b",
    r"^(?:can|could|will|would) (?:you|u) (?:schedule|staff|book|add|set ?up|put)\b",
    r"^schedule\b",
    rf"^(?:add|set ?up|create|build|make|book)\b(?:\s+\S+){{0,6}}\s+{_SHIFT_NOUN}\b",
)
_SCHEDULE_RE = tuple(re.compile(p, re.IGNORECASE) for p in _SCHEDULE_PATTERNS)
```

`classify_intent` order becomes: HELP → LINK → **SCHEDULE** → RECALL → `?`+interrogative → LOG.
(Before RECALL so "can you schedule…" never lands in ASK; RECALL's `^can (?:you|u)
(?:show|list|tell|remind|summar|recap|find|pull|look)` verb set doesn't overlap `schedule|staff|…`.)
First pattern uses `re.DOTALL`? No — single-line channel messages; keep default. `.` in the
lookahead-scan segment is fine (whitespace collapse not needed; `\s` matches are covered by `.`
except newlines — acceptable: a multi-line message's first line decides, same as every other
pattern here).

---

## Part 3 — Pure rules: `server/app/matcha/services/scheduling/schedule_chat_rules.py` (new)

DB-free (mirrors `schedule_rules.py`). All datetimes UTC wall-clock (the `template_windows`
convention — no timezone conversion anywhere).

```python
ALLOWED_ROLES = frozenset({"client", "admin"})     # same pair as promote/evaluate_huume_action

@dataclass(frozen=True)
class ScheduleVerdict:
    kind: Literal["proceed", "refuse"]
    reason: Optional[str] = None
    @property
    def ok(self) -> bool: ...

def evaluate_schedule_proposal(
    *, role: Optional[str], features: dict,
    stage: Literal["propose", "confirm"],
    proposal_status: Optional[str] = None,       # required when stage="confirm"
) -> ScheduleVerdict
# order (mirrors promote.evaluate_promote): role ∉ ALLOWED_ROLES → refuse
#   ("I can only build schedules for managers — if you need a shift change, file a
#    swap or availability request from the Schedule tab in your portal.");
# not features.get("ems") → refuse (silent-tier: caller no-ops);
# not features.get("employee_schedule") → refuse
#   ("Scheduling isn't turned on for this workspace — an admin can enable Employee Schedule.");
# stage=="confirm" and proposal_status not in ("proposed","clarifying") → refuse
#   (f"That proposal is already {proposal_status}.")

@dataclass(frozen=True)
class NeedsClarify:
    question: str
    options: list[str] = field(default_factory=list)   # ≤6, rendered as a dashed list

def resolve_week(week_hint: Optional[str], today: date) -> date
# returns week_start (a SUNDAY, matching shift_compliance._week_window + the FE grid).
# "next_week" → next Sunday strictly after today's week; "this_week"/None → this week's Sunday.

def resolve_dates(
    spec: dict, week_start: date, today: date,
    template_days: Optional[list[int]] = None,          # days_of_week mask, 0=Sunday
) -> list[date] | NeedsClarify
# precedence: spec["date"] (ISO str) → that date alone (even outside the week);
# spec["weekdays"] (names) → those days within [week_start, +7d);
# template_days → mask ∩ week;
# else NeedsClarify("Which days should I schedule?").
# Any resolved date < today is dropped; if ALL drop → NeedsClarify (never propose the past).

def match_location(hint: Optional[str], locations: list[dict]) -> list[dict]
# locations = active business_locations rows (id, name, address, city, state, zipcode).
# Scoring per row (case-folded): 3 = every hint token in name; 2 = hint substring of name
# or name substring of hint; 1 = hint substring of address; 0.5 = hint == city.
# Returns all rows tied at max score (empty list = no match).
# hint None/empty: exactly one active location → [that one]; else [] (caller clarifies).
# "la jolla" must hit a row NAMED "La Jolla …" (city='San Diego') via name, never via city.

def match_template(hint: Optional[str], label: Optional[str], templates: list[dict]) -> Optional[dict]
# candidates matched on template name then role, stem-normalized: strip non-alnum, compare
# token stems where "opener"/"opening"→"open", "closer"/"closing"→"clos".
# precedence: exact name == hint → name-token stem match → role stem match; ties by (name, id).
# hint falls back to label ("opener") when template_hint is null.

def build_adhoc_spec(label: str, start_time: time, end_time: time, role: Optional[str]) -> dict
# {"label", "start_time", "end_time", "role", "break_minutes": 0, "template_id": None}
# break=0 deliberately: the §512 meal-break advisory then tells the truth rather than us
# inventing a break the manager never said.

@dataclass
class CandidateContext:
    employee_id: str; name: str; job_title: Optional[str]
    conflicts: list[dict]           # find_conflicts rows
    violations: list[dict]          # check_shift_compliance rows
    week_hours: float

@dataclass
class RankResult:
    chosen: list[CandidateContext]                    # len ≤ slots_needed
    alternates: list[CandidateContext]
    excluded: list[tuple[CandidateContext, str]]      # (ctx, human reason w/ verbatim violation)

def rank_candidates(
    slots_needed: int, candidates: list[CandidateContext],
    *, pinned_ids: Optional[list[str]] = None, shift_role: Optional[str] = None,
) -> RankResult
# exclusions first: any conflict → excluded ("already on a shift 15:00–23:00 that day");
# any severity=='block' violation → excluded (verbatim message + statute) — a hard statutory
# violation is never proposed. Pinned survivors sort first regardless of advisories (the manager
# named them; advisories still listed). Then: zero-advisory → fewer advisories → lower week_hours
# → job_title stem-matches shift_role bonus → name → employee_id. Fully deterministic.

_CONFIRM_RE = re.compile(r"^(?:confirm(?:ed)?|yes|yep|yeah|yea|sure|do it|go ahead|"
                         r"approve[d]?|book it|ship it|lgtm|looks good|\U0001F44D)\b", re.I)
_CANCEL_RE  = re.compile(r"^(?:cancel|no|nope|nah|stop|don'?t|scrap(?: it)?|never ?mind|"
                         r"forget it|kill it)\b", re.I)

def parse_confirm_reply(text: str) -> Literal["confirm", "cancel", "other"]
# strip_mention() applied by caller first; confirm checked before cancel ("no wait, confirm"
# is 'cancel' — leading token wins, deterministic).
```

---

## Part 4 — Orchestration: `server/app/matcha/services/scheduling/schedule_chat.py` (new)

### Stage A — the ONE Gemini call

```python
async def parse_schedule_request(content: str, today: date) -> Optional[dict]
```

One `event_intake.FLASH_LITE_MODEL` call via `event_intake._get_client()` (same underscore-import
family as the day-3 seed script), `types.GenerateContentConfig(temperature=0.2,
response_mime_type="application/json", max_output_tokens=800)`, parsed with
`clean_model_json` + strict shape-coercion (mirror `event_intake._parse_model_json`). Prompt: "You
are a PARSER for a shift-scheduling assistant… extract only what the manager said; NEVER invent
times, dates, counts, or people. Today is {today.isoformat()} ({weekday})." Output schema:

```json
{"actionable": true,
 "ack": "one short casual sentence, like a teammate replying in chat",
 "location_hint": "la jolla store",
 "week_hint": "next_week",
 "shift_requests": [
   {"label": "opener", "template_hint": "opener", "date": null,
    "weekdays": [], "start_time": null, "end_time": null,
    "role": null, "count": 1, "employee_name_hints": []}],
 "note": null}
```

Coercion: `ack` through `event_intake._sanitize_pill_text(value, 160)`; `count` int-clamped 1..10;
`shift_requests` capped at 6; `week_hint` ∈ {"next_week","this_week",None}; times parsed
`HH:MM`-strict else None; anything malformed → drop that field to null (never the whole parse).
Returns `None` on any exception (caller falls back to LOG — see Part 5).

### Stage B — deterministic resolution + candidate assembly

```python
@dataclass
class ProposalBuild:
    kind: Literal["proposal", "clarify"]
    proposal_id: Optional[UUID]           # set for both — clarify persists too (status='clarifying')
    pill_text: str

async def build_proposal(
    conn, *, company_id: UUID, channel_id: UUID, source_message_id: UUID,
    created_by: UUID, parsed: dict, today: date,
    original_content: str, clarify_history: Optional[list[dict]] = None,
    existing_proposal_id: Optional[UUID] = None,      # clarify round 2 reuses the row
) -> ProposalBuild
```

1. `SELECT id, name, address, city, state, zipcode FROM business_locations WHERE company_id=$1
   AND is_active IS NOT FALSE` → `match_location(parsed["location_hint"], rows)`. 0 or >1 →
   persist `status='clarifying'` + clarify pill listing `f"{name or address} ({city})"` options.
2. `SELECT id, name, role, location_id, start_time, end_time, break_minutes, required_staff,
   days_of_week FROM schedule_shift_templates WHERE company_id=$1` (filter to matched location_id
   or NULL location) → per shift_request `match_template`; miss + explicit times →
   `build_adhoc_spec`; miss + no times → clarify ("What hours should the {label} run?").
3. `week_start = resolve_week(...)`; `resolve_dates(...)` per request; `NeedsClarify` → clarify.
   Shift datetimes: `datetime.combine(d, tmpl_start_time, tzinfo=timezone.utc)` (+1 day on
   `end <= start`, exactly `schedule_rules.template_windows`).
4. Name hints: `SELECT id, first_name, last_name, job_title, employment_status FROM employees
   WHERE org_id=$1 AND (first_name ILIKE $2 OR last_name ILIKE $2 OR
   first_name || ' ' || last_name ILIKE $2)` per hint; inactive filtered via
   `INACTIVE_EMPLOYMENT_STATUSES`; 0 → clarify ("Who's {hint}? I couldn't find them on the
   roster."), >1 → clarify listing matches; 1 → pinned id for that slot.
5. Candidates per unique (starts_at, ends_at) window:
   - roster: `SELECT id, first_name, last_name, job_title FROM employees WHERE org_id=$1 AND
     COALESCE(employment_status,'active') <> ALL($2::text[])` (the `fetch_roster` WHERE).
   - batched overlap pre-filter (one query, NOT per-employee):
     `SELECT DISTINCT a.employee_id FROM schedule_shifts s JOIN schedule_shift_assignments a ON
     a.shift_id=s.id WHERE s.company_id=$1 AND s.status<>'cancelled' AND s.starts_at<$3 AND
     s.ends_at>$2` → busy set (pinned employees skip the pre-filter — their conflict is
     *reported*, not silently dropped).
   - survivors capped at `_CANDIDATE_CAP = 8` per slot (pinned always included), deterministic
     order (fewest assignments that week? no — keep simple: name, id).
   - ONE `schedule_intelligence.fetch_lapse_items(conn, company_id, all_considered_ids,
     credential_templates_enabled=…, training_enabled=…)` for every considered id across all
     slots (flags from one `get_company_features(company_id, conn=conn)` — the same hoist
     `create_shift` does).
   - per survivor: `shift_compliance.check_shift_compliance(conn, company_id,
     location_id=loc_id, starts_at=…, ends_at=…, break_minutes=…, employee_id=eid,
     lapse_items=lapse_map.get(str(eid), []))` + `find_conflicts(conn, company_id, eid, …)`
     → `CandidateContext` (week_hours pulled from the violations context? no —
     `shift_compliance._week_hours(conn, …)` is importable; call it for the sort key).
   - `rank_candidates(count, contexts, pinned_ids=…, shift_role=…)`.
6. Open-slot fallback: `chosen` short of `count` → shift proposed with the shortfall unassigned +
   `required_staff=count`; run the intrinsic `check_shift_compliance(..., employee_id=None)` for
   the shift itself so meal/daily-OT advisories still appear.
7. Persist (INSERT or UPDATE when `existing_proposal_id`):
   `proposal` JSONB =
   ```json
   {"original_content": str, "ack": str, "week_start": "2026-08-02",
    "location": {"id","name","city","state"},
    "clarify_question": str|null, "clarify_options": [...],
    "clarify_history": [{"q","a"}],
    "shifts": [{"label","template_id","role","starts_at","ends_at","break_minutes",
                "required_staff","assignees": [{"employee_id","name","violations":[...]}],
                "open_slots": int, "intrinsic_violations": [...],
                "excluded": [{"name","reason"}]}]}
   ```
8. `pill_text = proposal_text(...)` / `clarify_text(...)` (below).

**Never holds a conn across Gemini** — `channels_ws` handler owns the two-block structure; this
function takes `conn` and is called entirely inside the second block (parse happened before it).

### Confirm / reply

```python
async def apply_reply(
    conn, *, claimed: dict, replier_user_id: UUID, replier_role: Optional[str],
    features: dict, content: str, today: date,
) -> tuple[Optional[str], Optional[UUID]]   # (pill_text, re_arm_proposal_id)
```

`claimed` = the RETURNING row of the atomic claim (Part 5). Routing on
`parse_confirm_reply(strip_mention(content))` × `claimed["status"]`:

- `cancel` (either status) → `UPDATE … SET status='cancelled'` → pill
  `"👍 Scrapped it — nothing was created."`, no re-arm.
- `confirm` + `status='proposed'` → `execute_proposal(...)` below.
- `confirm` + `status='clarifying'` → treat as `other` (nothing concrete to confirm yet).
- `other` + `status='clarifying'` → the reply IS the clarify answer:
  `clarify_rounds >= 2` → `status='cancelled'` + pill "Let's do this on the schedule page —
  I couldn't pin down the details here."; else re-run Stage A on
  `compose: f"{original_content}\n(Q: {clarify_question} A: {content})"` → `build_proposal(...,
  existing_proposal_id=claimed["id"], clarify_history=…)` → new pill, re-arm.
- `other` + `status='proposed'` → pill `"Didn't catch that — reply **confirm** to put these on
  the schedule, or **cancel**."`, re-arm same proposal (we hold the claim; the re-arm UPDATE
  can't race).

```python
async def execute_proposal(
    conn, *, proposal_row: dict, confirmed_by: UUID, features: dict,
) -> str    # result pill text
```

1. `evaluate_schedule_proposal(role=…, features=…, stage="confirm", proposal_status=…)` — already
   verified by caller before calling; re-asserted here anyway (pure, free).
2. Per (shift, assignee): re-run `find_conflicts` + `check_shift_compliance` (fresh
   `fetch_lapse_items` batch). NEW `severity=='block'` or new conflict → drop that assignee
   (created open; named in pill with the verbatim violation). Advisories → proceed; collected
   into `violations_acknowledged`.
3. `async with conn.transaction():` — per shift
   `create_shift_core(conn, company_id, …, employee_ids=[surviving], created_by=confirmed_by,
   status="published", audit_details={"source": "huume_chat", "proposal_id": str(id),
   "channel_id": str(channel_id)})`; then
   `UPDATE schedule_chat_proposals SET status='confirmed', created_shift_ids=$…,
   confirmed_by=$…, confirmed_at=NOW(), updated_at=NOW() WHERE id=$…`; then one
   `log_audit(conn, company_id, "shift", None, confirmed_by, "schedule_chat.confirm",
   {"proposal_id", "shift_ids", "violations_acknowledged", "dropped_assignees"})`.
4. Return `result_text(...)`.

### Pill builders (server-composed; casual voice; `**bold**`-pairs only; NO 🤔 — that codepoint is
`extract_question`'s EMS recovery hook, schedule clarify round-trips through the proposal ROW)

```python
def proposal_text(proposal: dict) -> str
def clarify_text(question: str, options: list[str]) -> str   # "…\nJust reply to this message."
def result_text(shifts_created: list[dict], dropped: list[dict]) -> str
```

```
📅 {ack} Here's what I'd put on the **La Jolla Studio** schedule, week of **Sun Aug 2**:
**Opener** — Mon Aug 3, 06:00–14:00 · Maria Lopez
**Closer** — Mon Aug 3, 15:00–23:00 · Devon Kim
Heads up on Devon: Employee is scheduled 42.5h this week — past 40h incurs weekly overtime; ensure overtime pay. (FLSA, 29 U.S.C. § 207(a))
I left Riley off the opener: Employee is 17 — a 9.0h shift exceeds the 8h daily limit for minors. (Cal. Lab. Code § 1391)
Reply **confirm** and I'll publish these to the schedule, or **cancel**.
```

```
✅ Done — 2 shifts are live (**Opener** Mon · Maria, **Closer** Mon · Devon). Your team can see them in the portal now.
```

Honesty line appended when `schedule_compliance.rules_summary(state)` reports the state
uncurated AND no approved db_rules: `"Heads up — I don't have codified scheduling thresholds for
{ST}, so double-check meal-break and overtime rules yourself."` FW-unmapped adds NO line (pill
mirrors the engine's silence). Statute strings NEVER paraphrased.

---

## Part 5 — `server/app/werk/routes/channels_ws.py` wiring (lazy imports per werk→matcha rule)

### Dispatch diff (`_bg_ems_dispatch`, currently :543)

```python
if reply_to_system_id_str is not None:
    claimed = await _bg_ems_clarify(channel_id_str, reply_to_system_id_str, sender_user_id_str, content)
    if claimed:
        return
    handled = await _bg_schedule_reply(channel_id_str, reply_to_system_id_str, sender_user_id_str, content)
    if handled:
        return
if has_huume_mention:
    from app.matcha.services.ems.intent import LINK, LOG, SCHEDULE, classify_intent
    intent = classify_intent(content)
    if intent == LOG:
        await _bg_ems_intake(channel_id_str, message_id_str, sender_user_id_str, content)
    elif intent == LINK:
        await _bg_ems_link(channel_id_str, sender_user_id_str)
    elif intent == SCHEDULE:
        await _bg_schedule_request(channel_id_str, message_id_str, sender_user_id_str, content)
    else:
        await _bg_ems_ask(channel_id_str, sender_user_id_str, content, intent)
```

EMS clarify stays FIRST (a reply answering a live EMS question keeps winning). Schedule-claim miss
falls through to the mention fork (an "@huume new thing" typed onto a stale schedule pill isn't
swallowed — same reasoning as EMS).

### `_bg_schedule_request(channel_id_str, message_id_str, sender_user_id_str, content) -> None`

`_bg_ems_ask`'s envelope (top-level try/except, two conn blocks):

1. Block 1: `_ems_company_gate` (None → return). `features = merge_company_features(...)` — reuse
   by having `_ems_company_gate`'s query… no: simplest is a second fetch
   `SELECT is_personal, enabled_features, signup_source FROM companies WHERE id=$1` +
   `merge_company_features` (matches `_bg_ems_link`'s per-answer feature fetch). Role:
   `SELECT role FROM users WHERE id = $1`.
   `verdict = evaluate_schedule_proposal(role=role, features=merged, stage="propose")` — refuse
   with a reason containing "Scheduling isn't turned on" or the manager-only text → post that
   pill + return; refuse on `ems` → silent return (gate already passed, unreachable belt).
   `check_rate_limit(str(company_id), "ems_schedule", 20, 3600)` → over: silent return.
2. Release conn. `parsed = await schedule_chat.parse_schedule_request(strip_mention(content),
   date.today())`. Fallback rule: `parsed is None or not parsed.get("actionable") or not
   parsed.get("shift_requests")` → `await _bg_ems_intake(channel_id_str, message_id_str,
   sender_user_id_str, content)`; return. **Bias-to-LOG survives misroutes.**
3. Block 2: `build = await schedule_chat.build_proposal(conn, …)` →
   `sys_row = await _insert_system_message(conn, channel_id_str, build.pill_text)` →
   `UPDATE schedule_chat_proposals SET confirm_message_id = $1, updated_at = NOW() WHERE id = $2`
   (same-block arm, mirroring the EMS arm at :399) → `broadcast_system_message(...)`.

### `_bg_schedule_reply(channel_id_str, reply_to_id_str, sender_user_id_str, content) -> bool`

```python
claim_happened = False
try:
    async with get_connection() as conn:
        claimed = await conn.fetchrow("""
            UPDATE schedule_chat_proposals
            SET confirm_message_id = NULL, updated_at = NOW()
            WHERE confirm_message_id = $1
              AND status IN ('proposed', 'clarifying')
              AND created_at > NOW() - INTERVAL '7 days'
            RETURNING id, company_id, channel_id, status, proposal, clarify_rounds, created_by
        """, UUID(reply_to_id_str))
        if claimed is None:
            return False
        claim_happened = True
        # re-assert everything on the REPLIER (any admin/client may confirm):
        row = await conn.fetchrow("SELECT is_personal, enabled_features, signup_source FROM companies WHERE id=$1", claimed["company_id"])
        merged = merge_company_features(row["enabled_features"], row["signup_source"]) if row and not row["is_personal"] else {}
        role = await conn.fetchval("SELECT role FROM users WHERE id = $1", UUID(sender_user_id_str))
        verdict = evaluate_schedule_proposal(role=role, features=merged, stage="confirm", proposal_status=claimed["status"])
        if not verdict.ok:
            ...post verdict.reason pill (employee reply on a manager pill gets the manager-only text); return True
        ...confirm-path Gemini re-parse (clarify answers) must NOT hold this conn:
    # for clarify-answer replies: release, re-parse, reopen conn (mirror _bg_ems_clarify's split);
    # confirm/cancel paths are Gemini-free and run in one block via schedule_chat.apply_reply.
    ...
    return True
except Exception:
    logger.exception("schedule chat reply failed for %s", reply_to_id_str)
    return claim_happened      # claimed ⇒ never ALSO fall through to intake
```

The claim is backed by partial unique index; first reply wins; 7-day age guard IS the expiry (no
sweeper — stale pills simply never claim, like stale EMS pills). Re-arm (from `apply_reply`'s
`(pill, re_arm_id)` return): insert pill → `UPDATE … SET confirm_message_id = new_pill_id WHERE
id = $1` — safe, we hold the claim.

---

## Part 6 — Migration `server/alembic/versions/schedchat01_schedule_chat_proposals.py`

`revision = "schedchat01"`, `down_revision = "ems01"` (this branch's family; carry ems01's
multi-head caveat comment). `op.execute` DDL:

```sql
CREATE TABLE IF NOT EXISTS schedule_chat_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    channel_id UUID REFERENCES channels(id) ON DELETE SET NULL,
    source_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('clarifying','proposed','confirmed','cancelled','expired')),
    proposal JSONB NOT NULL DEFAULT '{}'::jsonb,
    parse JSONB,
    clarify_rounds SMALLINT NOT NULL DEFAULT 0,
    confirm_message_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL,
    created_shift_ids UUID[],
    confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL,
    confirmed_at TIMESTAMPTZ,
    token_usage JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_schedule_chat_proposal_confirm
    ON schedule_chat_proposals(confirm_message_id) WHERE confirm_message_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_schedule_chat_proposals_company
    ON schedule_chat_proposals(company_id, created_at DESC);
```

`downgrade()`: `DROP TABLE IF EXISTS schedule_chat_proposals;`. No bootstrap mirror (scheduling
family isn't mirrored). Commit BEFORE applying; apply with `./scripts/migrate-dev.sh` only (prod =
user's call later).

---

## Part 7 — Tests (all `cd server && ./venv/bin/python -m pytest <file> -q`)

### `tests/ems/test_intent_schedule.py`
- `test_flagship_sentence_schedules` — `"@huume I need an opener and a closer for our La Jolla store next week"` → SCHEDULE
- `test_schedule_requests` (parametrized → SCHEDULE): `"@huume can you schedule two front desk people for Saturday"`, `"@huume schedule an opener friday"`, `"@huume add a closing shift on the 3rd"`, `"@huume we'll need coverage next weekend"`, `"@huume could you staff the closing shift tomorrow"`, `"@huume book Maria for the opener monday"`
- `test_reports_still_log` (parametrized → LOG): `"@huume the opener called out sick"`, `"@huume we needed more staff last night and someone got hurt"`, `"@huume I need to report an incident"`, `"@huume we need to talk about what happened at closing"`, `"@huume the schedule printout by the fridge got soaked"`, `"@huume closing went long because the register crashed"`, `"@huume I need the manager to know the freezer died"` (no shift-noun)
- `test_recall_still_asks`: `"@huume what happened last week?"` → ASK; `"@huume can you show me the schedule complaints"` → ASK (recall verb set untouched)
- `test_help_still_wins`: `"@huume what can you do"` → HELP

### `tests/employee_schedule/test_schedule_chat_rules.py`
- `TestResolveWeek`: today=Wed → next_week = following Sunday; today=Sunday → next_week = +7 (not today); this_week/None → current Sunday
- `TestResolveDates`: explicit ISO date wins; `["monday","friday"]` within week; template mask `[1,2,3,4,5,6]` ∩ week; no signal → NeedsClarify; all-past dates → NeedsClarify; past-day-in-this-week dropped
- `TestMatchLocation`: "la jolla" hits name="La Jolla Studio" (city San Diego) not city="La Jolla"-less rows; "downtown" vs 2 downtown rows → both returned (tie); empty hint + 1 location → it; empty hint + 2 → []; no match → []
- `TestMatchTemplate`: "opener"→"Opening Shift"; "closer"→role="Closer" row; exact-name beats stem; None hint uses label; no match → None; tie broken by name
- `TestRankCandidates`: block-violation candidate excluded w/ reason; conflict excluded; zero-advisory sorts before 1-advisory; equal advisories → lower week_hours first; pinned survives ahead of cleaner unpinned; pinned with block still excluded; deterministic tie by id
- `TestParseConfirmReply`: "confirm"/"yes"/"do it"/"book it"/"👍 looks right" → confirm; "cancel"/"nah"/"never mind" → cancel; "make it 8am instead" → other; "no wait confirm" → cancel (leading token)
- `TestBuildAdhocSpec`: break_minutes == 0

### `tests/employee_schedule/test_schedule_chat_envelope.py`
- role matrix: employee/candidate/None → refuse + portal-pointer message; client/admin → proceed
- `ems` off → refuse; `employee_schedule` off → refuse w/ "Scheduling isn't turned on" text
- confirm stage: status confirmed/cancelled/expired → refuse; proposed/clarifying → proceed
- propose stage ignores proposal_status

### `tests/ems/test_schedule_dispatch.py`
Patch `channels_ws._bg_ems_clarify` / `_bg_schedule_reply` / `_bg_schedule_request` /
`_bg_ems_intake` / `_bg_ems_ask` / `_bg_ems_link` **on `channels_ws` itself** (the defining
module — server/CLAUDE.md patch rule):
- clarify claim True → schedule_reply never called
- clarify False + schedule_reply True → intake/ask never called
- both False + `@huume schedule an opener friday` → `_bg_schedule_request` called
- both False + `@huume the opener called out sick` → `_bg_ems_intake`
- (in `test_schedule_chat_service.py` or here) parse-fallback: monkeypatch
  `schedule_chat.parse_schedule_request` → None ⇒ `_bg_ems_intake` called with original args

### Existing suites must stay green (lift regression)
`tests/employee_schedule/` (if exists — else the compliance tests):
`./venv/bin/python -m pytest tests/ -q -k "schedule"` — `schedule_compliance`, `schedule_rules`,
fair-workweek, `_compliance` shim importers all pass untouched.

---

## Part 8 — Verification

```bash
cd server && ./venv/bin/python -m pytest tests/ems tests/employee_schedule -q
cd server && ./venv/bin/python -m pytest tests/ -q -k "schedule or ems"
grep -rn "from ._compliance import\|from ._shared import" server/app/matcha/routes/employee_schedule/
# migration (explicit user step, never auto):  ./scripts/migrate-dev.sh
```

No client changes ⇒ no tsc. Live (dev-remote up, after migrate-dev.sh + seed below), #Front Desk:
1. Priya (admin): `@huume I need an opener and a closer at la jolla next week` → proposal pill
   (weekly-OT advisory on the loaded adult; Riley excluded with the §1391 line).
2. Reply `confirm` → ✅ pill; shifts visible published at `/app/employee-schedule`; Casey's portal
   Schedule tab shows any shift Casey got.
3. Casey (employee): same ask → manager-only refusal pill.
4. Reply gibberish to a fresh proposal → "didn't catch that" re-arm; reply `cancel` → scrapped.
5. `@huume the opener called out sick` → logs an event (LOG regression).

## Part 9 — Demo seed `scripts/seed_lajolla_schedule_demo.py` (dev only, local matcha-postgres)

Company `287fffb5-ea50-40a2-bf07-6b5c2ca3c400` (Sunset Smile Dental Group), direct
`asyncpg.connect("postgresql://matcha:matcha_dev@localhost:5432/matcha")`:
- `business_locations`: `('La Jolla Studio', '7863 Girard Ave', 'San Diego', 'CA', '92037',
  is_active=true)`.
- Employees (org_id=company, emails reserved-domain `@sunsetdental.test`):
  - Dana Whitfield — adult; seed 5 published 8h shifts (Mon–Fri) NEXT week at the new location →
    weekly-OT advisory fires when proposed for a 6th.
  - Riley Soto — `employee_demographics.date_of_birth` = 17 years ago → minor-hours BLOCK on the
    9h closer spec (excluded-with-citation line).
  - Marcus Bell — clean, gets chosen.
- `schedule_shift_templates`: `('Opener', role 'Front Desk', 06:00, 14:00, days [1,2,3,4,5,6],
  break 30, staff 1, location=La Jolla)`, `('Closer', 'Front Desk', 14:00, 23:00, …)` — 9h span
  so Riley's block is real.
- `UPDATE companies SET enabled_features = enabled_features || '{"employee_schedule": true}'`
  (ems/huume/matcha_work already on).
- Idempotent: skip inserts when a 'La Jolla Studio' row already exists.

## Known gaps surfaced honestly, NOT fixed here

- Leave/PTO invisible to the schedule write path (pre-existing; UI writes equally affected).
- SD close→open rest gap: CA `min_rest=None` (no general statute) + FW unmapped ⇒ zero advisory —
  correct per codified data; a curated SD entry is a data follow-up, not engine code.
- Timezone: entire scheduling surface is UTC wall-clock; chat matches the convention.
