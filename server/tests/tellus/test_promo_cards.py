"""Pure-function + source-guard tests for Tell-Us promo campaigns / QR reward
cards. No DB, no HTTP — see TELLUS_PROMO_CAMPAIGNS_PLAN.md at the repo root.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tellus.dependencies import require_consumer, require_paid_brand
from app.tellus.services import promo_service
from app.tellus.services.promo_service import (
    PromoError,
    can_campaign_transition,
    claim_reason,
    effective_card_status,
    extract_card_token,
    map_redeem_failure,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
PAST = NOW - timedelta(days=1)
FUTURE = NOW + timedelta(days=1)


class TestEffectiveCardStatus:
    def test_issued_future_stays_issued(self):
        assert effective_card_status("issued", FUTURE, now=NOW) == "issued"

    def test_issued_past_derives_expired(self):
        assert effective_card_status("issued", PAST, now=NOW) == "expired"

    def test_redeemed_past_expiry_stays_redeemed(self):
        assert effective_card_status("redeemed", PAST, now=NOW) == "redeemed"

    def test_cancelled_terminal(self):
        assert effective_card_status("cancelled", PAST, now=NOW) == "cancelled"
        assert effective_card_status("cancelled", FUTURE, now=NOW) == "cancelled"


class TestCampaignTransitions:
    def test_active_to_paused_ok(self):
        assert can_campaign_transition("active", "paused") is True

    def test_paused_to_active_ok(self):
        assert can_campaign_transition("paused", "active") is True

    def test_active_to_cancelled_forbidden(self):
        assert can_campaign_transition("active", "cancelled") is False

    def test_cancelled_to_active_forbidden(self):
        assert can_campaign_transition("cancelled", "active") is False

    def test_cancelled_to_paused_forbidden(self):
        assert can_campaign_transition("cancelled", "paused") is False


class TestClaimReason:
    def _campaign(self, **overrides):
        base = {
            "status": "active", "starts_at": None, "ends_at": None,
            "claim_count": 0, "max_claims": 50,
        }
        base.update(overrides)
        return base

    def test_ok(self):
        assert claim_reason(self._campaign(), now=NOW) == "ok"

    def test_cancelled(self):
        assert claim_reason(self._campaign(status="cancelled"), now=NOW) == "cancelled"

    def test_paused(self):
        assert claim_reason(self._campaign(status="paused"), now=NOW) == "paused"

    def test_not_started(self):
        assert claim_reason(self._campaign(starts_at=FUTURE), now=NOW) == "not_started"

    def test_ended(self):
        assert claim_reason(self._campaign(ends_at=PAST), now=NOW) == "ended"

    def test_cap_reached(self):
        assert claim_reason(self._campaign(claim_count=50, max_claims=50), now=NOW) == "cap_reached"

    def test_cancelled_takes_precedence_over_cap(self):
        c = self._campaign(status="cancelled", claim_count=50, max_claims=50)
        assert claim_reason(c, now=NOW) == "cancelled"


class TestExtractCardToken:
    def test_bare_token(self):
        assert extract_card_token("abcDEF123456") == "abcDEF123456"

    def test_full_url(self):
        assert extract_card_token("https://hey-matcha.com/tellus/card/abcDEF123456") == "abcDEF123456"

    def test_url_trailing_slash(self):
        assert extract_card_token("https://hey-matcha.com/tellus/card/abcDEF123456/") == "abcDEF123456"

    def test_bare_path(self):
        assert extract_card_token("/tellus/card/abcDEF123456") == "abcDEF123456"

    def test_garbage_raises_422(self):
        with pytest.raises(PromoError) as exc:
            extract_card_token("not a token!!")
        assert exc.value.http_status == 422

    def test_too_short_raises_422(self):
        with pytest.raises(PromoError) as exc:
            extract_card_token("short")
        assert exc.value.http_status == 422


class TestMapRedeemFailure:
    def test_none_card_404(self):
        err = map_redeem_failure(None, now=NOW)
        assert err.http_status == 404

    def test_redeemed_409_with_context(self):
        card = {
            "status": "redeemed", "campaign_status": "active",
            "redeemed_at": PAST, "redeemed_store_name": "Downtown", "expires_at": FUTURE,
        }
        err = map_redeem_failure(card, now=NOW)
        assert err.http_status == 409
        assert err.extra["redeemed_at"] == PAST
        assert err.extra["redeemed_store_name"] == "Downtown"

    def test_cancelled_card_410(self):
        card = {"status": "cancelled", "campaign_status": "active", "expires_at": FUTURE}
        assert map_redeem_failure(card, now=NOW).http_status == 410

    def test_campaign_cancelled_410(self):
        card = {"status": "issued", "campaign_status": "cancelled", "expires_at": FUTURE}
        assert map_redeem_failure(card, now=NOW).http_status == 410

    def test_expired_410(self):
        card = {"status": "issued", "campaign_status": "active", "expires_at": PAST}
        assert map_redeem_failure(card, now=NOW).http_status == 410


def _all_function_source(module) -> str:
    """Concatenated source of every function defined in `module`, excluding
    the module docstring — so a guard can assert on what the CODE does
    without tripping on the docstring's prose describing what it avoids."""
    return "\n".join(
        inspect.getsource(obj)
        for _, obj in inspect.getmembers(module, inspect.isfunction)
        if obj.__module__ == module.__name__
    )


