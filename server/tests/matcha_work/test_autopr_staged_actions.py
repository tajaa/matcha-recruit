"""Staged outreach: what a research run proposes, and how a human closes it.

The invariant this file exists to protect is that the harness never sends.
Everything a run proposes lands as an immutable `autopr_staged_action` history
row; a person's approval is a second, unique `autopr_staged_action_result` row.
Because the outcome row is unique per action, "approved twice" — and therefore
"sent twice" — is not representable.
"""
import pytest

from app.matcha.services.matcha_work import project_task_service as pt


def test_a_well_formed_action_keeps_the_marker_key_free():
    """`kind` on the stored row is the marker every history query filters on.
    The action's own kind has to live under a different key or the row becomes
    invisible to its own lookup."""
    cleaned = pt._clean_staged_action(
        {"kind": "email", "to": "vendor@example.com", "subject": "Quote",
         "body": "Hi", "why": "Confirms pricing"}
    )
    assert cleaned == {
        "action_kind": "email", "to": "vendor@example.com",
        "subject": "Quote", "body": "Hi", "why": "Confirms pricing",
    }
    assert "kind" not in cleaned


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "an email",
        {"kind": "wire_money", "to": "a@example.com", "subject": "s", "body": "b", "why": "w"},
        {"kind": "email", "subject": "s", "body": "b", "why": "w"},            # no recipient
        {"kind": "email", "to": "", "subject": "s", "body": "b", "why": "w"},  # blank recipient
        {"kind": "email", "to": "a@example.com", "subject": "s", "body": "b"}, # no rationale
        {"kind": "email", "to": 12, "subject": "s", "body": "b", "why": "w"},  # not a string
    ],
)
def test_unusable_proposals_are_dropped_not_stored(raw):
    """A half-formed action on a card is one a human might approve without
    being able to read what they are approving."""
    assert pt._clean_staged_action(raw) is None


@pytest.mark.parametrize("field", ["to", "subject"])
def test_header_injection_in_an_addressable_field_is_refused(field):
    action = {"kind": "email", "to": "a@example.com", "subject": "Quote",
              "body": "Hi", "why": "w"}
    action[field] = action[field] + "\nBcc: someone-else@example.com"
    assert pt._clean_staged_action(action) is None


def test_oversized_fields_are_refused_at_their_documented_limit():
    limits = pt._STAGED_ACTION_FIELD_LIMITS
    assert limits == {"to": 200, "subject": 200, "body": 4000, "why": 600}
    # `to` has a second rule (it must be an address), so its at-the-limit value
    # is a long address rather than 200 x's.
    at_limit = {f: "x" * limit for f, limit in limits.items()}
    at_limit["to"] = "x" * (limits["to"] - len("@example.com")) + "@example.com"
    for field, limit in limits.items():
        action = {"kind": "email", "to": "a@example.com", "subject": "s",
                  "body": "b", "why": "w"}
        action[field] = ("x" * (limit + 1 - len("@example.com")) + "@example.com"
                         if field == "to" else "x" * (limit + 1))
        assert pt._clean_staged_action(action) is None, field
        action[field] = at_limit[field]
        assert pt._clean_staged_action(action) is not None, field


@pytest.mark.parametrize(
    "recipient",
    ["Acme Corp procurement lead", "the vendor", "someone@", "@example.com",
     "two people@example.com", "no-at-sign.example.com"],
)
def test_an_email_recipient_that_is_not_an_address_is_refused(recipient):
    """`to` becomes the RFC 5322 To: header verbatim on the send path. A name
    there is a proposal that can only fail at send time — after a person has
    already approved it and the claim has been written."""
    assert pt._clean_staged_action(
        {"kind": "email", "to": recipient, "subject": "s", "body": "b", "why": "w"}
    ) is None


@pytest.mark.parametrize("kind", ["contact", "review_request"])
def test_a_person_carried_action_may_name_a_person(kind):
    """Nothing hands these to a mail server, so a name or a role is the useful
    thing to write."""
    cleaned = pt._clean_staged_action(
        {"kind": kind, "to": "Acme Corp procurement lead", "subject": "s",
         "body": "b", "why": "w"}
    )
    assert cleaned is not None and cleaned["to"] == "Acme Corp procurement lead"


def test_only_email_is_sendable_by_this_system():
    """contact and review_request describe something a person does. Letting
    them resolve as `sent` would put this system's name on an act it never
    performed."""
    assert pt._SENDABLE_STAGED_ACTION_KINDS == {"email"}
    assert "contact" in pt._STAGED_ACTION_KINDS
    assert "review_request" in pt._STAGED_ACTION_KINDS


def test_sent_and_handled_are_distinct_outcomes():
    """"AutoPR sent it" and "a person sent it after reading it" are different
    claims, and these rows are the only record of which happened. `sending` is
    the claim written before the mail call, so a send that throws ends as
    `failed` instead of standing forever as `sent`."""
    assert pt._STAGED_ACTION_STATES == {
        "sending", "sent", "handled", "dismissed", "failed"
    }


