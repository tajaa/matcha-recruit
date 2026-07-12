"""Boot-free unit tests for the IR CAPA / analytics / ITA additions.

Covers pure logic only (no app boot, no DB): the corrective-action bullet
parser, the corrective-action overdue derivation, the ITA payload builder +
size category, and the ITA-deadline date math used by the deadline worker.

Run: cd server && ./venv/bin/python -m pytest tests/ir_incidents/test_ir_capa_analytics_ita.py -q
"""

import os
import sys
from datetime import date
from types import ModuleType

# provisioning.py raises at import time when these are unset, and importing
# copilot pulls in the whole routes package. Satisfy them with throwaway values
# (import-time guard only — no network). Same pattern as
# tests/matcha_work/test_journal_isolation.py.
for _k, _v in (
    ("GUSTO_OAUTH_CLIENT_ID", "test"),
    ("GUSTO_OAUTH_CLIENT_SECRET", "test"),
    ("GUSTO_OAUTH_REDIRECT_URI", "http://localhost/test"),
):
    os.environ.setdefault(_k, _v)

# Stub google.genai before any app imports (mirrors test_ir_incidents.py).
# Importing copilot pulls in the whole routes package, which reaches
# services/ir_voice_parser — and that module evaluates types.HarmCategory /
# HarmBlockThreshold at import time, so the stub has to carry them too.
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
types_module.SafetySetting = lambda **kw: None
types_module.Part = type("Part", (), {"from_bytes": staticmethod(lambda **kw: None)})
types_module.HarmCategory = type(
    "HarmCategory", (), {
        "HARM_CATEGORY_HARASSMENT": "harassment",
        "HARM_CATEGORY_HATE_SPEECH": "hate_speech",
        "HARM_CATEGORY_SEXUALLY_EXPLICIT": "sexually_explicit",
        "HARM_CATEGORY_DANGEROUS_CONTENT": "dangerous_content",
    },
)
types_module.HarmBlockThreshold = type("HarmBlockThreshold", (), {"BLOCK_NONE": "block_none"})
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)


# ── CAPA bullet parser (copilot recommendations → structured actions) ──────────

def test_parse_action_bullets_extracts_priority():
    from app.matcha.routes.ir_incidents.copilot import _parse_action_bullets

    field_value = (
        "Summary of the situation goes here (not a bullet)\n"
        "• Repair the guard rail (immediate priority)\n"
        "• Retrain the crew on lockout (short_term priority)\n"
        "• Add a quarterly audit (long_term priority)\n"
        "• Bullet with no tag"
    )
    parsed = _parse_action_bullets(field_value)
    assert parsed == [
        ("Repair the guard rail", "immediate"),
        ("Retrain the crew on lockout", "short_term"),
        ("Add a quarterly audit", "long_term"),
        ("Bullet with no tag", "short_term"),
    ]


def test_parse_action_bullets_ignores_non_bullets_and_blanks():
    from app.matcha.routes.ir_incidents.copilot import _parse_action_bullets

    assert _parse_action_bullets("") == []
    assert _parse_action_bullets(None) == []
    assert _parse_action_bullets("just a paragraph, no bullets") == []
    # A bullet that is only a priority tag has no description → dropped.
    assert _parse_action_bullets("• (immediate priority)") == []


# ── CAPA overdue derivation ────────────────────────────────────────────────────

def test_corrective_action_overdue_only_when_open_and_past_due():
    from app.matcha.routes.ir_incidents.capa import _is_overdue

    past = date(2020, 1, 1)
    future = date(2999, 1, 1)
    # Past due + still actionable → overdue.
    assert _is_overdue(past, "open") is True
    assert _is_overdue(past, "in_progress") is True
    # Completed / verified / cancelled are never overdue, even if past due.
    assert _is_overdue(past, "completed") is False
    assert _is_overdue(past, "verified") is False
    assert _is_overdue(past, "cancelled") is False
    # Future due date is not overdue; no due date is not overdue.
    assert _is_overdue(future, "open") is False
    assert _is_overdue(None, "open") is False


# ── ITA payload builder + size category ────────────────────────────────────────

def _fixture_establishment() -> dict:
    return {
        "location_id": "loc-1",
        "establishment_name": "North Plant",
        "company_name": "Acme Manufacturing",
        "ein": "12-3456789",
        "naics": "311111",
        "street_address": "1 Industrial Way",
        "city": "Springfield",
        "state": "IL",
        "zip_code": "62704",
        "annual_average_employees": 120,
        "total_hours_worked": 240000,
        "agg": {
            "total_cases": 3,
            "total_deaths": 0,
            "total_days_away_cases": 1,
            "total_restricted_cases": 1,
            "total_other_recordable": 1,
            "total_days_away": 10,
            "total_days_restricted": 5,
            "total_injuries": 3,
            "total_skin_disorders": 0,
            "total_respiratory": 0,
            "total_poisonings": 0,
            "total_hearing_loss": 0,
            "total_other_illnesses": 0,
        },
    }


def test_ita_size_category_bands():
    from app.matcha.services.ir_ita_submission import _ita_size_category

    assert _ita_size_category(0) == 1
    assert _ita_size_category(19) == 1
    assert _ita_size_category(20) == 2
    assert _ita_size_category(249) == 2
    assert _ita_size_category(250) == 3
    assert _ita_size_category(None) == 1


def test_build_ita_payload_matches_aggregate_numbers():
    from app.matcha.services.ir_ita_submission import build_ita_establishment_payload

    payload = build_ita_establishment_payload(_fixture_establishment(), 2025)
    est = payload["establishment"]
    summ = payload["summary"]

    assert est["ein"] == "12-3456789"
    assert est["establishment_name"] == "North Plant"
    assert est["year_filing_for"] == 2025
    assert est["size"] == 2  # 120 employees → band 2
    assert est["establishment_type"] == 1

    # Summary must mirror the 300A aggregate exactly (byte-identical to the CSV).
    assert summ["no_injuries_illnesses"] == 0  # 3 cases → not "no injuries"
    assert summ["total_dafw_cases"] == 1
    assert summ["total_djtr_cases"] == 1
    assert summ["total_other_cases"] == 1
    assert summ["total_dafw_days"] == 10
    assert summ["total_djtr_days"] == 5


def test_build_ita_payload_zero_cases_flags_no_injuries():
    from app.matcha.services.ir_ita_submission import build_ita_establishment_payload

    est = _fixture_establishment()
    est["agg"]["total_cases"] = 0
    payload = build_ita_establishment_payload(est, 2025)
    assert payload["summary"]["no_injuries_illnesses"] == 1


# ── ITA deadline math (deadline worker) ────────────────────────────────────────

def test_next_ita_deadline_rolls_to_next_year_after_march_2():
    from app.workers.tasks.ir_deadline_alerts import _next_ita_deadline

    # Before Mar 2 → this year's Mar 2.
    assert _next_ita_deadline(date(2026, 1, 15)) == date(2026, 3, 2)
    # Exactly Mar 2 → this year (inclusive).
    assert _next_ita_deadline(date(2026, 3, 2)) == date(2026, 3, 2)
    # After Mar 2 → next year's Mar 2.
    assert _next_ita_deadline(date(2026, 6, 1)) == date(2027, 3, 2)
