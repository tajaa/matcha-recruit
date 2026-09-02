"""Rule-resolution tests with fake asyncpg records."""

import asyncio
from datetime import date
from uuid import uuid4

import pytest

from app.core.models.schedule_break_rules import BreakRuleSetImport
from app.core.services.schedule_break_rule_import import review_break_rule_set
from app.matcha.services.scheduling.schedule_break_rule_store import resolve_break_rules


class FakeConn:
    def __init__(self, location, *, industry="retail", structured=None, state="CA"):
        self.location = location
        self.industry = industry
        self.structured = structured or []
        self.state = state

    async def fetchrow(self, query, *args):
        if "FROM business_locations" in query:
            return self.location
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "SELECT industry FROM companies" in query:
            return self.industry
        if "SELECT state FROM business_locations" in query:
            return self.state
        raise AssertionError(query)

    async def fetch(self, query, *args):
        if "FROM schedule_break_rule_sets" in query:
            return self.structured
        raise AssertionError(query)


def _location():
    return {
        "id": uuid4(),
        "address": "100 Main St",
        "city": "Los Angeles",
        "state": "CA",
        "zipcode": "90001",
        "jurisdiction_id": uuid4(),
        "timezone": "America/Los_Angeles",
        "naics": None,
    }


def _run(coro):
    return asyncio.run(coro)


def test_approved_structured_rule_beats_legacy_fallback():
    location = _location()
    rule_id = uuid4()
    row = {
        "id": rule_id,
        "rules": {
            "meal_periods": [{
                "ordinal": 1,
                "trigger_after_minutes": 240,
                "duration_minutes": 45,
                "paid": False,
                "deadline_offset_minutes": 240,
            }],
        },
        "citation": "City citation",
        "depth": 0,
        "industry_code": "retail",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row]),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "approved"
    assert result.rule_set_ids == (rule_id,)
    assert result.rules[0].duration_minutes == 45
    assert result.rules[0].trigger_after_minutes == 240


def test_approved_rule_preserves_reviewed_age_scope():
    location = _location()
    rule_id = uuid4()
    row = {
        "id": rule_id,
        "rules": {
            "meal_periods": [{
                "trigger_after_minutes": 240,
                "duration_minutes": 30,
                "maximum_age": 17,
            }],
        },
        "citation": "Minor meal citation",
        "depth": 0,
        "industry_code": "retail",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row]), company_id=uuid4(),
        location_id=location["id"], shift_date=date(2026, 8, 21),
    ))
    assert result.rules[0].maximum_age == 17


def test_ca_legacy_rule_is_adapted_until_structured_rows_exist():
    location = _location()
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[]),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "legacy_curated"
    assert result.rules[0].kind == "meal"
    assert result.rules[0].trigger_after_minutes == 300
    assert result.rules[0].duration_minutes == 30


def test_unmapped_state_returns_visible_advisory():
    location = _location()
    location["state"] = "XX"
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[], state="XX"),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "unmapped"
    assert result.rules == ()
    assert result.advisories[0]["code"] == "break_rules_unmapped"


def test_no_jurisdiction_is_unmapped_without_database_rule_query():
    location = _location()
    location["jurisdiction_id"] = None
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[]),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "unmapped"
    assert result.advisories[0]["code"] == "break_rules_unmapped"


def test_rest_count_bands_create_only_the_new_ordinal_per_threshold():
    rule_id = uuid4()
    location = _location()
    row = {
        "id": rule_id,
        "rules": {
            "rest_periods": [{
                "duration_minutes": 10,
                "paid": True,
                "count_bands": [
                    {"min_minutes": 240, "count": 1},
                    {"min_minutes": 360, "count": 2},
                ],
            }],
        },
        "citation": "City citation",
        "depth": 0,
        "industry_code": "retail",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row]),
        company_id=uuid4(), location_id=location["id"], shift_date=date(2026, 8, 21),
    ))
    assert [(rule.ordinal, rule.trigger_after_minutes) for rule in result.rules] == [
        (1, 240), (2, 360),
    ]


def test_malformed_supplied_age_is_rejected_instead_of_becoming_unscoped():
    location = _location()
    row = {
        "id": uuid4(),
        "rules": {"meal_periods": [{
            "trigger_after_minutes": 240,
            "duration_minutes": 30,
            "maximum_age": "seventeen",
        }]},
        "citation": "Minor meal citation", "depth": 0,
        "industry_code": "retail", "effective_from": date(2026, 1, 1),
        "effective_to": None,
    }

    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row]), company_id=uuid4(),
        location_id=location["id"], shift_date=date(2026, 8, 21),
    ))

    assert result.source == "error"
    assert result.rules == ()
    assert result.advisories[0]["code"] == "break_rules_invalid"


def test_aggregate_meal_break_cannot_exceed_shift_api_limit():
    location = _location()
    row = {
        "id": uuid4(),
        "rules": {"meal_periods": [
            {"ordinal": 1, "trigger_after_minutes": 1, "duration_minutes": 1000},
            {"ordinal": 2, "trigger_after_minutes": 2, "duration_minutes": 500},
        ]},
        "citation": "Bad import", "depth": 0,
        "industry_code": "retail", "effective_from": date(2026, 1, 1),
        "effective_to": None,
    }

    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row]), company_id=uuid4(),
        location_id=location["id"], shift_date=date(2026, 8, 21),
    ))

    assert result.source == "error"
    assert "1440" in result.advisories[0]["metadata"]["reason"]


def test_import_rejects_rules_the_runtime_parser_cannot_enforce():
    with pytest.raises(ValueError, match="whole numbers"):
        BreakRuleSetImport(
            jurisdiction_id=uuid4(), effective_from=date(2026, 1, 1),
            rules={"meal_periods": [{
                "trigger_after_minutes": 300,
                "duration_minutes": "thirty",
            }]},
            citation="Authority", source_type="manual",
        )


def test_approval_revalidates_the_locked_persisted_payload():
    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class Connection:
        def transaction(self):
            return Transaction()

        async def fetchrow(self, query, *_args):
            assert "FOR UPDATE" in query
            return {
                "id": uuid4(), "jurisdiction_id": uuid4(),
                "rules": {"meal_periods": [{
                    "trigger_after_minutes": 300,
                    "duration_minutes": "invalid",
                }]},
                "citation": "Authority",
            }

    with pytest.raises(ValueError, match="whole numbers"):
        _run(review_break_rule_set(
            Connection(), rule_set_id=uuid4(), decision="approved",
            actor_user_id=uuid4(),
        ))
