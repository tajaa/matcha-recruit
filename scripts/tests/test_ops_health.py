"""Focused tests for the pure availability and error-regression evaluators."""
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / "scripts" / "ops-health" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


availability = _load("availability")
regression = _load("error-regression")


def test_disk_warns_on_low_absolute_space_even_when_percent_is_low():
    result = availability.assess_disk({"mount": "/", "total_kb": str(60 * 1024**2), "available_kb": str(7 * 1024**2)})
    assert result["ok"] is False
    assert result["severity"] == "warning"


def test_disk_does_not_warn_for_current_production_volume_sizes():
    app = availability.assess_disk({"mount": "/", "total_kb": str(16 * 1024**2), "available_kb": str(7 * 1024**2)})
    db = availability.assess_disk({"mount": "/", "total_kb": str(8 * 1024**2), "available_kb": str(3 * 1024**2)})
    assert app["ok"] is True
    assert db["ok"] is True


def test_disk_marks_missing_mount_critical():
    result = availability.assess_disk({"mount": "/mnt/encdb/pgdata", "total_kb": "0", "available_kb": "0"})
    assert result["ok"] is False
    assert result["severity"] == "critical"


def test_worker_requires_container_ping_and_timer():
    result = availability.assess_worker({
        "worker": "running",
        "celery_ping": "ok",
        "timer_enabled": "enabled",
        "timer_active": "active",
        "timer_last": "n/a",
        "timer_age_seconds": "-1",
        "timer_result": "success",
    })
    assert result["ok"] is False
    assert "no recorded trigger" in result["failures"][0]


def test_worker_rejects_stale_timer_trigger():
    result = availability.assess_worker({
        "worker": "running",
        "celery_ping": "ok",
        "timer_enabled": "enabled",
        "timer_active": "active",
        "timer_last": "Tue 2026-08-25 00:00:00 UTC",
        "timer_age_seconds": "5401",
        "timer_result": "success",
    })
    assert result["ok"] is False
    assert "90 minutes ago" in result["failures"][0]


def _error(message: str, occurrences: int, *, level: str = "ERROR", error_id: str = "e1") -> dict:
    return {
        "id": error_id,
        "fingerprint": "daily-fingerprint",
        "kind": "exception",
        "level": level,
        "exception_type": "ValueError",
        "message": message,
        "traceback": 'File "/app/example.py", line 1, in fail',
        "source": "api",
        "request_path": "/api/items?token=secret",
        "occurrences": occurrences,
        "last_seen": "2026-08-25T12:00:00+00:00",
    }


def test_regression_normalizes_values_and_counts_counter_delta():
    before = [_error("Missing item 123", 2)]
    after = [_error("Missing item 456", 5)]
    result = regression.evaluate(before, after)
    assert result["total_delta"] == 3
    assert result["changes"][0]["path"] == "/api/items"
    assert result["alert"] is True


def test_regression_alerts_for_multiple_new_errors():
    after = [_error("First failure", 1, error_id="e1"), _error("Second failure", 1, error_id="e2")]
    result = regression.evaluate([], after)
    assert len(result["changes"]) == 2
    assert result["alert"] is True


def test_regression_does_not_alert_for_one_single_occurrence():
    result = regression.evaluate([], [_error("One failure", 1)])
    assert result["total_delta"] == 1
    assert result["alert"] is False


def test_regression_redacts_message_pii_and_query_values():
    result = regression.evaluate([], [_error("Failed for jane@example.com at /x?token=secret", 1)])
    assert "jane@example.com" not in result["changes"][0]["message"]
    assert "token=secret" not in result["changes"][0]["message"]


def test_regression_suppresses_redis_churn_but_keeps_real_errors():
    churn = {
        **_error("[Channels WS] Subscriber loop error (messages); restarting in 2s", 2, error_id="churn"),
        "exception_type": "ConnectionError",
        "traceback": (
            'File "/app/app/werk/routes/channels_ws.py", line 3082, in _subscriber_loop\n'
            "ConnectionError: Connection closed by server"
        ),
    }
    real_error = _error("duplicate key value violates unique constraint", 3, error_id="sql")
    result = regression.evaluate([], [churn, real_error])
    assert result["suppressed_deploy_churn"] == 1
    assert [row["error_id"] for row in result["changes"]] == ["sql"]
    assert result["alert"] is True


def test_regression_alerts_when_suppressed_churn_is_anomalous():
    churn_rows = [
        {
            **_error(
                "[Channels WS] Subscriber loop error (messages); restarting in 2s",
                1,
                error_id=f"churn-{i}",
            ),
            "exception_type": "gaierror",
            "traceback": (
                'File "/app/app/werk/routes/channels_ws.py", line 3082, in _subscriber_loop\n'
                "gaierror: Name or service not known"
            ),
        }
        for i in range(12)
    ]
    result = regression.evaluate([], churn_rows)
    assert result["suppressed_deploy_churn"] == 12
    assert result["changes"] == []
    assert result["alert"] is True
