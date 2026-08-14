from app.werk.services.channel_access import (
    ChannelCapability,
    ChannelScope,
    capability_allowed,
)


def test_work_only_project_discussion_keeps_chat():
    assert capability_allowed(
        scope=ChannelScope.PROJECT_DISCUSSION,
        features={"matcha_work": True, "matcha_ops": False},
        capability=ChannelCapability.CHAT,
    )


def test_work_only_project_discussion_cannot_run_ops_automation():
    assert not capability_allowed(
        scope=ChannelScope.PROJECT_DISCUSSION,
        features={"matcha_work": True, "matcha_ops": False},
        capability=ChannelCapability.AUTOMATION,
    )


def test_work_only_project_discussion_cannot_start_calls():
    assert not capability_allowed(
        scope=ChannelScope.PROJECT_DISCUSSION,
        features={"matcha_work": True, "matcha_ops": False},
        capability=ChannelCapability.CALL,
    )


def test_ops_channel_requires_ops_for_chat_and_calls():
    for capability in (
        ChannelCapability.CHAT,
        ChannelCapability.CALL,
        ChannelCapability.MANAGE,
    ):
        assert not capability_allowed(
            scope=ChannelScope.OPERATIONS,
            features={"matcha_ops": False},
            capability=capability,
        )
        assert capability_allowed(
            scope=ChannelScope.OPERATIONS,
            features={"matcha_ops": True},
            capability=capability,
        )


def test_platform_admin_bypasses_scope_entitlement():
    assert capability_allowed(
        scope=ChannelScope.OPERATIONS,
        features={},
        capability=ChannelCapability.CHAT,
        is_platform_admin=True,
    )
