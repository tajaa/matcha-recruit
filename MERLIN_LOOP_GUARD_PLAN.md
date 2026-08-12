# Merlin Loop Guard Plan

## Goal

Prevent Merlin's setup and page-editor tool loops from burning their remaining
model-call budget retrying rejected tool calls. The guard must preserve one
useful correction attempt, never hide successful sibling calls, and stop before
resending a known oversized prompt.

## Scope

Affected surfaces:

- Setup concierge: `server/app/cappe/services/merlin/setup_agent.py`
- Page-editor agent: `server/app/cappe/services/merlin/agent.py`
- Page-editor single-shot validation retry: `server/app/cappe/services/merlin/turn.py`

No database migration, route contract, or frontend change is required.

## Shared Loop Control

Create `server/app/cappe/services/merlin/loop_control.py`.

```python
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence

ToolStatus = Literal["changed", "informed", "failed", "neutral"]

@dataclass(frozen=True)
class ToolObservation:
    tool: str
    status: ToolStatus
    args: Mapping[str, Any]
    reason: Optional[str] = None

@dataclass(frozen=True)
class LoopDecision:
    stop: bool
    reason: Optional[str] = None
    fingerprint: Optional[str] = None

class NoProgressGuard:
    def __init__(
        self,
        *,
        max_consecutive_failed_batches: int = 2,
        max_same_failure: int = 2,
    ) -> None: ...

    def observe_batch(
        self,
        observations: Sequence[ToolObservation],
    ) -> LoopDecision: ...

def tool_call_fingerprint(tool: str, args: Mapping[str, Any]) -> str: ...
```

Fingerprint rules:

- Parse JSON-string arguments such as `payload` and `ops` before normalization.
- Serialize normalized values with sorted keys and hash them with SHA-256.
- Never log raw tool arguments because prompts may contain customer content.
- Fingerprint the tool plus normalized arguments, not the rejection wording.

## Progress Semantics

Evaluate one full Gemini function-call response as a batch.

| Status | Examples | Counter behavior |
| --- | --- | --- |
| `changed` | applied ops, staged action, executed action, placed image | Reset consecutive failures and remembered failure fingerprints |
| `informed` | successful screenshot or block inspection | Reset consecutive failed batches, retain failure fingerprints |
| `failed` | validation rejection, missing record, blocked execution, tool error | Record fingerprint and reason |
| `neutral` | `finish` | No effect |

Stopping rules:

1. Stop when the same failed fingerprint occurs twice, including if an informational lookup occurs between attempts.
2. Stop after two consecutive batches containing failures and no `changed` or `informed` outcome.
3. Never stop because of a failed sibling when the same batch made progress.
4. Successful mutation/proposal progress resets all remembered failures.
5. Successful informational reads reset only the consecutive-batch counter.

This catches the Huume-style sequence:

```text
rejected proposal
successful lookup
same rejected proposal
=> stop after the second proposal rejection
```

It allows useful recovery:

```text
rejected proposal
successful action
unrelated rejection
=> continue
```

## Setup Concierge Changes

Modify `server/app/cappe/services/merlin/setup_agent.py`.

Remove the ad hoc state:

```python
_MAX_REJECTED_STAGE_ATTEMPTS
rejected_stage_attempts
terminal_rejection
```

Instantiate:

```python
no_progress = NoProgressGuard(
    max_consecutive_failed_batches=2,
    max_same_failure=2,
)
```

Add:

```python
def _setup_observation(
    *,
    name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> ToolObservation: ...
```

Classify results:

- `stage_action` with `staged=True`: `changed`
- `stage_action` with a validation, gate, or JSON failure: `failed`
- `execute_staged_action` with `executed=True`: `changed`
- Missing action, same-turn refusal, settled action, or entitlement refusal: `failed`
- Unknown tool: `failed`
- `finish`: `neutral`

After all non-finish calls in the Gemini batch, pass observations to
`no_progress.observe_batch()`. On a stop decision, return a deterministic
message containing the latest validation reason.

## Page-Editor Agent Changes

Modify `server/app/cappe/services/merlin/agent.py`.

Remove:

```python
_MAX_REJECTED_APPLY_ATTEMPTS
rejected_apply_attempts
terminal_rejection
```

Add:

```python
def _agent_observation(
    *,
    name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> ToolObservation: ...
```

Classify results:

- `apply_ops` with at least one applied operation: `changed`
- `apply_ops` with no applied operation and rejection/error: `failed`
- Mixed valid/rejected operations: `changed`
- Successful `inspect_block`: `informed`
- Failed `inspect_block`: `failed`
- Successful screenshot: `informed`
- Screenshot unavailable, render failure, or exhausted budget: `failed`
- Successfully placed generated image: `changed`
- Invalid image target, quota rejection, generation failure, or placement failure: `failed`
- Unknown tool: `failed`

Successful operations must remain in `op_log` regardless of later failures.

## Parallel Finish Handling

Update both loops so a `finish` call cannot hide a failed sibling.

- `finish` alone: finish immediately.
- `finish` plus only successful tools: execute tools, then finish.
- `finish` plus any failed tool: defer finish and return all tool responses to Gemini.
- A `NoProgressGuard` stop decision takes precedence over model-provided finish text.
- Successful sibling calls remain applied or staged.

