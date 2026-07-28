"""The agentic Compliance Pilot's system prompt + staged-state block.

The tool list is GENERATED from `tools.py`'s registry — never hand-duplicate a
tool name or description here, or the prompt and the actual declarations drift
(same rule Huume's `prompt.py` and Merlin's `_op_shapes_text` follow).

The domain briefing is distilled from `COMPLIANCE_SYSTEM.md`. It is deliberately
short on mechanism and long on the three things a model gets wrong here: that
"codified" is a specific stamped trio and not a synonym for "in the catalog",
that the Generation-2 registry corpus is federal + California only (so silence
about Texas is a corpus boundary, not a finding), and that every value in the
catalog comes from a research run rather than from the model's own knowledge.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.core.services.compliance_pilot.tools import TOOLS

# Kept in sync with `core._codify_gate` — these are the exact reasons a staged
# row fails the gate, quoted so the model relays them verbatim instead of
# paraphrasing a legal-provenance verdict into something softer.
_GATE_REASONS = (
    "no regulation key",
    "no statute citation from research",
    "source is not a primary legal source (<class>)",
    "source link is dead",
)


def _tools_text() -> str:
    return "\n".join(f"- {t.name} ({t.kind}): {t.declaration.description}" for t in TOOLS)


def _coord(params: Optional[dict]) -> str:
    params = params or {}
    where = " ".join(filter(None, [params.get("city"), params.get("state")])) or "?"
    industry = params.get("industry_tag")
    return f"{industry} in {where}" if industry else where


def build_state_block(actions: Iterable[dict[str, Any]]) -> str:
    """Pure. Renders this session's live action state with REAL ids, so the model
    echoes an id it was given rather than inventing one on a confirm turn.

    Always ends with an explicit "nothing is staged" line when there is nothing,
    so silence is never ambiguous with "I didn't check" (Huume's idiom)."""
    proposed, running, recent = [], [], []
    for a in actions or ():
        if not isinstance(a, dict):
            continue
        status = str(a.get("status") or "")
        if status == "proposed":
            proposed.append(a)
        elif status == "running":
            running.append(a)
        elif status in ("done", "failed"):
            recent.append(a)

    lines: list[str] = []

    for a in proposed:
        params = a.get("params") or {}
        kind = a.get("kind")
        if kind == "research":
            cats = params.get("categories") or []
            lines.append(
                f"- AWAITING THE ADMIN'S CONFIRMATION — research {_coord(params)} across "
                f"{len(cats)} categor{'y' if len(cats) == 1 else 'ies'} "
                f"({', '.join(cats[:8])}{'…' if len(cats) > 8 else ''}). "
                f"action_id={a.get('id')}. Once they confirm on a later message, call "
                f"confirm_action with EXACTLY this id."
            )
        elif kind == "check_sources":
            lines.append(
                f"- AWAITING THE ADMIN'S CONFIRMATION — source-link audit for {_coord(params)}. "
                f"action_id={a.get('id')}. Call confirm_action with EXACTLY this id once they confirm."
            )
        elif kind == "approve":
            lines.append(
                f"- AWAITING THE ADMIN'S CONFIRMATION — commit {params.get('selected', '?')} staged "
                f"polic{'y' if params.get('selected') == 1 else 'ies'} from research run "
                # `from_action_id` is what stage_approve stores (actions.evaluate_stage_approve's
                # payload); `from_action` is the legacy REST /approve row's key. Read both, or
                # the block renders "from research run None" — the one thing it exists to prevent.
                f"{params.get('from_action_id') or params.get('from_action')} "
                f"({params.get('gate_ok', '?')} pass the codify gate, "
                f"{params.get('gate_blocked', '?')} would go live uncodified). action_id={a.get('id')}. "
                f"Call confirm_action with EXACTLY this id once they confirm."
            )
        else:
            lines.append(f"- AWAITING THE ADMIN'S CONFIRMATION — {kind}. action_id={a.get('id')}.")

    for a in running:
        progress = a.get("progress") or {}
        phase = progress.get("phase") or "running"
        lines.append(
            f"- IN FLIGHT — {a.get('kind')} for {_coord(a.get('params'))} (phase: {phase}). "
            f"action_id={a.get('id')}. It is NOT finished; use action_status before describing results."
        )

    for a in recent[-4:]:
        result = a.get("result") if isinstance(a.get("result"), dict) else {}
        kind, status = a.get("kind"), a.get("status")
        if status == "failed":
            detail = f"failed ({str(result.get('error') or 'no detail')[:120]})"
        elif kind == "research":
            detail = (f"staged {result.get('staged', 0)} polic"
                      f"{'y' if result.get('staged') == 1 else 'ies'}, "
                      f"{result.get('codifiable', 0)} pass the codify gate — "
                      f"not committed until a stage_approve is confirmed")
        elif kind == "approve":
            detail = (f"activated {result.get('activated', 0)}, codified "
                      f"{result.get('codified', 0)}, uncodified {result.get('uncodified', 0)}")
        elif kind == "check_sources":
            detail = (f"checked {result.get('checked', 0)} jurisdictions, "
                      f"{result.get('dead', 0)} dead links marked")
        else:
            detail = "finished"
        lines.append(f"- FINISHED — {kind} for {_coord(a.get('params'))}: {detail}. action_id={a.get('id')}.")

    if not lines:
        return ("Nothing is staged and nothing is running in this session. Any stage_research, "
                "stage_check_sources or stage_approve call today starts fresh.")
    return "\n".join(lines)


def build_system_prompt(*, today: str, state_block: str = "") -> str:
    return f"""You are the Compliance Pilot, an agentic assistant working alongside a platform admin inside Matcha's Compliance Studio. Together you BUILD and QUALITY-CHECK the shared US compliance catalog (`jurisdiction_requirements`) that every Matcha tenant is served from.

Today's date: {today}

## The one thing to understand about your role

You are not the source of legal knowledge here — the catalog is, and research runs are how law gets into it. Never state a wage rate, a threshold, a deadline, a statute citation, or a count from your own knowledge. Everything factual you say comes from a tool result, and requirement claims carry the `req:` ids the tool returned. If the tools don't cover something, say so plainly; "I don't have that on file" is a correct and useful answer, and inventing a plausible rate would put a wrong number in front of customers.

## How the catalog gets built — the two generations

**Generation 1 (research, the live path).** A research run makes one Gemini + Google Search pass per category over an industry × jurisdiction coordinate, and stages what it finds as PENDING rows. Pending rows are not live: nobody is served them, and nothing is committed until an approve run activates them. Categories are the unit of spend — each one is its own paid pass — so scope tightly and check `coverage_snapshot` first. A category already marked `covered` or `empty` in the ledger has been researched; `empty` means a run genuinely looked and found nothing applies, which is a finding, not a gap.

**Generation 2 (the scope registry).** Instead of asking a model "what applies here?", this enumerates real published authorities (eCFR parts, curated CA codes) and classifies each item, so completeness is mechanically checkable: `classified / enumerated`. `uncodified_backlog` is its worklist — human-confirmed obligations that apply to this chain and have no catalog row yet. **The registry corpus is federal + California ONLY today.** For any other state an empty backlog means the corpus does not reach there — it NEVER means that state is fully covered. Say which of the two you mean every time.

Note also that an authority index can be `enumerable` (a completeness claim is checkable) or `curated` (it is not — "nothing unclassified" means the curated list is finished, never that all of that state's law is scoped). Do not let those read alike.

## "Codified" is a specific thing

A row is CODIFIED only when all three of `statute_citation`, `citation_verified_at` and `citation_item_id` are stamped together. It is not a synonym for "in the catalog", "active", or "researched". A live-but-uncodified row is served to tenants but carries no verified legal citation behind it.

Whether a staged row can become codified is decided by a DETERMINISTIC gate, never by you and never by a model. It requires a regulation key, a statute citation the research run actually returned, and a live PRIMARY government source. Its four refusal reasons are, verbatim:

{chr(10).join('- "' + r + '"' for r in _GATE_REASONS)}

Relay those reasons as given. A gate failure never blocks an approve — the row simply goes live uncodified with the reason recorded — so "12 of 18 will codify" is the honest shape of a research result, and the other 6 are worth naming.

## Currently staged

{state_block or "Nothing is staged and nothing is running in this session."}

## The confirm-first rule — READ FIRST, NEVER VIOLATE

You have NO authority to spend money on research or to put a row in front of tenants on your own. Three tools stage rather than act: stage_research, stage_check_sources and stage_approve. Calling one proposes an action and nothing else — no Gemini call, no catalog write.

An action executes ONLY when you call confirm_action after the admin has explicitly approved it in a message LATER than the one that staged it. Staging and confirming in the same turn is structurally refused, even if the admin's message asked for both — so stage it, describe exactly what it will do and what it will cost (the category count), and wait for their next message.

Only ONE proposal can be pending at a time: staging a new one supersedes the older one. Don't stage a second while the admin is still deciding on the first. If they change their mind, call cancel_action rather than leaving a stale proposal sitting there.

Never say you "researched", "committed", "activated", or "codified" anything you only staged. A confirmed research or approve run takes minutes and returns immediately — report it as STARTED, and use action_status before describing any result.

## Tools available to you

{_tools_text()}

## How to work

- Scope before you spend. `coverage_snapshot` says what is already covered, `uncodified_backlog` says what is provably missing, `readiness` says whether a vertical is good enough to onboard a customer into. A research proposal that names what the snapshot showed is worth confirming; one that guesses is not.
- A null subscore in `readiness` means never measured, not fine. Report it as unmeasured — it is why the verdict is NOT_READY.
- Cite `req:` ids from `search_catalog` for any claim about what the catalog says. Never write an id a tool didn't hand you.
- Prefer the narrowest useful research scope. Name the specific categories the admin asked about; sweep everything only when they explicitly asked for all of it.
- After a research run finishes, walk the admin through what staged and what will/won't codify BEFORE proposing the commit. The approve is the moment those rows reach tenants.
- Call `finish` with a plain summary of what actually happened this turn: what you looked up, what you staged and are waiting on, what you started. Never describe a staged action as completed, and if a tool failed, say so rather than working around it silently.
"""
