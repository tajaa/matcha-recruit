"""Regression tests for the 2026-08 compliance-routes review fixes:
F1 current_user.id (CurrentUser has no .user_id, so the old code 500'd),
F2 honest feedback_recorded (was hardcoded to `data is not None`),
F3 admin-only /calibration/stats (was reachable by any compliance client
against a table with no company_id column). No DB, no network.
"""
import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.models.auth import CurrentUser
from app.core.routes.compliance import alerts, requirements


def _run(coro):
    return asyncio.run(coro)


def _user(role="client"):
    return CurrentUser(id=uuid4(), email="reviewer@example.com", role=role)


def _patch_common(monkeypatch, company_id, record_returns=True):
    seen = {}

    async def fake_resolve(current_user, override):
        return company_id

    async def fake_record(alert_id, user_id, actual_is_change,
                           admin_notes=None, correction_reason=None, company_id=None):
        seen["user_id"] = user_id
        return record_returns

    async def fake_dismiss(alert_uuid, cid):
        return True

    monkeypatch.setattr(alerts, "resolve_company_id", fake_resolve)
    monkeypatch.setattr(alerts, "record_verification_feedback", fake_record)
    monkeypatch.setattr(alerts, "dismiss_alert", fake_dismiss)
    return seen


def test_feedback_endpoint_passes_current_user_id(monkeypatch):
    seen = _patch_common(monkeypatch, uuid4())
    user = _user()
    out = _run(alerts.record_verification_feedback_endpoint(
        alert_id=str(uuid4()),
        data=alerts.VerificationFeedbackRequest(actual_is_change=True),
        company_id=None,
        current_user=user,
    ))
    assert seen["user_id"] == user.id  # AttributeError pre-fix (no .user_id on CurrentUser)
    assert out == {"message": "Feedback recorded"}


def test_dismiss_with_body_passes_id_and_reports_service_bool(monkeypatch):
    seen = _patch_common(monkeypatch, uuid4(), record_returns=False)
    user = _user()
    out = _run(alerts.dismiss_alert_endpoint(
        alert_id=str(uuid4()),
        data=alerts.DismissAlertRequest(is_false_positive=True),
        company_id=None,
        current_user=user,
    ))
    assert seen["user_id"] == user.id  # AttributeError pre-fix
    assert out["feedback_recorded"] is False  # was hardcoded True pre-fix


def test_dismiss_without_body_skips_feedback(monkeypatch):
    seen = _patch_common(monkeypatch, uuid4())
    out = _run(alerts.dismiss_alert_endpoint(
        alert_id=str(uuid4()), data=None, company_id=None, current_user=_user(),
    ))
    assert "user_id" not in seen
    assert out["feedback_recorded"] is False


def test_calibration_stats_rejects_client():
    with pytest.raises(HTTPException) as exc:
        _run(requirements.get_calibration_stats_endpoint(
            category=None, days=30, current_user=_user("client")))
    assert exc.value.status_code == 403


def test_calibration_stats_allows_admin(monkeypatch):
    async def fake_stats(category, days):
        return {"buckets": [], "days": days, "category_filter": category}

    monkeypatch.setattr(requirements, "get_calibration_stats", fake_stats)
    out = _run(requirements.get_calibration_stats_endpoint(
        category=None, days=30, current_user=_user("admin")))
    assert out["days"] == 30
