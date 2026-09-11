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
        "subject": "Quote", "action_body": "Hi", "why": "Confirms pricing",
    }
    assert "kind" not in cleaned
    # `body` is what every discussion renderer reads off an activity row —
    # the ticket thread, the AI brief, the harness's context. A draft nobody
    # approved must never be readable as something a person said.
    assert "body" not in cleaned


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


def test_staged_rows_are_bookkeeping_not_discussion():
    """Both rows ride event_type='activity' but neither is a comment: the
    proposal is rendered by the outreach section (its text lives under
    action_body) and the result row has no body at all. Every consumer of
    activity rows — badge, discussion thread, AI brief, overview feed, the
    model's own context — filters through this list."""
    assert "autopr_staged_action" in pt._AUTOPR_BOOKKEEPING_KINDS
    assert "autopr_staged_action_result" in pt._AUTOPR_BOOKKEEPING_KINDS
    assert "autopr_run_claim_move" in pt._AUTOPR_BOOKKEEPING_KINDS
    assert pt.is_autopr_bookkeeping_row({"kind": "autopr_staged_action", "action_body": "x"})
    assert pt.is_autopr_bookkeeping_row({"kind": "autopr_run_claim"})
    assert not pt.is_autopr_bookkeeping_row({"kind": "note", "body": "hello"})
    assert not pt.is_autopr_bookkeeping_row("not a dict")


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _StagingConn:
    """Enough of an asyncpg connection for stage_autopr_actions: the task
    exists, and rows previously staged under a run key are remembered."""

    def __init__(self, existing_by_key: dict[str, list[str]]):
        self.existing_by_key = existing_by_key
        self.inserted: list[dict] = []

    def transaction(self):
        return _Tx()

    async def fetchval(self, sql, *args):
        assert "FROM mw_tasks" in sql
        return 1

    async def execute(self, sql, *args):
        assert "FOR UPDATE" in sql

    async def fetch(self, sql, *args):
        assert "metadata->>'run_key'" in sql
        return [{"id": i} for i in self.existing_by_key.get(args[1], [])]

    async def fetchrow(self, sql, *args):
        import json

        assert "INSERT INTO mw_task_history" in sql
        meta = json.loads(args[4])
        self.inserted.append(meta)
        return {"id": f"new-{len(self.inserted)}"}


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


@pytest.mark.asyncio
async def test_staging_twice_under_the_same_run_key_returns_the_first_rows(monkeypatch):
    """A publication that died after staging and is retried must not put a
    second set of one-click Send rows on the card. The report file id is the
    key; the retry gets the rows the first attempt made."""
    from uuid import UUID, uuid4

    from app.core.services import platform_settings as ps

    board = UUID(sorted(pt.KANBAN_AUTOPR_PROJECT_IDS)[0])
    ps.prime_autopr_board_capabilities_cache({str(board): ["outreach"]})
    action = {"kind": "email", "to": "a@example.com", "subject": "s", "body": "b", "why": "w"}
    try:
        fresh = _StagingConn({})
        monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(fresh))
        first = await pt.stage_autopr_actions(
            project_id=board, task_id=uuid4(),
            actor_user_id=UUID(pt.KANBAN_AUTOPR_BOT_USER_ID),
            actions=[action], run_key="file-report-1",
        )
        assert first["staged"] == 1 and first["action_ids"] == ["new-1"]
        assert fresh.inserted[0]["run_key"] == "file-report-1"
        assert fresh.inserted[0]["kind"] == "autopr_staged_action"

        retry = _StagingConn({"file-report-1": ["old-1", "old-2"]})
        monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(retry))
        second = await pt.stage_autopr_actions(
            project_id=board, task_id=uuid4(),
            actor_user_id=UUID(pt.KANBAN_AUTOPR_BOT_USER_ID),
            actions=[action], run_key="file-report-1",
        )
        assert second == {
            "ok": True, "staged": 0, "action_ids": ["old-1", "old-2"],
            "already_staged": True,
        }
        assert retry.inserted == []
    finally:
        ps.prime_autopr_board_capabilities_cache({})


