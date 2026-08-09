"""One turn of the flyer design assistant.

Shaped after `cappe/services/merlin/turn.py`, including the parts that look like
overkill until they aren't:

  - A forced `"plan"` field the model fills BEFORE choosing ops. Logged, never
    returned. It is what stops "make it warmer" from becoming a layout rewrite.
  - The op shapes and rules are GENERATED from the registry, so the prompt
    cannot advertise something the validator rejects.
  - One validation-feedback retry, then a soft failure. Past the cost guard this
    function never raises: a Gemini timeout returns the original document and a
    message, it does not 500 the designer.
"""
import asyncio
import logging
from typing import Any, Optional

from google.genai import types

from ....core.services.genai_client import get_genai_client
from ....core.services.model_catalog import GEMINI_FLASH
from ....core.services.model_json import parse_model_json
from ....core.services.rate_limiter import GeminiRateLimiter
from .apply import apply_ops
from .catalog import MAX_OPS_PER_TURN, PALETTE_TOKENS, fields_text
from .layouts import LAYOUTS, LAYOUTS_BY_KEY, layouts_text
from .ops import op_rules_text, op_shapes_text, validate_document, validate_ops
from .palettes import PALETTES_BY_KEY, palettes_text

logger = logging.getLogger(__name__)

_TURN_TIMEOUT_SECONDS = 60.0
_MAX_HISTORY_MESSAGES = 20
_SERVICE = "tellus_flyer_ai"

_rate_limiter: Optional[GeminiRateLimiter] = None


def _get_rate_limiter() -> GeminiRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter


_SYSTEM_PROMPT = """You are the design assistant inside a promo-flyer editor. \
A small business owner — not a designer — is asking you to build or adjust a printed flyer whose \
whole job is to get a customer to scan its QR code and claim a reward.

You reply with ONLY a JSON object shaped exactly:

{"plan": "<2-3 sentences, written BEFORE you decide any op>", \
"message": "<one short sentence for the person, plain language>", "ops": [<op>, ...]}

"plan" is a forced thinking step, never shown to them: write it FIRST. Say what they are actually \
asking for in design terms, what the CURRENT layout and palette imply about what will look right, \
and which ops you will use and why. Then make your ops agree with your own plan — an op that \
contradicts what you just wrote is a failure, not a change of mind."""

_GENERAL_RULES: tuple[str, ...] = (
    "NEVER substitute a different change for the one you were asked to make. If you cannot do it "
    'with the ops below, return an empty "ops" array and say plainly what you can\'t do. Doing '
    "something they did not ask for is far worse than doing nothing.",
    'Your "message" must describe ONLY the ops you actually emitted. Never claim an effect you '
    "did not produce.",
    "Change only what was asked. Do not rewrite their copy, swap the palette, or restyle layers "
    "as a side effect of an unrelated request.",
    'When they say "this", "here" or "it", they mean whatever the SELECTED line below names. If '
    "nothing is selected and the target is ambiguous, ask which layer rather than guessing.",
    "Address layers ONLY by the id values given below — never by guessing at position or order.",
    f"At most {MAX_OPS_PER_TURN} ops per turn. Prefer editing a layer over deleting and recreating it.",
    'If the request is unclear or nothing needs to change, return an empty "ops" array with a '
    'clarifying "message".',
    "Output ONLY the JSON object. No markdown fences, no commentary.",
)

# Taste, as opposed to the scope/safety rules above. A flyer is read from across
# a room and then printed, which is a different set of constraints from a screen.
_DESIGN_PRINCIPLES: tuple[str, ...] = (
    f"Colours are semantic TOKENS ({', '.join(PALETTE_TOKENS)}) resolved through the flyer's "
    "palette. Prefer a token over a hex literal every time: a token stays correct when the "
    "palette changes, a hex is a guess frozen in place.",
    "The QR is the only part of the flyer a customer can act on. Never cover it, never shrink it "
    "below about a fifth of the page width, and never reduce the contrast between its colours — "
    "a code that does not scan turns the whole print run into litter.",
    "One dominant headline. A flyer is read from across a room, so a second competing large "
    "element costs more than it adds.",
    "Leave breathing room at the page edges. Text that runs to the trim looks like a mistake in "
    "print even when it renders fine on screen.",
    'For "make it look better / designed / professional", the honest answer is usually a palette '
    "swap or a whole layout, not five small nudges — reach for set_palette or apply_layout.",
)


def _rules_text() -> str:
    lines = list(_GENERAL_RULES) + op_rules_text() + list(_DESIGN_PRINCIPLES)
    return "Rules:\n" + "\n".join(f"- {r}" for r in lines)


