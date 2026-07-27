# Huume Harness — Review Findings & Extension Plan

> **Status (verified 2026-07-26): IMPLEMENTED — shipped in `d8833d1`.** All 15 findings and
> 4 extensions confirmed present in the current tree by symbol, and `d8833d1`'s file stat
> matches this doc's own file table with nothing left untouched; the 4 prescribed test files
> exist. Findings 13 and 14 were dispositioned "documented, not fixed" by design — both
> rationales survive as docstrings (`store.py:126-127`, `legal_skill.py:189-190`). Kept for
> history.

**Scope:** the Huume agentic harness — `server/app/matcha/services/huume/` (`agent.py`, `actions.py`, `store.py`, `tools.py`, `prompt.py`, `onboarding_skill.py`, `legal_skill.py`, `handbook_skill.py`), the REST counterpart `server/app/matcha/routes/matcha_work/huume.py`, and the dispatcher `_run_huume_dispatch` in `server/app/matcha/routes/matcha_work/messaging.py`.

**Reviewed on:** branch `claude/huume-chat-pilot-features-oh99pg` (PR #71), 2026-07-26.

**Verdict:** the safety architecture is sound — confirm-first envelope, the structural two-turn rule (`pre_turn_action` / `pre_turn_plans` frozen at turn start), the single advisory-locked plan executor, and the citation gate all hold up. Everything below is a gap *around* that architecture, not a hole in it. Nothing here is a security finding.

Companion doc: `HUUME_PILOT_CHAT_PLAN.md` (the Legal/Handbook Pilot chat-skill design this branch implements). This document is the follow-on: what to fix in the harness, and how to extend it.

---

## Part 1 — Findings (15)

### P1 — Correctness bugs

#### 1. `employment_type` is silently hardcoded on every new hire

`onboarding_skill.build_onboarding_plan` builds `plan["employee"]` from the offer but never copies `employment_type`, and `_step_create_employee` inserts a literal `'Full-Time Exempt'` (`onboarding_skill.py:480`). A part-time, contract, or non-exempt hire onboarded through Huume gets an employee record that says Full-Time Exempt. `offer_letters` carries the real value and `draft_offer_letter` already accepts it as a parameter, so the data is right there.

**Fix:** carry `employment_type` offer → plan → INSERT. Keep the current literal only as the fallback when the offer has no value.

#### 2. `huume_steps.args` / `huume_steps.result` are never populated

Migration `huume03` created both JSONB columns to hold the tool-call audit trail. `_StepRecorder.record` accepts neither, and the dispatcher's `huume_store.add_step(...)` call passes neither — so every audit row stores `{}` for both. The audit trail records that a tool ran, not what it was asked to do or what came back.

**Fix:** `_StepRecorder.record` takes `args` and `result`; both ride the `step` frame; the dispatcher passes them through to `add_step`. Truncate each to a bounded JSON size (~4KB) so a large pilot result can't bloat the table.

#### 3. Run status lies when the turn fails mid-way

`run_huume_turn`'s outer `except Exception` yields an `error` frame but still falls through to emit the final `huume_result` frame. The dispatcher only sets `run_failed = True` when the exception escapes the generator entirely — which this one doesn't. So a turn that blew up mid-loop is recorded as `huume_runs.status = 'completed'` with `error` NULL.

**Fix:** carry `error: str | None` on `huume_result.data`; the dispatcher marks the run `failed` and stores the error whenever it's set.

#### 4. No per-tool timeout

Only the *model* calls are wrapped in `asyncio.wait_for`. `call_tool` is awaited bare. A hung Google Workspace or Slack provisioning HTTP call, or a stalled pilot Gemini call, blocks indefinitely — the 240s wall clock is only consulted at the top of the loop, so it never fires while a tool is pending. The SSE stream just stops producing.

**Fix:** wrap `call_tool` in `asyncio.wait_for` bounded by the remaining wall-clock budget. On timeout: record the step with `status='error'`, hand `{"error": "timed out"}` back to the model as the function response, and let the loop continue (the model can report it or try something else).

#### 5. No SSE keepalive while a long tool runs

`ask_legal_pilot`, `draft_handbook_content` and `generate_legal_packet` each embed their own 90s-capped Gemini call. During that window the harness emits nothing — one `status` frame before the tool, then silence. `HUUME_PILOT_CHAT_PLAN.md` §10 flagged this as a known pre-existing gap; combined with finding 15 it is actively breaking long turns.

**Fix:** run the tool as a task and `asyncio.wait` on it with a ~15s tick, emitting a `status` heartbeat on each tick. Composes naturally with fix 4 (the same wait loop enforces the timeout) and fixes 15 (the heartbeats are what keep the client's inactivity timer alive).

#### 15. The frontend stream timeout (180s) is shorter than the backend wall clock (240s)

`client/src/work/api/matchaWork/messaging.ts:sendMessageStream` sets a fixed 180s total-duration abort. The backend's `_WALL_CLOCK_SECONDS` was raised to 240s specifically because pilot tools embed 90s Gemini calls. So a legitimate long turn is killed client-side with "Request timed out" while the backend runs to completion and persists the assistant message — the user sees a failure and the answer only appears on refresh.

**Fix:** convert the fixed total timeout into an **inactivity** timeout — reset the timer on every SSE event, ~90s of silence to abort. With fix 5's heartbeats, a healthy long turn stays alive indefinitely while a genuinely dead stream still fails fast.

*(Numbered 15 because it was found after the P2/P3 groups; it belongs with P1.)*

---

### P2 — Hardening / hygiene

#### 6. No per-company rate limit on Huume turns

`GeminiRateLimiter.check_limit("huume", "agent")` is a platform-global Gemini quota guard, not a tenant cap. Every other expensive surface has a per-company limit — handbook chat is 40/hr, Ask HR is 20/hr per employee. A Huume turn costs up to 8 model calls plus whatever the pilot tools spend, and has no tenant cap at all.

**Fix:** `check_rate_limit(str(company_id), "huume_turn", N, 3600)` in `_run_huume_dispatch`, before the run row is created. Reuse `core/services/redis_cache.check_rate_limit`, the same helper `handbook_pilot_chat` uses.

#### 7. `draft_offer_letter` returns the entire offer row to the model

`onboarding_skill.py:329` returns `{k: v for k, v in dict(row).items() if k not in ("id",)}` — every column, including `company_id`, the candidate token fields, and letter internals. Pure token noise, and it means a schema addition silently starts feeding new columns to the model.

**Fix:** whitelist the ~8 fields the model actually needs (candidate name/email, position, salary, start date, employment type, location, status).

#### 8. Staging happens before the authz checks

`evaluate_huume_action` returns `kind="stage"` at the top, before any role or feature check runs. A caller who will ultimately fail the role gate is told "reply confirm and I'll do it", and only gets refused on the confirm turn. The route-level `require_admin_or_client` makes this low-severity in practice — but the message is wrong, and the ordering is the opposite of `hr_pilot_actions.evaluate_hr_action`, which this function otherwise mirrors exactly.

**Fix:** run the role + feature checks before the stage branch so a refusal is immediate.

#### 9. Duplicate feature fetch every turn

`_run_huume_dispatch` calls `get_company_features(company_id)` to re-check the `huume` flag, then `run_huume_turn` immediately calls `store.get_thread_features_and_integrations(company_id)` — a second query for the same data on every single turn.

**Fix:** pass features (and integrations) into `run_huume_turn` from the dispatcher.

---

### P3 — Fidelity / efficiency

#### 10. Interleaved model text is dropped

`contents.append(types.Content(role="model", parts=call_parts))` appends only the function-call parts. When a response mixes text and tool calls, the model's own reasoning text vanishes from its history between iterations.

**Fix:** append all parts from the candidate, not just the function-call ones.

#### 11. `finish` alongside other calls is handled wrong

If the model emits `finish` in the same batch as other tool calls, `finished` is set and the loop breaks after the batch — the other tools still *execute*, but their results never reach the model, and the finish message was written before they ran. So the summary describes work whose outcome the model never saw.

**Fix:** only honour `finish` when it is the sole call in the batch. Otherwise ignore it, return the tool results, and let the model call `finish` on the next iteration with the outcomes in hand.

#### 12. No per-message cap in `_to_contents`

History is capped at 20 messages but each message is included whole. One long pilot answer sits in the history and inflates the prompt of every subsequent model call in the turn (and every later turn) — 8 calls per turn multiplies it.

**Fix:** cap each message's text (~6k chars) with a truncation marker.

#### 13. `execute_plan_locked` pins a pooled connection for the whole provisioning run *(documented, not fixed)*

The advisory lock must be held on one connection, so that connection is held open across a multi-minute Google Workspace / Slack provisioning run — while each step opens its *own* connection from the pool underneath. Two pool connections per execute, one of them idle the entire time.

**Disposition:** correct as written (a row lock would be worse; the lock genuinely has to outlive the steps). Optionally take the lock on a dedicated non-pool `asyncpg.connect`. Documented so it isn't rediscovered as a bug.

#### 14. `ask_matter` persists the user question before the analysis runs *(documented, not fixed)*

`legal_skill.ask_matter` inserts the user's `legal_matter_messages` row, then runs the analysis. A failure leaves an unanswered question in the matter transcript.

**Disposition:** this mirrors the Legal Pilot route exactly, and the transcript arguably *should* record that the question was asked. Documented, not changed — changing it here would desync the two surfaces.

---

## Part 2 — Extensions

### E1. New `lookup_context` topics

Add to `LOOKUP_TOPICS` (tools.py), `_TOPIC_REQUIRED_FEATURE` and `_lookup_context_impl` (onboarding_skill.py). Each follows the established three-state idiom — flag off returns `{"module": "off"}`, distinct from on-but-empty:

| Topic | Returns | Flag |
|---|---|---|
| `pto_leave` | Upcoming approved leave / PTO across the roster | `employees` |
| `policies` | Active policy titles + handbook section index, name-searchable | `handbooks` |
| `discipline` | Counts by status/type + upcoming review dates — **no narrative fields** | `discipline` |
| `compliance` | Open compliance requirement counts by category for the company's locations | `compliance` or `compliance_lite` |

Cheapest depth win available: each is one SQL block and one enum entry, and each makes a whole class of "what's the status of X?" question answerable with real numbers.

### E2. Discipline-draft skill (staged action #2)

A new `draft_discipline` tool riding the existing `huume_action` two-turn machinery — the same stage-then-confirm shape as `send_offer`.

**Envelope** — extend `actions.evaluate_huume_action`'s action-type set, in this order:
1. Role + flags: `huume` + `matcha_work` + `discipline`.
2. Field validation: `employee_name`, `infraction_type ∈ {attendance, performance, policy_violation}` (the same draftable subset HR Pilot allows — the heavier categories hard-stop), `description` required.
3. Deterministic hard-stop re-check on the payload text via `hr_pilot_escalation.classify_message` (mirroring `hr_pilot_actions._apply_hard_stop_recheck`). A category hit refuses and routes to corporate HR.

We deliberately do **not** call `evaluate_hr_action` itself: it hard-requires `thread_hr_pilot_mode` and the `hr_pilot` flag, neither of which a Huume thread has. We re-implement its ordering against Huume's own gates.

**Executor** — `actions.execute_huume_action` dispatches to the existing `hr_pilot_actions.execute_hr_action` with `type='discipline_draft'`. That function already owns employee resolution, the deterministic `discipline_compliance.check_discipline_compliance` gate (a statutory block refuses — no override path), and the `status='draft'` write through `discipline_engine.issue_discipline_with_supersede`. Its `clarify` / `blocked` / `escalate` statuses are relayed to the admin as plain refusal messages; any returned `bg_tasks` run best-effort (awaited, try/except-logged).

Plus: tool declaration in `tools.py` (kind `staged`), a prompt section in `prompt.py` (explicitly: never for harassment, discrimination, safety, or leave topics — those hard-stop), and a state-block line so a staged discipline action is named with its id on the confirm turn.

### E3. Multimodal image attachments

`tc.msg_dicts` already carry `image_parts` as `[(bytes, mime), ...]` — `fetch_image_parts_for_messages` populates them at `messaging.py:1494`, before the Huume dispatch runs. `agent._to_contents` simply drops them (the module docstring notes images are "out of scope for this tool-calling path"). They're already fetched and paid for.

**Fix:** emit `types.Part.from_bytes(data=..., mime_type=...)` on the owning user messages, capped (~6 images / ~4MB total).

### E4. Live step timeline in the web client

`useThreadController.ts`'s `onEvent` handles only `status` frames (3 call sites). `step` frames are parsed and dropped; `HuumeStepTimeline` renders post-hoc from `message.metadata.huume_steps` once the turn completes. So during the slowest part of the turn the user sees a spinner, and the timeline appears only after it no longer matters.

**Fix:** accumulate `step` frames into controller state (`pendingHuumeSteps`), render the **existing** `HuumeStepTimeline` component inside the pending "Thinking…" bubble while streaming, clear on `complete` / `error`. No new component.

---

## Part 3 — Execution

### Files

**Backend**

| File | Covers |
|---|---|
| `services/huume/agent.py` | fixes 2, 3, 4, 5, 10, 11, 12; E2 tool handler; E3 |
| `services/huume/onboarding_skill.py` | fixes 1, 7; E1 topics |
| `services/huume/actions.py` | fix 8; E2 envelope + executor dispatch |
| `services/huume/tools.py` | E1 topic enum; E2 tool declaration |
| `services/huume/prompt.py` | E2 prompt section + state-block line |
| `routes/matcha_work/messaging.py` (`_run_huume_dispatch`) | fixes 2, 3, 6, 9 |
| `server/tests/huume/` | new + extended pure tests (below) |

**Frontend**

| File | Covers |
|---|---|
| `client/src/work/api/matchaWork/messaging.ts` | fix 15 (inactivity timeout) |
| `client/src/work/pages/MatchaWorkThread/useThreadController.ts` | E4 step accumulation |
| pending-bubble render site (`MatchaWorkThread.tsx` / `MessageBubble.tsx`) | E4 live timeline |

**No migrations.** `huume_steps.args` / `.result` already exist (huume03); E2 stages through `current_state.huume_action`, which already exists.

### Tests

Extend `server/tests/huume/` — all pure, no DB or Gemini:

- envelope ordering: role/flag refusal now precedes the stage verdict (fix 8)
- discipline-draft envelope: field validation, hard-stop re-check, `discipline` flag off (E2)
- `_StepRecorder` carries args + result and truncates oversized payloads (fix 2)
- `finish` arriving alongside other calls is deferred, not honoured (fix 11)
- plan builder carries `employment_type` through from the offer (fix 1)
- new `lookup_context` topics gate three-state (off / empty / populated) (E1)
- `_to_contents` per-message cap (fix 12)

### Verification

```bash
cd server && ./venv/bin/python -m pytest tests/huume/ -q
cd server && ./venv/bin/python -m pytest tests/legal_defense/ tests/handbook_pilot/ tests/hr_pilot/ -q   # unchanged
cd client && npx tsc -p tsconfig.app.json --noEmit   # the -p form; bare `tsc --noEmit` checks nothing
```

Manual smoke (dev stack, per repo test-data rules — reserved email domains only):

1. Huume thread turn that invokes a pilot tool → heartbeat `status` frames and a live step timeline appear during the tool call; no client-side 180s abort.
2. Build + execute a plan from a **part-time** offer → the employee row carries the offer's `employment_type`, not `Full-Time Exempt`.
3. Inspect `huume_steps` for that run → `args` and `result` are populated.
4. Ask for a discipline write-up → staged, not written; confirm on the next message → a `status='draft'` `progressive_discipline` row exists.