@pytest.mark.asyncio
async def test_only_a_real_send_outcome_may_be_appended_to_a_claim():
    """record_autopr_staged_send_outcome deliberately appends without the
    uniqueness check, so it must never be usable to write anything but the two
    outcomes a send can have."""
    from uuid import uuid4

    for state in ("handled", "dismissed", "sending", "delivered"):
        with pytest.raises(ValueError, match="Not a send outcome"):
            await pt.record_autopr_staged_send_outcome(
                project_id=uuid4(), task_id=uuid4(), action_id=uuid4(),
                actor_user_id=uuid4(), state=state,
            )


def test_the_per_approver_send_ceiling_is_set():
    """gmail_service's own limiter lives on the instance and every request
    builds a fresh one, so it never fires across requests."""
    assert pt._STAGED_SEND_MAX_PER_HOUR == 20


def test_a_run_cannot_stage_more_than_the_documented_ceiling():
    assert pt._MAX_STAGED_ACTIONS_PER_RUN == 10


@pytest.mark.asyncio
async def test_resolving_with_an_unknown_state_is_refused_before_any_write():
    with pytest.raises(ValueError, match="Invalid staged action state"):
        await pt.resolve_autopr_staged_action(
            project_id=__import__("uuid").uuid4(),
            task_id=__import__("uuid").uuid4(),
            action_id=__import__("uuid").uuid4(),
            actor_user_id=__import__("uuid").uuid4(),
            state="delivered",
        )


@pytest.mark.asyncio
async def test_staging_on_an_unwatched_board_is_refused():
    from uuid import uuid4

    with pytest.raises(pt.AutoPRReconsiderationConflict, match="does not watch"):
        await pt.stage_autopr_actions(
            project_id=uuid4(),
            task_id=uuid4(),
            actor_user_id=uuid4(),
            actions=[{"kind": "email", "to": "a@example.com", "subject": "s",
                      "body": "b", "why": "w"}],
        )


@pytest.mark.asyncio
async def test_staging_on_a_watched_board_without_the_outreach_grant_is_refused(monkeypatch):
    from uuid import UUID, uuid4

    from app.core.services import platform_settings as ps

    board = UUID(sorted(pt.KANBAN_AUTOPR_PROJECT_IDS)[0])
    ps.prime_autopr_board_capabilities_cache({str(board): ["research"]})
    try:
        with pytest.raises(pt.AutoPRReconsiderationConflict, match="outreach"):
            await pt.stage_autopr_actions(
                project_id=board,
                task_id=uuid4(),
                actor_user_id=UUID(pt.KANBAN_AUTOPR_BOT_USER_ID),
                actions=[{"kind": "email", "to": "a@example.com", "subject": "s",
                          "body": "b", "why": "w"}],
            )
    finally:
        ps.prime_autopr_board_capabilities_cache({})


@pytest.mark.asyncio
async def test_a_granted_board_with_only_unusable_proposals_writes_nothing(monkeypatch):
    """Reaching the database at all would mean an empty action row could be
    created for a proposal the cleaner already rejected."""
    from uuid import UUID, uuid4

    from app.core.services import platform_settings as ps

    board = UUID(sorted(pt.KANBAN_AUTOPR_PROJECT_IDS)[0])
    ps.prime_autopr_board_capabilities_cache({str(board): ["outreach"]})

    def _explode(*args, **kwargs):
        raise AssertionError("no database access expected")

    monkeypatch.setattr(pt, "get_connection", _explode)
    try:
        result = await pt.stage_autopr_actions(
            project_id=board,
            task_id=uuid4(),
            actor_user_id=UUID(pt.KANBAN_AUTOPR_BOT_USER_ID),
            actions=[{"kind": "wire_money", "to": "a", "subject": "b", "body": "c", "why": "d"}],
        )
        assert result == {"ok": True, "staged": 0, "action_ids": []}
    finally:
        ps.prime_autopr_board_capabilities_cache({})


@pytest.mark.asyncio
async def test_only_the_autopr_account_may_stage_outreach(monkeypatch):
    """A staged row renders as "Drafted by AutoPR" with a one-click Send beside
    it. Board membership must not be enough to write one: a collaborator could
    otherwise put words in the bot's mouth for a colleague to send from their
    own mailbox, past every other guard."""
    from uuid import UUID, uuid4

    from app.core.services import platform_settings as ps

    board = UUID(sorted(pt.KANBAN_AUTOPR_PROJECT_IDS)[0])
    ps.prime_autopr_board_capabilities_cache({str(board): ["outreach"]})

    def _explode(*args, **kwargs):
        raise AssertionError("no database access expected")

    monkeypatch.setattr(pt, "get_connection", _explode)
    try:
        with pytest.raises(pt.AutoPRActorNotPermitted, match="service account"):
            await pt.stage_autopr_actions(
                project_id=board,
                task_id=uuid4(),
                actor_user_id=uuid4(),
                actions=[{"kind": "email", "to": "a@example.com", "subject": "s",
                          "body": "b", "why": "w"}],
            )
    finally:
        ps.prime_autopr_board_capabilities_cache({})


def test_result_rows_stay_out_of_the_unviewed_updates_badge():
    """The outcome row carries no body of its own, so it must not put an
    unread chip on a card that has nothing new to read."""
    assert "autopr_staged_action_result" in pt._AUTOPR_BOOKKEEPING_KINDS