For deferred finish calls, append the required function response:

```python
types.Part.from_function_response(
    name="finish",
    response={
        "status": "deferred",
        "reason": "One or more tool calls failed; review their results before finishing.",
    },
)
```

This keeps the Gemini function-call transcript complete.

## Token Budget Guard

Add to `loop_control.py`:

```python
@dataclass
class TurnTokenBudget:
    max_prompt_tokens: int
    max_total_tokens: int
    prompt_tokens: int = 0
    total_tokens: int = 0
    last_prompt_tokens: int = 0

    def record_response(
        self,
        response: Any,
        *,
        fallback_prompt_tokens: int,
    ) -> None: ...

    def reason_before_next_call(
        self,
        *,
        estimated_next_prompt_tokens: int,
    ) -> Optional[str]: ...

def estimate_prompt_tokens(
    system_instruction: str,
    contents: Sequence[Any],
) -> int: ...
```

Behavior:

- Prefer Gemini `usage_metadata.prompt_token_count` and `total_token_count`.
- Use conservative text/JSON character estimation when metadata is absent.
- Before another call, project the next prompt using at least `last_prompt_tokens`.
- Stop before resending a known huge prompt.
- Preserve model-call and wall-clock limits as independent guards.
- Log aggregate token totals, call count, tier, and stop reason only.

Recommended initial limits:

| Surface | Prompt tokens | Total tokens |
| --- | ---: | ---: |
| Setup Merlin | 180,000 | 225,000 |
| Regular agent | 300,000 | 375,000 |
| Max agent | 500,000 | 625,000 |

Extend `_Bounds` in `agent.py`:

```python
class _Bounds:
    __slots__ = (
        "model_calls",
        "screenshots",
        "wall_clock",
        "prompt_tokens",
        "total_tokens",
    )
```

`server/app/core/services/ai_usage.py` already records actual per-call token
counts and cost. This guard uses tokens as a deterministic per-turn ceiling;
it does not modify the global rate limiter.

## Retry Context Reduction

Modify `server/app/cappe/services/merlin/agent.py`:

- Keep the existing one-recent-screenshot pruning behavior.
- After the first planning call, replace initial user attachment image parts
  with a text placeholder.
- Retain original attachment bytes in local `atts` so
  `generate_image(attachment_index=...)` remains valid.
- Do not aggressively rewrite function-call history because Gemini requires
  matching function call/response pairs and thought signatures.

Modify `server/app/cappe/services/merlin/turn.py`:

- Apply `TurnTokenBudget` before its single validation retry.
- If repeating the prompt would exceed budget, return the first rejection
  instead of issuing a second model call.

## Tests

Update `server/tests/cappe/test_merlin_agent.py`:

1. Same rejected operation twice stops after two calls.
2. Different rejected operations in two no-progress batches stop.
3. Rejection, valid apply, then rejection does not stop.
4. Rejection, successful inspection, then same rejection stops.
5. Parallel valid and invalid `apply_ops` preserves valid operations.
6. Mixed batch with `finish` defers finish.
7. Deferred finish receives a function response.
8. Repeated malformed `ops` JSON stops.
9. Repeated invalid `inspect_block` stops.
10. Repeated image-target rejection stops.
11. Repeated image-generation failure stops.
12. Repeated screenshot failure stops.
13. Token projection prevents resending a 170k-token prompt.
14. Operations completed before token cutoff survive.
15. Normal usage under the token budget remains unchanged.
16. Existing model-call, screenshot, and operation limits still pass.

Update `server/tests/cappe/test_merlin_setup_agent.py`:

1. Same rejected staged action twice stops.
2. Different rejected staged actions in consecutive batches stop.
3. Rejection, successful stage, then rejection does not stop.
4. Rejection, informational call, then same rejection stops where applicable.
5. Repeated nonexistent action execution stops.
6. Repeated same-turn execution refusal stops.
7. Repeated already-executed action refusal stops.
8. Successful stage plus rejected sibling does not terminate.
9. Mixed batch with `finish` defers finish.
10. Malformed payload participates in the guard.
11. Token cutoff preserves previously staged/executed work.

Update `server/tests/cappe/test_merlin_turn.py`:

1. Large first response prevents validation retry.
2. Small first response still permits one retry.
3. Missing usage metadata uses fallback estimation.

Extend fake responses in the Merlin test modules:

```python
class _FakeUsage:
    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int

class _FakeResponse:
    def __init__(
        self,
        calls,
        text="",
        usage_metadata: Optional[_FakeUsage] = None,
    ): ...
```

## Verification

Run focused non-database-mutating tests:

```bash
cd server
python3 -m py_compile \
  app/cappe/services/merlin/loop_control.py \
  app/cappe/services/merlin/agent.py \
  app/cappe/services/merlin/setup_agent.py \
  app/cappe/services/merlin/turn.py

python3 -m pytest \
  tests/cappe/test_merlin_agent.py \
  tests/cappe/test_merlin_setup_agent.py \
  tests/cappe/test_merlin_turn.py -q
```

Then run:

```bash
git diff --check
```

Replace the current uncommitted counter-based implementation with this
batch-aware guard before committing.
