# Huume Schedule Retry Cost Fix

## Objective

Prevent Huume schedule clarification/refusal loops from repeatedly calling Gemini, while preserving the existing staged schedule-change workflow and adding bounded, auditable retry behavior.

Observed production pattern:

- Schedule turns repeatedly retried rejected `propose_schedule_change` calls.
- Several turns reached the eight-call model limit.
- The August 5 audit found 32 Huume turns, 114 Gemini calls, 2.25M input tokens, and approximately `$3.44` in spend.
- Individual runaway turns used roughly 167k–171k input tokens and cost approximately `$0.27`–`$0.29`.

## Scope

In scope:

- Structured schedule proposal outcomes.
- Terminal handling for deterministic schedule clarification/refusal.
- One schedule proposal attempt per Huume turn.
- Duplicate and repeated schedule-call detection.
- Cumulative prompt-token bound for the outer Huume loop.
- Structured stop/retry telemetry.
- Unit and loop regression tests.

Out of scope:

- Database schema changes.
- Changes to `schedule_chat` resolution rules.
- Changes to confirmation semantics or `confirm_id` handling.
- Changes to the platform-wide Gemini rate limiter.
- Changes to the existing eight-call or 300-second bounds except for adding another bound.

## 1. Structured Schedule Results

**File:** `server/app/matcha/services/huume/schedule_skill.py`

Add an explicit result contract:

```python
from typing import Literal, NotRequired, TypedDict


class ScheduleProposalResult(TypedDict):
    status: Literal["ready", "clarify", "refused"]
    message: NotRequired[str]
    proposal_id: NotRequired[str]
    pill_text: NotRequired[str]
```

Keep the public function signature stable:

```python
async def propose(
    conn,
    *,
    company_id: UUID,
    actor_user_id: UUID,
    args: dict[str, Any],
) -> ScheduleProposalResult:
```

Return shapes:

```python
{
    "status": "ready",
    "proposal_id": str(build.proposal_id),
    "pill_text": build.pill_text,
}
```

```python
{
    "status": "clarify",
    "message": "<user-facing question and candidate list>",
}
```

```python
{
    "status": "refused",
    "message": "<non-retryable failure explanation>",
}
```

Classification rules:

| Condition | Status | Agent behavior |
| --- | --- | --- |
| Proposal built successfully | `ready` | Continue normal staging |
| `build.kind == "clarify"` | `clarify` | End turn with deterministic question |
| Invalid/incomplete edit request | `clarify` | End turn and request missing fields |
| Unexpected scheduling exception | `refused` | End turn; do not retry |
| Authorization/feature refusal later in agent | Existing `refused` | End schedule attempt |

Add a pure formatter:

```python
def _thread_clarification_message(pill_text: str) -> str:
```

It must:

- Remove the calendar prefix.
- Remove channel-only `Just reply to this message.` text.
- Preserve the complete numbered candidate list.
- Append direct user-facing guidance:

```text
Reply with the shift time, employee, or whether you mean the staffed or unstaffed shift.
```

The result must not contain model-facing instructions such as `Ask the admin...`; it becomes the final assistant response directly.

## 2. Per-Turn Schedule Guard

**File:** `server/app/matcha/services/huume/agent.py`

Add constants beside `_MAX_MODEL_CALLS`:

```python
_MAX_SCHEDULE_PROPOSALS_PER_TURN = 1
_MAX_TURN_PROMPT_TOKENS = 100_000
```

The prompt-token threshold is below the observed 167k–171k runaway turns while retaining room for legitimate multi-tool workflows. It applies to Huume's outer loop; pilot tools retain their own internal budgets.

Add a canonical fingerprint helper:

```python
def _tool_call_fingerprint(name: str, args: dict[str, Any]) -> str:
    canonical = json.dumps(
        _json_safe(args),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return f"{name}:{canonical}"
```

Add turn-local state inside `run_huume_turn(...)`:

```python
schedule_proposal_attempts = 0
schedule_proposal_fingerprints: set[str] = set()
duplicate_tool_calls_blocked = 0
tool_rejections = 0
stop_reason: Optional[str] = None
terminal_message: Optional[str] = None
```

Do not change the `run_huume_turn(...)` signature.

### Dispatch Logic

Before executing `propose_schedule_change`:

```python
fingerprint = _tool_call_fingerprint(name, args)

if fingerprint in schedule_proposal_fingerprints:
    # Record a rejected step, increment duplicate_tool_calls_blocked,
    # and skip call_tool.
elif schedule_proposal_attempts >= _MAX_SCHEDULE_PROPOSALS_PER_TURN:
    # Record a rejected step, increment tool_retry_limit_blocks,
    # and skip call_tool.
else:
    schedule_proposal_attempts += 1
    schedule_proposal_fingerprints.add(fingerprint)
    # Execute normally.
```

