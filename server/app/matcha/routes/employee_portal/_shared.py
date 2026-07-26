"""Shared deps + helpers for the employee_portal package.

The five feature-dependency lists must each be defined exactly once: each
wraps Depends(require_feature(<flag>)), and require_feature is a factory
(dependencies.py) returning a fresh closure per call. dependency_overrides
in tests keys on function-object identity, so recreating a Depends(...) list
in more than one module would create distinct closures for the same flag.
"""
from typing import Any, Optional

from fastapi import Depends
from pydantic import BaseModel

from app.matcha.dependencies import require_feature

_pto_dep = [Depends(require_feature("time_off"))]
_policies_dep = [Depends(require_feature("policies"))]
_compliance_plus_dep = [Depends(require_feature("compliance"))]
_schedule_dep = [Depends(require_feature("employee_schedule"))]
_benefits_dep = [Depends(require_feature("benefits_admin"))]


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None


# NOTE: no callers as of 2026-07 (repo-wide grep) — deletion candidate in a
# follow-up. Kept verbatim during the employee_portal split.
def _parse_json_array(value: Any) -> list[str]:
    import json

    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(trimmed)
    return result


def _normalize_string_list(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        trimmed = value.strip()
        if not trimmed:
            continue
        key = trimmed.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(trimmed)
    return deduped
