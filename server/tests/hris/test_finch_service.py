"""Unit tests for FinchHRISService normalization + pure helpers.

Covers the doc-verified field paths (2026-07):
- work location at employment.location (work_location / residence fallbacks)
- flsa_status values exempt / non_exempt / unknown (underscore matters —
  the old substring check misclassified non_exempt as exempt)
- benefit-type matching against Finch's documented enum (s125_medical,
  fsa_medical; no plain "health"/"section_125_medical" types, and hsa_* is a
  deposit, not a premium)
- employer health premium ACCUMULATES across health benefits, and only counts
  "fixed" contributions (a "percent" amount is a rate, not cents)
- provider-agnostic location normalization (Finch + Gusto shapes)

Network-touching paths (fetch_workers/fetch_company against live Finch) are
exercised via the sandbox connection flow, not here.
"""
import asyncio
from decimal import Decimal

from app.matcha.services.finch_service import (
    FinchHRISService,
    _FINCH_MOCK_EMPLOYEES,
    _is_health_benefit,
)
from app.matcha.services.hris_service import (
    GustoHRISService,
    get_hris_service,
    normalize_hris_locations,
)


def _worker(employment: dict, individual: dict | None = None) -> dict:
    return {"id": "w-1", "individual": individual or {}, "employment": employment}


class TestNormalizeWorkerLocation:
    def test_documented_location_key(self):
        norm = FinchHRISService.normalize_worker(
            _worker({"location": {"city": "Austin", "state": "TX"}})
        )
        assert norm["work_city"] == "Austin"
        assert norm["work_state"] == "TX"

    def test_work_location_fallback(self):
        norm = FinchHRISService.normalize_worker(
            _worker({"work_location": {"city": "Reno", "state": "NV"}})
        )
        assert norm["work_city"] == "Reno"
        assert norm["work_state"] == "NV"

    def test_residence_fallback(self):
        norm = FinchHRISService.normalize_worker(
            _worker({}, individual={"residence": {"city": "Boise", "state": "ID"}})
        )
        assert norm["work_state"] == "ID"

    def test_mock_dataset_uses_documented_key(self):
        # Regression: the mocks previously used work_location and never
        # exercised the real schema path.
        for record in _FINCH_MOCK_EMPLOYEES:
            assert "location" in record["employment"]
            assert "work_location" not in record["employment"]


class TestNormalizeWorkerFlsa:
    def _classify(self, flsa, unit="yearly"):
        return FinchHRISService.normalize_worker(
            _worker({"flsa_status": flsa, "income": {"amount": 100000, "unit": unit}})
        )["pay_classification"]

    def test_non_exempt_underscore_is_hourly(self):
        # THE bug: "nonexempt" in "non_exempt" is False, so this used to hit
        # the `"exempt" in flsa` branch and come back exempt.
        assert self._classify("non_exempt") == "hourly"

    def test_non_exempt_hyphen_and_spaced(self):
        assert self._classify("non-exempt") == "hourly"
        assert self._classify("Salaried Nonexempt") == "hourly"

    def test_exempt(self):
        assert self._classify("exempt") == "exempt"

    def test_unknown_falls_back_to_unit(self):
        assert self._classify("unknown", unit="hourly") == "hourly"
        assert self._classify("unknown", unit="yearly") == "exempt"

    def test_missing_flsa_falls_back_to_unit(self):
        assert self._classify(None, unit="hourly") == "hourly"
        assert self._classify(None, unit="fixed") == "exempt"

    def test_income_minor_units(self):
        norm = FinchHRISService.normalize_worker(
            _worker({"income": {"amount": 12000000, "unit": "yearly"}})
        )
        assert norm["pay_rate"] == Decimal("120000.00")


class TestIsHealthBenefit:
    def test_documented_health_types(self):
        for t in ("s125_medical", "fsa_medical"):
            assert _is_health_benefit(t), t

    def test_hsa_is_not_a_premium(self):
        # An employer HSA contribution is a deposit into the employee's account,
        # not a premium the employer keeps paying post-termination — counting it
        # would inflate the leak estimate.
        for t in ("hsa_pre", "hsa_post"):
            assert not _is_health_benefit(t), t

    def test_non_health_documented_types(self):
        for t in ("s125_dental", "s125_vision", "401k", "401k_roth", "403b",
                  "457", "simple_ira", "commuter", "fsa_dependent_care",
                  "custom_pre_tax", "custom_post_tax"):
            assert not _is_health_benefit(t), t

    def test_provider_custom_medical_variant(self):
        assert _is_health_benefit("medical_plan")

    def test_none_and_empty(self):
        assert not _is_health_benefit(None)
        assert not _is_health_benefit("")


