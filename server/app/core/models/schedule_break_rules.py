"""Validated transport models for reviewed schedule break rules."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class BreakRuleSetImport(BaseModel):
    jurisdiction_id: UUID | None = None
    industry_code: str | None = Field(default=None, max_length=80)
    effective_from: date
    effective_to: date | None = None
    rules: dict[str, Any]
    citation: str = Field(min_length=1, max_length=2000)
    authority_url: str | None = Field(default=None, max_length=2000)
    source_type: Literal["csv", "api", "manual"]
    source_external_id: str | None = Field(default=None, max_length=255)
    source_version: str | None = Field(default=None, max_length=100)

    @field_validator("industry_code", "source_external_id", "source_version", mode="before")
    @classmethod
    def _strip_optional_text(cls, value):
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @field_validator("rules")
    @classmethod
    def _validate_rule_shape(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("rules must be an object")
        for key in ("meal_periods", "rest_periods"):
            if key in value and not isinstance(value[key], list):
                raise ValueError(f"{key} must be a list")
        if "meal_periods" not in value and "rest_periods" not in value:
            raise ValueError("rules must contain meal_periods or rest_periods")
        # Import and runtime resolution must accept exactly the same shape.
        # Import lazily to avoid coupling model module initialization to the
        # scheduling service graph.
        from app.matcha.services.scheduling.schedule_break_rule_store import (
            validate_break_rule_payload,
        )
        validate_break_rule_payload(value)
        return value

    @model_validator(mode="after")
    def _validate_dates(self):
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective_to must be on or after effective_from")
        if self.source_type != "manual" and not self.source_external_id:
            raise ValueError("CSV/API imports require source_external_id")
        return self


class BreakRuleSetReview(BaseModel):
    decision: Literal["approved", "rejected"]


class BreakRuleSetResponse(BaseModel):
    id: UUID
    jurisdiction_id: UUID | None
    industry_code: str | None
    effective_from: date
    effective_to: date | None
    rules: dict[str, Any]
    citation: str
    authority_url: str | None
    source_type: str
    source_external_id: str | None
    source_version: str | None
    review_status: str
    reviewed_by: UUID | None
    reviewed_at: str | None
