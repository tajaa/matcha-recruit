"""Route dependency and request-shape guards for the shoutout radar."""
import pytest

from app.tellus.dependencies import require_consumer
from app.tellus.models.shoutout_offers import ShoutoutOfferRevokeIn
from app.tellus.models.shoutouts import (
    ShoutoutApproveIn, ShoutoutConfigPut, ShoutoutEnableIn, ShoutoutHandleIn, ShoutoutRejectIn, ShoutoutTestPostIn,
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
    for model in (ShoutoutConfigPut, ShoutoutEnableIn, ShoutoutHandleIn, ShoutoutRejectIn, ShoutoutApproveIn, ShoutoutTestPostIn, ShoutoutOfferRevokeIn):
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
