"""The Compliance Pilot's confirm-first safety envelope — PURE and DB-free.

Structural mirror of `matcha/services/huume/actions.py`, reimplemented here
because core/ must not import matcha/. Every check that does not need the
database lives in this module as a plain function over plain dicts, so the whole
gate is unit-testable without a database or a Gemini key.

The rule the module exists to enforce, structurally rather than by prompt:

    A staged action cannot be confirmed on the turn that staged it.

`evaluate_confirm` takes `pre_turn_proposed_ids` — a snapshot of the session's
proposed action ids taken BEFORE any tool call in the turn ran. An action staged
earlier in this same turn is by construction absent from that snapshot, so the
model cannot stage-and-confirm in one breath even if the admin's message asked
for both. This is the same `pre_turn_plans` idiom Huume uses for onboarding
plans, and it is the reason the check reads a snapshot instead of a timestamp.

The second invariant is SINGLE-SLOT: staging supersedes any older proposal in
the session, so an admin's "yes, go ahead" can never be ambiguous about which of
three stale proposals it meant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Optional

# Caps on model-supplied arguments. Mirrors of `core.py`'s `_coerce_proposal`
# clamps, kept identical so a coordinate that survives the loop is one the
# legacy single-shot path would also have accepted.
_MAX_CITY = 120
_MAX_INDUSTRY = 80
_MAX_CATEGORIES = 60
_MAX_RATIONALE = 300
_MAX_QUERY = 500
_MAX_IDS = 500

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

# Statuses an action can be in. 'proposed' is the only one a confirm may act on.
TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled", "superseded"})


@dataclass(frozen=True)
class PilotVerdict:
    """Result of a pure gate.

    kind: "proceed" — cleared; `payload` carries the normalized arguments.
          "stage"   — staged this turn; tell the admin to confirm next turn.
          "refuse"  — a guard blocked it. `message` is relayed to the model
                      verbatim as the tool result, so it must read as an
                      instruction to the model, not an apology to a human.
    """
    kind: str
    message: str
    payload: Optional[dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


# --------------------------------------------------------------------------- #
# Argument coercion — every value below arrives from the model
# --------------------------------------------------------------------------- #

def coerce_state(v: Any) -> Optional[str]:
    """Two-letter US state code, or None. Rejects rather than truncates a longer
    token: 'California'[:2] is 'CA' by luck, but 'Illinois'[:2] is 'IL' by luck
    too and 'Ohio'[:2] is 'OH' — the coincidences stop at states whose name and
    code share a prefix, so silently truncating would send research to the wrong
    jurisdiction some of the time. `core.py:_coerce_proposal` truncates because
    its model was told to emit a code; here the caller gets None and asks."""
    s = str(v or "").strip().upper()
    return s if len(s) == 2 and s.isalpha() else None


def coerce_city(v: Any) -> Optional[str]:
    s = str(v or "").strip()[:_MAX_CITY]
    return s or None


def coerce_industry(v: Any) -> Optional[str]:
    s = str(v or "").strip()[:_MAX_INDUSTRY]
    return s or None


def coerce_text(v: Any, cap: int = _MAX_RATIONALE) -> str:
    return str(v or "").strip()[:cap]


def coerce_query(v: Any) -> Optional[str]:
    s = str(v or "").strip()[:_MAX_QUERY]
    return s or None


def coerce_categories(v: Any) -> Optional[list[str]]:
    """None means "the admin asked for everything" — a meaning an empty list
    must NOT silently acquire, since `resolve_proposal` reads a falsy value as
    the full-catalog sweep. An explicitly empty list is therefore also None:
    both mean "no specific topics named"."""
    if not isinstance(v, (list, tuple)):
        return None
    cats = [str(c).strip() for c in v if str(c or "").strip()][:_MAX_CATEGORIES]
    return cats or None


def coerce_uuid(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    return s.lower() if _UUID_RE.match(s) else None


def coerce_uuid_list(v: Any) -> list[str]:
    if not isinstance(v, (list, tuple)):
        return []
    out, seen = [], set()
    for item in v[:_MAX_IDS]:
        u = coerce_uuid(item)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


# --------------------------------------------------------------------------- #
# The two-turn confirm gate
# --------------------------------------------------------------------------- #

def evaluate_confirm(
    action_row: Optional[dict[str, Any]],
    pre_turn_proposed_ids: Iterable[str],
) -> PilotVerdict:
    """Pure gate for `confirm_action`. Order: exists → still proposed → not
    staged this turn.

    `pre_turn_proposed_ids` is snapshotted before the turn's first tool call, so
    "staged this turn" is decided structurally rather than by asking the model to
    remember. The ordering matters: an action the admin cancelled gets the
    honest "already cancelled" message rather than the two-turn message."""
    if not isinstance(action_row, dict) or not action_row.get("id"):
        return PilotVerdict(
            kind="refuse",
            message="There's no action with that id in this session. Call list_actions to see the real ids.",
        )

    action_id = str(action_row["id"])
    status = str(action_row.get("status") or "").strip()

    if status == "running":
        return PilotVerdict(
            kind="refuse",
            message="That action is already running — use action_status to check on it.",
        )
    if status in TERMINAL_STATUSES:
        detail = {
            "done": "already finished",
            "failed": "already failed",
            "cancelled": "was cancelled",
            "superseded": "was replaced by a newer proposal",
        }[status]
        return PilotVerdict(
            kind="refuse",
            message=f"That action {detail} — it can't be confirmed. Stage a new one if the admin wants it done again.",
        )
    if status != "proposed":
        return PilotVerdict(kind="refuse", message="That action isn't awaiting confirmation.")

    if action_id not in {str(i) for i in (pre_turn_proposed_ids or ())}:
        return PilotVerdict(
            kind="stage",
            message=(
                "That was staged this turn, so it can't be confirmed yet. Describe what you've "
                "proposed and wait for the admin's next message — confirming it there will work."
            ),
        )

    return PilotVerdict(kind="proceed", message="", payload={"action_id": action_id})


def evaluate_cancel(action_row: Optional[dict[str, Any]]) -> PilotVerdict:
    """Pure gate for `cancel_action`. Unlike confirm, cancelling something staged
    THIS turn is allowed — undoing a proposal the admin already objected to is
    the safe direction, and forcing them to wait a turn to retract it would be
    perverse."""
    if not isinstance(action_row, dict) or not action_row.get("id"):
        return PilotVerdict(
            kind="refuse",
            message="There's no action with that id in this session. Call list_actions to see the real ids.",
        )
    status = str(action_row.get("status") or "").strip()
    if status == "running":
        return PilotVerdict(
            kind="refuse",
            message="That run is already in flight and can't be cancelled from here.",
        )
    if status != "proposed":
        return PilotVerdict(
            kind="refuse",
            message="Only a proposal awaiting confirmation can be cancelled; that one already ran or was voided.",
        )
    return PilotVerdict(kind="proceed", message="", payload={"action_id": str(action_row["id"])})


# --------------------------------------------------------------------------- #
# Staging
# --------------------------------------------------------------------------- #

def supersede_targets(
    actions: Iterable[dict[str, Any]], *, exclude_id: Optional[str] = None
) -> list[str]:
    """Ids of proposals a newly-staged action displaces. Pure.

    Single-slot, like Huume: staging anything supersedes every older proposal in
    the session regardless of kind. Several live proposals would make the
    admin's "go ahead" ambiguous, and the loop resolves that ambiguity by never
    creating it. `exclude_id` protects the row just inserted."""
    out = []
    for a in actions or ():
        if not isinstance(a, dict):
            continue
        if str(a.get("status") or "") != "proposed":
            continue
        aid = str(a.get("id") or "")
        if not aid or (exclude_id and aid == str(exclude_id)):
            continue
        out.append(aid)
    return out


def evaluate_stage_approve(
    from_action_row: Optional[dict[str, Any]],
    ids: Any = None,
) -> PilotVerdict:
    """Pure gate for `stage_approve`, run at STAGE time so the admin sees a real
    selection before confirming rather than after.

    `ids` omitted → the gate-passing subset of the run's `staged_rows`, which is
    the default the admin almost always wants. `ids` given → validated as a
    subset of the run's own `staged_ids`, and gate-failing rows among them are
    KEPT: approve activates them live-but-uncodified with the reason recorded,
    exactly as the legacy `/approve` route does. Silently dropping them would
    make an explicit request quietly do less than it said."""
    if not isinstance(from_action_row, dict) or not from_action_row.get("id"):
        return PilotVerdict(
            kind="refuse",
            message="There's no action with that id in this session. Call list_actions to see the real ids.",
        )
    if str(from_action_row.get("kind") or "") != "research":
        return PilotVerdict(
            kind="refuse",
            message="Only a research run stages policies to commit — that action is a different kind.",
        )
    status = str(from_action_row.get("status") or "")
    if status != "done":
        hint = ("it hasn't finished yet — check action_status"
                if status in ("running", "proposed") else "it didn't finish successfully")
        return PilotVerdict(
            kind="refuse",
            message=f"That research run has nothing to commit: {hint}.",
        )

    result = from_action_row.get("result")
    staged_rows = (result or {}).get("staged_rows") if isinstance(result, dict) else None
    staged_rows = [r for r in (staged_rows or []) if isinstance(r, dict)]
    known_ids = {str(r.get("id")) for r in staged_rows if r.get("id")}
    # Fall back to the action's own staged_ids column when the result payload is
    # thin (an older row, or one written before staged_rows existed).
    if not known_ids:
        known_ids = {str(i) for i in (from_action_row.get("staged_ids") or [])}
    if not known_ids:
        return PilotVerdict(
            kind="refuse",
            message="That research run staged no policies, so there's nothing to commit.",
        )

    requested = coerce_uuid_list(ids)
    if requested:
        unknown = [i for i in requested if i not in {k.lower() for k in known_ids}]
        if unknown:
            return PilotVerdict(
                kind="refuse",
                message=(
                    f"{len(unknown)} of those requirement ids aren't part of that research run. "
                    "Use action_status to list the run's staged policies and their real ids."
                ),
            )
        # Preserve the run's own ordering rather than the model's.
        wanted = set(requested)
        selected = [str(r["id"]) for r in staged_rows if str(r.get("id", "")).lower() in wanted] \
            or [i for i in requested]
        explicit = True
    else:
        selected = [str(r["id"]) for r in staged_rows if r.get("gate_ok") and r.get("id")]
        explicit = False
        if not selected:
            blocked = sorted({str(r.get("gate_reason") or "unknown reason") for r in staged_rows})
            return PilotVerdict(
                kind="refuse",
                message=(
                    "None of that run's staged policies pass the codify gate, so committing them "
                    f"would add live-but-uncodified rows. Reasons: {'; '.join(blocked[:4])}. "
                    "Tell the admin, and only pass explicit ids if they still want them live."
                ),
            )

    by_id = {str(r.get("id")): r for r in staged_rows}
    gate_ok = sum(1 for i in selected if (by_id.get(i) or {}).get("gate_ok"))
    return PilotVerdict(
        kind="proceed",
        message="",
        payload={
            "from_action_id": str(from_action_row["id"]),
            "ids": selected,
            "selected": len(selected),
            "gate_ok": gate_ok,
            "gate_blocked": len(selected) - gate_ok,
            "explicit_selection": explicit,
        },
    )
