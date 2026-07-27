"""Model selection: the supported-model table, the mode-driven picker, and the
keyword heuristic that classifies a turn's thinking level.
"""
import logging
from app.core.services.platform_settings import get_matcha_work_model_mode
from cachetools import TTLCache  # noqa: E402

logger = logging.getLogger(__name__)


SUPPORTED_MODELS = {
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
}


PRO_MODEL = "gemini-3.1-pro-preview"


async def _get_model(
    settings,
    model_override: str | None = None,
    company_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """Pick the Gemini model for a call, enforcing plan entitlements.

    The pro model is a paid entitlement (Pro/Business plans) — a client-sent
    `model_override` is clamped to the plan, never trusted (previously any
    user could force the pro model via the header picker).
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

    if model_override and model_override in SUPPORTED_MODELS:
        if model_override != PRO_MODEL or await _pro_allowed():
            return model_override
        # Pro override without entitlement — fall through to plan selection.

    mode = await get_matcha_work_model_mode()
    if mode == "heavy":
        return PRO_MODEL

    if await _pro_allowed():
        return PRO_MODEL

    return settings.analysis_model


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
