"""DB-free guards for the broker↔company chat service.

The interesting invariants here are structural — "does this query still carry the
active-link predicate?" — so they're asserted against the SQL the module builds
rather than against a live database. That is deliberate: the bug these cover
(broker-side reads scoping only on broker_id, so a terminated broker kept the
whole history) was invisible to any test that only exercised the happy path with
a live link.
"""

import inspect

from app.matcha.services import broker_chat_service as svc


# --- preview -----------------------------------------------------------------

def test_preview_passes_short_bodies_through():
    assert svc.preview_text("hi") == "hi"


def test_preview_truncates_with_ellipsis_at_the_limit():
    body = "x" * (svc.PREVIEW_LIMIT + 50)
    out = svc.preview_text(body)
    assert out == "x" * svc.PREVIEW_LIMIT + "…"
    assert len(out) == svc.PREVIEW_LIMIT + 1


def test_preview_does_not_truncate_at_exactly_the_limit():
    body = "x" * svc.PREVIEW_LIMIT
    assert svc.preview_text(body) == body


# --- the active-link predicate ------------------------------------------------

def test_link_predicate_covers_both_sides_of_the_pair():
    """Matching on broker_id alone would let any linked broker read another's
    conversation with the same company (and vice versa)."""
    p = svc._ACTIVE_LINK_PREDICATE
    assert "l.broker_id = c.broker_id" in p
    assert "l.company_id = c.company_id" in p


def test_link_predicate_is_built_from_the_status_constant():
    """One source of truth: adding a status to ACTIVE_LINK_STATUSES must widen
    the SQL too, not just the Python helpers."""
    for status in svc.ACTIVE_LINK_STATUSES:
        assert f"'{status}'" in svc._ACTIVE_LINK_PREDICATE
    assert "'terminated'" not in svc._ACTIVE_LINK_PREDICATE


def _source(fn):
    return inspect.getsource(fn)


def test_every_read_path_carries_the_link_predicate():
    """A terminated relationship must hide the history from BOTH sides. The
    company side is incidentally safe (its broker_ids come from live links); the
    broker side has nothing but this predicate standing between an ex-broker and
    the full transcript."""
    for fn in (svc.list_conversations, svc.get_conversation, svc.total_unread):
        assert "_ACTIVE_LINK_PREDICATE" in _source(fn), fn.__name__


def test_message_mutations_carry_the_link_predicate():
    """Edit/delete never load the conversation, so the guard has to live in the
    UPDATE's own WHERE clause."""
    for fn in (svc.edit_message, svc.delete_message):
        assert "_ACTIVE_LINK_PREDICATE" in _source(fn), fn.__name__


# --- read watermark -----------------------------------------------------------

def test_mark_read_watermarks_on_the_message_not_on_now():
    """Stamping NOW() marked read anything that arrived during the read
    round-trip. The watermark must come from the acknowledged message's
    created_at, with NOW() only as the no-id fallback."""
    src = _source(svc.mark_read)
    assert "SELECT m.created_at FROM broker_company_messages m" in src
    assert "GREATEST(" in src  # never moves backwards


# --- idempotency scope --------------------------------------------------------

def test_send_idempotency_is_scoped_to_the_conversation():
    """A sender-wide key made a client_message_id reused across threads return
    the other thread's row with is_new=False — a silently dropped send."""
    src = _source(svc.post_message)
    assert "ON CONFLICT (conversation_id, sender_user_id, client_message_id)" in src


# --- conversation tail --------------------------------------------------------

def test_edit_and_delete_refresh_the_conversation_tail():
    """Otherwise a deleted message's text survives in both sidebars' preview."""
    for fn in (svc.edit_message, svc.delete_message):
        assert "_refresh_conversation_tail" in _source(fn), fn.__name__


def test_tail_refresh_ignores_deleted_messages():
    src = _source(svc._refresh_conversation_tail)
    assert "deleted_at IS NULL" in src
    assert "ORDER BY created_at DESC" in src
