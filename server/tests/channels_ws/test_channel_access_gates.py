import pytest

from app.werk.services.channel_access import (
    ChannelCapability,
    ChannelScope,
    capability_allowed,
    ops_automation_allowed,
)


def test_project_discussion_never_allows_ops_automation():
    assert not capability_allowed(
        scope=ChannelScope.PROJECT_DISCUSSION,
        features={"matcha_work": True, "matcha_ops": True, "ems": True},
        capability=ChannelCapability.AUTOMATION,
    )
    assert not ops_automation_allowed(
        type("Access", (), {
            "scope": ChannelScope.PROJECT_DISCUSSION,
            "features": {"matcha_ops": True, "ems": True},
        })(),
        "ems",
    )


def test_ops_automation_requires_parent_and_child():
    access = type("Access", (), {
        "scope": ChannelScope.OPERATIONS,
        "features": {"matcha_ops": True, "inventory": False},
    })()
    assert not ops_automation_allowed(access, "inventory")
    access.features["inventory"] = True
    assert ops_automation_allowed(access, "inventory")


@pytest.mark.parametrize(
    ("scope", "expected"),
    [(ChannelScope.PROJECT_DISCUSSION, False), (ChannelScope.COMMUNITY, True)],
)
def test_project_discussion_and_community_call_policy(scope, expected):
    assert capability_allowed(
        scope=scope,
        features={"matcha_work": True, "matcha_ops": False},
        capability=ChannelCapability.CALL,
    ) is expected
