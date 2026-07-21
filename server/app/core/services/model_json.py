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

_PY_LITERALS = {"True": "true", "False": "false", "None": "null"}
_WORD_RE = re.compile(r"\b(?:True|False|None)\b")


def _rewrite_python_literals(text: str) -> str:
    """Rewrite bare ``True``/``False``/``None`` to JSON, OUTSIDE string values.

    The obvious implementation — ``re.sub(r":\\s*True\\b", ": true", text)`` — is
    what every local copy used, and it silently corrupts data. Anchoring on a
    colon does not confine the match to a JSON value position, because string
    values contain colons too::

        {"note": "Status: True positive"}  ->  {"note": "Status: true positive"}

    The model's own words get edited on the way to the parser and the corruption
    is invisible downstream. A regex cannot decide this: "am I inside a string?"
    is not a property of the local neighbourhood. So scan once, tracking string
    state and backslash escapes, and only substitute outside strings.
    """
    if not text:
        return text

    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    escaped = False

    while i < n:
        ch = text[i]

        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        m = _WORD_RE.match(text, i)
        if m:
            out.append(_PY_LITERALS[m.group(0)])
            i = m.end()
            continue

        out.append(ch)
        i += 1

    return "".join(out)


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


def clean_model_json(text: str, *, allow_array: bool = False) -> str:
    """Fence-strip, then narrow to the outermost JSON value, then fix literals.

    The brace narrowing is what rescues a response wrapped in prose ("Here is
    the JSON you asked for: {...}").

    ``allow_array`` defaults to **False**, matching every local copy this
    replaced: they narrowed on ``{``/``}`` only. Widening it silently was a real
    bug — callers of this helper expect an object and do ``data.get(...)``
    *outside* the try that wraps ``json.loads`` (see
    ``ticket_draft_service.py:286``, ``commit_scan_service.py:215``). With array
    narrowing on, a model returning ``[...]`` parses successfully and then dies
    on ``.get`` with an uncaught AttributeError — whereas before, ``json.loads``
    raised inside the try and the caller's fail-closed path handled it.
    ``parse_model_json`` enables it, because it returns a parsed value and a
    top-level array is a legitimate response there.
    """
    text = strip_json_fence(text)
    if not text:
        return text

    obj_start, obj_end = text.find("{"), text.rfind("}")
    if obj_start != -1 and obj_end > obj_start:
        text = text[obj_start : obj_end + 1]
    elif allow_array:
        arr_start, arr_end = text.find("["), text.rfind("]")
        if arr_start != -1 and arr_end > arr_start:
            text = text[arr_start : arr_end + 1]

    return _rewrite_python_literals(text).strip()


def parse_model_json(text: str, default: Optional[Any] = None) -> Any:
    """Best-effort parse of a model response. Returns ``default`` on failure.

    Tries, in order: the fence-stripped text as-is (cheapest, and correct when
    the model behaved), then the fully cleaned text. A response that survives
    neither is genuinely unusable.
    """
    if not text:
        return default

    fenced = strip_json_fence(text)
    for candidate in (fenced, clean_model_json(text, allow_array=True)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return default
