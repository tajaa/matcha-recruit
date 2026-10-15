"""One assistant run, from a claimed row to what is posted back in chat.

The worker task calls `run_assistant`. It reads the conversation, works out
which abilities this person has in this conversation right now, builds the
policy context from the person's own words, runs the loop, and turns the
outcome into a message: the answer, a question, or a confirmation card.

Everything here is pool-free (`connection_or_direct`): it runs in Celery.
"""
from __future__ import annotations

import logging
import os
from types import SimpleNamespace
from uuid import UUID

from app.database import connection_or_direct, decode_jsonb
from app.matcha.services.huume.claude_client import get_claude_client
from app.matcha.services.huume.luna_client import get_luna_client

from .. import calendar_service, apple_calendar_service
from ..agent_card import agent as card_agent
from ..agent_card import images
from ..project_agent import store
from ..project_agent.chat import broadcast_espresso_message, persist_espresso_message
from . import (
    catalog, chat_progress, conversation, grants, history, inputs, models, policy, prompts, result, runner,
)
from .ask import ASK_USER
from .context import FrozenAction, RunContext, RunLimits

logger = logging.getLogger(__name__)

USAGE_FEATURE = "matcha.espresso.assistant"
RESULT_METADATA_KIND = "agent_result"
RECEIPT_METADATA_KIND = "agent_receipt"
COMMIT_MODE_ENV = "ASSISTANT_COMMIT_MODE"
_PHOTO_SECONDS = 45.0
# Room for a booking: the browser alone may take close to three minutes.
LIMITS = RunLimits(max_model_calls=10, wall_seconds=330.0)
FAILED = "I couldn't finish that. {reason}"


def commit_mode(ability_key: str | None = None) -> str:
    """Calendar consent is sufficient by default. An explicit server mode
    still overrides it; other outward abilities keep their preview default."""
    configured = os.getenv(COMMIT_MODE_ENV)
    if configured is None and ability_key == "calendar":
        return "live"
    return "live" if (configured or "").strip() == "live" else "dry_run"


async def load_counts(conn, user_id: UUID, abilities) -> dict[tuple[str, int], int]:
    """How many actions each commit tool has already taken for this person in
    each of its ceiling windows. A claimed or unknown action counts: it may
    have happened."""
    counts: dict[tuple[str, int], int] = {}
    for ability in abilities:
        for tool in ability.tools:
            for _limit, window in tool.ceilings:
                counts[(tool.name, window)] = await store.count_commits(conn, user_id, tool.name, window)
    return counts


async def _own_addresses(conn, user_id: UUID, gmail) -> frozenset[str]:
    own = set()
    email = await conn.fetchval("SELECT email FROM users WHERE id = $1", user_id)
    normalized = policy.normalize_address(email or "")
    if normalized:
        own.add(normalized)
    if gmail is not None and gmail.is_configured:
        try:
            status = await gmail.get_status()
            connected = policy.normalize_address(status.get("email") or "")
            if connected:
                own.add(connected)
        except Exception:
            logger.info("could not read the connected Gmail address", exc_info=True)
    return frozenset(own)


async def _post(run: dict, content: str, metadata: dict | None = None) -> None:
    async with connection_or_direct() as conn:
        message = await persist_espresso_message(
            conn, run["company_id"], run["channel_id"], content, metadata=metadata,
        )
    await broadcast_espresso_message(message)


def receipt_text(receipt: dict) -> str:
    title = receipt.get("title") or "Done"
    status = receipt.get("status")
    lead = {
        "done": "Done", "dry_run": "Dry run (nothing was sent)", "unknown": "Outcome unknown",
        "failed": "Did not go through", "handoff": "Over to you",
    }.get(status, "Done")
    return f"{lead}: {title}"[:400]


def receipt_view(receipt: dict) -> dict:
    link = receipt.get("link")
    if not (isinstance(link, dict) and str(link.get("url") or "").startswith("https://")):
        link = None
    return {
        "action": receipt.get("action"),
        "title": str(receipt.get("title") or "")[:160],
        "status": receipt.get("status") or "done",
        "lines": [
            {"label": str(l.get("label"))[:40], "value": str(l.get("value"))[:600], "mono": bool(l.get("mono"))}
            for l in (receipt.get("lines") or [])[:8] if isinstance(l, dict)
        ],
        "link": link,
        "note": (str(receipt["note"])[:300] if receipt.get("note") else None),
    }


