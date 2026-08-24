"""The waste-reason taxonomy. Single source of truth for the vocabulary
enforced by the DB CHECK on inventory_movements.waste_reason (migration
invwaste01) — tests/inventory/test_waste_reasons.py pins these two in sync.
Generic shrinkage vocabulary, not food-specific: works identically for a
clinic's expired reagents or a retailer's damaged stock. FOOD_DEFAULT_REASONS
is only a UI hint (which four to show first for a food-service tenant)."""

WASTE_REASONS: tuple[str, ...] = (
    "spoilage", "expired", "prep_error", "overproduction",
    "breakage", "contamination", "theft", "comp", "recall", "unknown",
)

FOOD_DEFAULT_REASONS: tuple[str, ...] = ("spoilage", "expired", "prep_error", "overproduction")

# Unexplained shrink is the number that goes in front of an owner — spoilage
# is an ordering problem, theft is not.
UNEXPLAINED_REASONS: frozenset[str] = frozenset({"theft", "unknown"})

# A personnel accusation must never be minted by an extraction model from a
# Slack-style chat aside — only a human choosing it explicitly (the page or
# a Huume-thread staged action) may record 'theft'. See the provenance
# invariant in services/inventory/CLAUDE.md.
CHAT_FORBIDDEN_REASONS: frozenset[str] = frozenset({"theft"})

_LABELS: dict[str, str] = {
    "spoilage": "Spoilage",
    "expired": "Expired",
    "prep_error": "Prep error",
    "overproduction": "Overproduction",
    "breakage": "Breakage",
    "contamination": "Contamination",
    "theft": "Theft",
    "comp": "Comp",
    "recall": "Recall",
    "unknown": "Unknown",
}


def label(reason: str) -> str:
    return _LABELS.get(reason, reason.replace("_", " ").title())


def is_unexplained(reason: str | None) -> bool:
    return reason in UNEXPLAINED_REASONS


def coerce_chat_reason(reason: str | None) -> str:
    """Chat-path gate: an unrecognised or forbidden reason always becomes
    'unknown' rather than being rejected outright — the movement still gets
    recorded (a real stock loss happened), it just can't carry an
    unreviewed accusation."""
    if reason in WASTE_REASONS and reason not in CHAT_FORBIDDEN_REASONS:
        return reason
    return "unknown"