def test_the_send_ceiling_counts_one_row_per_attempt():
    """A completed send writes BOTH a `sending` claim and a `sent` outcome by
    the same actor, so counting the pair charged every send twice and halved a
    documented ceiling of 20 to a real one of 10. The claim alone is one row
    per attempt: a failure still costs the hour, a success is billed once."""
    import inspect

    src = inspect.getsource(pt.count_recent_staged_sends)
    assert "metadata->>'state' = 'sending'" in src
    assert "IN ('sending', 'sent')" not in src
    # Bounded to the watched boards so the (project_id, created_at) index
    # carries the query — there is no index on actor_user_id.
    assert "project_id = ANY($2::uuid[])" in src


@pytest.mark.asyncio
async def test_the_ceiling_covers_the_board_being_sent_from(monkeypatch):
    """The send gate is the stored `outreach` grant, which outlives a board's
    membership in the watched set. Counting only the watched boards let such a
    board match zero rows, so its ceiling never fired at all."""
    from uuid import UUID, uuid4

    seen: dict = {}

    class _CountConn:
        async def fetchval(self, sql, *args):
            seen["ids"] = args[1]
            return 0

    orphan = uuid4()
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_CountConn()))
    await pt.count_recent_staged_sends(actor_user_id=uuid4(), project_id=orphan)
    assert orphan in seen["ids"]
    for watched in pt.KANBAN_AUTOPR_PROJECT_IDS:
        assert UUID(watched) in seen["ids"]


class _CeilingConn:
    """resolve_autopr_staged_action's connection when a ceiling is supplied."""

    def __init__(self, recent):
        self.recent = recent
        self.executed: list[str] = []
        self.inserted: list = []

    def transaction(self):
        return _Tx()

    async def execute(self, sql, *args):
        self.executed.append(sql)

    async def fetchval(self, sql, *args):
        return self.recent

    async def fetchrow(self, sql, *args):
        import json
        from datetime import datetime, timezone

        if "FOR UPDATE" in sql:
            return {"id": args[0], "metadata": "{}"}
        if "autopr_staged_action_result" in sql and "SELECT" in sql:
            return None
        assert "INSERT INTO mw_task_history" in sql
        self.inserted.append(json.loads(args[4]))
        return {"id": "r1", "created_at": datetime.now(timezone.utc)}


@pytest.mark.asyncio
async def test_the_ceiling_is_counted_inside_the_claim_transaction(monkeypatch):
    """Read in its own transaction beforehand, the ceiling bounded nothing: the
    per-action FOR UPDATE serializes two approvals of the SAME action and
    nothing about two approvals of different ones, so N concurrent requests all
    saw the same pre-claim number and all passed. The count has to happen under
    a per-approver lock in the transaction that writes the claim."""
    from uuid import uuid4

    conn = _CeilingConn(recent=pt._STAGED_SEND_MAX_PER_HOUR)
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(conn))
    with pytest.raises(pt.AutoPRSendCeilingReached, match="Hourly limit"):
        await pt.resolve_autopr_staged_action(
            project_id=uuid4(), task_id=uuid4(), action_id=uuid4(),
            actor_user_id=uuid4(), state="sending",
            max_recent_sends=pt._STAGED_SEND_MAX_PER_HOUR,
        )
    assert any("pg_advisory_xact_lock" in s for s in conn.executed)
    # Refused before the claim row, not after it.
    assert conn.inserted == []


@pytest.mark.asyncio
async def test_a_close_under_the_ceiling_claims_normally(monkeypatch):
    from uuid import uuid4

    conn = _CeilingConn(recent=pt._STAGED_SEND_MAX_PER_HOUR - 1)
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(conn))
    result = await pt.resolve_autopr_staged_action(
        project_id=uuid4(), task_id=uuid4(), action_id=uuid4(),
        actor_user_id=uuid4(), state="sending",
        max_recent_sends=pt._STAGED_SEND_MAX_PER_HOUR,
    )
    assert result["state"] == "sending"
    assert conn.inserted[-1]["state"] == "sending"


