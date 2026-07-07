"""Analysis Pilot request models (Pydantic v2)."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.matcha.services.analysis_packs.mapping import CANONICAL_ROLES

# Sentinels a caller may use to clear a heuristic role assignment.
_ROLE_CLEARERS = {"", "none", "ignore"}


class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    domain: Optional[str] = Field(None, max_length=30)
    goal: Optional[str] = Field(None, max_length=2000)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    goal: Optional[str] = Field(None, max_length=2000)
    status: Optional[Literal["active", "closed"]] = None


class DatasetPatch(BaseModel):
    """Confirm/adjust a dataset before (re)analysis. `mapping` overrides column→
    role (validated against the canonical vocabulary); `column_kinds` marks a
    series as already-returns; `extraction` lets the user correct document-
    extracted figures before they drive metrics; `orientation` overrides the
    tabular layout heuristic (re-parses the stored file); `reextract` re-runs
    the document extraction (recovery after a transient Gemini failure)."""
    mapping: Optional[dict[str, str]] = None
    column_kinds: Optional[dict[str, Literal["level", "returns"]]] = None
    periods_per_year: Optional[int] = Field(None, ge=1, le=100000)
    risk_free: Optional[float] = Field(None, ge=-1, le=1)
    kind: Optional[str] = Field(None, max_length=30)
    extraction: Optional[dict] = None
    orientation: Optional[Literal["columns", "rows"]] = None
    reextract: bool = False

    @field_validator("mapping")
    @classmethod
    def _known_roles(cls, v: Optional[dict[str, str]]) -> Optional[dict[str, str]]:
        """An unknown role would be stored forever and silently ignored by every
        pack's `applies()` — reject it with the valid vocabulary instead."""
        if not v:
            return v
        allowed = set(CANONICAL_ROLES) | _ROLE_CLEARERS
        bad = sorted({r for r in v.values() if r not in allowed})
        if bad:
            raise ValueError(
                f"Unknown role(s): {', '.join(bad)}. Valid roles: {', '.join(CANONICAL_ROLES)} "
                f"(or ''/'none'/'ignore' to clear)."
            )
        return v


class ComparisonCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    dataset_ids: list[UUID] = Field(..., min_length=2, max_length=8)
    spec: Optional[dict] = None


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    # Highlighted-record cids the turn should focus on (validated against the
    # corpus index server-side; unknown ids are dropped, not errored).
    focus: Optional[list[str]] = Field(None, max_length=10)


class ReportIn(BaseModel):
    # Scope is derived: a comparison_id focuses the report's comparison section.
    comparison_id: Optional[UUID] = None
