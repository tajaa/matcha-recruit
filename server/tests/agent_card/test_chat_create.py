from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha import dependencies
from app.matcha.services.matcha_work import project_service, project_task_service
from app.matcha.services.matcha_work.agent_card import chat_create, chat_flow, enqueue


@pytest.mark.parametrize("text, repo, expected", [
    ("@espresso find me organic sweat pants to buy online. ship home, not office.", False,
     "find me organic sweat pants to buy online. ship home, not office."),
    ("@espresso please find the best standing desk under $400", True,
     "please find the best standing desk under $400"),
    ("hey @espresso can you compare noise cancelling headphones", False,
     "hey can you compare noise cancelling headphones"),
    ("@espresso what's the best espresso grinder for home", False, "what's the best espresso grinder for home"),
    ("@espresso buy me a 6 ft braided usb-c cable", True, "buy me a 6 ft braided usb-c cable"),
    ("@espresso find the best espresso machine under $500", True, "find the best espresso machine under $500"),
    ("@espresso research standing desks, ship to Oakland", True, "research standing desks, ship to Oakland"),
    # Repo questions stay with the repo agent.
    ("@espresso how does the auth middleware work", True, None),
    ("@espresso find where we validate the webhook signature", True, None),
    # Errand verbs, but no money word: in a repo project these are code questions.
    ("@espresso compare our two auth flows", True, None),
    ("@espresso what's the best place to add caching", True, None),
    ("@espresso find where the order total is computed", True, None),
    ("@espresso recommend a review process for deals", True, None),
    # Code talk is never an errand, even with no repo connected (it would
    # spend a monthly agent run on a web search).
    ("@espresso compare our two auth flows", False, None),
    ("@espresso find the function that prices a cart", False, None),
    ("@espresso research how does the scheduler pick shifts", False, None),
    ("@espresso find it", False, None),  # too short to be an errand
    ("@espresso thanks!", False, None),
])
def test_errand_request(text, repo, expected):
    assert chat_create.errand_request(text, repo_connected=repo) == expected


@pytest.mark.parametrize("request_text, title", [
    ("find me organic sweat pants to buy online. ship home, not office.", "Find me organic sweat pants to buy online"),
    ("compare noise cancelling headphones", "Compare noise cancelling headphones"),
    ("find " + "very " * 60 + "long", None),
])
def test_card_title(request_text, title):
    out = chat_create.card_title(request_text)
    if title:
        assert out == title
    else:
        assert len(out) <= 120 and out.endswith("…")


def _user(role="individual"):
    return SimpleNamespace(id=uuid4(), role=role, email="haley@example.com", name="Haley")


