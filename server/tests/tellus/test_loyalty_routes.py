"""Route dependency and request-shape guards for loyalty."""
import inspect

from app.tellus.dependencies import require_verified_consumer
from app.tellus.models.loyalty import LoyaltyPurchaseIn, LoyaltyVisitIn
from app.tellus.routes import loyalty, loyalty_public


def direct_calls(router):
    return {
        route.path: [dependency.call for dependency in route.dependant.dependencies]
        for route in router.routes
    }


def capability_from_dependency(dependency):
    return next(
        cell.cell_contents
        for cell in (dependency.__closure__ or ())
        if cell.cell_contents in {"rewards.manage", "redemptions.redeem"}
    )


def test_consumer_routes_require_verified_consumer():
    calls = direct_calls(loyalty.router)
    for path, dependencies in calls.items():
        if path.startswith("/me/"):
            assert require_verified_consumer in dependencies


def test_builder_routes_require_rewards_capability():
    for route in loyalty.router.routes:
        if "/businesses/" in route.path and "/stores/" not in route.path:
            dependency = route.dependant.dependencies[0].call
            assert capability_from_dependency(dependency) == "rewards.manage"


def test_counter_routes_require_redemption_capability():
    for route in loyalty.router.routes:
        if "/stores/" in route.path:
            dependency = route.dependant.dependencies[0].call
            assert capability_from_dependency(dependency) == "redemptions.redeem"


def test_public_routes_have_no_bearer_dependency():
    for route in loyalty_public.router.routes:
        assert all("require_" not in (getattr(dep.call, "__name__", "")) for dep in route.dependant.dependencies)


def test_visit_body_forbids_amount_and_purchase_requires_cents():
    assert set(LoyaltyVisitIn.model_fields) == {"member_token"}
    assert set(LoyaltyPurchaseIn.model_fields) == {"member_token", "amount_cents"}
    source = inspect.getsource(loyalty_public.scanner_visit)
    assert "amount_cents" not in source
