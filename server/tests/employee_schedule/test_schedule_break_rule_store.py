"""Rule-resolution tests with fake asyncpg records."""

import asyncio
import inspect
from datetime import date
from uuid import uuid4

import pytest

from app.core.models.schedule_break_rules import BreakRuleSetImport
from app.core.services.schedule_break_rule_import import review_break_rule_set
from app.matcha.services.scheduling import schedule_break_rule_store
from app.matcha.services.scheduling.schedule_break_rule_store import (
    ResolvedBreakRules,
    record_break_rule_applicability_decision,
    resolve_break_rules,
)
from app.matcha.services.scheduling.shift_compliance import _DB_RULES_CACHE


@pytest.fixture(autouse=True)
def _clear_db_rules_cache():
    """`_approved_db_rules` memoizes per state for 10 minutes, process-wide."""
    _DB_RULES_CACHE.clear()
    yield
    _DB_RULES_CACHE.clear()


class FakeConn:
    def __init__(
        self, location, *, industry="retail", structured=None, state="CA",
        extractions=None, extractions_fail=False, applicability_decision="confirmed",
        employer_employee_count=24,
    ):
        self.location = location
        self.industry = industry
        self.structured = structured or []
        self.state = state
        self.extractions = extractions or []
        self.extractions_fail = extractions_fail
        self.applicability_decision = applicability_decision
        self.employer_employee_count = employer_employee_count
        self.headcount_queries = 0
        self.confirmation_context_hashes = []

    async def fetchrow(self, query, *args):
        if "FROM business_locations" in query:
            return self.location
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "pg_advisory_xact_lock_shared" in query:
            return None
        if "SELECT industry FROM companies" in query:
            return self.industry
        if "SELECT state FROM business_locations" in query:
            return self.state
        if "company_handbook_profiles" in query:
            self.headcount_queries += 1
            return self.employer_employee_count
        if "company_schedule_break_rule_confirmations" in query:
            self.confirmation_context_hashes.append(args[3])
            return self.applicability_decision
        raise AssertionError(query)

    async def fetch(self, query, *args):
        if "FROM schedule_break_rule_sets" in query:
            return self.structured
        if "FROM schedule_rule_extractions" in query:
            if self.extractions_fail:
                raise RuntimeError("catalog unavailable")
            return self.extractions
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
        "authority_url": "https://example.gov/rule",
        "source_type": "manual",
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row]),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "approved_and_organization_confirmed"
    assert result.rule_set_ids == (rule_id,)
    assert result.rules[0].duration_minutes == 45
    assert result.rules[0].trigger_after_minutes == 240
    assert result.rules[0].effective_from == date(2026, 1, 1)
    assert result.rules[0].authority_url == "https://example.gov/rule"
    assert result.rules[0].source_type == "manual"
    assert result.employer_employee_count == 24


def test_reviewed_expected_rule_requires_organization_confirmation():
    location = _location()
    rule_id = uuid4()
    row = {
        "id": rule_id,
        "rules": {"meal_periods": [{
            "trigger_after_minutes": 360,
            "duration_minutes": 30,
            "window_start": "11:00",
            "window_end": "14:00",
        }]},
        "citation": "Expected authority",
        "depth": 0,
        "industry_code": "retail",
        "effective_from": date(2026, 1, 1),
        "effective_to": None,
        "authority_url": "https://example.gov/rule",
        "source_type": "api",
        "review_status": "approved",
        "jurisdiction_id": location["jurisdiction_id"],
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row], applicability_decision=None), company_id=uuid4(),
        location_id=location["id"], shift_date=date(2026, 8, 21),
    ))
    assert result.source == "confirmation_required"
    assert result.rules == ()
    assert result.expected_rules[0].rule_set_id == rule_id
    advisory = result.advisories[0]
    assert advisory["code"] == "break_rules_confirmation_required"
    assert advisory["metadata"]["citation"] == "Expected authority"
    assert len(advisory["metadata"]["context_hash"]) == 64


def test_confirmed_expected_rule_operates_after_separate_source_review():
    location = _location()
    row = {
        "id": uuid4(),
        "rules": {"meal_periods": [{
            "trigger_after_minutes": 360, "duration_minutes": 30,
        }]},
        "citation": "Expected authority", "depth": 0,
        "industry_code": "retail", "effective_from": date(2026, 1, 1),
        "effective_to": None, "authority_url": "https://example.gov/rule",
        "source_type": "api", "review_status": "approved",
        "jurisdiction_id": location["jurisdiction_id"],
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row], applicability_decision="confirmed"),
        company_id=uuid4(), location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "approved_and_organization_confirmed"
    assert len(result.rules) == 1
    assert result.expected_rules == result.rules
    assert result.advisories == ()