@pytest.fixture
def env(monkeypatch):
    holder = {"posted": [], "role": "owner", "access": True}

    async def post(company_id, channel_id, content, **kw):
        holder["posted"].append(content)

    async def resolve(project_id, user, *, company_id):
        holder["resolved_with"] = company_id
        return ({"title": "Errands"}, holder["role"]) if holder["access"] else None

    task = {"id": str(uuid4()), "title": "t", "category": "agent", "board_column": "todo"}
    holder["create"] = AsyncMock(return_value=task)
    holder["preflight"] = AsyncMock()
    holder["enqueue"] = AsyncMock(return_value={"run_id": "r", "round": 1, "status": "queued"})
    holder["task"] = task
    monkeypatch.setattr(chat_create, "post_as_espresso", post)
    monkeypatch.setattr(project_service, "resolve_project_access", resolve)
    monkeypatch.setattr(dependencies, "get_client_company_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(project_task_service, "create_project_task", holder["create"])
    monkeypatch.setattr(enqueue, "preflight", holder["preflight"])
    monkeypatch.setattr(enqueue, "enqueue_card_agent", holder["enqueue"])
    return holder


async def _create(user=None, request="find me organic sweat pants to buy online. ship home, not office."):
    return await chat_create.create_card_from_chat(
        project_id=uuid4(), company_id=uuid4(), channel_id=uuid4(), user=user or _user(), request=request,
    )


@pytest.mark.asyncio
async def test_a_chat_errand_becomes_a_queued_agent_card_in_todo(env):
    task = await _create()
    assert task is env["task"]
    kwargs = env["create"].await_args.kwargs
    assert kwargs["category"] == "agent" and kwargs["board_column"] == "todo"
    assert kwargs["title"] == "Find me organic sweat pants to buy online"
    assert kwargs["description"] == "find me organic sweat pants to buy online. ship home, not office."
    env["preflight"].assert_awaited_once()
    assert env["enqueue"].await_args.kwargs == {
        "task": env["task"], "user": env["enqueue"].await_args.kwargs["user"],
        "reason": "created", "skip_preflight": True,
    }
    assert env["posted"][0].startswith(f"⟦ticket:{env['task']['id']}|Find me organic sweat pants to buy online|Todo⟧")
    assert "On it." in env["posted"][0]


@pytest.mark.asyncio
async def test_gates_run_before_any_card_exists(env):
    env["preflight"].side_effect = HTTPException(403, {"code": "plan_required"})
    assert await _create() is None
    env["create"].assert_not_awaited()
    assert env["posted"] == ["I didn't make a card. Agent cards need the Pro plan."]


@pytest.mark.asyncio
async def test_monthly_cap_refusal(env):
    env["preflight"].side_effect = HTTPException(429, {"code": "agent_run_limit", "limit": 40})
    await _create()
    assert env["posted"] == ["I didn't make a card. You've used all 40 agent runs this month."]


@pytest.mark.asyncio
@pytest.mark.parametrize("role, access, message", [
    ("viewer", True, "read-only access"),
    ("owner", False, "only make cards for people on this project"),
])
async def test_access_and_edit_rights_are_the_rest_rules(env, role, access, message):
    env["role"], env["access"] = role, access
    assert await _create() is None
    env["create"].assert_not_awaited()
    assert message in env["posted"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["broker", "creator", "agency", "candidate"])
async def test_only_company_member_roles_can_add_cards_from_chat(env, role):
    # The REST route's `require_company_member` gate, applied before anything else.
    assert await _create(user=_user(role)) is None
    env["create"].assert_not_awaited()
    env["preflight"].assert_not_awaited()
    assert env["posted"] == ["Only members of this workspace can add agent cards."]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", dependencies.COMPANY_MEMBER_ROLES)
async def test_company_member_roles_pass_the_role_gate(env, role):
    assert await _create(user=_user(role)) is env["task"]


@pytest.mark.asyncio
async def test_admins_resolve_access_without_a_company(env):
    await _create(user=_user("admin"))
    assert env["resolved_with"] is None


@pytest.mark.asyncio
async def test_a_queue_refusal_keeps_the_card_and_says_so(env):
    env["enqueue"].side_effect = HTTPException(503, "Couldn't start the agent right now.")
    assert await _create() is env["task"]
    assert "I made the card, but couldn't start it yet. Couldn't start the agent right now." in env["posted"][0]
    assert "Run again" in env["posted"][0]


@pytest.mark.asyncio
async def test_handle_mention_routes_errands_and_leaves_repo_questions(env, monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(chat_create, "create_card_from_chat", create)
    monkeypatch.setattr(chat_flow, "handle_chat_answer", AsyncMock(return_value=False))
    common = dict(project_id=uuid4(), company_id=uuid4(), channel_id=uuid4(), user=_user())
    assert await chat_create.handle_mention(text="@espresso find me wool socks to buy", repo_connected=False, **common)
    assert create.await_args.kwargs["request"] == "find me wool socks to buy"
    assert not await chat_create.handle_mention(text="@espresso how does login work", repo_connected=True, **common)


@pytest.mark.asyncio
async def test_espresso_buy_it_answers_an_open_purchase_question_instead_of_making_a_card(env, monkeypatch):
    create = AsyncMock()
    answer = AsyncMock(return_value=True)
    monkeypatch.setattr(chat_create, "create_card_from_chat", create)
    monkeypatch.setattr(chat_flow, "handle_chat_answer", answer)
    common = dict(project_id=uuid4(), company_id=uuid4(), channel_id=uuid4(), user=_user())
    assert await chat_create.handle_mention(text="@espresso buy it", repo_connected=False, **common)
    assert answer.await_args.kwargs["content"] == "buy it"
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_mention_reports_an_unexpected_failure(env, monkeypatch):
    monkeypatch.setattr(chat_create, "create_card_from_chat", AsyncMock(side_effect=RuntimeError("db")))
    common = dict(project_id=uuid4(), company_id=uuid4(), channel_id=uuid4(), user=_user())
    assert await chat_create.handle_mention(text="@espresso find me wool socks to buy", repo_connected=False, **common)
    assert "Something went wrong" in env["posted"][0]
