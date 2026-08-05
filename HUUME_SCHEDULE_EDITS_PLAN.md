# Huume max-capability: schedule edits + channel/thread parity — MECHANICAL plan

## Context

Prod test: "@huume can you swap those two? give Cara's shift Casey and Caseys to Cara's" → refusal. User mandate: Huume as helpful as possible across ALL domains it touches, on BOTH surfaces (`/work` channels + `/work` threads). Explorer verification (3 agents, 2026-08-04) found the true state:

- **Thread Huume: 36 tools, but schedule is READ-ONLY** (one `lookup_context(schedule)` topic listing 20 upcoming shifts, no ids surfaced, zero writes). Inventory/HR-ops/pilots are deep — the inventory ops skill (5 staged tools + `stage_inventory_order`) just merged (`3d898e8`/`7a6be76`/`00521aa`, 2026-08-04).
- **Channel Huume: 3 tools** (`lookup_context`, `find_shift_coverage`, `stage_inventory_order`) + two deterministic intent forks (SCHEDULE create-only, INVENTORY).
- **`schedule_chat.py` is create-only** — no swap/reassign/retime/cancel/unassign vocabulary anywhere.
- **Two live mis-handlings, not just gaps**: (a) the prod message ends with "Casey" not "?" → classified LOG → minted a phantom `ems_events` row (the ASK fallback requires trailing `?`); (b) "can you reassign Cara's shift to Casey" ALREADY matches `_SCHEDULE_PATTERNS` pattern 5 → routed into the create-only parser → nonsense new-shift proposal or event-log fallback.
- Edit logic (assign/unassign/retime/cancel) lives INLINE in route handlers (`routes/employee_schedule/`); `werk → matcha.routes` must stay 0, so chat can't reach it without extraction — the exact precedent `create_shift_core` set (2ef1fe0 lifted `shift_writes.py`/`shift_compliance.py` out of routes for schedule_chat).

Disclosure invariant KEPT: HR-confidential writes (discipline/ER/PTO/offers) stay thread-only. Schedule staffing is portal-visible team data (documented posture in `channel_grounding.py:28-48`); edits are admin-gated like `find_shift_coverage`.

**One shared machinery, three consumers**: extracted write cores → (1) REST routes, (2) channel `schedule_chat` staged proposals, (3) thread Huume staged actions. Extraction surface differs per surface; resolver/validator/executor are single-sourced.

---

## Part 1 — Extract edit write cores into `services/scheduling/shift_writes.py`

Thin WRITE helpers (checks stay caller-side, matching how `create_shift_core` works — callers run `find_conflicts`/`availability_violations`/`check_shift_compliance` and decide). Each takes `conn`, caller owns the transaction. Snapshots/audit built INSIDE the core so the schedule_intelligence contract can't drift per-caller.

```python
async def apply_assignment_core(conn, *, company_id, shift_id, employee_id,
                                actor_user_id, audit_details=None) -> None
    # from routes/employee_schedule/assignments.py:62-114: INSERT assignment,
    # log_audit("assignment.create", details={..., "location_id", "shift_starts_at"}),
    # training/evaluate_scheduled_role_rules hooks (dedupe with create_shift_core's copy)

async def remove_assignment_core(conn, *, company_id, shift_id, employee_id,
                                 actor_user_id, audit_details=None) -> bool
    # from assignments.py:118-149: DELETE + log_audit("assignment.delete")

async def retime_shift_core(conn, *, company_id, shift_row, new_starts_at, new_ends_at,
                            actor_user_id, audit_details=None) -> None
    # from shifts.py:319-483 retime slice: UPDATE, before/after shift_snapshot
    # (_shared.py:90 shape) + was_published, log_audit("shift.update")

async def cancel_shift_core(conn, *, company_id, shift_row, actor_user_id,
                            audit_details=None) -> None
    # from shifts.py:430-443: status='cancelled', snapshot details, log_audit("shift.update")
```

Routes refactored to call cores; HTTP 409/422 raising stays in handlers via existing `raise_*` wrappers (`routes/employee_schedule/_shared.py:184-198`) — zero behavior change, existing route tests must stay green.

**Invariants (from schedule-intelligence explorer):** audit action names EXACTLY `shift.update`/`assignment.create`/`assignment.delete` (`fair_workweek.RELEVANT_ACTIONS` — new names invisible to FW exposure + pretext shield); details carry snapshot `before`/`after` + `was_published` + `shift_starts_at` (else `uncostable_legacy`); chat-driven changes counted employer-initiated (honest — a manager typed it; docstring note); cancelled-is-terminal; conflict checks use `find_conflicts(..., exclude_shift_id=...)` on retime/reassign.

