"""Pure registration and dependency guards for friends routes."""


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
