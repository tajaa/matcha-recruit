"""EMS event categories — pure, DB-free registry.

Deliberately wider than IR's incident_type vocabulary (safety/behavioral/
property/near_miss/other, see models/ir/types.py:IRIncidentType): EMS logs
anything a company needs documentation for, not just legal/safety records.
`incident_recommendation` is judged by the model PER EVENT, never hardcoded
per category here — a `property` event (black mold) or a `guest_experience`
event (thrown food, refund dispute) can each warrant an incident; an empty
ice machine (`equipment`) usually doesn't. The six examples below are the
few-shot block for the classify prompt in event_intake.py.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmsCategory:
    key: str
    label: str
    doc_sections: tuple[str, ...]  # section keys the extractor fills into `doc` JSONB
    example: str  # few-shot narrative for the classify prompt


CATEGORIES: dict[str, EmsCategory] = {
    "behavioral": EmsCategory(
        key="behavioral",
        label="Behavioral",
        doc_sections=("who", "what_happened", "prior_context"),
        example=(
            "I asked Jenna to bin the frozen hot dogs. It took her 1 hour and "
            "when I asked why it took so long she rolled her eyes at me."
        ),
    ),
    "safety": EmsCategory(
        key="safety",
        label="Safety",
        doc_sections=("who", "where", "injury", "witnesses"),
        example="Julia slipped in the back of house.",
    ),
    "operational": EmsCategory(
        key="operational",
        label="Operational",
        doc_sections=("process", "change", "impact"),
        example=(
            "We implemented the new coconut oil for popping and we are "
            "getting less volume from this system."
        ),
    ),
    "equipment": EmsCategory(
        key="equipment",
        label="Equipment",
        doc_sections=("asset", "issue", "since_when", "impact"),
        example="The ice machine is empty, it hasn't made new ice since yesterday.",
    ),
    "property": EmsCategory(
        key="property",
        label="Property",
        doc_sections=("location", "condition", "risk"),
        example="I noticed what appears to be black mold in the corner of the back stock room.",
    ),
    "guest_experience": EmsCategory(
        key="guest_experience",
        label="Guest Experience",
        doc_sections=("situation", "resolution_offered", "outcome"),
        example=(
            "A guest brought back his pizza saying it did not taste good. I "
            "offered to remake it for him but he said no and demanded a "
            "refund. When I processed the refund he said his experience has "
            "been horrible and threw the pizza on the ground."
        ),
    ),
}

FALLBACK_KEY = "uncategorized"

# All valid `category` values a caller/DB row may carry, including the fallback.
ALL_KEYS = frozenset(CATEGORIES) | {FALLBACK_KEY}


def normalize_category(raw: str | None) -> str:
    """Unknown/missing model output collapses to FALLBACK_KEY — never a raw,
    unvalidated model string reaches the `category` column."""
    if raw and raw in CATEGORIES:
        return raw
    return FALLBACK_KEY


def category_label(key: str) -> str:
    cat = CATEGORIES.get(key)
    return cat.label if cat else "Uncategorized"


def prompt_block() -> str:
    """Render the six categories + examples as the classify prompt's
    few-shot block, one line per category."""
    lines = [
        f'- "{cat.key}" ({cat.label}): {cat.example}'
        for cat in CATEGORIES.values()
    ]
    return "\n".join(lines)
