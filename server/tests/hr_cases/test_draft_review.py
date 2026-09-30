"""Write-up review: structure, ladder, manager redaction, AI wording pass,
and the orchestration order (a leave block skips the AI call).

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_draft_review.py -q
"""
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.services.hr_cases import draft_review as dr
from tests._helpers.routes import QueryConn

GOOD_LETTER = (
    "Jane Doe, this written warning concerns your late arrivals on September 3 and 2026-09-10. "
    "On both days you arrived more than thirty minutes after your scheduled start without notice, "
    "which left the front counter unstaffed during the morning rush and put extra load on your team. "
    "Going forward you are expected to arrive on time for every scheduled shift and to call your "
    "manager before your start time if you will be late for any reason at all. If this continues it "
    "may lead to further disciplinary action, up to and including termination of employment. "
    "Employee signature: ____________  Date: ______ (signing acknowledges receipt, not agreement)."
)


def codes(items):
    return [i["code"] for i in items]


def test_good_letter_has_no_structure_notes():
    assert dr.check_structure(GOOD_LETTER, employee_name="Jane Doe") == []


def test_structure_flags_each_missing_part():
    got = codes(dr.check_structure("Please be better.", employee_name="Jane Doe",
                                   occurrence_dates=[date(2026, 9, 3)]))
    assert got == ["missing_employee_name", "missing_date", "too_short", "missing_expectation",
                   "missing_consequence", "missing_signature_block"]


def test_structure_accepts_last_name_only():
    assert "missing_employee_name" not in codes(dr.check_structure("Ms. Doe was late.", employee_name="Jane Doe"))


def test_structure_without_known_employee_skips_name_check():
    assert "missing_employee_name" not in codes(dr.check_structure("x", employee_name=None))


@pytest.mark.parametrize("action,prior,expected", [
    ("verbal_warning", [], []),
    ("written_warning", [("verbal_warning", None)], []),
    ("final_warning", [], ["skips_step"]),
    ("final_warning", [("verbal_warning", None)], ["skips_step"]),
    ("written_warning", [("written_warning", None)], ["repeats_level"]),
    ("verbal_warning", [("final_warning", None)], ["repeats_level"]),
    ("other", [("final_warning", None)], []),
    ("pip", [("verbal_warning", None), ("other", None)], []),
])
def test_ladder(action, prior, expected):
    assert codes(dr.ladder_advisories(action, prior)) == expected


def test_for_manager_hides_leave_findings():
    review = {
        "blocks": [{"source": "compliance", "code": "protected_leave_overlap", "detail": "FMLA on 9/3"}],
        "advisories": [
            {"source": "compliance", "code": "leave_overlap_non_attendance", "detail": "sick leave 9/3"},
            {"source": "ai", "code": "ai_review", "detail": "tone"},
            {"source": "structure", "code": "missing_date", "detail": "no date"},
        ],
    }
    view = dr.for_manager(review)
    assert view["held_for_hr"] is True and "HR has been told" in view["message"]
    assert view["notes"] == [{"code": "missing_date", "detail": "no date"}]
    assert "FMLA" not in str(view) and "sick" not in str(view)
    assert dr.for_manager(None) is None
    assert dr.for_manager({"blocks": [], "advisories": []})["held_for_hr"] is False


class FakeModels:
    def __init__(self, text=None, error=None):
        self.text, self.error, self.prompts = text, error, []

    async def generate_content(self, model, contents):
        self.prompts.append(contents)
        if self.error:
            raise self.error
        return SimpleNamespace(text=self.text)


def patch_genai(monkeypatch, models):
    from app.matcha.services._shared import gemini

    monkeypatch.setattr(gemini, "_genai", lambda: SimpleNamespace(aio=SimpleNamespace(models=models)))


@pytest.mark.asyncio
async def test_ai_wording_review_parses_and_caps(monkeypatch):
    models = FakeModels(text='{"advisories": [{"detail": "Cites the injury report as misconduct."}, {"detail": ""}]}')
    patch_genai(monkeypatch, models)
    out = await dr.ai_wording_review(text="letter", action_type="written_warning", infraction_type="conduct",
                                     incident_account="account", policy_titles=["Conduct policy"])
    assert out == [{"source": "ai", "code": "ai_review", "detail": "Cites the injury report as misconduct."}]
    assert "Conduct policy" in models.prompts[0] and "account" in models.prompts[0]


@pytest.mark.asyncio
async def test_ai_wording_review_outage_is_one_advisory(monkeypatch):
    patch_genai(monkeypatch, FakeModels(error=TimeoutError()))
    out = await dr.ai_wording_review(text="x", action_type="other", infraction_type="conduct",
                                     incident_account=None, policy_titles=[])
    assert codes(out) == ["ai_review_unavailable"]


@pytest.mark.asyncio
async def test_review_draft_block_skips_ai(monkeypatch):
    from app.matcha.services.discipline import discipline_compliance

    async def gate(conn, **kw):
        return {"blocks": [{"code": "protected_leave_overlap", "detail": "barred", "statute": "CA 246.5"}],
                "advisories": []}

    async def ai(**kw):
        raise AssertionError("AI must not run on a blocked draft")
    monkeypatch.setattr(discipline_compliance, "check_discipline_compliance", gate)
    monkeypatch.setattr(dr, "ai_wording_review", ai)
    conn = QueryConn(fetch={"FROM hr_cases": []})
    review = await dr.review_draft(conn, company_id=uuid4(), employee_id=uuid4(), employee_name="Jane Doe",
                                   text=GOOD_LETTER, action_type="written_warning", infraction_type="attendance",
                                   occurrence_dates=[date(2026, 9, 3)])
    assert review["blocks"][0]["statute"] == "CA 246.5"


@pytest.mark.asyncio
async def test_review_draft_combines_layers(monkeypatch):
    from app.matcha.services.discipline import discipline_compliance

    async def gate(conn, **kw):
        return {"blocks": [], "advisories": [{"code": "retaliation_window", "detail": "complaint 30 days ago"}]}

    async def ai(**kw):
        return [{"source": "ai", "code": "ai_review", "detail": "vague"}]
    monkeypatch.setattr(discipline_compliance, "check_discipline_compliance", gate)
    monkeypatch.setattr(dr, "ai_wording_review", ai)
    conn = QueryConn(fetch={"FROM hr_cases": [{"action_type": "written_warning",
                                               "delivered_at": datetime(2026, 5, 1, tzinfo=timezone.utc)}]})
    review = await dr.review_draft(conn, company_id=uuid4(), employee_id=uuid4(), employee_name="Jane Doe",
                                   text=GOOD_LETTER, action_type="written_warning", infraction_type="attendance",
                                   occurrence_dates=[date(2026, 9, 3)], case_id=uuid4())
    assert [a["source"] for a in review["advisories"]] == ["compliance", "ladder", "ai"]
    assert review["blocks"] == []
    assert conn.args_for("FROM hr_cases")[3] is not None  # excludes the case itself