@pytest.mark.asyncio
async def test_a_non_send_transition_is_never_charged_to_the_ceiling(monkeypatch):
    """Marking something handled or dismissed sends no mail."""
    from uuid import uuid4

    for state in ("handled", "dismissed"):
        conn = _CeilingConn(recent=pt._STAGED_SEND_MAX_PER_HOUR + 5)
        monkeypatch.setattr(pt, "get_connection", lambda c=conn: _Ctx(c))
        result = await pt.resolve_autopr_staged_action(
            project_id=uuid4(), task_id=uuid4(), action_id=uuid4(),
            actor_user_id=uuid4(), state=state,
            max_recent_sends=pt._STAGED_SEND_MAX_PER_HOUR,
        )
        assert result["state"] == state
        assert conn.executed == []


def test_a_send_outcome_is_written_under_the_same_lock_as_a_close():
    """"The newest row wins" only holds if every writer of a result row queues
    behind the same lock. Without it, a person dismissing a claim that had gone
    stale can commit AFTER a slow send finally returns, and that later
    `dismissed` outranks the `sent` row carrying the provider's message id —
    the card then denies a delivery that actually happened."""
    import inspect

    src = inspect.getsource(pt.record_autopr_staged_send_outcome)
    assert "conn.transaction()" in src
    assert "FOR UPDATE" in src


# ---------------------------------------------------------------------------
# What a person may still do with an action, by its newest outcome row.
# ---------------------------------------------------------------------------
def test_affordances_pending_and_failed_may_send_or_close():
    """A transient provider error must not brick a proposal: `failed` keeps
    every option `pending` had."""
    assert pt._staged_action_affordances(None, None) == (True, True)
    assert pt._staged_action_affordances("failed", None) == (True, True)


def test_affordances_a_stale_claim_may_be_closed_but_never_resent():
    """A `sending` claim with no outcome means the process died holding it. It
    may have delivered, so it is never re-sent; once a person has checked
    their mailbox they may close it either way."""
    from datetime import datetime, timedelta, timezone

    fresh = datetime.now(timezone.utc) - timedelta(seconds=30)
    stale = datetime.now(timezone.utc) - pt._STAGED_SEND_STALE_AFTER - timedelta(seconds=1)
    assert pt._staged_action_affordances("sending", fresh) == (False, False)
    assert pt._staged_action_affordances("sending", stale) == (False, True)


@pytest.mark.parametrize("state", ["sent", "handled", "dismissed"])
def test_affordances_settled_states_offer_nothing(state):
    from datetime import datetime, timezone

    assert pt._staged_action_affordances(state, datetime.now(timezone.utc)) == (False, False)


class _ResolveConn:
    """The three statements resolve_autopr_staged_action makes, with the
    action present and one prior outcome row of the given age."""

    def __init__(self, existing_state, existing_age):
        from datetime import datetime, timezone

        self.existing_state = existing_state
        self.existing_at = (
            None if existing_age is None else datetime.now(timezone.utc) - existing_age
        )
        self.inserted = []

    def transaction(self):
        return _Tx()

    async def fetchrow(self, sql, *args):
        import json

        if "FOR UPDATE" in sql:
            return {"id": args[0], "metadata": "{}"}
        if "autopr_staged_action_result" in sql and "SELECT" in sql:
            if self.existing_state is None:
                return None
            return {"state": self.existing_state, "created_at": self.existing_at}
        assert "INSERT INTO mw_task_history" in sql
        self.inserted.append(json.loads(args[4]))
        from datetime import datetime, timezone

        return {"id": "r1", "created_at": datetime.now(timezone.utc)}


async def _resolve_with(monkeypatch, existing_state, existing_age, new_state):
    from uuid import uuid4

    conn = _ResolveConn(existing_state, existing_age)
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(conn))
    result = await pt.resolve_autopr_staged_action(
        project_id=uuid4(), task_id=uuid4(), action_id=uuid4(),
        actor_user_id=uuid4(), state=new_state,
    )
    return conn, result


