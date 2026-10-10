"""Model selection: the supported-model table, the mode-driven picker, and the
keyword heuristic that classifies a turn's thinking level.
"""
import logging
from app.core.services import anthropic_messages
from app.core.services.anthropic_messages import (
    CLAUDE_HAIKU,
    CLAUDE_MODELS,
    CLAUDE_SONNET,
    anthropic_configured,
)
from app.core.services.model_catalog import GEMINI_FLASH, GEMINI_FLASH_LITE
from app.core.services.platform_settings import get_matcha_work_model_mode
from app.matcha.services.matcha_work.app_surface import work_surface

logger = logging.getLogger(__name__)


FLASH = GEMINI_FLASH
FLASH_LITE = GEMINI_FLASH_LITE

# The picker's Claude entries run the same skill-engine call on Anthropic
# (`_claude.py`). They are honored only while ANTHROPIC_API_KEY is set; Sonnet
# is the premium pick and carries the same plan gate as PRO_MODEL.
SUPPORTED_MODELS = {FLASH_LITE, FLASH, CLAUDE_HAIKU, CLAUDE_SONNET}
PREMIUM_CLAUDE_MODELS = {CLAUDE_SONNET}


def is_claude_model(model: str | None) -> bool:
    return model in CLAUDE_MODELS

# Pro-preview retired from matcha-work (product decision, 2026-07-31) — the
# whole thread harness now runs a two-model fleet. PRO_MODEL kept as an alias
# to FLASH (not deleted) so the entitlement machinery in _get_model below
# stays wired for a future pro-class model.
PRO_MODEL = FLASH

# Old picker ids (still sent by un-migrated web localStorage / Espresso
# builds until they ship the two-option picker — see MODEL_OPTIONS in
# client/src/work/components/panels/constants.ts) — normalized to the new
# fleet BEFORE the SUPPORTED_MODELS check, so a stale client keeps working.
_MODEL_ALIASES = {
    "gemini-3-flash-preview": FLASH,
    "gemini-3.6-flash": FLASH,
    "gemini-3.1-flash-lite": FLASH_LITE,
    "gemini-3.1-pro-preview": FLASH,
    # Both pickers shipped "Flash Lite 3.7" with this id, which the account
    # does not serve and which was never in SUPPORTED_MODELS — so picking it
    # silently ran Flash. Stored picks and old app builds still send it.
    "gemini-3.7-flash-lite": FLASH_LITE,
}


async def _get_model(
    settings,
    model_override: str | None = None,
    company_id: str | None = None,
    user_id: str | None = None,
    *,
    gemini_only: bool = False,
) -> str:
    """Pick the model for a call, enforcing plan entitlements.

    The admin "AI models" setting for this account's chat (Matcha Work chat
    for a business, Espresso chat for a personal account — `work_surface`,
    read through `anthropic_messages.claude_override`) wins over every Gemini
    outcome: while it names a Claude model, a Gemini pick or the plan default
    runs that model instead. Both
    apps always send their stored pick (Flash unless changed), so "only when
    no pick was sent" would never fire. An explicit Claude pick is still
    honored, so a person can choose Haiku vs Sonnet; the admin's choice is not
    plan-gated, matching every other surface it routes. `gemini_only` is for
    the modes that need Gemini's own tools (payer search) and skips both.

    The pro model is a paid entitlement (Pro/Business plans) — a client-sent
    `model_override` is clamped to the plan, never trusted (previously any
    user could force the pro model via the header picker). Claude Sonnet is
    gated the same way; Claude Haiku is open to every plan (it is cheaper
    than Flash Lite). A Claude pick with no ANTHROPIC_API_KEY configured, or
    a Sonnet pick without the entitlement, falls through to the Gemini plan
    model below — never an error.
    """
    async def _pro_allowed() -> bool:
        try:
            from app.matcha.services.billing import entitlements_service
            if user_id:
                plan = await entitlements_service.resolve_plan_for_user(user_id)
                return plan in (entitlements_service.PLAN_PRO, entitlements_service.PLAN_BUSINESS)
            if company_id:
                # Legacy call sites without a user: an active personal-pro
                # subscription on the company unlocks the pro model.
                from uuid import UUID as _UUID
                from app.matcha.services.billing import billing_service
                sub = await billing_service.get_active_subscription(
                    _UUID(company_id), pack_ids=billing_service.WERK_PACK_IDS
                )
                return bool(sub and sub.get("pack_id") == entitlements_service.PRO_PACK_ID)
        except Exception:
            # Fail closed (deny pro), but log — otherwise a resolver outage
            # silently drops paid users to the free model with no signal.
            logger.warning(
                "pro-entitlement resolution failed (user=%s company=%s); denying pro model",
                user_id, company_id, exc_info=True,
            )
        return False

    model_override = _MODEL_ALIASES.get(model_override, model_override)
    admin_model = None
    if gemini_only:
        model_override = None if is_claude_model(model_override) else model_override
    else:
        # Matcha Work chat for a business account, Espresso chat for a personal one.
        admin_model = await anthropic_messages.claude_override(await work_surface(company_id, "chat"))

    if is_claude_model(model_override) and (model_override == admin_model or (
        anthropic_configured() and (model_override not in PREMIUM_CLAUDE_MODELS or await _pro_allowed())
    )):
        return model_override
    if admin_model:
        # A Gemini pick, or a Claude pick this plan can't have.
        return admin_model
    if model_override in SUPPORTED_MODELS and not is_claude_model(model_override):
        if model_override != PRO_MODEL or await _pro_allowed():
            return model_override
        # Pro override without entitlement — fall through to plan selection.

    mode = await get_matcha_work_model_mode()
    if mode == "heavy":
        return PRO_MODEL

    if await _pro_allowed():
        return PRO_MODEL

    return FLASH


