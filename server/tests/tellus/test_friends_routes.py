"""Pure registration and dependency guards for friends routes."""

import inspect


def test_every_friends_route_requires_verified_consumer():
    from app.tellus.dependencies import require_verified_consumer
    from app.tellus.routes.friends import router

    assert len(router.routes) > 0
    for route in router.routes:
        dependencies = [dependency.call for dependency in route.dependant.dependencies]
        assert require_verified_consumer in dependencies, f"{route.path} is not consumer-gated"


def test_friends_router_is_registered():
    from app.tellus.routes import tellus_router

    paths = {route.path for route in tellus_router.routes}
    assert "/friends/handle-available" in paths
    assert "/me/handle" in paths


def test_friend_notification_kinds_are_push_allowlisted():
    from app.tellus.routes import friends
    from app.tellus.services.push import PUSH_KINDS

    source = inspect.getsource(friends)
    for kind in ("friend_request", "friend_accepted"):
        assert kind in source
        assert kind in PUSH_KINDS
    assert "friend_added" in PUSH_KINDS


def test_friendship_service_owns_mirrors_and_ledger_idempotency():
    from app.tellus.services import friends_service

    source = inspect.getsource(friends_service.create_friendship)
    assert "ON CONFLICT DO NOTHING" in source
    assert "pair_key" in source
    assert "earn_engagement" in source
    assert "UniqueViolationError" not in source


def test_remove_friendship_deletes_both_mirrors_in_one_statement():
    from app.tellus.services import friends_service

    source = inspect.getsource(friends_service.remove_friendship)
    assert source.count("DELETE FROM tellus_friendships") == 1
    assert "account_id = $1 AND friend_account_id = $2" in source
    assert "account_id = $2 AND friend_account_id = $1" in source