@pytest.mark.asyncio
async def test_a_failed_send_may_be_retried_or_closed(monkeypatch):
    for new_state in ("sending", "handled", "dismissed"):
        conn, result = await _resolve_with(monkeypatch, "failed", None, new_state)
        assert result["state"] == new_state
        assert conn.inserted[-1]["state"] == new_state


@pytest.mark.asyncio
async def test_a_stale_claim_may_be_closed_but_not_resent(monkeypatch):
    from datetime import timedelta

    stale = pt._STAGED_SEND_STALE_AFTER + timedelta(minutes=1)
    with pytest.raises(pt.AutoPRReconsiderationConflict, match="already sending"):
        await _resolve_with(monkeypatch, "sending", stale, "sending")
    conn, result = await _resolve_with(monkeypatch, "sending", stale, "handled")
    assert result["state"] == "handled"


@pytest.mark.asyncio
async def test_a_fresh_claim_blocks_everything(monkeypatch):
    """This is the row that makes a concurrent second approval impossible."""
    from datetime import timedelta

    for new_state in ("sending", "handled", "dismissed"):
        with pytest.raises(pt.AutoPRReconsiderationConflict, match="already sending"):
            await _resolve_with(monkeypatch, "sending", timedelta(seconds=5), new_state)


@pytest.mark.asyncio
@pytest.mark.parametrize("settled", ["sent", "handled", "dismissed"])
async def test_a_settled_action_refuses_every_transition(monkeypatch, settled):
    from datetime import timedelta

    for new_state in ("sending", "handled", "dismissed"):
        with pytest.raises(pt.AutoPRReconsiderationConflict, match=f"already {settled}"):
            await _resolve_with(monkeypatch, settled, timedelta(minutes=30), new_state)


@pytest.mark.parametrize(
    "address",
    ["vendor@example.com", "x@acme.test", "ops@matcha.invalid", "a@b.localhost"],
)
def test_reserved_test_domains_are_never_handed_to_gmail(address):
    """The proposal may be staged (it is only text), but the send path applies
    the same guard the transactional mailer does."""
    assert pt.staged_recipient_is_reserved_test_domain(address)
    # Deliberately not a registrable name: the negative case needs an address
    # the guard does NOT catch, and `.notatld` is absent from the DNS root, so
    # nothing here can ever resolve or bounce if it escapes into a fixture.
    assert not pt.staged_recipient_is_reserved_test_domain("vendor@vendor.notatld")


# ---------------------------------------------------------------------------
# Reading a staged action back: the two readers the client and the send path use.
# ---------------------------------------------------------------------------
class _ListConn:
    def __init__(self, metadata):
        self.metadata = metadata

    async def fetch(self, sql, *args):
        from datetime import datetime, timezone

        return [{
            "id": "a1", "metadata": self.metadata,
            "created_at": datetime.now(timezone.utc),
            "result_metadata": None, "resolved_at": None,
            "resolved_by_name": None,
        }]


class _GetConn:
    def __init__(self, metadata):
        self.metadata = metadata

    async def fetchrow(self, sql, *args):
        return {"id": "a1", "metadata": self.metadata, "state": None, "state_at": None}


_LEGACY_ROW = {
    "kind": "autopr_staged_action", "action_kind": "email",
    "to": "vendor@vendor.notatld", "subject": "Quote",
    "body": "the draft as it was stored before the rename", "why": "w",
}


@pytest.mark.asyncio
async def test_a_row_staged_before_the_rename_still_reads_back(monkeypatch):
    """The draft key moved from `body` to `action_body` with no backfill, so
    rows written by the previous release carry only `body`. Reading just the
    new key returned null for them — and `MWStagedAction.body` is non-optional
    in Espresso, so one such row failed the decode of the WHOLE list and
    blanked the outreach section, taking every newer proposal with it."""
    from uuid import uuid4

    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_ListConn(_LEGACY_ROW)))
    listed = await pt.list_autopr_staged_actions(project_id=uuid4(), task_id=uuid4())
    assert listed[0]["body"] == _LEGACY_ROW["body"]

    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_GetConn(_LEGACY_ROW)))
    got = await pt.get_autopr_staged_action(
        project_id=uuid4(), task_id=uuid4(), action_id=uuid4()
    )
    assert got["body"] == _LEGACY_ROW["body"]