def test_grandfathered_expected_rule_preserves_pre_migration_behavior():
    location = _location()
    row = {
        "id": uuid4(),
        "rules": {"meal_periods": [{
            "trigger_after_minutes": 360, "duration_minutes": 30,
        }]},
        "citation": "Expected authority", "depth": 0,
        "industry_code": "retail", "effective_from": date(2026, 1, 1),
        "effective_to": None, "authority_url": "https://example.gov/rule",
        "source_type": "api", "jurisdiction_id": location["jurisdiction_id"],
    }
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[row], applicability_decision="grandfathered"),
        company_id=uuid4(), location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "approved"
    assert len(result.rules) == 1
    assert result.applicability_decision == "grandfathered"
    assert result.advisories == ()


def test_headcount_change_does_not_invalidate_applicability_context():
    location = _location()
    row = {
        "id": uuid4(),
        "rules": {"meal_periods": [{
            "trigger_after_minutes": 360,
            "duration_minutes": 30,
            "minimum_employees": 20,
        }]},
        "citation": "Expected authority", "depth": 0,
        "industry_code": "retail", "effective_from": date(2026, 1, 1),
        "effective_to": None, "authority_url": None, "source_type": "manual",
        "jurisdiction_id": location["jurisdiction_id"],
    }
    company_id = uuid4()
    first = FakeConn(location, structured=[row], employer_employee_count=47)
    second = FakeConn(location, structured=[row], employer_employee_count=48)

    first_result = _run(resolve_break_rules(
        first, company_id=company_id, location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    second_result = _run(resolve_break_rules(
        second, company_id=company_id, location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))

    assert first_result.applicability_context_hash == second_result.applicability_context_hash
    assert first_result.employer_employee_count == 47
    assert second_result.employer_employee_count == 48


def test_empty_active_roster_keeps_employer_size_unknown_and_can_be_prefetched():
    location = _location()
    row = {
        "id": uuid4(),
        "rules": {"meal_periods": [{
            "trigger_after_minutes": 360,
            "duration_minutes": 30,
            "minimum_employees": 20,
        }]},
        "citation": "Expected authority", "depth": 0,
        "industry_code": "retail", "effective_from": date(2026, 1, 1),
        "effective_to": None, "authority_url": None, "source_type": "manual",
        "jurisdiction_id": location["jurisdiction_id"],
    }
    conn = FakeConn(location, structured=[row], employer_employee_count=None)
    result = _run(resolve_break_rules(
        conn, company_id=uuid4(), location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.employer_employee_count is None
    assert conn.headcount_queries == 1

    prefetched = FakeConn(location, structured=[row])
    result = _run(resolve_break_rules(
        prefetched, company_id=uuid4(), location_id=location["id"],
        shift_date=date(2026, 8, 22), employer_employee_count=None,
    ))
    assert result.employer_employee_count is None
    assert prefetched.headcount_queries == 0
    assert "NULLIF(COUNT(*)::int, 0)" in inspect.getsource(
        schedule_break_rule_store.get_employer_employee_count
    )


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
    # § 512 fixes a deadline and no earliest; the suggester's own placement
    # floor is what keeps a break off the shift's first minute.
    assert result.rules[0].earliest_offset_minutes is None


def _extraction(rule_key, value, *, no_rule=False, citation="WAC 296-126-092"):
    return {
        "rule_key": rule_key, "rule_value": None if no_rule else value,
        "no_rule": no_rule, "citation": citation, "block_grade": False,
    }


def _wa_location():
    location = _location()
    location["state"] = "WA"
    location["city"] = "Seattle"
    location["timezone"] = "America/Los_Angeles"
    return location


def test_approved_catalog_earliest_becomes_a_break_offset():
    location = _wa_location()
    result = _run(resolve_break_rules(
        FakeConn(
            location, structured=[], state="WA",
            extractions=[
                _extraction("meal_break_after_hours", 5.0),
                _extraction("meal_break_minutes", 30.0),
                _extraction("meal_break_earliest_after_hours", 2.0),
            ],
        ),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "catalog_extraction"
    assert result.rules[0].earliest_offset_minutes == 120
    assert result.rules[0].deadline_offset_minutes == 300


def test_a_state_that_sets_no_earliest_gets_no_offset():
    location = _wa_location()
    result = _run(resolve_break_rules(
        FakeConn(
            location, structured=[], state="WA",
            extractions=[
                _extraction("meal_break_after_hours", 5.0),
                _extraction("meal_break_minutes", 30.0),
                _extraction("meal_break_earliest_after_hours", None, no_rule=True),
            ],
        ),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.rules[0].earliest_offset_minutes is None


def test_no_rule_on_the_meal_itself_yields_no_break_rule():
    """`no_rule=true` arrives as the NO_CAP sentinel, not as a number.

    Before the legacy fallback merged approved extractions, only the curated
    table reached these reads and no meal key in it is ever NO_CAP; letting the
    sentinel through to `float()` 500s every break-plan call for the location.
    """
    location = _wa_location()
    location["state"] = "TX"
    result = _run(resolve_break_rules(
        FakeConn(
            location, structured=[], state="TX",
            extractions=[
                _extraction("meal_break_after_hours", None, no_rule=True),
                _extraction("meal_break_minutes", None, no_rule=True),
            ],
        ),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.rules == ()
    assert result.source == "unmapped"


def test_no_rule_on_the_second_meal_keeps_the_first():
    location = _wa_location()
    result = _run(resolve_break_rules(
        FakeConn(
            location, structured=[], state="WA",
            extractions=[
                _extraction("meal_break_after_hours", 5.0),
                _extraction("meal_break_minutes", 30.0),
                _extraction("meal_break_earliest_after_hours", 2.0),
                _extraction("second_meal_after_hours", None, no_rule=True),
            ],
        ),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert [rule.ordinal for rule in result.rules] == [1]
    assert result.rules[0].earliest_offset_minutes == 120


def test_an_earliest_past_the_deadline_is_dropped_and_reported():
    """Two independently-approved thresholds can describe an empty window.

    Enforcing it would be a permanent deadline_conflict on every shift at the
    location with nothing on screen saying why, so the deadline (the one whose
    breach is the violation) is kept alone and an advisory carries the rest.
    """
    location = _wa_location()
    result = _run(resolve_break_rules(
        FakeConn(
            location, structured=[], state="WA",
            extractions=[
                _extraction("meal_break_after_hours", 5.0),
                _extraction("meal_break_minutes", 30.0),
                _extraction("meal_break_earliest_after_hours", 6.0),
            ],
        ),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.rules[0].earliest_offset_minutes is None
    assert result.rules[0].deadline_offset_minutes == 300
    advisory = next(
        item for item in result.advisories if item["code"] == "break_rules_inconsistent"
    )
    assert advisory["metadata"] == {
        "earliest_after_hours": 6.0, "meal_break_after_hours": 5.0,
    }


def test_an_earliest_exactly_at_the_deadline_is_also_dropped():
    location = _wa_location()
    result = _run(resolve_break_rules(
        FakeConn(
            location, structured=[], state="WA",
            extractions=[
                _extraction("meal_break_after_hours", 5.0),
                _extraction("meal_break_minutes", 30.0),
                _extraction("meal_break_earliest_after_hours", 5.0),
            ],
        ),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.rules[0].earliest_offset_minutes is None
    assert "break_rules_inconsistent" in [item["code"] for item in result.advisories]


def test_a_catalog_read_failure_is_visible_rather_than_silent():
    location = _wa_location()
    result = _run(resolve_break_rules(
        FakeConn(location, structured=[], state="WA", extractions_fail=True),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    codes = [advisory["code"] for advisory in result.advisories]
    assert "break_rules_catalog_unavailable" in codes


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
    assert [advisory["code"] for advisory in result.advisories] == ["break_rules_unmapped"]


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


def test_import_and_runtime_preserve_an_approved_empty_rule_collection():
    item = BreakRuleSetImport(
        jurisdiction_id=uuid4(), effective_from=date(2026, 1, 1),
        rules={"meal_periods": [], "rest_periods": []},
        citation="Authority", source_type="manual",
    )
    assert item.rules == {"meal_periods": [], "rest_periods": []}

    location = _location()
    conn = FakeConn(location, structured=[{
        "id": uuid4(), "rules": item.rules, "citation": "Authority", "depth": 0,
        "industry_code": None, "effective_from": date(2026, 1, 1),
        "effective_to": None, "authority_url": None, "source_type": "manual",
        "jurisdiction_id": location["jurisdiction_id"],
    }], applicability_decision=None)
    result = _run(resolve_break_rules(
        conn, company_id=uuid4(), location_id=location["id"],
        shift_date=date(2026, 8, 21),
    ))
    assert result.source == "approved"
    assert result.rules == ()
    assert result.advisories == ()
    assert conn.headcount_queries == 0
    assert conn.confirmation_context_hashes == []


def test_import_validates_clock_windows_and_employer_size_bounds():
    item = BreakRuleSetImport(
        jurisdiction_id=uuid4(), effective_from=date(2026, 1, 1),
        rules={"meal_periods": [{
            "trigger_after_minutes": 360,
            "duration_minutes": 30,
            "minimum_employees": 50,
            "shift_spans_window_start": "11:00",
            "shift_spans_window_end": "14:00",
            "window_start": "11:00",
            "window_end": "14:00",
        }]},
        citation="Authority", source_type="manual",
    )
    assert item.rules["meal_periods"][0]["minimum_employees"] == 50

    with pytest.raises(ValueError, match="supplied together"):
        BreakRuleSetImport(
            jurisdiction_id=uuid4(), effective_from=date(2026, 1, 1),
            rules={"meal_periods": [{
                "trigger_after_minutes": 360,
                "duration_minutes": 30,
                "window_start": "11:00",
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
        def __init__(self):
            self.locked = False

        def transaction(self):
            return Transaction()

        async def fetchval(self, query, *_args):
            assert "pg_advisory_xact_lock(" in query
            self.locked = True

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

    conn = Connection()
    with pytest.raises(ValueError, match="whole numbers"):
        _run(review_break_rule_set(
            conn, rule_set_id=uuid4(), decision="approved",
            actor_user_id=uuid4(),
        ))
    assert conn.locked


def test_rule_review_uses_commit_order_timestamp_for_recovery():
    source = inspect.getsource(review_break_rule_set)
    assert "lock_schedule_break_rule_guidance(conn, exclusive=True)" in source
    assert "updated_at = clock_timestamp()" in source
    assert "DELETE FROM company_schedule_break_rule_confirmations" in source
    assert "decision = 'grandfathered'" in source


def test_rule_rereview_retires_grandfathered_compatibility(monkeypatch):
    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    class Connection:
        def __init__(self):
            self.deleted = []

        def transaction(self):
            return Transaction()

        async def fetchval(self, query, *_args):
            assert "pg_advisory_xact_lock(" in query

        async def fetchrow(self, query, *args):
            if "FOR UPDATE" in query:
                return {
                    "id": args[0], "jurisdiction_id": uuid4(),
                    "rules": {"meal_periods": []}, "citation": "Authority",
                }
            assert "UPDATE schedule_break_rule_sets" in query
            return {
                "id": args[0], "review_status": args[1],
                "reviewed_by": args[2], "reviewed_at": "now",
            }

        async def execute(self, query, *args):
            self.deleted.append((query, args))

    monkeypatch.setattr(
        "app.workers.tasks.schedule_break_refresh.enqueue_schedule_break_recovery",
        lambda: None,
    )
    conn = Connection()
    rule_set_id = uuid4()
    result = _run(review_break_rule_set(
        conn, rule_set_id=rule_set_id, decision="approved", actor_user_id=uuid4(),
    ))

    assert result["review_status"] == "approved"
    assert len(conn.deleted) == 1
    assert "decision = 'grandfathered'" in conn.deleted[0][0]
    assert conn.deleted[0][1] == (rule_set_id,)


def test_applicability_decision_rechecks_context_before_upsert(monkeypatch):
    location_id = uuid4()
    company_id = uuid4()
    rule_id = uuid4()
    expected_rule = schedule_break_rule_store._rules_from_payload(
        rule_id,
        {"meal_periods": [{"trigger_after_minutes": 360, "duration_minutes": 30}]},
        "Authority",
    )[0]

    class Connection:
        def __init__(self):
            self.writes = []

        async def fetchval(self, query, *_args):
            assert "pg_advisory_xact_lock(" in query

        async def execute(self, query, *args):
            self.writes.append((query, args))

    async def fake_resolve(*_args, **_kwargs):
        return ResolvedBreakRules(
            rules=(), rule_set_ids=(rule_id,), timezone=None, industry_code="retail",
            source="confirmation_required", advisories=(),
            expected_rules=(expected_rule,), applicability_context_hash="b" * 64,
        )

    monkeypatch.setattr(schedule_break_rule_store, "resolve_break_rules", fake_resolve)
    conn = Connection()
    _run(record_break_rule_applicability_decision(
        conn, company_id=company_id, location_id=location_id,
        shift_date=date(2026, 8, 21), rule_set_id=rule_id,
        context_hash="b" * 64, decision="confirmed", actor_user_id=uuid4(),
    ))
    assert len(conn.writes) == 1
    assert "ON CONFLICT (company_id, location_id, rule_set_id, context_hash)" in conn.writes[0][0]
    assert "VALUES ($1, $2, $3, $4, $5, $6, clock_timestamp())" in conn.writes[0][0]
    assert "confirmed_at = clock_timestamp()" in conn.writes[0][0]

    with pytest.raises(LookupError, match="context changed"):
        _run(record_break_rule_applicability_decision(
            conn, company_id=company_id, location_id=location_id,
            shift_date=date(2026, 8, 21), rule_set_id=rule_id,
            context_hash="c" * 64, decision="confirmed", actor_user_id=uuid4(),
        ))
