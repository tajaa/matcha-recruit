"""HR case lifecycle — pure.

    cd server && ./venv/bin/python -m pytest tests/hr_cases/test_stages.py -q
"""
import pytest

from app.matcha.services.hr_cases import stages


@pytest.mark.parametrize("stage,event,expected", [
    ("flagged", "start_draft", "drafting"),
    ("flagged", "draft_submitted", "hr_review"),
    ("drafting", "draft_submitted", "hr_review"),
    ("changes_requested", "draft_submitted", "hr_review"),
    ("hr_review", "approve", "approved"),
    ("hr_review", "request_changes", "changes_requested"),
    ("approved", "delivered", "delivered"),
    ("delivered", "signed_uploaded", "verifying"),
    ("needs_attention", "signed_uploaded", "verifying"),
    ("verifying", "verified", "closed"),
    ("verifying", "attention", "needs_attention"),
    ("needs_attention", "acknowledge", "closed"),
    ("hr_review", "dismiss", "dismissed"),
])
def test_allowed_transitions(stage, event, expected):
    assert stages.next_stage(stage, event) == expected


@pytest.mark.parametrize("stage,event", [
    ("flagged", "approve"),            # nothing to approve yet
    ("flagged", "delivered"),          # can't deliver before approval
    ("hr_review", "delivered"),
    ("approved", "dismiss"),           # approved letters aren't silently dropped
    ("delivered", "dismiss"),
    ("closed", "signed_uploaded"),
    ("dismissed", "draft_submitted"),
    ("verifying", "acknowledge"),
])
def test_refused_transitions(stage, event):
    with pytest.raises(stages.InvalidTransition) as exc:
        stages.next_stage(stage, event)
    assert "Can't" in str(exc.value)


def test_unknown_event():
    with pytest.raises(ValueError):
        stages.next_stage("flagged", "teleport")


def test_every_stage_has_label_and_column():
    for stage in stages.STAGES:
        assert stage in stages.STAGE_LABEL
        assert stage in stages.COLUMN_OF
    assert stages.OPEN_STAGES == set(stages.STAGES) - {"closed", "dismissed"}


def test_allowed_events_and_checklist():
    assert set(stages.allowed_events("hr_review")) == {"approve", "request_changes", "dismiss"}
    assert stages.allowed_events("closed") == []
    done = [i["done"] for i in stages.checklist("delivered")]
    assert done == [True, True, True, True, True, False, False]
    assert all(i["done"] for i in stages.checklist("closed"))
    assert [i["done"] for i in stages.checklist("dismissed")].count(True) == 1