The guard belongs in the outer tool-processing loop around `call_tool`, not inside `schedule_skill.propose`, because it is per-agent-turn state.

### Schedule Outcome Handling

Update the existing special case around `agent.py:1002`:

```python
proposed = await schedule_skill.propose(...)

if proposed["status"] == "clarify":
    return {
        "status": "clarify",
        "message": proposed["message"],
    }, rejected_step

if proposed["status"] == "refused":
    return {
        "status": "refused",
        "message": proposed["message"],
    }, rejected_step

staged.update({
    "proposal_id": proposed["proposal_id"],
    "pill_text": proposed["pill_text"],
})
```

After each schedule tool result:

```python
if payload.get("status") in {"clarify", "refused"}:
    tool_rejections += 1
    terminal_message = str(payload["message"])
    stop_reason = (
        "schedule_clarification"
        if payload["status"] == "clarify"
        else "schedule_refused"
    )
```

Process the already-returned model batch, but do not execute another `propose_schedule_change` in that batch and do not make another Gemini call after the batch. Preserve unrelated tool results that were already executed or included in the paid response.

At the end of the batch:

```python
if terminal_message:
    final_message = terminal_message
    break
```

This preserves the existing behavior of processing every call in a current model batch while preventing another expensive model iteration.

## 3. Token Budget Guard

**File:** `server/app/matcha/services/huume/agent.py`

Add a pure bound helper:

```python
def _turn_bound_reason(
    *,
    model_calls: int,
    elapsed_seconds: float,
    prompt_tokens: int,
) -> Optional[Literal[
    "model_call_limit",
    "wall_clock_limit",
    "prompt_token_limit",
]]:
```

Precedence:

```python
if model_calls >= _MAX_MODEL_CALLS:
    return "model_call_limit"
if elapsed_seconds >= _WALL_CLOCK_SECONDS:
    return "wall_clock_limit"
if prompt_tokens >= _MAX_TURN_PROMPT_TOKENS:
    return "prompt_token_limit"
return None
```

Use it before every Gemini request:

```python
bound_reason = _turn_bound_reason(
    model_calls=model_calls,
    elapsed_seconds=elapsed(),
    prompt_tokens=total_usage["prompt_tokens"],
)
if bound_reason:
    stop_reason = bound_reason
    break
```

Usage metadata arrives after a call, so a single call can cross the threshold. Its tool calls should still execute, but the next model call must not happen.

For `prompt_token_limit`, use deterministic final text:

```text
I reached this turn's AI budget, so I stopped before making another request. See the completed steps above.
```

No changes are needed in:

- `server/app/matcha/services/huume/store.py`
- `server/app/matcha/services/matcha_work/turn_pipeline.py`
- Database schema or migrations

Existing JSONB usage storage preserves extra telemetry fields, while `_record_turn_usage` safely ignores fields it does not bill from.

## 4. Telemetry

**File:** `server/app/matcha/services/huume/agent.py`

Add these keys to `total_usage` before yielding `huume_result`:

```python
if stop_reason:
    total_usage["stop_reason"] = stop_reason

total_usage["schedule_proposal_attempts"] = schedule_proposal_attempts
```

Log bound and terminal events without complete arguments:

```python
logger.info(
    "Huume turn stopped reason=%s calls=%s prompt_tokens=%s "
    "schedule_attempts=%s duplicate_blocks=%s retry_blocks=%s",
    stop_reason,
    model_calls,
    total_usage["prompt_tokens"],
    schedule_proposal_attempts,
    duplicate_tool_calls_blocked,
    tool_retry_limit_blocks,
)
```

## 5. Prompt Alignment

**File:** `server/app/matcha/services/huume/prompt.py`

Update the schedule paragraph around `prompt.py:307`:

```text
A schedule clarification or refusal ends the current turn. Relay the returned
options exactly and wait for the admin's next message. Never call
propose_schedule_change twice in one turn.
```

Server-side enforcement remains authoritative.

## 6. Schedule Skill Unit Tests

**File:** `server/tests/huume/test_huume_schedule_skill.py`

Add:

```python
def test_clarify_returns_structured_terminal_result()
```

Assertions:

- `status == "clarify"`.
- Full candidate list is preserved.
- No `proposal_id`.
- No channel-only reply instruction.
- No model-facing `Ask the admin` instruction.

```python
def test_invalid_edit_request_returns_clarify()
```

