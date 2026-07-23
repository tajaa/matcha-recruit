"""Turns a business owner's raw image ask into a prompt Gemini responds to
well — deterministic, no LLM call of its own (unlike the descriptive text a
model would produce, this can't fail, hallucinate, or add latency/cost to a
turn that already has one real Gemini call in it).

A site owner's own words ("a nice photo for my bakery") are honest but bare —
they're the WHAT, not the HOW a professional brief would specify (framing,
lighting, finish). This module adds the HOW: known style/mood keywords expand
into short photographic-direction clauses; anything else (free text, or a
style typed instead of picked from a chip) rides through as its own clause
rather than being dropped. A baseline "no text/watermark, polished business
site" clause is always appended, since every generated image here becomes a
section image or background.

Pure string building — safe to unit test without the SDK, and reusable by
both the wizard's direct-generate path and (if it ever needs it) the agent
tool's prompt guidance.
"""
from .merlin_catalog import AI_IMAGE_PROMPT_MAX

# Keyed on the wizard's own chip labels (MerlinPanel.tsx WIZARD_STYLES /
# WIZARD_MOODS) so a chip pick maps straight to a clause. Free text (a style
# the user typed instead of clicking) falls through to the "unknown" branches
# below rather than needing a matching entry here.
_STYLE_CLAUSES = {
    "photorealistic": "professional photography, shot on a full-frame camera, natural depth of field, sharp focus",
    "illustration": "clean vector-style illustration, flat modern design, balanced color palette",
    "3d render": "polished 3D render, soft studio lighting, realistic materials and shadows",
    "minimalist": "minimalist composition, generous negative space, restrained color palette",
    "cinematic": "cinematic photography, dramatic lighting, shallow depth of field, film-like color grade",
    "watercolor": "watercolor painting, soft edges, gentle color bleed, textured paper",
}
_MOOD_CLAUSES = {
    "bright & airy": "bright and airy, soft natural light, light and open feel",
    "warm": "warm tones, inviting golden light, cozy atmosphere",
    "moody": "moody atmosphere, low-key lighting, rich shadows",
    "golden hour": "golden hour lighting, warm low sun, long soft shadows",
    "studio": "clean studio lighting, neutral backdrop, even exposure",
}
# "You decide" / omitted — let the model make an appropriate call rather than
# forcing a specific direction; still an explicit instruction, not silence.
_STYLE_DEFAULT = "a style that fits a professional business website"
_MOOD_DEFAULT = "a mood and lighting that fits a professional business website"
_BASELINE = (
    "high detail, professional composition, no text, no watermarks, "
    "no logos, suited to a polished business website"
)


def _clause(raw: str | None, table: dict[str, str], default: str) -> str:
    if raw is None:
        return default
    text = raw.strip()
    if not text or text.lower() == "you decide":
        return default
    return table.get(text.lower(), text)


def build_image_prompt(prompt: str, *, style: str | None = None, mood: str | None = None) -> str:
    """Compose the final Gemini prompt from a user description plus optional
    style/mood direction (chip label, free text, or omitted/"you decide").

    `prompt` is the user's own description of WHAT to depict — never rewritten,
    only appended to. The whole output is capped to the same bound the request
    model enforces on the raw prompt; the cap is spent on the DESCRIPTION, not
    the clauses — a maxed-out user prompt has its tail trimmed to leave room for
    the style/mood/baseline direction, rather than the direction (the point of
    this function) being sliced off the end."""
    suffix = " ".join([
        f"Style: {_clause(style, _STYLE_CLAUSES, _STYLE_DEFAULT)}.",
        f"Mood and lighting: {_clause(mood, _MOOD_CLAUSES, _MOOD_DEFAULT)}.",
        _BASELINE + ".",
    ])
    # Reserve the suffix's room (+1 for the join space) before truncating the
    # description. The suffix is bounded (style/mood capped at 120 each by the
    # request model, baseline is fixed), so this budget is always comfortably
    # positive — the final cap is belt-and-suspenders.
    head_budget = max(0, AI_IMAGE_PROMPT_MAX - len(suffix) - 1)
    head = prompt.strip()[:head_budget]
    return f"{head} {suffix}".strip()[:AI_IMAGE_PROMPT_MAX]
