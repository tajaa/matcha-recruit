"""HR case lifecycle — pure, no DB.

Every stage move goes through `next_stage(stage, event)`; there is no other
way to change `hr_cases.stage`. An event that doesn't apply to the current
stage raises `InvalidTransition` rather than silently doing nothing, so a
stale button or a replayed Huume confirm can't skip a step (e.g. mark a case
delivered before HR approved it).
"""

from __future__ import annotations

STAGES = (
    "flagged", "drafting", "hr_review", "changes_requested", "approved",
    "delivered", "verifying", "needs_attention", "closed", "dismissed",
)
OPEN_STAGES = frozenset(STAGES) - {"closed", "dismissed"}

# event -> {from_stage: to_stage}
_TRANSITIONS: dict[str, dict[str, str]] = {
    # HR asks the GM for a write-up (or the GM says they're writing one).
    "start_draft": {"flagged": "drafting"},
    # A draft landed and passed the hard checks.
    "draft_submitted": {
        "flagged": "hr_review", "drafting": "hr_review", "changes_requested": "hr_review",
    },
    "approve": {"hr_review": "approved"},
    "request_changes": {"hr_review": "changes_requested"},
    "delivered": {"approved": "delivered"},
    # Signed copy uploaded; a re-upload after a problem goes back through the check.
    "signed_uploaded": {"delivered": "verifying", "needs_attention": "verifying"},
    "verified": {"verifying": "closed"},
    "attention": {"verifying": "needs_attention"},
    "acknowledge": {"needs_attention": "closed"},
    "dismiss": {
        "flagged": "dismissed", "drafting": "dismissed",
        "hr_review": "dismissed", "changes_requested": "dismissed",
    },
}

EVENTS = tuple(_TRANSITIONS)


class InvalidTransition(ValueError):
    def __init__(self, stage: str, event: str):
        self.stage = stage
        self.event = event
        super().__init__(f"Can't {event.replace('_', ' ')} a case that is {STAGE_LABEL.get(stage, stage).lower()}.")


def next_stage(stage: str, event: str) -> str:
    if event not in _TRANSITIONS:
        raise ValueError(f"Unknown HR case event: {event}")
    to = _TRANSITIONS[event].get(stage)
    if to is None:
        raise InvalidTransition(stage, event)
    return to


def allowed_events(stage: str) -> list[str]:
    return [e for e, moves in _TRANSITIONS.items() if stage in moves]


STAGE_LABEL = {
    "flagged": "Flagged",
    "drafting": "Waiting on draft",
    "hr_review": "HR review",
    "changes_requested": "Changes requested",
    "approved": "Approved to deliver",
    "delivered": "Delivered",
    "verifying": "Checking signed copy",
    "needs_attention": "Needs attention",
    "closed": "Closed",
    "dismissed": "Dismissed",
}

# Board columns on the HR Cases page, left to right.
COLUMNS = (
    ("new", "New", ("flagged", "drafting")),
    ("review", "HR review", ("hr_review", "changes_requested")),
    ("delivery", "Delivery", ("approved", "delivered")),
    ("signed", "Signed copy", ("verifying", "needs_attention")),
    ("done", "Done", ("closed", "dismissed")),
)
COLUMN_OF = {stage: key for key, _label, stages in COLUMNS for stage in stages}

CHECKLIST = (
    ("flagged", "Incident reviewed"),
    ("draft", "Write-up drafted"),
    ("review", "HR legal review"),
    ("approved", "Approved to deliver"),
    ("delivered", "Delivered to employee"),
    ("signed", "Signed copy uploaded"),
    ("verified", "Signed copy checked and filed"),
)

# How far along the checklist each stage is (items with index < n are done).
_PROGRESS = {
    "flagged": 1, "drafting": 1, "hr_review": 2, "changes_requested": 2,
    "approved": 4, "delivered": 5, "verifying": 6, "needs_attention": 6,
    "closed": 7, "dismissed": 1,
}


def checklist(stage: str) -> list[dict]:
    done = _PROGRESS.get(stage, 0)
    return [{"key": key, "label": label, "done": i < done} for i, (key, label) in enumerate(CHECKLIST)]