def _selection_line(design: dict[str, Any], selection: Optional[dict[str, Any]]) -> str:
    if not selection or not selection.get("layer"):
        return "SELECTED: nothing — the whole flyer is the target."
    lid = selection["layer"]
    layer = next((l for l in design.get("layers", []) if l.get("id") == lid), None)
    if layer is None:
        return "SELECTED: nothing — the whole flyer is the target."
    bits = [f"layer {lid}", f"kind {layer.get('type')}"]
    if layer.get("type") == "text":
        bits.append(f'text "{str(layer.get("text") or "")[:80]}"')
    return "SELECTED: " + ", ".join(bits)


def _campaign_line(campaign: dict[str, Any]) -> str:
    return (
        "This flyer advertises one campaign. Its wording is the source of truth for what the "
        "reward is — use it rather than inventing an offer:\n"
        f"- title: {campaign.get('title')}\n"
        f"- reward: {campaign.get('reward_text')}\n"
        f"- description: {campaign.get('description') or '(none)'}"
    )


def _build_prompt(
    *,
    message: str,
    design: dict[str, Any],
    campaign: dict[str, Any],
    history: list[dict[str, Any]],
    selection: Optional[dict[str, Any]],
    feedback: Optional[str],
) -> str:
    import json

    parts = [
        _SYSTEM_PROMPT,
        op_shapes_text(),
        _rules_text(),
        "Layer kinds and their fields:\n" + fields_text(),
        "Palettes for set_palette:\n" + palettes_text(),
        "Layouts for apply_layout:\n" + layouts_text(),
        _campaign_line(campaign),
        "Current design (JSON):\n" + json.dumps(design, separators=(",", ":")),
        _selection_line(design, selection),
    ]

    trimmed = history[-_MAX_HISTORY_MESSAGES:]
    if trimmed:
        convo = []
        for turn in trimmed:
            if turn.get("role") == "assistant" and turn.get("ops_summary"):
                convo.append(f"assistant: {turn.get('content', '')} [{turn['ops_summary']}]")
            else:
                convo.append(f"{turn.get('role')}: {turn.get('content', '')}")
        parts.append("Conversation so far:\n" + "\n".join(convo))

    if feedback:
        parts.append(f"PREVIOUS ATTEMPT FAILED: {feedback}\nFix and return valid JSON only.")

    parts.append(f"User: {message}")
    return "\n\n".join(parts)


def _rejection_feedback(rejected: list[dict[str, Any]]) -> str:
    reasons = "; ".join(f"{r['op'].get('op', '?')}: {r['reason']}" for r in rejected[:6])
    return f"{len(rejected)} op(s) were invalid — {reasons}"


async def _generate(prompt: str) -> Any:
    """One Gemini call. `thinking_config` carries a LEVEL, never a budget — the
    3.x models reject `thinking_budget` outright with a 400."""
    client = get_genai_client()
    limiter = _get_rate_limiter()
    try:
        return await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_FLASH,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            ),
            timeout=_TURN_TIMEOUT_SECONDS,
        )
    finally:
        # Recorded even on timeout: the request was issued and billed, so
        # skipping it here lets a slow model burn quota invisibly.
        await limiter.record_call(_SERVICE, "assist")


