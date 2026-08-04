# Huume in channels: full ops read access (schedule, incidents, inventory, HR ops)

## Context

Channel "@huume" ASK intent (`_bg_ems_ask` → `services/ems/ask.py`) is grounded ONLY
on that channel's `ems_events` — can't answer schedule/incident/inventory/HR
questions. Write paths (schedule build, inventory, event log) already work; this is
the read gap. Fix: registry-driven grounding reusing
`services/huume/onboarding_skill.py:_lookup_context_impl` (already has per-topic
feature gates via `_TOPIC_REQUIRED_FEATURE` + legal-record redaction).

**Decided policy** (user-approved): broad HR ops. Admin askers additionally get
training_status/credentials/pto_leave (names broadcast = deliberate disclosure,
same posture as behavioral events). Schedule names visible to everyone (portal
parity). Excluded always: `er_cases`, `documents`, `discipline`, `offers`
(thread-only; comment in registry says why). No full agent loop in channels, no
new writes, no new flags, no migration.

| topic | admin_only | location_scoped | flag (already in impl) |
|---|---|---|---|
| `schedule` | no | yes | `employee_schedule` |
| `inventory` | no | yes | `inventory` |
| `incidents` | yes | yes | `incidents` |
| `training_status` | yes | no | `training` |
| `credentials` | yes | no | `credential_templates` |
| `pto_leave` | yes | no | `employees` |

`events` stays on its existing bespoke path in `ask.py`, unchanged.

Fetch-all-allowed per ask (no planner model call) — ~10 indexed LIMIT queries,
capped by existing `ems_ask` 30/hr rate limit.

## Step 1 — `server/app/matcha/services/huume/onboarding_skill.py`

First: `grep -rn "lookup_context\|_lookup_context_impl" server/app server/tests`
to confirm importers (Code Modification Rules).

1a. `_lookup_context_impl(...)` gains `location_id: Optional[UUID] = None` kwarg.
    The agent-facing `lookup_context` wrapper is NOT changed (model never supplies
    it; only the channel caller uses the impl directly). `None` = no filter
    everywhere (thread behavior byte-identical).

1b. `schedule` topic (line ~290): replace the query with (names + location filter):
```sql
SELECT s.id, s.role, s.starts_at, s.ends_at, s.required_staff,
       COUNT(a.id) FILTER (WHERE a.status != 'declined') AS assigned_count,
       ARRAY_REMOVE(ARRAY_AGG(DISTINCT e.first_name || ' ' || e.last_name)
                    FILTER (WHERE a.status != 'declined'), NULL) AS assignees
FROM schedule_shifts s
LEFT JOIN schedule_shift_assignments a ON a.shift_id = s.id
LEFT JOIN employees e ON e.id = a.employee_id
WHERE s.company_id = $1 AND s.status = 'published'
  AND s.starts_at > NOW() AND s.starts_at < NOW() + INTERVAL '7 days'
  AND ($2::uuid IS NULL OR s.location_id = $2)
GROUP BY s.id ORDER BY s.starts_at LIMIT 20
```
(Verify `schedule_shift_assignments.employee_id` column name in `empsched01`
migration during implementation.)

1c. `incidents` topic (line ~304): append to BOTH queries' WHERE:
`AND ($N::uuid IS NULL OR location_id = $N)`.

1d. `inventory` topic (line ~420): WHERE gains
`AND ($2::uuid IS NULL OR it.location_id IS NULL OR it.location_id = $2)`
— store-bound channel sees own + legacy-shared rows (mirrors
`inventory/movements.list_item_names`); `None` stays unfiltered so the thread
agent keeps seeing everything (comment the divergence: movements' stricter
unscoped rule exists for write-matching disambiguation, not reads).

## Step 2 — NEW `server/app/matcha/services/ems/channel_grounding.py`

```python
@dataclass(frozen=True)
class ChannelTopic:
    topic: str            # _lookup_context_impl topic name
    title: str            # prompt section header, e.g. "UPCOMING SCHEDULE (next 7 days)"
    admin_only: bool
    location_scoped: bool
    help_line: str        # capability-pill bullet
    render: Callable[[dict], str]   # topic result -> block text; "" = omit section

CHANNEL_TOPICS: tuple[ChannelTopic, ...] = (...)  # 6 rows per the table above
```

- Six pure render fns (`_render_schedule`, `_render_inventory`, `_render_incidents`,
  `_render_training`, `_render_credentials`, `_render_pto`) — compact dashed lines
  in `render_events_block`'s style; return `""` when the result is empty.
  Input shapes = exactly what `_lookup_context_impl` returns today (schedule:
  `upcoming_shifts` + new `assignees`; incidents: `counts_by_type_and_severity` +
  `incidents`; inventory: `items`; training_status: `counts_by_status`+`overdue`;
  credentials: `expiring_or_overdue`; pto_leave: `upcoming_pto`+`active_leave`+
  `pending_requests`).
- `async def fetch_topic_blocks(conn, *, company_id, features, is_admin, location_id) -> list[tuple[str, str]]`:
  loop registry → skip `admin_only` for non-admin → lazy-import + call
  `_lookup_context_impl(conn, company_id=..., topic=..., features=features,
  location_id=location_id if t.location_scoped else None)` → skip on
  `result.get("module") == "off"` → `t.render(result)` → append `(t.title, text)`
  if text. Per-topic `try/except: logger.exception; continue` — one broken topic
  never kills the answer.