@pytest.mark.asyncio
async def test_the_current_key_wins_over_a_stray_legacy_one(monkeypatch):
    """The fallback must not let a `body` key resurrect an older draft."""
    from uuid import uuid4

    row = {**_LEGACY_ROW, "action_body": "the current draft"}
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_ListConn(row)))
    listed = await pt.list_autopr_staged_actions(project_id=uuid4(), task_id=uuid4())
    assert listed[0]["body"] == "the current draft"


@pytest.mark.asyncio
async def test_an_undeliverable_recipient_is_not_offered_a_send_button(monkeypatch):
    """The send route refuses a reserved test domain, so a card that still
    reported the row as retryable kept a Send button that 400s identically
    forever — neither sendable nor settled. It stays closable: a person can
    read what was proposed and mark it handled or dismissed."""
    from uuid import uuid4

    row = {**_LEGACY_ROW, "to": "vendor@example.com", "action_body": "hi"}
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_ListConn(row)))
    listed = await pt.list_autopr_staged_actions(project_id=uuid4(), task_id=uuid4())
    assert listed[0]["retryable"] is False
    assert listed[0]["closable"] is True

    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_GetConn(row)))
    got = await pt.get_autopr_staged_action(
        project_id=uuid4(), task_id=uuid4(), action_id=uuid4()
    )
    assert got["retryable"] is False


@pytest.mark.asyncio
async def test_a_deliverable_recipient_keeps_its_send_button(monkeypatch):
    from uuid import uuid4

    row = {**_LEGACY_ROW, "action_body": "hi"}
    monkeypatch.setattr(pt, "get_connection", lambda: _Ctx(_ListConn(row)))
    listed = await pt.list_autopr_staged_actions(project_id=uuid4(), task_id=uuid4())
    assert listed[0]["retryable"] is True


@pytest.mark.parametrize("kind", ["contact", "review_request"])
def test_only_an_email_can_be_undeliverable(kind):
    """Nothing hands a contact or review request to a mail server, so the
    recipient there is a person's name and no address guard applies."""
    assert not pt._staged_action_is_undeliverable(kind, "vendor@example.com")
    assert pt._staged_action_is_undeliverable("email", "vendor@example.com")


# ---------------------------------------------------------------------------
# The send route's failure handling.
# ---------------------------------------------------------------------------
def test_a_lost_reply_does_not_become_a_retryable_failure():
    """`send_email` runs against Gmail with a 30s timeout. A TransportError
    means the request went out and the reply was lost — the mail may well have
    been accepted. Recording `failed` there marks the row retryable and puts a
    Retry button on a delivered email, mailing the recipient twice from the
    approver's own mailbox. The claim is left standing instead, which is the
    existing "interrupted send" state: never re-sent, closable by a person who
    has checked their Sent folder."""
    import inspect

    from app.matcha.routes.matcha_work import task_history as th

    src = inspect.getsource(th.send_autopr_staged_action_endpoint)
    assert "httpx.TransportError" in src
    assert "if not delivery_unknown:" in src
    # The ceiling moved into the claim's own transaction; a separate read
    # beforehand is the race this route used to have.
    assert "max_recent_sends=" in src
    assert "count_recent_staged_sends" not in src


def test_an_undeliverable_recipient_is_reported_before_the_retryable_check():
    """Reporting such a row as not-retryable is what removes the dead Send
    button, but it also means the generic "already <state>" branch would fire
    first and hide the real reason from anyone calling the API directly."""
    import inspect

    from app.matcha.routes.matcha_work import task_history as th

    src = inspect.getsource(th.send_autopr_staged_action_endpoint)
    assert src.index("reserved test domain") < src.index('action["retryable"]')
