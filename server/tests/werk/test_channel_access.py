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


# ── a private conversation with Espresso ─────────────────────────────────────

import inspect  # noqa: E402
import re  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.werk.services import channel_access  # noqa: E402
from app.werk.services.channel_access import (  # noqa: E402
    ChannelAccess,
    assert_channel_capability,
    load_channel_access,
    refuse_membership_change,
)

ASSISTANT_ON = {"matcha_work": True, "espresso_assistant": True}


def _allowed(capability=ChannelCapability.CHAT, features=None, **over):
    owner = uuid4()
    kwargs = dict(scope=ChannelScope.ASSISTANT, features=ASSISTANT_ON if features is None else features,
                  capability=capability, user_id=owner, assistant_user_id=owner)
    kwargs.update(over)
    return capability_allowed(**kwargs)


def test_assistant_scope_is_chat_only_and_owner_only():
    assert _allowed()
    for capability in (ChannelCapability.CALL, ChannelCapability.AUTOMATION, ChannelCapability.MANAGE):
        assert not _allowed(capability)
    assert not _allowed(user_id=uuid4())
    assert not _allowed(user_id=None)
    assert not _allowed(user_id=None, assistant_user_id=None)


def test_platform_admin_does_not_bypass_the_assistant_scope():
    assert not _allowed(user_id=uuid4(), is_platform_admin=True)
    for capability in (ChannelCapability.CALL, ChannelCapability.MANAGE):
        assert not _allowed(capability, is_platform_admin=True)
    # The owner, who happens to be a platform admin, still has their own conversation.
    assert _allowed(is_platform_admin=True)
    # The decision is made before the bypass, not after it.
    source = inspect.getsource(capability_allowed)
    assert source.index("ChannelScope.ASSISTANT") < source.index("if is_platform_admin")


def test_assistant_scope_needs_the_flag():
    assert not _allowed(features={"matcha_work": True})
    assert not _allowed(features={"espresso_assistant": True})
    assert not _allowed(features={})


def _access(scope, **over):
    owner = uuid4()
    base = dict(channel_id=uuid4(), company_id=uuid4(), scope=scope, features=ASSISTANT_ON,
                is_member=True, member_role="owner", is_platform_admin=False,
                user_id=owner, assistant_user_id=owner if scope is ChannelScope.ASSISTANT else None)
    base.update(over)
    return ChannelAccess(**base)


def test_a_private_conversation_refuses_every_change_to_who_is_in_it():
    with pytest.raises(HTTPException) as exc:
        refuse_membership_change(_access(ChannelScope.ASSISTANT))
    assert exc.value.status_code == 403 and "private" in exc.value.detail
    for scope in (ChannelScope.OPERATIONS, ChannelScope.PROJECT_DISCUSSION, ChannelScope.COMMUNITY):
        refuse_membership_change(_access(scope))


def test_asserting_a_capability_uses_who_is_asking():
    assert_channel_capability(_access(ChannelScope.ASSISTANT), ChannelCapability.CHAT)
    stranger = _access(ChannelScope.ASSISTANT, user_id=uuid4(), is_platform_admin=True)
    with pytest.raises(HTTPException) as exc:
        assert_channel_capability(stranger, ChannelCapability.CHAT)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_loading_access_carries_the_owner_and_an_unknown_scope_fails_closed():
    owner, channel = uuid4(), uuid4()

    class Conn:
        def __init__(self, row):
            self.row = row

        async def fetchrow(self, query, *args):
            assert "ch.assistant_user_id" in query
            return self.row

    row = {"id": channel, "company_id": uuid4(), "channel_scope": "assistant",
           "enabled_features": ASSISTANT_ON, "signup_source": "bespoke",
           "assistant_user_id": owner, "member_role": "owner", "is_member": True}
    access = await load_channel_access(Conn(row), channel_id=channel, user_id=owner, user_role="client")
    assert access.scope is ChannelScope.ASSISTANT
    assert access.user_id == owner and access.assistant_user_id == owner
    # A scope this code has never heard of is treated as the most locked-down shared one.
    future = await load_channel_access(
        Conn({**row, "channel_scope": "something_new", "assistant_user_id": None}),
        channel_id=channel, user_id=owner, user_role="client")
    assert future.scope is ChannelScope.OPERATIONS
    with pytest.raises(channel_access.ChannelAccessDenied):
        await load_channel_access(Conn(None), channel_id=channel, user_id=owner, user_role="client")


def test_every_membership_mutating_route_refuses_the_assistant_scope():
    """Walks the channel routes: anything that changes who is in a channel, or
    what the channel is, must go through `_require_shared_channel`."""
    from app.werk.routes import channels
    from tests._helpers.routes import iter_api_routes

    must_refuse = {
        ("POST", "/{channel_id}/join"), ("POST", "/{channel_id}/members"), ("PATCH", "/{channel_id}"),
        ("POST", "/{channel_id}/leave"), ("PATCH", "/{channel_id}/members/{user_id}"),
        ("DELETE", "/{channel_id}/members/{user_id}"), ("POST", "/{channel_id}/unarchive"),
        ("DELETE", "/{channel_id}"), ("POST", "/{channel_id}/transfer-ownership"),
        ("POST", "/{channel_id}/checkout"), ("POST", "/{channel_id}/cancel-subscription"),
        ("PATCH", "/{channel_id}/price"), ("PATCH", "/{channel_id}/paid-settings"),
        ("POST", "/{channel_id}/invites"), ("GET", "/{channel_id}/invites"),
        ("DELETE", "/{channel_id}/invites/{invite_id}"), ("POST", "/{channel_id}/email-invites"),
        ("POST", "/{channel_id}/tip"), ("POST", "/join-by-invite/{code}"),
    }
    seen = set()
    for route in iter_api_routes(channels.router):
        for method in route.methods or ():
            key = (method, route.path)
            if key in must_refuse:
                seen.add(key)
                source = inspect.getsource(route.endpoint)
                assert "_require_shared_channel(" in source, f"{method} {route.path} does not refuse"
    assert seen == must_refuse
    helper = inspect.getsource(channels._require_shared_channel)
    assert "refuse_membership_change(access)" in helper


def test_a_private_conversation_is_never_in_the_channel_list():
    from app.werk.routes import channels

    source = inspect.getsource(channels.list_channels)
    assert re.search(r"COALESCE\(ch\.channel_scope, 'operations'\) <> 'assistant'", source)