class TestAtomicSourceGuards:
    """Pins the SQL shapes that make claim/redeem race-safe — see
    promo_service.py's module docstring for the invariants these enforce."""

    def test_claim_uses_on_conflict_do_nothing(self):
        src = inspect.getsource(promo_service.claim_card)
        assert "ON CONFLICT (campaign_id, account_id) DO NOTHING" in src

    def test_claim_never_catches_unique_violation(self):
        src = _all_function_source(promo_service)
        assert "UniqueViolationError" not in src

    def test_cap_update_single_statement(self):
        src = inspect.getsource(promo_service.claim_card)
        assert "claim_count < max_claims" in src
        assert "claim_count = claim_count + 1" in src

    def test_redeem_single_update_predicates(self):
        src = inspect.getsource(promo_service.redeem_card)
        for predicate in (
            "pc.status = 'issued'",
            "pc.expires_at > NOW()",
            "c.brand_id = $4",
            "c.status <> 'cancelled'",
        ):
            assert predicate in src

    def test_no_points_economy_writes(self):
        src = _all_function_source(promo_service)
        assert "tellus_points_ledger" not in src
        assert "tellus_points_balances" not in src

    def test_cancel_never_decrements_claim_count(self):
        src = inspect.getsource(promo_service.cancel_campaign)
        assert "claim_count -" not in src
        assert "claim_count - " not in src


class TestBrandGateSweep:
    """Mirrors test_admin_management.py::TestAdminGateSweep."""

    def test_every_campaign_and_scanner_route_requires_paid_brand(self):
        from app.tellus.routes.promo import router

        assert len(router.routes) > 0
        for route in router.routes:
            if route.path.startswith("/me/"):
                continue
            deps = [d.call for d in route.dependant.dependencies]
            assert require_paid_brand in deps, f"{route.path} is not require_paid_brand-gated"

    def test_me_routes_require_consumer(self):
        from app.tellus.routes.promo import router

        me_routes = [r for r in router.routes if r.path.startswith("/me/")]
        assert len(me_routes) == 2
        for route in me_routes:
            deps = [d.call for d in route.dependant.dependencies]
            assert require_consumer in deps, f"{route.path} is not require_consumer-gated"


class TestPublicRouterShape:
    def test_public_routes_have_no_auth_dependency(self):
        from app.tellus.routes.promo_public import router

        no_auth_paths = {"/p/{claim_token}", "/scan/{device_token}", "/scan/{device_token}/redeem"}
        for route in router.routes:
            if route.path in no_auth_paths:
                deps = [d.call for d in route.dependant.dependencies]
                assert require_consumer not in deps
                assert require_paid_brand not in deps

    def test_claim_post_requires_consumer(self):
        from app.tellus.routes.promo_public import router

        claim_route = next(r for r in router.routes if r.path == "/p/{claim_token}/claim")
        deps = [d.call for d in claim_route.dependant.dependencies]
        assert require_consumer in deps