Use insufficient edit arguments and assert deterministic clarification rather than a generic `error` result.

```python
def test_success_returns_ready_contract()
```

Mock `schedule_chat.build_edit_proposal` and assert:

- `status == "ready"`.
- Correct `proposal_id`.
- Correct `pill_text`.

```python
def test_build_exception_returns_non_retryable_refusal()
```

Mock the builder to raise and assert:

- `status == "refused"`.
- User-facing fallback message.
- No proposal identifiers.

```python
def test_thread_clarification_removes_channel_suffix()
```

Pure formatter test covering the complete multiline candidate list.

## 7. Agent Loop Regression Tests

**New file:** `server/tests/huume/test_huume_loop_bounds.py`

Reuse the fake Gemini response conventions from `test_huume_routing.py`.

Test helpers:

```python
def _fake_call(name: str, args: dict[str, Any]) -> types.FunctionCall:
```

```python
def _fake_response(
    *,
    calls: list[types.FunctionCall] | None = None,
    text: str | None = None,
    prompt_tokens: int = 0,
) -> MagicMock:
```

```python
async def _collect_turn_frames(
    monkeypatch,
    *,
    responses: list[Any],
) -> tuple[list[dict[str, Any]], AsyncMock]:
```

Test cases:

```python
async def test_schedule_clarification_stops_after_one_model_call()
```

- First Gemini response calls `propose_schedule_change`.
- Mock `schedule_skill.propose` to return `status="clarify"`.
- Configure a second Gemini response to fail if called.
- Assert exactly one Gemini call.
- Assert final message equals the deterministic clarification.
- Assert `model_calls == 1`.
- Assert `stop_reason == "schedule_clarification"`.

```python
async def test_duplicate_schedule_call_in_same_batch_is_not_executed()
```

- One Gemini response includes two identical schedule calls.
- Assert `schedule_skill.propose.await_count == 1`.
- Assert the duplicate step has `status="rejected"`.
- Assert `duplicate_tool_calls_blocked == 1`.
- Assert no second Gemini request.

```python
async def test_changed_schedule_retry_in_same_batch_hits_tool_cap()
```

- One batch contains two schedule calls with different `target_time_hint` values.
- Assert only the first reaches `schedule_skill.propose`.
- Assert `tool_retry_limit_blocks == 1`.
- This proves the cap is same-tool based, not only exact-duplicate based.

```python
def test_fingerprint_ignores_dictionary_order()
```

Same semantic arguments in different key order must produce equal fingerprints.

```python
def test_fingerprint_changes_with_disambiguation_hint()
```

Changing `target_time_hint` or `target_staffing_hint` must produce a different fingerprint.

```python
async def test_prompt_token_limit_prevents_followup_model_call()
```

- First Gemini response consumes at least 100k prompt tokens and calls a cheap mocked read tool.
- Assert the tool result is retained.
- Assert no second Gemini request.
- Assert `stop_reason == "prompt_token_limit"`.
- Assert final text explains the budget stop.

```python
def test_turn_bound_reason_precedence()
```

Cover model-call, wall-clock, prompt-token, and unbounded cases.

## 8. Existing Test Updates

**File:** `server/tests/huume/test_usage_accounting.py`

Add a test proving extra telemetry does not interfere with token accumulation:

```python
def test_usage_telemetry_fields_survive_accumulation()
```

**File:** `server/tests/huume/test_huume_routing.py`

No behavior changes should be required. Existing planner/executor tests must continue proving normal non-schedule turns can perform multiple model calls.

## 9. Documentation

**File:** `server/app/matcha/services/huume/CLAUDE.md`

Extend the Schedule Skill section with these invariants:

- One schedule proposal attempt per Huume turn.
- Clarification/refusal is terminal for that turn.
- The complete deterministic candidate list becomes the assistant response without another Gemini call.
- Equivalent calls in one batch are rejected in memory.
- Huume's outer loop stops before another call after 100k cumulative prompt tokens.
- No database migration is involved.

## 10. Verification

Run focused tests:

```bash
cd server
./venv/bin/python -m pytest \
  tests/huume/test_huume_schedule_skill.py \
  tests/huume/test_huume_loop_bounds.py \
  tests/huume/test_usage_accounting.py \
  tests/huume/test_huume_routing.py -q
```

Then the complete Huume suite:

```bash
cd server
./venv/bin/python -m pytest tests/huume/ -q
```

Finally run syntax validation:

```bash
cd server
./venv/bin/python -m py_compile \
  app/matcha/services/huume/agent.py \
  app/matcha/services/huume/schedule_skill.py \
  app/matcha/services/huume/prompt.py
```
