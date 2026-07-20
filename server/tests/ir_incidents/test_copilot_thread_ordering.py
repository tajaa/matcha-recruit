"""Regression tests for the IR Copilot "thread update and trigger logic" bug.

Two independent backend failures, both of which silently emptied the admin's
recommendation list:

1. **Ordering.** `ir_incident_ai_messages.created_at` defaulted to `NOW()` —
   which is `transaction_timestamp()`, constant for a whole transaction. The
   resume-after-info-request path writes an entire round inside one transaction,
   so the assistant text row and every card row of that round carried an
   identical timestamp. Reads ordered by `created_at` alone, and
   `_extract_current_cards` resets its accumulator on the assistant text row —
   so if the tied cards happened to sort first, the whole round's cards were
   dropped and the panel rendered a summary with nothing to act on.
   Fixed by inserting `clock_timestamp()` explicitly (monotonic *within* a
   transaction) plus an `, id` tiebreaker on the reads.

2. **Empty round wipes state.** `generate_guidance` swallows Gemini
   timeouts/parse errors into `payload = {}`. `persist_assistant_round` then
   wrote a blank assistant row and ran its supersede sweep anyway, marking every
   open card superseded. A transient model hiccup erased the user's cards.

These are pure/mock-level tests — no DB, no network.
"""

import json

import pytest

from app.matcha.routes.ir_incidents.copilot import _extract_current_cards
from app.matcha.services.ir_ai_orchestrator import persist_assistant_round


def _card_row(card_id: str, **metadata_extra):
    return {
        "role": "assistant",
        "message_type": "card",
        "metadata": {
            "card": {
                "id": card_id,
                "title": f"Card {card_id}",
                "recommendation": "Do the thing",
                "rationale": "Because",
                "action": {"type": "set_field", "label": "Set it"},
            },
            **metadata_extra,
        },
    }


def _text_row(content="Here is where things stand."):
    return {"role": "assistant", "message_type": "text", "metadata": {}, "content": content}


# --------------------------------------------------------------------------
# 1. Ordering
# --------------------------------------------------------------------------

def test_cards_after_assistant_text_are_current():
    """The happy path: insertion order is text-then-cards."""
    cards = _extract_current_cards([_text_row(), _card_row("a"), _card_row("b")])
    assert [c.id for c in cards] == ["a", "b"]


def test_cards_before_their_assistant_text_are_dropped():
    """This is the failure the tiebreaker prevents.

    Pinning it as a *property of the extractor* rather than a bug: the reset on
    assistant text is deliberate (it's what stops prior rounds leaking forward).
    The extractor is correct; it just requires the caller to feed it rows in
    genuine insertion order. That contract is what `clock_timestamp()` +
    `ORDER BY created_at, id` now guarantee — so if this assertion ever flips,
    the extractor changed and the ordering fix is no longer load-bearing.
    """
    cards = _extract_current_cards([_card_row("a"), _card_row("b"), _text_row()])
    assert cards == []


def test_only_latest_round_survives_the_reset():
    rows = [_text_row("round one"), _card_row("old"), _text_row("round two"), _card_row("new")]
    assert [c.id for c in _extract_current_cards(rows)] == ["new"]


def test_accepted_superseded_and_skipped_cards_are_excluded():
    rows = [
        _text_row(),
        _card_row("accepted", accepted=True),
        _card_row("superseded", superseded=True),
        _card_row("skipped", skipped=True),
        _card_row("live"),
    ]
    assert [c.id for c in _extract_current_cards(rows)] == ["live"]


# --------------------------------------------------------------------------
# 2. Empty / failed rounds must not wipe cards
# --------------------------------------------------------------------------

class _FakeConn:
    """Records every write so a test can assert the supersede sweep did or did
    not run. `fetchval` returns the last assistant text (dedupe probe)."""

    def __init__(self, last_assistant_text=None):
        self.last_assistant_text = last_assistant_text
        self.inserted: list[dict] = []
        self.executed: list[str] = []

    async def fetchrow(self, _query, incident_id, role, message_type, content, metadata, created_by):
        # metadata arrives as the json.dumps'd string the real INSERT binds;
        # append_message coerces it back on the way out, so mirror that here.
        row = {
            "id": f"row-{len(self.inserted)}",
            "role": role,
            "message_type": message_type,
            "content": content,
            "metadata": json.loads(metadata) if metadata is not None else None,
            "created_by": created_by,
            "created_at": None,
        }
        self.inserted.append(row)
        return row

    async def fetchval(self, _query, _incident_id):
        return self.last_assistant_text

    async def execute(self, query, *_args):
        self.executed.append(query)

    @property
    def superseded(self) -> bool:
        return any("'{superseded}'" in q for q in self.executed)

    def rows_of_type(self, message_type: str) -> list[dict]:
        return [r for r in self.inserted if r["message_type"] == message_type]


