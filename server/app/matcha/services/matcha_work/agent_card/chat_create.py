"""`@espresso find me … to buy` in a project chat → a new agent card.

The mention becomes an ordinary agent card: created in To do with the whole
message as its details (so constraints like "ship home, not office" travel
with it), then queued exactly like a card made on the board. It moves To do →
In progress → Review on its own, and Espresso asks back in this chat when the
result is ready (`chat_flow.offer_result`).

Same gates as `POST …/tasks` with category `agent`: the company-member role
gate, the REST project-access rule, editor role, and `enqueue.preflight` (plan, monthly cap, token budget,
rate limit) BEFORE the card exists, so a refusal never leaves a dead card.

Which mentions count as errands is deterministic (`errand_request`), so a
repository question to `@espresso` keeps going to the repo agent.
"""
from __future__ import annotations

import logging
import re
from uuid import UUID

from fastapi import HTTPException

from . import chat_flow, flights
from ..project_agent.chat import post_as_espresso

logger = logging.getLogger(__name__)

_MENTION = re.compile(r"(?i)(?:(?<=^)|(?<=\s))@espresso\b")
_POLITE = r"(?:(?:hey|hi|ok|okay)\s+)?(?:please\s+|pls\s+|can you\s+|could you\s+|would you\s+)?"
_ERRAND_START = re.compile(
    rf"^{_POLITE}(?:find|buy|order|purchase|shop|get me|look for|search for|hunt for|track down|"
    r"compare|research|recommend|source|pick out|what(?:'s| is) the best|which is the best)\b",
    re.I,
)
# In a repo-connected project "find …", "compare …" or "what's the best …"
# can be a code question, so an errand there also needs a word that means
# spending money. Deliberately narrow: "order", "review", "best" and "deal"
# are everyday code words ("find where the order total is computed"). An
# unmistakable trip counts too (`flights.is_trip`: "flights to Denver",
# "airfare", "one-way tickets"), never a bare "flight" or "round-trip": this
# codebase has flight search code, an HR "flight risk" feature and JSON
# round-trip tests.
_SHOPPING = re.compile(
    r"\b(?:buy|buying|purchase|shop|shopping|for sale|price|prices|priced|cheap|cheaper|cheapest|"
    r"affordable|online|in stock|amazon|order me|ship(?:ped|ping)? (?:to|home)|deliver(?:ed|y)? to)\b"
    r"|\$\s?\d",
    re.I,
)
# A question about the app itself is never an errand, repo-connected or not:
# it would spend one of the user's monthly agent runs on a web search.
_CODE_TALK = re.compile(
    r"\b(?:code|codebase|repo|repository|function|method|endpoint|module|migration|schema|"
    r"component|stack trace|pull request|commit)s?\b"
    r"|\bwhere (?:is|are|do|does|we|in)\b|\bhow (?:does|do|is|are)\b"
    r"|\b(?:is|are) (?:computed|calculated|implemented|defined|handled|stored|validated|rendered|parsed)\b"
    r"|\bour (?:\w+ ){0,2}(?:app|api|auth|backend|frontend|flows?|logic|services?|system)\b",
    re.I,
)
_MIN_WORDS = 3
_TITLE_CHARS = 120


def strip_mention(text: str) -> str:
    return _MENTION.sub("", text or "", count=1).strip()


def errand_request(text: str, *, repo_connected: bool) -> str | None:
    """The errand text when this `@espresso` message asks for something to be
    found or bought; None when it's a question for the repo agent."""
    request = " ".join(strip_mention(text).split())
    if len(request.split()) < _MIN_WORDS or not _ERRAND_START.search(request):
        return None
    spends_money = _SHOPPING.search(request) or flights.is_trip(request)
    if _CODE_TALK.search(request) or (repo_connected and not spends_money):
        return None
    return request


def card_title(request: str) -> str:
    """The first sentence, capitalized and trimmed: "find me organic sweat
    pants to buy online. ship home" → "Find me organic sweat pants to buy online"."""
    first = re.split(r"(?<=[.!?])\s+", request.strip(), maxsplit=1)[0].rstrip(" .!?")
    first = first[:1].upper() + first[1:]
    if len(first) > _TITLE_CHARS:
        first = first[: _TITLE_CHARS - 1].rsplit(" ", 1)[0] + "…"
    return first


