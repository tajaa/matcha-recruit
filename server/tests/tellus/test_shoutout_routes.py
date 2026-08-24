"""Route dependency and request-shape guards for the shoutout radar."""
import inspect

import pytest

from app.tellus.dependencies import require_consumer
from app.tellus.models.shoutout_offers import ShoutoutOfferRevokeIn
from app.tellus.models.shoutouts import (
    ShoutoutApproveIn, ShoutoutConfigPut, ShoutoutEnableIn, ShoutoutHandleIn, ShoutoutManualScanIn, ShoutoutRejectIn,
    ShoutoutScanResultOut, ShoutoutTestPostIn,
)
from app.tellus.routes import promo_public, shoutouts


def _dependencies(route):
    return [dependency.call for dependency in route.dependant.dependencies]


def _capability(dependency):
    return next(
        value.cell_contents
        for value in dependency.__closure__ or ()
        if value.cell_contents == "promos.manage"
    )


def test_every_brand_shoutout_route_requires_promos_manage():
    assert shoutouts.router.routes
    for route in shoutouts.router.routes:
        dependency = next(call for call in _dependencies(route) if getattr(call, "__closure__", None))
        assert _capability(dependency) == "promos.manage", route.path


def test_public_offer_previews_are_unauthenticated_and_claims_require_consumers():
    routes = {route.path: route for route in promo_public.router.routes}
    for path in ("/o/{offer_token}", "/o/code/{short_code}"):
        assert require_consumer not in _dependencies(routes[path])
    for path in ("/o/{offer_token}/claim", "/o/code/{short_code}/claim"):
        assert require_consumer in _dependencies(routes[path])


def test_shoutout_input_models_forbid_unknown_fields():
    for model in (ShoutoutConfigPut, ShoutoutEnableIn, ShoutoutHandleIn, ShoutoutManualScanIn, ShoutoutRejectIn, ShoutoutApproveIn, ShoutoutTestPostIn, ShoutoutOfferRevokeIn):
        assert model.model_config.get("extra") == "forbid"


def test_approve_requires_a_client_request_id_and_limits_overrides():
    with pytest.raises(ValueError):
        ShoutoutApproveIn()
    with pytest.raises(ValueError):
        ShoutoutApproveIn(client_request_id="not-a-uuid")
    with pytest.raises(ValueError):
        ShoutoutApproveIn(client_request_id="00000000-0000-0000-0000-000000000000", expiry_days=0)
    with pytest.raises(ValueError):
        ShoutoutApproveIn(client_request_id="00000000-0000-0000-0000-000000000000", title="x" * 121)


def test_test_post_normalizes_the_customer_handle():
    body = ShoutoutTestPostIn(
        platform="instagram", post_url="https://instagram.com/p/example", author_handle=" @Happy_Customer ", excerpt="Great post",
    )
    assert body.author_handle == "happy_customer"


def test_manual_scan_normalizes_the_handle_without_persisting_it():
    body = ShoutoutManualScanIn(platform="instagram", handle=" @OneOff_Handle ", max_results=10)
    assert body.handle == "oneoff_handle"
    with pytest.raises(ValueError):
        ShoutoutManualScanIn(platform="instagram", handle=" @ ")
    with pytest.raises(ValueError):
        ShoutoutManualScanIn(platform="instagram", handle="oneoff_handle", max_results=101)


def test_manual_scan_uses_the_grounded_scan_service():
    source = inspect.getsource(shoutouts.run_manual_scan)
    assert 'trigger="manual"' in source
    assert "force=True" in source
    assert "manual_max_results=body.max_results" in source


def test_stats_route_is_post_and_calls_the_instagram_stats_service():
    route = next(route for route in shoutouts.router.routes if route.path.endswith("/shoutouts/mentions/{mention_id}/stats"))
    assert "POST" in route.methods
    source = inspect.getsource(shoutouts.fetch_mention_stats)
    assert "instagram_stats.fetch_mention_stats" in source


def test_manual_scan_response_exposes_rejection_reasons():
    route = next(route for route in shoutouts.router.routes if route.path.endswith("/shoutouts/scan"))
    assert route.response_model is ShoutoutScanResultOut
    result = ShoutoutScanResultOut(
        new=0, duplicate=0, source_mismatch_rejected=2,
        invalid_candidates_rejected=1, below_confidence_rejected=0,
    )
    assert result.source_mismatch_rejected == 2