def _payload(summary="Next steps.", cards=None, open_questions=None):
    return {
        "summary": summary,
        "cards": cards if cards is not None else [],
        "open_questions": open_questions or [],
    }


@pytest.mark.asyncio
async def test_failed_round_leaves_existing_cards_alone():
    """generate_guidance swallowed a Gemini error -> empty payload."""
    conn = _FakeConn(last_assistant_text="Earlier summary.")
    await persist_assistant_round(
        conn, incident_id="inc-1", user_id=None, user_message=None,
        guidance_payload={},
    )
    assert conn.superseded is False
    assert conn.inserted == []


@pytest.mark.asyncio
async def test_failed_round_still_persists_the_user_message():
    """The admin really did say it — only the assistant half of the round is
    abandoned."""
    conn = _FakeConn()
    await persist_assistant_round(
        conn, incident_id="inc-1", user_id=None, user_message="what next?",
        guidance_payload={},
    )
    assert [r["content"] for r in conn.inserted] == ["what next?"]
    assert conn.superseded is False


@pytest.mark.asyncio
async def test_summary_only_round_still_supersedes():
    """A summary-only round DOES clear prior cards — and must, for coherence.

    Gating the sweep on the new round having cards was tried and reverted: it
    cannot save those cards, because `_extract_current_cards` resets on the new
    assistant text row and drops them from the panel either way (see
    `test_cards_before_their_assistant_text_are_dropped`). Skipping the sweep
    only desynchronizes the DB from the UI, leaving invisible-but-live rows for
    the close-path idempotency probes to rediscover. The round that must not
    clear anything is the empty/failed one, which returns before writing a text
    row at all.
    """
    conn = _FakeConn()
    await persist_assistant_round(
        conn, incident_id="inc-1", user_id=None, user_message=None,
        guidance_payload=_payload(summary="Still waiting on the witness statement."),
    )
    assert conn.superseded is True
    assert len(conn.rows_of_type("text")) == 1
    assert conn.rows_of_type("card") == []


@pytest.mark.asyncio
async def test_round_with_cards_supersedes_prior_cards():
    """The original 3x-duplicate-card fix must still hold."""
    conn = _FakeConn()
    card = {"id": "c1", "title": "Set severity", "action": {"type": "set_field", "label": "Set"}}
    await persist_assistant_round(
        conn, incident_id="inc-1", user_id=None, user_message=None,
        guidance_payload=_payload(cards=[card]),
    )
    assert conn.superseded is True
    assert len(conn.rows_of_type("card")) == 1


@pytest.mark.asyncio
async def test_open_questions_only_round_is_not_treated_as_empty():
    """Questions with no summary and no cards are still a real turn.

    Known rough edge, deliberately pinned rather than silently accepted: the
    text row is written with empty content, so the panel's summary line renders
    blank for this turn (the extractor reads the last assistant text row's
    content as the summary). Worth revisiting by synthesizing a summary from the
    questions; the round must NOT be swallowed by the empty-payload early return
    in the meantime, which is what this asserts.
    """
    conn = _FakeConn()
    await persist_assistant_round(
        conn, incident_id="inc-1", user_id=None, user_message=None,
        guidance_payload=_payload(summary="", open_questions=["Who witnessed it?"]),
    )
    assert len(conn.rows_of_type("text")) == 1
    assert conn.rows_of_type("text")[0]["metadata"]["open_questions"] == ["Who witnessed it?"]


@pytest.mark.asyncio
async def test_duplicate_cards_within_a_round_are_deduped_before_the_sweep():
    conn = _FakeConn()
    card = {"id": "c1", "title": "Set severity", "action": {"type": "set_field", "label": "Set"}}
    await persist_assistant_round(
        conn, incident_id="inc-1", user_id=None, user_message=None,
        guidance_payload=_payload(cards=[card, dict(card)]),
    )
    assert len(conn.rows_of_type("card")) == 1
    assert conn.superseded is True