async def run_flyer_turn(
    *,
    message: str,
    design: dict[str, Any],
    campaign: dict[str, Any],
    history: Optional[list[dict[str, Any]]] = None,
    selection: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """-> {"message", "design", "ops", "results", "rejected"}.

    Raises `RateLimitExceeded` (the caller turns it into a 429) and nothing else.
    Every other failure — timeout, unusable JSON, a Gemini error — degrades to a
    message-only response carrying the ORIGINAL document.
    """
    limiter = _get_rate_limiter()
    await limiter.check_limit(_SERVICE, "assist")  # fail fast, before any Gemini call

    history = history or []
    feedback: Optional[str] = None
    out_message = "Sorry — I couldn't work that one out. Try rephrasing it?"
    out_ops: list[dict[str, Any]] = []
    out_rejected: list[dict[str, Any]] = []
    out_results: list[dict[str, Any]] = []
    out_design = design

    for attempt in range(2):  # one attempt + one validation-feedback retry
        if attempt > 0:
            await limiter.check_limit(_SERVICE, "assist")

        prompt = _build_prompt(
            message=message, design=design, campaign=campaign,
            history=history, selection=selection, feedback=feedback,
        )
        try:
            response = await _generate(prompt)
            payload = parse_model_json(getattr(response, "text", None) or "", default=None)
            if not isinstance(payload, dict):
                raise ValueError("payload was not a JSON object")

            # The forced planning step. Logged for debuggability — when a turn's
            # ops don't match the ask, this is the explanation — but never
            # returned or persisted: it is an internal reasoning aid, and it
            # would bloat every later turn's resent history.
            plan = payload.get("plan")
            if isinstance(plan, str) and plan.strip():
                logger.info("Flyer AI plan (attempt %d/2): %s", attempt + 1, plan.strip())

            raw_message = str(payload.get("message") or "").strip() or "Done."
            raw_ops = payload.get("ops")
            valid, rejected = validate_ops(
                raw_ops if isinstance(raw_ops, list) else [], design, campaign,
            )
        except asyncio.TimeoutError:
            logger.warning("Flyer AI timed out (attempt %d/2)", attempt + 1)
            feedback = f"the previous attempt timed out after {_TURN_TIMEOUT_SECONDS}s — be more concise"
            continue
        except ValueError as exc:
            logger.warning("Flyer AI returned unusable JSON (attempt %d/2): %s", attempt + 1, exc)
            feedback = "the previous attempt was not valid JSON — return ONLY the JSON object"
            continue
        except Exception as exc:  # noqa: BLE001 — never-raises past the cost guard
            logger.warning("Flyer AI call failed (attempt %d/2): %s", attempt + 1, exc)
            break

        if raw_ops and not valid and rejected and attempt == 0:
            # Everything was rejected — worth one retry with the reasons.
            feedback = _rejection_feedback(rejected)
            out_message, out_rejected = raw_message, rejected
            continue

        out_design, out_results = apply_ops(design, valid)
        out_message, out_ops, out_rejected = raw_message, valid, rejected
        break

    return {
        "message": out_message,
        "design": out_design,
        "ops": out_ops,
        "results": out_results,
        "rejected": out_rejected,
    }


async def generate_ideas(*, campaign: dict[str, Any], count: int = 3) -> list[dict[str, Any]]:
    """Whole-flyer starting points.

    Deterministic on purpose: the layouts and palettes are hand-authored, and
    Gemini only picks the pairings and rewrites the campaign's copy to fit each
    look. A model composing a page layer-by-layer produces something that needs
    fixing before it can be printed; this produces something printable that can
    then be refined by asking.
    """
    limiter = _get_rate_limiter()
    await limiter.check_limit(_SERVICE, "ideas")

    prompt = (
        "Pick flyer directions for this promo campaign.\n\n"
        f"{_campaign_line(campaign)}\n\n"
        "Available layouts:\n" + layouts_text() + "\n\n"
        "Available palettes:\n" + palettes_text() + "\n\n"
        f"Choose {count} DIFFERENT (layout, palette) pairings that suit this particular business "
        "and offer, and for each one write a short headline and a short reward line that fit that "
        "look. Keep the meaning of the campaign's own wording — you are rephrasing for fit, not "
        "inventing a different offer. Headlines are at most 40 characters, reward lines at most "
        "60.\n\n"
        'Reply with ONLY: {"ideas":[{"layout":"<key>","palette":"<key>","title":"...",'
        '"reward":"...","blurb":"<why this suits them, one short sentence>"}]}'
    )

    try:
        response = await _generate(prompt)
        payload = parse_model_json(getattr(response, "text", None) or "", default=None)
        raw = payload.get("ideas") if isinstance(payload, dict) else None
    except Exception as exc:  # noqa: BLE001 — fall through to the deterministic set
        logger.warning("Flyer AI ideas call failed: %s", exc)
        raw = None

    picks: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            layout = LAYOUTS_BY_KEY.get(str(entry.get("layout")))
            palette = PALETTES_BY_KEY.get(str(entry.get("palette")))
            if layout is None or palette is None:
                continue
            picks.append({
                "layout": layout,
                "palette": palette,
                "title": str(entry.get("title") or campaign.get("title") or "")[:120],
                "reward": str(entry.get("reward") or campaign.get("reward_text") or "")[:200],
                "blurb": str(entry.get("blurb") or layout.blurb)[:200],
            })

    # Backfill so "Generate ideas" always returns something, even if the model
    # is down. A brand staring at an error learns nothing; three sane starting
    # points are useful with or without the copywriting.
    for layout, palette_key in zip(LAYOUTS, ("warm-paper", "midnight", "fresh-mint", "bold-citrus", "mono-ink")):
        if len(picks) >= count:
            break
        if any(p["layout"].key == layout.key for p in picks):
            continue
        picks.append({
            "layout": layout,
            "palette": PALETTES_BY_KEY[palette_key],
            "title": campaign.get("title") or "",
            "reward": campaign.get("reward_text") or "",
            "blurb": layout.blurb,
        })

    ideas: list[dict[str, Any]] = []
    for pick in picks[:count]:
        copy = {**campaign, "title": pick["title"], "reward_text": pick["reward"]}
        document = pick["layout"].build(copy, dict(pick["palette"].colors))
        # Same gate the model's own set_document output passes through — a
        # layout that drifts out of spec is dropped, not shipped.
        if validate_document(document):
            continue
        ideas.append({
            "key": f"{pick['layout'].key}-{pick['palette'].key}",
            "label": f"{pick['layout'].label} · {pick['palette'].label}",
            "blurb": pick["blurb"],
            "design": document,
        })
    return ideas
