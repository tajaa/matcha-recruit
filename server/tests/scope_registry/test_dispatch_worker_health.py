"""Dispatch routes must not report success into an empty Celery queue.

`.delay()` onto a broker with no worker listening SUCCEEDS — the task just sits
in Redis until a worker starts. So the route returns 200 and nothing ever
happens, which at the UI is indistinguishable from a real run: the operator
clicks Ingest, watches the counts never move, and concludes the pipeline is
broken. (Whether a worker is running is environment-dependent —
`dev-remote.sh` starts one as a local process, a bare `run.py` does not.)
"""
import app.core.routes.scope_registry as sr


def test_dispatch_reports_queued_when_no_worker_answers(monkeypatch):
    monkeypatch.setattr(sr, "_worker_online", lambda: False)

    res = sr._dispatch("running", "us-flsa")

    assert res.worker_online is False
    assert res.status == "queued_no_worker", (
        "a task queued to nobody must not report 'running' — that is the exact "
        "lie that makes the feature look broken"
    )
    assert res.message and "no celery worker" in res.message.lower()
    assert res.slug == "us-flsa"


def test_dispatch_reports_running_when_a_worker_answers(monkeypatch):
    monkeypatch.setattr(sr, "_worker_online", lambda: True)

    res = sr._dispatch("running", "us-flsa")

    assert res.worker_online is True
    assert res.status == "running"
    assert res.message is None  # nothing to warn about


def test_worker_online_is_false_when_the_broker_is_unreachable(monkeypatch):
    """Advisory only — a broker we cannot reach must never raise into the
    dispatch route (the task is already queued by then)."""
    class _Boom:
        def ping(self, timeout=0):
            raise ConnectionError("no broker")

    import app.workers.celery_app as ca
    monkeypatch.setattr(ca.celery_app, "control", _Boom())

    assert sr._worker_online() is False


def test_worker_online_is_false_when_nobody_replies(monkeypatch):
    class _Silent:
        def ping(self, timeout=0):
            return []  # broker reachable, no workers subscribed

    import app.workers.celery_app as ca
    monkeypatch.setattr(ca.celery_app, "control", _Silent())

    assert sr._worker_online() is False