## Part 2 — `schedule_chat.py` edit vocabulary

**Parse** — `_build_parse_prompt` gains an `action` discriminator; coercer `_coerce_edit_request` mirrors `_coerce_shift_request`:

```python
{"actionable": bool, "ack": str, "action": "create"|"edit",
 "shift_requests": [...unchanged...],
 "edit_requests": [{                     # max 4
   "kind": "swap"|"reassign"|"assign"|"unassign"|"retime"|"cancel",
   "target": {"assignee_name","date","start_time","role_hint"},   # which shift
   "second_target": {...}|None,          # swap only
   "to_employee_name": str|None,         # reassign/assign
   "new_date","new_start_time","new_end_time": ...|None}]}        # retime
```

**Resolve** — new `_resolve_shift_ref(conn, company_id, location_id, ref) -> {"shift": row}|{"ambiguous": [rows]}|{"none": reason}`: published shifts today..+14d scoped company+location, filtered by assignee name (reuse the existing employee-matching used for `employee_name_hints` pinning), date, start-time proximity, role. 0 or >1 → clarify round (existing state machine, `CLARIFY_ROUND_CAP=2`, options listed like location clarify).

**Build** — `build_edit_proposal(...) -> ProposalBuild` (same dataclass): resolves every ref, dry-runs checks per op (conflicts with `exclude_shift_id`, availability, `check_shift_compliance(fw_event="assign"/"retime"/"cancel")` — same "Heads up" advisory lines; `rules_unmapped` computed via `_approved_db_rules` exactly like `build_proposal:563-566`, never `rules_summary(state)`), persists to `schedule_chat_proposals` with `proposal` JSONB carrying `{"kind": "edit", "ops": [...resolved ops with shift ids...]}`. **No migration** — kind lives in the JSONB doc; claim/re-arm/7-day/clarify machinery all reused as-is. New `edit_proposal_text` render fn (`proposal_text` is coupled to the create shape).