async def run_assistant(run: dict, *, stats: dict | None = None) -> runner.RunOutcome:
    """Run one claimed `assistant` row and post what came of it."""
    stats = stats if stats is not None else {}
    run_id, user_id, channel_id = run["id"], run["requested_by"], run["channel_id"]
    surface = run["surface"]
    progress = chat_progress.ChatProgress(channel_id=channel_id, run_id=run_id)

    from ..gmail_service import GmailService

    gmail = GmailService(user_id)
    async with connection_or_direct() as conn:
        private = surface == "assistant" and await conversation.is_private_conversation(
            conn, channel_id=channel_id, user_id=user_id,
        )
        active = await grants.load_grants(conn, user_id) if private else {}
        if active:
            await gmail.load_token()
        apple = await apple_calendar_service.connection(user_id) if "calendar" in active else None
        scopes = gmail.granted_scopes | ({apple_calendar_service.SCOPE} if apple_calendar_service.configured(apple) else set())
        situation = catalog.Situation(
            private=private, grants=active,
            google_connected=gmail.is_configured, granted_scopes=frozenset(scopes),
            # The worker's claim query carries who asked (role, email).
            allowed=catalog.allowances_for(SimpleNamespace(
                role=run.get("requester_role"), email=run.get("requester_email"),
            )),
        )
        everything = catalog.build_catalog(
            fetch_page=lambda url: card_agent.fetch_page_tool(url), gmail=gmail,
        )
        abilities = catalog.abilities_for(everything, situation)
        replay, own_texts = await history.build_history(
            conn, channel_id=channel_id, requester_id=user_id,
            trigger_message_id=run["trigger_message_id"],
        )
        if run["prompt"] not in own_texts:
            own_texts = (*own_texts, run["prompt"])
        # Files the person gave Espresso: those on this message (and any sent
        # on their own just before), plus the list of earlier ones. Never
        # grounding for an outward action: a file is data, like a page.
        run_files = (
            await inputs.for_run(
                conn, user_id=user_id, channel_id=channel_id,
                trigger_message_id=run["trigger_message_id"], run_id=run_id,
            )
            if private else inputs.RunFiles()
        )
        # Links earlier runs here already verified: a follow-up ("send me
        # those links") may cite them again without re-finding them.
        earlier = await history.earlier_links(conn, channel_id=channel_id, exclude_run=run_id)
        counts = await load_counts(conn, user_id, abilities)
        timezone_name = await calendar_service.get_timezone(user_id, conn)
        own = await _own_addresses(conn, user_id, gmail if active else None)
        frozen = None
        if run.get("resume_prompt_id"):
            payload = decode_jsonb(await conn.fetchval(
                """SELECT payload FROM mw_agent_card_prompts
                   WHERE id = $1 AND owner_user_id = $2 AND kind = 'confirm_action'
                     AND status = 'answered' AND answer = 'yes'""",
                run["resume_prompt_id"], user_id,
            ), None)
            if not payload:
                raise runner.AgentRunError("That confirmation is no longer valid.")
            frozen = FrozenAction.from_payload(payload)

    async def on_receipt(receipt: dict) -> None:
        await _post(run, receipt_text(receipt), {
            "kind": RECEIPT_METADATA_KIND, "run_id": str(run_id),
            "action_receipt": receipt_view(receipt),
        })

    # Settled at enqueue (`models.resolve`): the person's pick from the menu,
    # else the admin "AI models" setting, else Luna. A model this server no
    # longer offers (the Anthropic key was removed since) runs the default.
    model = run.get("model") or ""
    if model not in models.offered():
        model = await models.default_model()
        await store.set_run_model(run_id, model)
    claude_model = model if models.is_claude(model) else None
    ctx = RunContext(
        run_id=run_id, user_id=user_id, company_id=run["company_id"],
        role=run.get("requester_role") or "client", surface=surface, ask=run["prompt"],
        storage_prefix=f"matcha-work/{run['company_id']}/assistant/{channel_id}/{run_id}",
        progress=progress, limits=LIMITS, usage_feature=USAGE_FEATURE,
        model=model,
        channel_id=channel_id, project_id=run.get("project_id"),
        policy=policy.PolicyContext(
            surface=surface, private_conversation=private, counts=counts,
            # What the person pointed at is worked out at the moment of each
            # action, from these texts and the threads the run has read by then.
            grounding=policy.Grounding(user_texts=own_texts, own_addresses=own),
        ),
        granted_scopes=situation.granted_scopes, grants=active,
        commit_mode=commit_mode(), commit_modes={a.key: commit_mode(a.key) for a in abilities}, resume=frozen, resume_prompt_id=run.get("resume_prompt_id"),
        on_receipt=on_receipt,
        # Nothing from the private conversation is stored by the provider: even
        # a run without mail or calendar replays earlier answers built from them.
        store_responses=not private and not any(a.private_only for a in abilities),
        timezone=timezone_name,
    )
    contract = runner.ResultContract(
        finish=result.finish_tool(abilities),
        normalize=lambda args, state: result.normalize(args, state, abilities),
    )
    from .prompt import build_system_prompt

    files_text, file_images = (
        await inputs.model_parts(run_files) if run_files.fresh or run_files.index else (None, [])
    )
    outcome = await runner.run_agent(
        ctx,
        client=get_claude_client() if claude_model else get_luna_client(),
        abilities=abilities,
        contract=contract,
        instructions=build_system_prompt(
            ctx, abilities, unavailable=catalog.switch_on_hints(everything, situation),
        ),
        first_input=[*replay, inputs.request_item(run["prompt"], files_text, file_images)],
        first_note="Working on it…",
        extra_tools=[ASK_USER],
        stats=stats,
        earlier_links=earlier,
    )
    await _deliver(run, ctx, outcome, progress)
    return outcome


