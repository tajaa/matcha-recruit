"""Pure-function tests for read-time redemption expiry (no DB).

effective_redemption_status derives 'expired' at read time — no cron flips
rows (same pattern as effective_review_state). These pin the derivation.
"""
from datetime import datetime, timedelta, timezone

from app.tellus.services.marketplace_service import effective_redemption_status


def _row(status="issued", expires_at=None):
    return {"status": status, "expires_at": expires_at}


PAST = datetime.now(timezone.utc) - timedelta(days=1)
FUTURE = datetime.now(timezone.utc) + timedelta(days=1)


class TestEffectiveRedemptionStatus:
    def test_issued_past_expiry_reads_expired(self):
        assert effective_redemption_status(_row(expires_at=PAST)) == "expired"

    def test_issued_future_expiry_stays_issued(self):
        assert effective_redemption_status(_row(expires_at=FUTURE)) == "issued"

    def test_issued_null_expiry_stays_issued(self):
        # Pre-migration rows with expires_at NULL never auto-expire.
        assert effective_redemption_status(_row()) == "issued"

    def test_redeemed_past_expiry_untouched(self):
        # Terminal states never flip — a claimed coffee stays claimed.
        assert effective_redemption_status(_row(status="redeemed", expires_at=PAST)) == "redeemed"

    def test_cancelled_untouched(self):
        assert effective_redemption_status(_row(status="cancelled", expires_at=PAST)) == "cancelled"
