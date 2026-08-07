"""Pure-function tests for the brand publish-now guard (server/app/tellus/
routes/feedback.py:can_publish_now). No DB, no HTTP.
"""
from datetime import datetime, timedelta, timezone

from app.tellus.routes.feedback import can_publish_now

_NOW = datetime.now(timezone.utc)


def _row(**overrides):
    base = {"review_state": "held", "moderation_status": "visible", "publish_at": _NOW + timedelta(hours=10)}
    base.update(overrides)
    return base


class TestCanPublishNow:
    def test_held_and_future_is_eligible(self):
        assert can_publish_now(_row()) is None

    def test_held_and_already_past_is_rejected(self):
        err = can_publish_now(_row(publish_at=_NOW - timedelta(hours=1)))
        assert err is not None
        assert "already published" in err

    def test_no_review_state_is_rejected(self):
        err = can_publish_now(_row(review_state=None, publish_at=None))
        assert err is not None
        assert "held review" in err

    def test_withdrawn_is_rejected(self):
        err = can_publish_now(_row(review_state="withdrawn"))
        assert err is not None
        assert "held review" in err

    def test_removed_is_rejected(self):
        err = can_publish_now(_row(moderation_status="removed"))
        assert err is not None
        assert "removed" in err