class TestFetchBenefitFacts:
    def _run(self, benefits, enrolled, contributions):
        svc = FinchHRISService()

        async def fake_list_benefits(config, secrets):
            return benefits

        async def fake_list_enrolled(config, secrets, bid):
            return enrolled.get(bid, [])

        async def fake_individuals(config, secrets, bid):
            return contributions.get(bid, {})

        svc.list_benefits = fake_list_benefits
        svc.list_enrolled = fake_list_enrolled
        svc.get_benefit_individuals = fake_individuals
        return asyncio.run(
            svc.fetch_benefit_facts({"mode": "finch"}, {"access_token": "t"}, ["i-1", "i-2"])
        )

    def test_premium_accumulates_across_health_benefits(self):
        # s125_medical $650.00 + fsa_medical $50.00 employer contribution → $700.00,
        # not the last-write-wins $50.00 the old assignment produced.
        facts = self._run(
            benefits=[
                {"id": "b-med", "type": "s125_medical"},
                {"id": "b-fsa", "type": "fsa_medical"},
                {"id": "b-401k", "type": "401k"},
            ],
            enrolled={"b-med": ["i-1"], "b-fsa": ["i-1"], "b-401k": ["i-1", "i-2"]},
            contributions={
                "b-med": {"i-1": {"company_contribution": {"amount": 65000, "type": "fixed"}}},
                "b-fsa": {"i-1": {"company_contribution": {"amount": 5000, "type": "fixed"}}},
                "b-401k": {"i-1": {"company_contribution": {"amount": 99900, "type": "fixed"}}},
            },
        )
        assert facts["i-1"]["employer_health_premium_monthly"] == 700.0
        assert facts["i-1"]["has_benefits_enrollment"] is True
        # 401k enrollment alone is not a health-benefit fact.
        assert "i-2" not in facts

    def test_percent_contribution_is_not_a_dollar_premium(self):
        # `amount` is only minor-units when type == "fixed". A 50% contribution
        # (amount 5000) must NOT be reported as "$50.00/mo" — enrollment is still
        # a fact, the premium isn't.
        facts = self._run(
            benefits=[{"id": "b-med", "type": "s125_medical"}],
            enrolled={"b-med": ["i-1"]},
            contributions={
                "b-med": {"i-1": {"company_contribution": {"amount": 5000, "type": "percent"}}},
            },
        )
        assert facts["i-1"]["has_benefits_enrollment"] is True
        assert facts["i-1"]["employer_health_premium_monthly"] == 0.0

    def test_percent_does_not_pollute_a_fixed_premium(self):
        facts = self._run(
            benefits=[
                {"id": "b-med", "type": "s125_medical"},
                {"id": "b-fsa", "type": "fsa_medical"},
            ],
            enrolled={"b-med": ["i-1"], "b-fsa": ["i-1"]},
            contributions={
                "b-med": {"i-1": {"company_contribution": {"amount": 65000, "type": "fixed"}}},
                "b-fsa": {"i-1": {"company_contribution": {"amount": 5000, "type": "percent"}}},
            },
        )
        assert facts["i-1"]["employer_health_premium_monthly"] == 650.0

    def test_mock_mode_alternates(self):
        svc = FinchHRISService()
        facts = asyncio.run(
            svc.fetch_benefit_facts({"mode": "finch_mock"}, {}, ["a", "b"])
        )
        assert facts["a"]["has_benefits_enrollment"] is True
        assert facts["b"]["has_benefits_enrollment"] is False


class TestNormalizeHrisLocations:
    def test_finch_shape(self):
        out = normalize_hris_locations([
            {"line1": "1 Market St", "line2": "Fl 2", "city": "San Francisco",
             "state": "ca", "postal_code": "94105", "country": "us"},
        ])
        assert out == [{
            "name": "1 Market St", "line1": "1 Market St", "line2": "Fl 2",
            "city": "San Francisco", "state": "CA", "postal_code": "94105",
            "country": "US",
        }]

    def test_gusto_shape(self):
        out = normalize_hris_locations([
            {"street_1": "350 5th Ave", "city": "New York", "state": "NY",
             "zip": "10118", "active": True},
        ])
        assert out[0]["line1"] == "350 5th Ave"
        assert out[0]["postal_code"] == "10118"
        assert out[0]["state"] == "NY"

    def test_missing_fields_are_none(self):
        out = normalize_hris_locations([{"city": "Portland", "state": "OR"}])
        assert out[0]["postal_code"] is None
        assert out[0]["line1"] is None
        assert out[0]["name"] == "Portland, OR"

    def test_non_dict_and_empty(self):
        assert normalize_hris_locations(None) == []
        assert normalize_hris_locations(["nope", 3]) == []


class TestMockPipeline:
    def test_mock_workers_normalize_cleanly(self):
        for record in _FINCH_MOCK_EMPLOYEES:
            norm = FinchHRISService.normalize_worker(record)
            assert norm["email"], "mock workers must have an email or sync skips them"
            assert norm["hris_id"] == record["id"]
            assert norm["work_state"] == "CA"

    def test_mock_flsa_paths_both_exercised(self):
        classifications = {
            FinchHRISService.normalize_worker(r)["pay_classification"]
            for r in _FINCH_MOCK_EMPLOYEES
        }
        assert classifications == {"exempt", "hourly"}

    def test_mock_company_locations_normalize(self):
        svc = FinchHRISService()
        locs = asyncio.run(svc.fetch_locations({"mode": "finch_mock"}, {}))
        assert {(l["city"], l["state"]) for l in locs} == {
            ("San Francisco", "CA"), ("Los Angeles", "CA"),
        }
        assert all(l["postal_code"] for l in locs)

    def test_provider_mock_modes_route_to_the_provider_class(self):
        # get_hris_service dispatches on the connection's mode, so a plain "mock"
        # lands on the base ADP HRISService — the provider mock datasets (and the
        # provider-specific field paths they exercise) are only reachable through
        # the *_mock modes.
        assert isinstance(get_hris_service("finch_mock"), FinchHRISService)
        assert isinstance(get_hris_service("gusto_mock"), GustoHRISService)
        assert not isinstance(get_hris_service("mock"), (FinchHRISService, GustoHRISService))

    def test_gusto_mock_locations_normalize(self):
        locs = asyncio.run(GustoHRISService().fetch_locations({"mode": "gusto_mock"}, {}))
        assert {(l["city"], l["state"]) for l in locs} == {
            ("San Francisco", "CA"), ("Oakland", "CA"), ("New York", "NY"),
        }
