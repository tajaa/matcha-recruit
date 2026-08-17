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
