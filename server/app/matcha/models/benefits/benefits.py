"""Pydantic request/response models for the benefits open-enrollment workflow.

Distinct from the pre-existing eligibility/roster models in
``benefits_eligibility.py`` (CSV ingest shapes) — these back the plan
catalog, OE periods, elections, and life events added 2026-07-23.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

PlanType = Literal["medical", "dental", "vision", "life", "disability", "other"]
PlanStatus = Literal["draft", "active", "archived"]
CoverageTier = Literal["employee_only", "employee_spouse", "employee_children", "family"]
CostPeriod = Literal["monthly", "per_pay_period"]
OePeriodStatus = Literal["draft", "open", "closed"]
ElectionStatus = Literal["draft", "submitted", "approved", "rejected"]
LifeEventType = Literal[
    "marriage", "divorce", "birth_adoption", "death_of_dependent",
    "loss_of_coverage", "gain_of_coverage", "dependent_status_change",
    "relocation", "other",
]
LifeEventStatus = Literal["pending", "approved", "denied", "expired"]
DependentRelationship = Literal["spouse", "child", "domestic_partner", "other"]


class TierInput(BaseModel):
    coverage_tier: CoverageTier
    employee_cost: float = Field(ge=0)
    employer_cost: float = Field(ge=0)
    cost_period: CostPeriod = "monthly"


class PlanCreate(BaseModel):
    plan_type: PlanType
    name: str = Field(min_length=1, max_length=200)
    carrier_name: Optional[str] = None
    description: Optional[str] = None
    waivable: bool = True
    tiers: list[TierInput] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    carrier_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[PlanStatus] = None
    waivable: Optional[bool] = None


class OePeriodCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    starts_on: date
    ends_on: date
    plan_year_start: Optional[date] = None

    @model_validator(mode="after")
    def _check_dates(self):
        if self.ends_on < self.starts_on:
            raise ValueError("ends_on must be on or after starts_on")
        return self


class OePeriodUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    plan_year_start: Optional[date] = None


class DependentInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    relationship: DependentRelationship
    dob: Optional[date] = None


class ElectionUpsert(BaseModel):
    plan_type: PlanType
    plan_id: Optional[UUID] = None
    tier_id: Optional[UUID] = None
    waived: bool = False
    dependents: list[DependentInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_waive_consistency(self):
        if self.waived:
            if self.plan_id is not None or self.tier_id is not None:
                raise ValueError("waived elections must not carry plan_id/tier_id")
        else:
            if self.plan_id is None or self.tier_id is None:
                raise ValueError("non-waived elections require both plan_id and tier_id")
        return self


class DecisionInput(BaseModel):
    note: Optional[str] = None


class LifeEventCreate(BaseModel):
    event_type: LifeEventType
    event_date: date
    description: Optional[str] = None
