"""Pure-function + source-guard tests for Tell-Us promo campaigns / QR reward
cards. No DB, no HTTP — see TELLUS_PROMO_CAMPAIGNS_PLAN.md at the repo root.
"""
import inspect
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.tellus.dependencies import require_consumer, require_paid_brand
from app.tellus.models.promo import CampaignCreate
from app.tellus.routes._shared import is_managed_object
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


class TestLocationCampaignModel:
    def test_location_campaign_requires_store_and_radius(self):
        with pytest.raises(ValueError):
            CampaignCreate(title="Nearby", reward_text="Free coffee", max_claims=10, campaign_type="location")

    def test_location_campaign_accepts_ten_mile_radius(self):
        from uuid import uuid4

        campaign = CampaignCreate(
            title="Nearby", reward_text="Free coffee", max_claims=10,
            campaign_type="location", store_id=uuid4(), radius_miles=10,
        )
        assert campaign.radius_miles == 10

    def test_location_campaign_rejects_radius_over_ten(self):
        from uuid import uuid4

        with pytest.raises(ValueError):
            CampaignCreate(
                title="Nearby", reward_text="Free coffee", max_claims=10,
                campaign_type="location", store_id=uuid4(), radius_miles=10.1,
            )


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

    def test_brand_inactive(self):
        c = self._campaign(plan_status="past_due")
        assert claim_reason(c, now=NOW) == "brand_inactive"

    def test_cancelled_takes_precedence_over_brand_inactive(self):
        c = self._campaign(status="cancelled", plan_status="past_due")
        assert claim_reason(c, now=NOW) == "cancelled"

    def test_missing_plan_status_key_defaults_active(self):
        # Callers that never joined tellus_brands (none currently do, but
        # this keeps claim_reason from exploding if one is added) must not
        # be forced into brand_inactive by a missing key.
        assert claim_reason(self._campaign(), now=NOW) == "ok"


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
        # ISO string, not a datetime — .extra feeds HTTPException(detail=...)
        # which Starlette serializes with json.dumps.
        assert err.extra["redeemed_at"] == PAST.isoformat()
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

    def test_shoutout_wrong_store_is_rejected_after_expiry_checks(self):
        from uuid import uuid4

        store_id = uuid4()
        err = map_redeem_failure(
            {
                "status": "issued", "campaign_status": "active", "expires_at": FUTURE,
                "campaign_type": "shoutout", "store_id": store_id,
            },
            now=NOW, scanner_store_id=uuid4(),
        )
        assert err.http_status == 409
        assert err.code == "wrong_store"

    def test_extra_is_json_serializable(self):
        """The routes splat .extra into HTTPException(detail=...) and Starlette
        serializes that with json.dumps, NOT jsonable_encoder — so a raw
        datetime in here turns a 409 into a 500."""
        card = {
            "status": "redeemed", "campaign_status": "active",
            "redeemed_at": PAST, "redeemed_store_name": "Downtown", "expires_at": FUTURE,
        }
        err = map_redeem_failure(card, now=NOW)
        json.dumps({"code": err.code, "message": err.message, **err.extra})

    def test_redeemed_without_timestamp_is_none(self):
        card = {
            "status": "redeemed", "campaign_status": "active",
            "redeemed_at": None, "redeemed_store_name": None, "expires_at": FUTURE,
        }
        assert map_redeem_failure(card, now=NOW).extra["redeemed_at"] is None


class TestIsManagedObject:
    """is_managed_object gates every storage delete_file call in the tellus
    routes — a substring match would hand third-party URLs to the deleter."""

    def test_cloudfront_url_under_prefix(self):
        assert is_managed_object("https://cdn.example.net/tellus/promo/b/c/flyer.png", "/tellus/promo/")

    def test_relative_legacy_path(self):
        assert is_managed_object("tellus/promo/b/c/flyer.png", "/tellus/promo/")

    def test_third_party_url_mentioning_prefix_is_not_ours(self):
        assert not is_managed_object(
            "https://elsewhere.example/proxy?src=/tellus/promo/b/c/flyer.png", "/tellus/promo/"
        )

    def test_wrong_prefix(self):
        assert not is_managed_object("https://cdn.example.net/tellus/logos/b/logo.png", "/tellus/promo/")

    def test_none_and_empty(self):
        assert not is_managed_object(None, "/tellus/promo/")
        assert not is_managed_object("", "/tellus/promo/")


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
        assert "c.campaign_type <> 'shoutout' OR c.store_id IS NULL OR c.store_id = $2" in src

    def test_no_points_economy_writes(self):
        src = _all_function_source(promo_service)
        assert "tellus_points_ledger" not in src
        assert "tellus_points_balances" not in src

    def test_cancel_never_decrements_claim_count(self):
        src = inspect.getsource(promo_service.cancel_campaign)
        assert "claim_count -" not in src
        assert "claim_count - " not in src

    def test_location_claim_is_checked_before_card_insert(self):
        src = inspect.getsource(promo_service.claim_card)
        assert src.index("_location_claim_allowed") < src.index("INSERT INTO tellus_promo_cards")

    def test_location_push_is_single_send_and_radius_scoped(self):
        src = inspect.getsource(promo_service.push_campaign)
        assert "push_sent_at" in src
        assert "location_updated_at" in src
        assert "DISTINCT ON (dt.token)" in src
        assert "MILES_TO_KM" in src


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


