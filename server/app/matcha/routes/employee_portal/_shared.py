"""Shared deps + helpers for the employee_portal package.

The five feature-dependency lists must each be defined exactly once: each
wraps Depends(require_feature(<flag>)), and require_feature is a factory
(dependencies.py) returning a fresh closure per call. dependency_overrides
in tests keys on function-object identity, so recreating a Depends(...) list
in more than one module would create distinct closures for the same flag.
"""
from typing import Optional

from fastapi import Depends
from pydantic import BaseModel

from app.matcha.dependencies import require_all_features, require_feature

_pto_dep = [Depends(require_feature("time_off"))]
_policies_dep = [Depends(require_feature("policies"))]
_compliance_plus_dep = [Depends(require_feature("compliance"))]
_schedule_dep = [Depends(require_all_features("matcha_ops", "employee_schedule"))]
_benefits_dep = [Depends(require_feature("benefits_admin"))]


class CompleteTaskRequest(BaseModel):
    notes: Optional[str] = None
