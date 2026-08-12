"""Shared bounds for Merlin's tool-calling loops.

The page editor and setup concierge have different tools, but both need the
same protection against a model repeating a rejected call until it reaches its
model-call ceiling. This module keeps that policy independent of either tool
registry so their behavior cannot drift.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Optional, Sequence

ToolStatus = Literal["changed", "informed", "failed", "neutral"]

_JSON_ARGUMENTS = frozenset({"ops", "payload"})


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


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def tool_call_fingerprint(tool: str, args: Mapping[str, Any]) -> str:
    """Return a stable, non-reversible fingerprint for a tool invocation.

    Gemini sends some wide payloads as JSON strings. Decode those before
    canonicalizing so equivalent object and string representations share a
    fingerprint. The digest, rather than customer-provided arguments, is safe
    to place in diagnostics.
    """
    normalized_args: dict[str, Any] = {}
    for key, value in args.items():
        if key in _JSON_ARGUMENTS and isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        normalized_args[str(key)] = _normalize(value)
    encoded = json.dumps(
        {"tool": tool, "args": _normalize(normalized_args)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class NoProgressGuard:
    """Track repeated failed tool batches for one model turn.

    A successful mutation clears all previous failures. Informational work
    clears only the consecutive-failure count: a lookup between two identical
    rejected writes does not make the retry useful.
    """

    def __init__(
        self,
        *,
        max_consecutive_failed_batches: int = 2,
        max_same_failure: int = 2,
    ) -> None:
        self.max_consecutive_failed_batches = max_consecutive_failed_batches
        self.max_same_failure = max_same_failure
        self._consecutive_failed_batches = 0
        self._failure_counts: dict[str, int] = {}

    def observe_batch(self, observations: Sequence[ToolObservation]) -> LoopDecision:
        changed = any(observation.status == "changed" for observation in observations)
        informed = any(observation.status == "informed" for observation in observations)
        failures = [observation for observation in observations if observation.status == "failed"]

        if changed:
            self._consecutive_failed_batches = 0
            self._failure_counts.clear()
            return LoopDecision(stop=False)

        repeated: Optional[tuple[ToolObservation, str]] = None
        for observation in failures:
            fingerprint = tool_call_fingerprint(observation.tool, observation.args)
            self._failure_counts[fingerprint] = self._failure_counts.get(fingerprint, 0) + 1
            if self._failure_counts[fingerprint] >= self.max_same_failure:
                repeated = (observation, fingerprint)

        if repeated is not None:
            observation, fingerprint = repeated
            return LoopDecision(stop=True, reason=observation.reason, fingerprint=fingerprint)

        if informed:
            self._consecutive_failed_batches = 0
            return LoopDecision(stop=False)

        if failures:
            self._consecutive_failed_batches += 1
            if self._consecutive_failed_batches >= self.max_consecutive_failed_batches:
                return LoopDecision(stop=True, reason=failures[-1].reason)
        return LoopDecision(stop=False)


def _part_tokens(part: Any) -> int:
    text = getattr(part, "text", None)
    if isinstance(text, str):
        return max(1, (len(text) + 2) // 3)

    inline = getattr(part, "inline_data", None)
    data = getattr(inline, "data", None)
    if isinstance(data, (bytes, bytearray)):
        # A byte-based estimate is intentionally conservative when Gemini does
        # not return usage metadata for a multimodal call.
        return max(1, (len(data) + 2) // 3)

    function_call = getattr(part, "function_call", None)
    if function_call is not None:
        return max(1, (len(json.dumps(_normalize(getattr(function_call, "args", {}) or {}))) + 2) // 3)

    function_response = getattr(part, "function_response", None)
    if function_response is not None:
        return max(1, (len(json.dumps(_normalize(getattr(function_response, "response", {}) or {}))) + 2) // 3)
    return 0


def estimate_prompt_tokens(system_instruction: str, contents: Sequence[Any]) -> int:
    """Conservatively estimate token input when Gemini omits usage metadata."""
    total = max(1, (len(system_instruction or "") + 2) // 3)
    for content in contents:
        for part in getattr(content, "parts", None) or []:
            total += _part_tokens(part)
    return total


@dataclass
class TurnTokenBudget:
    max_prompt_tokens: int
    max_total_tokens: int
    prompt_tokens: int = 0
    total_tokens: int = 0
    last_prompt_tokens: int = 0

    def record_response(self, response: Any, *, fallback_prompt_tokens: int) -> None:
        usage = getattr(response, "usage_metadata", None)
        prompt = getattr(usage, "prompt_token_count", None) if usage is not None else None
        total = getattr(usage, "total_token_count", None) if usage is not None else None
        completion = getattr(usage, "candidates_token_count", None) if usage is not None else None
        thinking = getattr(usage, "thoughts_token_count", None) if usage is not None else None

        prompt = prompt if isinstance(prompt, int) and prompt >= 0 else fallback_prompt_tokens
        if not isinstance(total, int) or total < 0:
            total = prompt + (completion if isinstance(completion, int) and completion > 0 else 0)
            total += thinking if isinstance(thinking, int) and thinking > 0 else 0

        self.prompt_tokens += prompt
        self.total_tokens += total
        self.last_prompt_tokens = prompt

    def reason_before_next_call(self, *, estimated_next_prompt_tokens: int) -> Optional[str]:
        if self.total_tokens >= self.max_total_tokens:
            return "I stopped here to stay within this turn's AI budget."
        if self.prompt_tokens >= self.max_prompt_tokens:
            return "I stopped here to stay within this turn's AI context budget."
        projected_prompt = max(estimated_next_prompt_tokens, self.last_prompt_tokens)
        if self.prompt_tokens + projected_prompt > self.max_prompt_tokens:
            return "I stopped before retrying because this page's context is too large for this turn."
        return None
