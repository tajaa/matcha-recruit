"""Parsing model (Gemini) responses that are supposed to be JSON.

Fifteen private helpers across the codebase did some version of this under five
names (``_clean_json_text`` / ``_strip_json_fence`` / ``_parse_json_response`` /
``_parse_gemini_json`` / ``_extract_json_payload``).

They are NOT the copies the cleanup plan assumed — normalising indentation and
names, only two of the fifteen are actually identical. They differ in
*robustness*, and that is the real problem: the model emits the same malformed
output to every caller, but only some callers recover from it. Concretely,
``gemini_compliance`` and ``commit_scan_service`` rewrite Python literals
(``True``/``False``/``None``) into JSON, which Gemini emits regularly — while
``ticket_draft_service``, whose helper is otherwise the same, does not, and so
simply fails to parse those responses.

Three layers, because callers genuinely need different return types:

* ``strip_json_fence`` — ``str -> str``, fences only. For callers that hand the
  text to something else.
* ``clean_model_json`` — ``str -> str``, the union of every fixup any local copy
  applied. Superset of all of them, so adopting it can only widen what parses.
* ``parse_model_json`` — ``str -> Any``, cleaning plus a balanced-span fallback,
  returning ``default`` instead of raising.

NOTE on migration: several local helpers deliberately let ``json.loads`` raise
(``protocol_analysis_service``, ``accommodation_service``) so their caller can
catch it. Those are NOT interchangeable with ``parse_model_json``, which
swallows. Swapping them would convert a loud failure into a silent default — so
they were left alone rather than mechanically replaced.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

__all__ = ["strip_json_fence", "clean_model_json", "parse_model_json"]

# `True`/`False`/`None` as a JSON *value* — anchored on the colon so a literal
# occurrence inside a string ("Nothing to report") is not rewritten.
_PY_TRUE = re.compile(r":\s*True\b")
_PY_FALSE = re.compile(r":\s*False\b")
_PY_NONE = re.compile(r":\s*None\b")

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def strip_json_fence(text: str) -> str:
    """Remove a leading ```json / ``` fence and a trailing ```.

    Handles the unclosed-fence case (model opens ```json and never closes it),
    which the prefix/suffix form below gets right and a single regex does not.
    """
    text = (text or "").strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def clean_model_json(text: str) -> str:
    """Fence-strip, then narrow to the outermost JSON value, then fix literals.

    The brace/bracket narrowing is what rescues a response wrapped in prose
    ("Here is the JSON you asked for: {...}"). Objects are preferred over
    arrays when both appear, matching what every local copy did.
    """
    text = strip_json_fence(text)
    if not text:
        return text

    obj_start, obj_end = text.find("{"), text.rfind("}")
    arr_start, arr_end = text.find("["), text.rfind("]")
    if obj_start != -1 and obj_end > obj_start:
        text = text[obj_start : obj_end + 1]
    elif arr_start != -1 and arr_end > arr_start:
        text = text[arr_start : arr_end + 1]

    text = _PY_TRUE.sub(": true", text)
    text = _PY_FALSE.sub(": false", text)
    text = _PY_NONE.sub(": null", text)
    return text.strip()


def parse_model_json(text: str, default: Optional[Any] = None) -> Any:
    """Best-effort parse of a model response. Returns ``default`` on failure.

    Tries, in order: the fence-stripped text as-is (cheapest, and correct when
    the model behaved), then the fully cleaned text. A response that survives
    neither is genuinely unusable.
    """
    if not text:
        return default

    fenced = strip_json_fence(text)
    for candidate in (fenced, clean_model_json(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return default