def _actor(user):
    from app.core.models.auth import CurrentUser

    return user if isinstance(user, CurrentUser) else CurrentUser(
        id=user.id, email=getattr(user, "email", None) or "", role=user.role,
    )


def _reason(exc: HTTPException) -> str:
    """One readable sentence for a gate's refusal."""
    detail = exc.detail
    if isinstance(detail, dict):
        if detail.get("code") == "plan_required":
            return "Agent cards need the Pro plan."
        if detail.get("code") == "agent_run_limit":
            return f"You've used all {detail.get('limit')} agent runs this month."
        detail = detail.get("message") or ""
    return str(detail or "Please try again in a moment.")


async def create_card_from_chat(
    *, project_id: UUID, company_id: UUID, channel_id: UUID, user, request: str,
) -> dict | None:
    """Create and queue the agent card, and say so in the chat. Returns the
    task, or None when it was refused (the reason is posted)."""
    from app.matcha.dependencies import COMPANY_MEMBER_ROLES, get_client_company_id
    from app.matcha.services.matcha_work import project_task_service as pt_svc
    from app.matcha.services.matcha_work.project_service import resolve_project_access, role_can_edit

    from . import enqueue

    actor = _actor(user)
    if actor.role not in COMPANY_MEMBER_ROLES:
        # The REST route's role gate (`require_company_member`): brokers,
        # creators and agency users can't add cards on the board either.
        await post_as_espresso(company_id, channel_id, "Only members of this workspace can add agent cards.")
        return None
    caller_company = None if actor.role == "admin" else await get_client_company_id(actor)
    access = await resolve_project_access(project_id, actor, company_id=caller_company)
    if access is None:
        await post_as_espresso(company_id, channel_id, "I can only make cards for people on this project.")
        return None
    project, role = access
    if not role_can_edit(role):
        await post_as_espresso(company_id, channel_id, "You have read-only access to this project, so I can't add a card.")
        return None
    try:
        await enqueue.preflight(actor, company_id)
    except HTTPException as exc:
        await post_as_espresso(company_id, channel_id, f"I didn't make a card. {_reason(exc)}")
        return None

    title = card_title(request)
    task = await pt_svc.create_project_task(
        project_id=project_id,
        company_id=company_id,
        created_by=actor.id,
        title=title,
        description=request,
        board_column="todo",
        category=enqueue.AGENT_CATEGORY,
        project_title=project.get("title"),
    )
    token = chat_flow._ticket_token(task["id"], title, "todo")
    try:
        await enqueue.enqueue_card_agent(task=task, user=actor, reason="created", skip_preflight=True)
    except HTTPException as exc:
        await post_as_espresso(
            company_id, channel_id,
            f"{token}\nI made the card, but couldn't start it yet. {_reason(exc)} "
            "Use Run again on the card.",
        )
        return task
    await post_as_espresso(
        company_id, channel_id,
        f"{token}\nOn it. I added this to To do and I'm starting now. "
        "I'll check back here when I have picks.",
    )
    return task


async def handle_mention(
    *, project_id: UUID, company_id: UUID, channel_id: UUID, user, text: str, repo_connected: bool,
) -> bool:
    """Handle an `@espresso` mention if it's for the agent-card flow. Returns
    False to let the repo agent take it.

    "@espresso buy it" from someone with an open buy question answers that
    question instead of making a new card.
    """
    request = strip_mention(text)
    if chat_flow.is_buy_intent(request) or chat_flow.plain_card_choice(request):
        handled = await chat_flow.handle_chat_answer(channel_id=channel_id, user=user, content=request)
        if handled:
            return True
    errand = errand_request(text, repo_connected=repo_connected)
    if errand is None:
        return False
    try:
        await create_card_from_chat(
            project_id=project_id, company_id=company_id, channel_id=channel_id, user=user, request=errand,
        )
    except Exception:
        logger.exception("agent card from chat failed project=%s", project_id)
        await post_as_espresso(company_id, channel_id, "Something went wrong making that card. Please try again.")
    return True