async def picker_models(*, pro_allowed: bool, company_id=None) -> tuple[list[dict], str]:
    """The chat model picker for one person: `[{"id", "locked"}]` in menu
    order, plus the id it starts on. THE rule both apps render (sent as
    `entitlements.workspace.chat_models` / `default_chat_model`), so neither
    client re-derives it; `_get_model` enforces the same rule per turn and
    `test_skill_engine_claude` holds the two together.

    While the admin AI-model setting routes this account's chat (Matcha Work
    or Espresso, by `company_id`) to Claude, only Claude rows: a Gemini pick
    would run it anyway. The admin's own model is never locked; Sonnet
    otherwise needs the pro entitlement.
    """
    admin_model = await anthropic_messages.claude_override(await work_surface(company_id, "chat"))
    if admin_model:
        rows = [
            {"id": m, "locked": m in PREMIUM_CLAUDE_MODELS and not pro_allowed and m != admin_model}
            for m in (CLAUDE_HAIKU, CLAUDE_SONNET)
        ]
        return rows, admin_model
    rows = [{"id": FLASH_LITE, "locked": False}, {"id": FLASH, "locked": False}]
    if anthropic_configured():
        rows += [{"id": CLAUDE_HAIKU, "locked": False}, {"id": CLAUDE_SONNET, "locked": not pro_allowed}]
    return rows, FLASH


# ── Auto-thinking heuristic ──
# Trivial chat → no thinking (fastest). Most general questions → low. Compliance,
# payer, multi-step skills, analytical asks → high.
_HIGH_THINK_KEYWORDS = (
    "compare", "trade-off", "tradeoff", "analyze", "analysis",
    "evaluate", "design", "architect", "architecture", "strategy",
    "strategize", "diagnose", "debug", "root cause", "why does",
    "why is", "explain why", "step by step", "step-by-step", "plan",
    "outline a", "implement", "refactor", "optimi", "calculate",
    "derive", "prove", "what if", "tradeoffs", "pros and cons",
)


_TRIVIAL_PATTERNS = (
    "hi", "hey", "hello", "yo", "sup", "thanks", "thank you", "ty",
    "ok", "okay", "cool", "nice", "got it", "great",
)


def classify_thinking_level(
    user_message: str,
    current_skill: str,
    compliance_mode: bool,
    payer_mode: bool,
    node_mode: bool,
    grounded_mode: bool = False,
) -> str:
    """Return Gemini thinking level: "none", "low", or "high".

    Used to keep latency low on trivial chat while letting complex / compliance /
    multi-step skill calls actually reason. Falls back to "low" when uncertain.
    """
    if compliance_mode or payer_mode:
        return "high"
    msg = (user_message or "").strip().lower()
    if not msg:
        return "low"
    # Trivial single-token replies
    if len(msg) < 12:
        stripped = msg.rstrip("!.?")
        if stripped in _TRIVIAL_PATTERNS:
            return "none"
    # Skill threads doing real document work benefit from thinking
    if current_skill in {"offer_letter", "review", "workbook", "handbook",
                         "policy", "presentation", "project", "onboarding"}:
        return "high"
    if node_mode or grounded_mode:
        return "high"
    if any(kw in msg for kw in _HIGH_THINK_KEYWORDS):
        return "high"
    # Long, structured questions → likely worth thinking
    if len(msg) > 280 or msg.count("\n") > 2:
        return "high"
    return "low"


def resolve_turn_model(thinking_level: str, inferred_skill: str, plan_model: str) -> str:
    """Downgrade to flash-lite ONLY where no document/outbound op is
    plausible this turn — never inside a skill thread.

    `classify_thinking_level` checks its trivial-phrase set BEFORE the skill
    check, so a trivial-shaped message ("ok", "yes") inside e.g. an
    offer_letter thread still classifies thinking_level="none" even though
    "ok" there can mean "send the draft" (a real `send_draft` op). Gating
    flash-lite on `inferred_skill == "chat"` (the skill-less default from
    `_text._infer_skill_from_state`) as well as thinking_level keeps it out
    of every skill thread — flash-lite only ever sees a turn that can emit
    at most a plain chat reply, never a structured update.

    Deliberately applies even when the turn carried an explicit
    `model_override`: the web client always sends one (localStorage-defaulted
    picker — see client/src/work/pages/MatchaWorkThread/useThreadController.ts
    and .../ProjectView/useProjectView.ts), so "only downgrade when no
    override was sent" would mean "never downgrade on web". The picker sets
    the model for REAL turns; a trivial skill-less ack has no answer quality
    to protect, so it stays eligible for the cheap tier regardless of what
    the picker was set to.

    The cheap tier stays on the picked PROVIDER: a Claude pick downgrades to
    Claude Haiku, never to Gemini. Swapping providers on an "ok" would put a
    different model's voice into a thread the person explicitly moved to
    Claude, and Haiku is already cheaper than Flash Lite.
    """
    if thinking_level == "none" and inferred_skill == "chat":
        return CLAUDE_HAIKU if is_claude_model(plan_model) else FLASH_LITE
    return plan_model
