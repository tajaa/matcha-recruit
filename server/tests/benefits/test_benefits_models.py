"""Pydantic shape validation for the benefits models (no DB)."""
from datetime import date
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.matcha.models.benefits import (
    DependentInput,
    ElectionUpsert,
    OePeriodCreate,
    PlanCreate,
    TierInput,
)


def test_election_waived_requires_no_plan_or_tier():
    ElectionUpsert(plan_type="medical", waived=True)  # OK
    with pytest.raises(ValidationError):
        ElectionUpsert(plan_type="medical", waived=True, plan_id=uuid4(), tier_id=uuid4())


def test_election_non_waived_requires_plan_and_tier():
    ElectionUpsert(plan_type="medical", waived=False, plan_id=uuid4(), tier_id=uuid4())  # OK
    with pytest.raises(ValidationError):
        ElectionUpsert(plan_type="medical", waived=False)
    with pytest.raises(ValidationError):
        ElectionUpsert(plan_type="medical", waived=False, plan_id=uuid4())


def test_dependent_relationship_literal_rejects_unknown_value():
    DependentInput(name="Jamie Doe", relationship="spouse")  # OK
    with pytest.raises(ValidationError):
        DependentInput(name="Jamie Doe", relationship="cousin")


def test_oe_period_rejects_ends_before_starts():
    OePeriodCreate(name="2027 Open Enrollment", starts_on=date(2027, 1, 1), ends_on=date(2027, 1, 31))  # OK
    with pytest.raises(ValidationError):
        OePeriodCreate(name="Bad window", starts_on=date(2027, 2, 1), ends_on=date(2027, 1, 1))


def test_plan_create_defaults():
    plan = PlanCreate(plan_type="dental", name="Delta Dental PPO")
    assert plan.waivable is True
    assert plan.tiers == []


def test_tier_input_rejects_negative_cost():
    TierInput(coverage_tier="employee_only", employee_cost=0, employer_cost=100)  # OK
    with pytest.raises(ValidationError):
        TierInput(coverage_tier="employee_only", employee_cost=-1, employer_cost=100)