**Execute** — `execute_edit_proposal(conn, *, proposal_row, confirmed_by, features) -> str`: one transaction; re-runs all checks against CURRENT state (proposal may be hours old — `execute_proposal`'s posture); per-op drop-with-reason, never hard-fail the batch. **Swap is atomic-or-dropped**: pre-check both directions with `exclude_shift_id=<shift they're leaving>`; either direction hard-blocked → whole swap dropped with the violation quoted; advisories proceed. Ops call Part 1 cores. Result pill reuses `result_text` conventions: `[[shift:id:date]]` deep links + `[[barruler]]`/`[[bar:...]]` strip for affected shifts.

**Dispatch** — `_bg_schedule_reply`'s confirm branch (channels_ws.py:983) dispatches on `proposal.get("kind", "create")` → `execute_proposal` | `execute_edit_proposal`. `_bg_schedule_request` routes on parse's `action`. Everything else (claim, re-arm, refusal re-arm on ORIGINAL pill, exception → `EXECUTE_FAILED_TEXT` + re-arm) unchanged.

## Part 3 — `intent.py` edit patterns

Append to `_SCHEDULE_PATTERNS` (bias-to-LOG preserved; a match that later parses non-actionable still falls back to `_bg_ems_intake` — existing safety valve):

```python
# 6 — bot-directed swap/switch/trade; no shift noun required (anaphoric "those two")
r"^(?:can|could|will|would) (?:you|u) (?:swap|switch|trade)\b",
# 7 — give/move/take/swap reaching a shift noun ("give Cara's shift to Casey",
#     "take Dana off the schedule") — fixes the trailing-clause LOG-misroute
rf"(?:^|[.!?]\s+)(?:give|move|take|bump|switch|swap|trade)\b"
rf"(?:(?!\bto (?:report|log|file)\b).)*?\b{_SHIFT_NOUN}\b",
# 8 — cancel/drop the shift
rf"(?:^|[.!?]\s+)(?:cancel|drop|remove|scrap)\b(?:\s+\S+){{0,6}}\s+{_SHIFT_NOUN}\b",
```

Tense-exact verbs (`\bmove\b` won't match "moved") keep "we moved the freezer and someone got hurt" → LOG. Pattern-5 reassign phrasings now land in a parser that can express them — mis-handling (b) fixed by Part 2, no regex removal needed.

## Part 4 — Channel ASK-loop additions (`channel_agent.py`)

**4a. `propose_schedule_change` write tool** — the NL safety net for phrasings regexes miss AND the fix for context-dependent references. Declaration takes STRUCTURED args (kind/target names/dates/times — mirror the parse shape) — the loop model extracts them; **no second Gemini call inside the tool arm** (never hold the pooled conn across a model call — `_bg_schedule_request`'s own rule). Server side `channel_grounding.run_schedule_change(conn, *, company_id, features, is_admin, location_id, location_unavailable, args) -> {"text", "proposal_id"|None, "pill_text"|None}`:
- re-asserts admin + `evaluate_schedule_proposal(stage="propose")` + rate-limit `ems_schedule` (model args advisory-only — `run_coverage_lookup`'s posture)
- builds a parse-shaped dict from args → `build_edit_proposal`/`build_proposal` (both deterministic, conn-safe)
- returns the confirm pill text; agent sets `final_text = pill_text` VERBATIM + breaks (the `staged_this_round` pattern, one stage per turn)

Return contract gains `pending_proposal_id`; `_bg_ems_ask` (channels_ws.py:422-426 region) stamps `schedule_chat_proposals.confirm_message_id = pill.id` exactly like it stamps orders. Confirm then rides the EXISTING `_bg_schedule_reply` claim.

**4b. `record_stock_movement` tool** — "can you log that we used 5 boxes of gloves?" is ASK-shaped and today refused. Kinds **`out|stockout|adjust` ONLY** — the just-merged provenance invariant (`00521aa`) forbids a bare chat `in`: received stock must come through `orders.mark_received` or `receipts.receive_channel_lines`/`commit_receipt_lines`. Mirror the thread tool exactly: `in` absent from the enum, steering text toward receiving against the open order / Receive Delivery (reuse `actions.py:156`'s wording). Writes via `movements_service.find_or_create_item` + `record_movements` (same trust level as the deterministic `extract_inventory` out/stockout path); gated `evaluate_inventory_action(stage="movement")` (any role, `inventory` flag).

**4c. Recent-messages context** — resolves "those two". `_bg_ems_ask` fetches last 12 non-system channel messages (sender name + content truncated ~200 chars) and passes `recent_block` into `answer_channel_question` → new prompt section `## RECENT CHANNEL MESSAGES` under the existing treat-as-data rule (same posture as the events block, which already carries user-authored text; room-visible content, no new disclosure). The tool description tells the model to restate anaphora into concrete names/dates when calling `propose_schedule_change`.

**4d. Prompt + help sync** — honesty example extended to name `propose_schedule_change`; `channel_grounding.help_lines` + `ask.help_text` advertise schedule changes (admin) + stock logging so advertised == available. `sanitize_pill_text` already passes `[[tokens]]` (verified — strips only `*` and 🤔).

## Part 5 — Thread Huume schedule tools

Follow the inventory template exactly (the extension pattern is table-driven):

- **`lookup_context(topic="schedule")` enriched**: surface short shift ids + assignee names (model must echo real ids; current render has no ids). `onboarding_skill.py:354` arm.
- **`find_shift_coverage` read tool**: same `coverage.find_coverage_candidates` service, feature-gated `employee_schedule` via `PILOT_TOOL_REQUIRED_FEATURE`-style per-call check (thread surface is already admin/client-only).
- **Staged writes** — 2 new action types in `_HUUME_ACTION_REQUIRED_FEATURE` (both → `employee_schedule`) + `_HR_OPS_TOOL_SPECS` entries (zero new dispatch code) + `services/huume/schedule_skill.py:execute`:
  - `schedule_edit` — tool `propose_schedule_change(kind, shift_id, employee_id?, to_employee_id?, second_shift_id?, new_date?, new_start?, new_end?, confirm_id)`, `mints_confirm_id=True`, `decision_fields=("kind","shift_id","employee_id","to_employee_id","second_shift_id","new_start","new_end")` — explicit ids (thread convention), from the enriched lookup.
  - `schedule_create` — tool `create_shifts(date, start_time, end_time, role?, count?, employee_names?, confirm_id)` → executor reuses `create_shift_core` + the same checks-then-drop.
  - `schedule_skill.execute` dispatches kinds onto Part 1 cores inside one transaction, drop-with-reason strings returned in the result summary. Registered in `actions.execute_huume_action` dispatch + `tools.py` TOOLS entries (`discovery=True`, `intent_hints` for routing/prompt teaching — free from the registry).
- **Known ceiling, unchanged**: the single `huume_action` slot (one pending write per thread). Widening to a keyed dict is real surgery on the confirm-first machinery — deliberately out of scope; `cancel_staged` is the escape hatch. Documented in huume/CLAUDE.md.

## Part 6 — Docs

- `services/scheduling/CLAUDE.md`: edit vocabulary + cores paragraph on the `employee_schedule` row.
- `services/ems/CLAUDE.md`: channel-agent tool list update (schedule change + stock movement + recent-messages context), admin gating rationale.
- `services/huume/CLAUDE.md`: schedule skill + the slot-ceiling note.
- `server/CLAUDE.md` symbol map: edit cores + `run_schedule_change` + `schedule_skill.py` lines.

## Files

| File | Change |
|---|---|
| `services/scheduling/shift_writes.py` | +4 cores (extracted) |
| `routes/employee_schedule/{assignments,shifts}.py` | call cores (behavior-neutral refactor) |
| `services/scheduling/schedule_chat.py` | parse discriminator, resolver, `build_edit_proposal`, `execute_edit_proposal`, `edit_proposal_text` |
| `services/ems/intent.py` | +3 patterns |
| `services/ems/channel_agent.py` | +2 tools, recent-messages prompt section, `pending_proposal_id` |
| `services/ems/channel_grounding.py` | `run_schedule_change`, help_lines |
| `services/ems/ask.py` | help_text bullet |
| `werk/routes/channels_ws.py` | kind dispatch in `_bg_schedule_reply`, action routing in `_bg_schedule_request`, recent-messages fetch, proposal stamping in `_bg_ems_ask` |
| `services/huume/{tools,agent,actions}.py` | +3 tools, +2 action types, spec entries |
| `services/huume/schedule_skill.py` | **new** |
| `services/huume/onboarding_skill.py` | schedule topic ids |
| 4 CLAUDE.md files | doc sync |

No migration. No frontend change ([[shift]]/[[bar]] tokens already render). No new feature flag (rides `employee_schedule` + `ems`/`huume`).

## Tests

- `tests/employee_schedule/test_shift_writes_cores.py` — cores: audit action names + details shape (assert `shift_snapshot` keys + `was_published`), cancelled-terminal, exclude_shift_id plumbed.
- `tests/employee_schedule/test_schedule_chat_edits.py` — edit coercer clamps; resolver unique/ambiguous/none; swap atomic-or-dropped (either direction blocked → both untouched); execute drop-with-reason; `rules_unmapped` honesty; edit pill carries `[[shift:]]`+`[[bar:]]` tokens.
- `tests/ems/test_intent.py` (extend) — patterns 6-8 positive; regressions: "we moved the freezer…"→LOG, "we needed more staff last night and someone got hurt"→LOG, prod message full text→SCHEDULE (not LOG).
- `tests/ems/test_channel_agent.py` (extend) — tool gating (non-admin refused server-side), `pending_proposal_id` stamping contract, structured-args advisory re-validation, one-stage-per-turn break.
- `tests/huume/test_schedule_skill.py` — envelope (feature/role/two-turn), decision_fields restage, executor dispatch.
- Existing suites stay green: employee_schedule routes (refactor is behavior-neutral), schedule_chat pill text, huume, ems, inventory.

## Verification (live dev-remote, then prod after merge)

1. Recreate prod transcript exactly: create opener+closer via @huume, confirm, then "@huume can you swap those two? give Cara's shift Casey and Caseys to Cara's" → edit pill listing both reassignments + heads-up lines → reply confirm → DB shows swapped `schedule_shift_assignments`, `schedule_audit_log` rows with `assignment.create`/`assignment.delete` + snapshots → result pill with deep links + bars.
2. "@huume move the closer to 1pm" → retime pill → confirm → starts_at moved, `shift.update` audit row.
3. "@huume cancel Saturday's opener" → cancel flow; then confirm cancelled shift can't be re-edited (terminal).
4. Ambiguity: two same-day shifts, "swap those two" with no names → clarify listing → answer → pill.
5. Thread surface: in a /work Huume thread — lookup schedule (ids visible), `propose_schedule_change` stage → state block shows staged → confirm → executed; `find_shift_coverage` answers.
6. Non-admin (employee) tries channel edit → server-side refusal text.
7. `cd server && ./venv/bin/python -m pytest tests/employee_schedule tests/ems tests/huume tests/inventory -q`.

## Out of scope (deliberate)

- `huume_action` keyed-slot widening (one pending write per thread stands).
- Channel EMS promote / HR-ops / pilots (disclosure posture unchanged).
- Employee-initiated swap requests via chat (portal `schedule_requests` owns that flow; chat is the manager surface).
- Chat-history context for THREAD Huume (threads already carry their own transcript).
- `schedule_chat_proposals.kind` column (JSONB doc carries it).