- `def help_lines(*, features, is_admin) -> list[str]`: registry rows where role
  allows AND `(features or {}).get(_TOPIC_REQUIRED_FEATURE[t.topic])` (lazy-import
  the dict from onboarding_skill).
- Module docstring: broadcast posture + exclusion list rationale.

## Step 3 — `server/app/matcha/services/ems/ask.py`

3a. `_build_prompt(question, events_block, *, is_admin, extra_blocks=())` —
after the EVENTS section, per `(title, text)`: `f"## {title}\n{text}\n\n"`.
Change the rule line "Answer ONLY from the events above" → "Answer ONLY from the
data sections above" (both occurrences: intro sentence + Rules bullet).

3b. `answer_question(question, events, *, is_admin, extra_blocks=())` —
pass-through to `_build_prompt`. Nothing else changes (sanitize, fallback copy).

3c. `help_text(*, is_admin, extra_lines=())` — insert `extra_lines` after the 4
static bullets, before the admin Ops bullet. `FIRST_TIME_HINT` unchanged.

## Step 4 — `server/app/werk/routes/channels_ws.py:_bg_ems_ask` (lines 277–359)

4a. After the `role`/`is_admin` fetch (line ~314), inside the same conn block:
`features = await _schedule_company_features(conn, company_id)` — existing helper
(line ~428; generic merged-features helper despite the schedule name).

4b. HELP branch (line ~316):
```python
extra = channel_grounding.help_lines(features=features, is_admin=is_admin)
text = ems_ask.help_text(is_admin=is_admin, extra_lines=extra)
```

4c. ASK branch, after the events fetch (line ~326), still inside the conn block:
```python
loc_id, _ = await _channel_location(conn, channel_id_str)   # existing helper, line 215
extra_blocks = await channel_grounding.fetch_topic_blocks(
    conn, company_id=company_id, features=features, is_admin=is_admin, location_id=loc_id)
```
Change the empty short-circuit from `if not events:` to
`if not events and not extra_blocks:` (keeps the hidden-behavioral `filtered`
nuance for the all-empty case).

4d. Post-conn answer call gains `extra_blocks=extra_blocks`.
`channel_grounding` import: lazy in-function alongside the existing
`from app.matcha.services.ems import ask as ems_ask` (line ~302).
`skip_rate_limit` backstop callers unaffected (signature unchanged).

## Step 5 — `server/app/matcha/services/ems/intent.py`

Append to `_RECALL_PATTERNS` (end of tuple; order within RECALL irrelevant):
```python
r"^who(?:'s| is| are)? (?:working|scheduled|on (?:the )?schedule|on shift|opening|closing)\b",
r"^(?:what|when)(?:'s| is| are)? (?:my|the|our) (?:next )?(?:shifts?|schedule)\b",
r"^how (?:much|many)\b(?=.*\b(?:in stock|stock|inventory|on hand|left|remaining)\b)",
```
Safe vs earlier forks: SCHEDULE patterns all need a request verb (checked before
RECALL, none of these match); INVENTORY patterns need a `we/i` lead. Bias-to-LOG
holds — none of these is report phrasing.

## Step 6 — tests

- `server/tests/huume/test_huume_lookups.py`: schedule topic returns `assignees`;
  `location_id=None` leaves every query unfiltered (thread regression guard).
- NEW `server/tests/ems/test_channel_grounding.py`: registry policy — admin_only
  rows skipped for employee asker; `module: off` result → no block; render fns'
  output shape + `""` on empty; one raising topic doesn't kill the rest.
- `server/tests/ems/test_ems_ask.py` (exists): `_build_prompt` renders
  `extra_blocks` sections + new rule wording; `help_text` inserts `extra_lines`.
- `server/tests/ems/test_ems_intent.py` (exists): new patterns → ASK
  ("who's working tomorrow", "when's my next shift", "how many aprons left in
  stock"); reports still LOG ("we needed more staff last night and someone got
  hurt", "we ran out of cups" → INVENTORY unchanged).
- Patch rule: patch `onboarding_skill` (defining module), never a facade.

## Step 7 — docs

- `server/app/matcha/services/ems/CLAUDE.md`: ask is now multi-source — policy
  matrix, registry location, exclusions + why.
- `server/app/werk/CLAUDE.md` + root CLAUDE.md werk paragraph: import count
  58→59 (new lazy `ems.channel_grounding` call site in channels_ws.py; file
  count stays 9).
- `server/app/matcha/services/huume/CLAUDE.md`: one line — schedule topic
  returns assignees; `_lookup_context_impl` takes optional `location_id`.

## Verification

- `cd server && ./venv/bin/python -m pytest tests/ems/ tests/huume/ -q`
- Manual in a channel with `ems`+`employee_schedule`+`incidents`+`inventory` on:
  - "@huume who's working tomorrow?" → shifts with names (store-scoped if bound)
  - "@huume any incidents this month?" as admin → redacted summary; as employee →
    honest "not something I can pull up here"
  - "@huume how much flour is left in stock?" → store-scoped stock answer
  - "@huume help" → pill lists only enabled topics
  - Flags off → sections omitted, no crash, no module mention