async def _deliver(run: dict, ctx: RunContext, outcome: runner.RunOutcome,
                   progress: chat_progress.ChatProgress) -> None:
    run_id = run["id"]
    usage = dict(model_calls=outcome.model_calls, token_usage=outcome.token_usage,
                 search_calls=outcome.search_calls)
    if outcome.kind == "result":
        stored = dict(outcome.result or {})
        picks = result.picks_block(stored)
        photos = next((b for b in stored.get("blocks") or [] if b.get("type") == "photos"), None)
        image_warnings: list[str] = []
        if picks is not None or photos is not None:
            await progress.note("Collecting photos…", force=True)
            # The photo rehoster keys its storage path on two ids; a run in a
            # chat has a conversation and itself where a card has a project
            # and a task. One call, so picks and photos share one budget and
            # one deadline. A photo that cannot be rehosted is dropped, never
            # shown from the site it came from.
            image_warnings = await images.rehost_images(
                picks or {}, company_id=run["company_id"], project_id=run["channel_id"], task_id=run_id,
                total_seconds=_PHOTO_SECONDS, photos=photos["photos"] if photos is not None else None,
            )
            if photos is not None and not photos["photos"]:
                stored["blocks"] = [b for b in stored["blocks"] if b is not photos]
        stored["warnings"] = (outcome.warnings + image_warnings)[:30]
        await store.mark_run(run_id, status="done", result=stored, **usage)
        await progress.finish("done")
        await _post(run, result.text_fallback(stored), {
            "kind": RESULT_METADATA_KIND, "run_id": str(run_id),
            "result_v2": result.chat_view(stored),
        })
        return
    if outcome.kind == "question":
        question = outcome.question or {}
        await store.mark_run(run_id, status="done", result={
            "schema": result.SCHEMA_VERSION, "question": question,
        }, **usage)
        await progress.finish("done", "Waiting for your answer")
        async with connection_or_direct() as conn, conn.transaction():
            message = await prompts.ask(
                conn, run=run, kind=prompts.ASK_USER, payload=question,
                view=prompts.ask_view(question), content=question.get("question") or "",
            )
        await broadcast_espresso_message(message)
        return
    frozen = outcome.pending
    assert frozen is not None
    ungrounded = [t.value for t in (outcome.decision.ungrounded if outcome.decision else ())]
    payload = frozen.to_payload()
    await store.mark_run(run_id, status="done", result={
        "schema": result.SCHEMA_VERSION, "held": {"tool": frozen.tool, "preview": frozen.preview},
    }, **usage)
    await progress.finish("done", "Waiting for your go-ahead")
    view = prompts.confirm_view(payload, ungrounded)
    async with connection_or_direct() as conn, conn.transaction():
        message = await prompts.ask(
            conn, run=run, kind=prompts.CONFIRM_ACTION, payload=payload,
            view=view, content=f"{view['question']} {prompts.CONFIRM_HINT}",
        )
    await broadcast_espresso_message(message)


async def report_failure(run: dict, reason: str) -> None:
    """Close the progress card and say so in chat. Best-effort."""
    try:
        await chat_progress.ChatProgress(
            channel_id=run["channel_id"], run_id=run["id"],
        ).finish("failed", reason)
        await _post(run, FAILED.format(reason=reason))
    except Exception:
        logger.warning("assistant failure could not be reported run=%s", run["id"], exc_info=True)