class TestDesignJsonSourceGuards:
    """Pins the fix for the asyncpg-has-no-JSON-codec trap (see
    routes/admin/_shared.py:decode_audit_rows for the sibling bug this
    mirrors) — a raw dict bound to a jsonb param 500s, and an un-decoded
    jsonb read hands the frontend a string instead of an object."""

    def test_save_design_casts_to_jsonb_and_never_binds_a_dict(self):
        src = inspect.getsource(promo_service.save_design)
        assert "$3::jsonb" in src
        assert "design_json_text" in src

    def test_get_campaign_design_decodes_json(self):
        src = inspect.getsource(promo_service.get_campaign_design)
        assert "json.loads" in src

    def test_route_serializes_before_calling_save_design(self):
        from app.tellus.routes import promo as promo_routes

        src = inspect.getsource(promo_routes.put_campaign_design)
        assert "json.dumps(body.design_json)" in src
        assert ".encode()" in src  # byte-length check, not char-length


class TestUpdateCampaignPatchGuards:
    def test_no_coalesce_left(self):
        src = inspect.getsource(promo_service.update_campaign)
        assert "COALESCE($" not in src

    def test_uses_model_fields_set(self):
        src = inspect.getsource(promo_service.update_campaign)
        assert "model_fields_set" in src

    def test_update_excludes_cancelled_campaigns(self):
        src = inspect.getsource(promo_service.update_campaign)
        assert "status <> 'cancelled'" in src

    def test_patch_columns_subset_of_model_fields(self):
        from app.tellus.models.promo import CampaignPatch

        assert set(promo_service._PATCH_COLUMNS) <= set(CampaignPatch.model_fields)


class TestRedeemCardNoExtraStoreQuery:
    def test_redeem_card_reuses_scanner_store_name(self):
        src = inspect.getsource(promo_service.redeem_card)
        assert "FROM tellus_stores" not in src
        assert 'scanner.get("store_name")' in src


class TestFlyerUploadOrdering:
    """Ownership must be verified before the S3 write — otherwise a 404 on a
    foreign campaign_id leaves an orphaned object in the public bucket."""

    def test_ownership_check_precedes_upload(self):
        from app.tellus.routes import promo as promo_routes

        src = inspect.getsource(promo_routes.upload_flyer)
        assert src.index("assert_campaign_owned") < src.index("storage.upload_file")

    def test_cleans_up_on_late_failure(self):
        from app.tellus.routes import promo as promo_routes

        src = inspect.getsource(promo_routes.upload_flyer)
        assert "delete_managed_object(url)" in src


class TestManagedObjectHelpersHoisted:
    def test_promo_route_has_no_private_managed_helpers(self):
        from app.tellus.routes import promo as promo_routes

        src = inspect.getsource(promo_routes)
        assert "_is_managed_flyer" not in src
        assert "_delete_flyer_object" not in src

    def test_links_route_has_no_private_managed_helpers(self):
        from app.tellus.routes import links as links_routes

        src = inspect.getsource(links_routes)
        assert "_is_managed_logo" not in src
        assert "_delete_logo_object" not in src


class TestClaimRateLimits:
    def test_per_campaign_hourly_cap_removed(self):
        from app.tellus.routes import promo_public

        src = inspect.getsource(promo_public.claim)
        assert '"tellus_promo_claim_token", 120' not in src

    def test_per_ip_limit_raised(self):
        from app.tellus.routes import promo_public

        src = inspect.getsource(promo_public.claim)
        assert '"tellus_promo_claim", 100, 3600' in src
