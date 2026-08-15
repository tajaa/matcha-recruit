"""_notify_huume_thread_of_offer_event (offer_letters.py) — the best-effort
helper that posts a system notice + bell notification into the matcha-work
thread that originated a signed/declined offer.

Prior bugs pinned here:
- lookup only worked via mw_threads.linked_offer_letter_id, a one-slot
  column repointed by whichever offer was drafted in a thread most recently
  — drafting a second candidate silently broke the first candidate's alert.
  source_thread_id (set once, at draft time) fixes that; this file asserts
  the new column is preferred and the old column still works as a fallback
  for pre-migration rows.
- the notification link was "/work/threads/{thread_id}" (wrong route,
  navigates to a thread literally named "threads") instead of "/work/{id}".
- thread_id was only bound partway through the try body, so a failure
  before that point raised NameError out of a "never raises" helper.

    cd server && ./venv/bin/python -m pytest tests/huume/test_notify_huume_offer_event.py -q
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.routes.employee_lifecycle import offer_letters as offer_letters_mod

MOD = "app.matcha.routes.employee_lifecycle.offer_letters"
DOC_MOD = "app.matcha.services.matcha_work.matcha_work_document"
NOTIFY_MOD = "app.matcha.services.notification_service"

COMPANY_ID = uuid4()
OFFER_ID = uuid4()
THREAD_ID = uuid4()
CREATOR_ID = uuid4()
APPROVER_ID = uuid4()
SENDER_ID = uuid4()


def _conn_ctx(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _base_offer(**overrides):
    offer = {
        "id": OFFER_ID, "company_id": COMPANY_ID, "status": "accepted",
        "candidate_name": "Jane Doe", "position_title": "Dental Assistant",
        "signed_name": "Jane Doe", "source_thread_id": None,
    }
    offer.update(overrides)
    return offer


def _patch_side_effects(monkeypatch):
    monkeypatch.setattr(f"{DOC_MOD}.add_message", AsyncMock(return_value={"id": uuid4()}))
    monkeypatch.setattr(f"{DOC_MOD}.apply_update", AsyncMock())
    bulk = AsyncMock()
    monkeypatch.setattr(f"{NOTIFY_MOD}.create_notifications_bulk", bulk)
    monkeypatch.setattr(
        "app.matcha.routes.work.thread_ws.thread_manager.broadcast_new_message",
        AsyncMock(),
    )
    return bulk


class TestNoThreadFound:
    @pytest.mark.asyncio
    async def test_returns_silently_when_nothing_matches(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value=None)
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        bulk = _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(), event="accepted", detail="signed",
        )
        bulk.assert_not_called()


class TestNeverRaises:
    @pytest.mark.asyncio
    async def test_get_connection_failure_does_not_raise(self, monkeypatch):
        # Fails before thread_id is ever bound — the exact shape of the
        # prior NameError bug. Must not propagate.
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(side_effect=RuntimeError("db down")))
        _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(), event="accepted", detail="signed",
        )  # no raise

    @pytest.mark.asyncio
    async def test_downstream_failure_after_thread_found_does_not_raise(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": THREAD_ID, "created_by": CREATOR_ID})
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        monkeypatch.setattr(f"{DOC_MOD}.apply_update", AsyncMock(side_effect=RuntimeError("boom")))
        monkeypatch.setattr(f"{DOC_MOD}.add_message", AsyncMock())
        monkeypatch.setattr(f"{NOTIFY_MOD}.create_notifications_bulk", AsyncMock())

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=THREAD_ID), event="accepted", detail="signed",
        )  # no raise


class TestThreadLookup:
    @pytest.mark.asyncio
    async def test_prefers_source_thread_id_over_reverse_lookup(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": THREAD_ID, "created_by": CREATOR_ID})
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=THREAD_ID), event="accepted", detail="signed",
        )

        first_query = conn.fetchrow.call_args_list[0].args[0]
        assert "FROM mw_threads t" in first_query
        assert conn.fetchrow.call_count == 1  # never falls through to the reverse lookup

    @pytest.mark.asyncio
    async def test_offer_sender_is_notified_when_not_thread_creator_or_approver(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={
            "id": THREAD_ID,
            "created_by": CREATOR_ID,
            "offer_sender_id": SENDER_ID,
        })
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        bulk = _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=THREAD_ID), event="accepted", detail="signed",
        )

        assert set(bulk.call_args.kwargs["user_ids"]) == {CREATOR_ID, SENDER_ID}
        assert "huume_assets" in conn.fetchrow.call_args.args[0]

    @pytest.mark.asyncio
    async def test_falls_back_to_linked_offer_letter_id_when_no_source_thread(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": THREAD_ID, "created_by": CREATOR_ID})
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=None), event="accepted", detail="signed",
        )

        query = conn.fetchrow.call_args_list[0].args[0]
        assert "linked_offer_letter_id" in query


class TestNotificationShape:
    @pytest.mark.asyncio
    async def test_link_is_work_thread_not_work_threads_thread(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": THREAD_ID, "created_by": CREATOR_ID})
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        bulk = _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=THREAD_ID), event="accepted", detail="signed",
        )

        assert bulk.call_args.kwargs["link"] == f"/work/{THREAD_ID}"
        assert "threads" not in bulk.call_args.kwargs["link"]

    @pytest.mark.asyncio
    async def test_recipients_are_creator_plus_hr_approvers_deduped(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": THREAD_ID, "created_by": CREATOR_ID})
        conn.fetch = AsyncMock(return_value=[{"id": CREATOR_ID}, {"id": APPROVER_ID}])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        bulk = _patch_side_effects(monkeypatch)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=THREAD_ID), event="accepted", detail="signed",
        )

        sent_ids = set(bulk.call_args.kwargs["user_ids"])
        assert sent_ids == {CREATOR_ID, APPROVER_ID}

    @pytest.mark.asyncio
    async def test_no_recipients_skips_notification_call_but_still_posts_message(self, monkeypatch):
        conn = MagicMock()
        conn.fetchrow = AsyncMock(return_value={"id": THREAD_ID, "created_by": None})
        conn.fetch = AsyncMock(return_value=[])
        monkeypatch.setattr(f"{MOD}.get_connection", MagicMock(return_value=_conn_ctx(conn)))
        bulk = _patch_side_effects(monkeypatch)
        add_message_mock = AsyncMock(return_value={"id": uuid4()})
        monkeypatch.setattr(f"{DOC_MOD}.add_message", add_message_mock)

        await offer_letters_mod._notify_huume_thread_of_offer_event(
            _base_offer(source_thread_id=THREAD_ID), event="accepted", detail="signed",
        )

        bulk.assert_not_called()
        add_message_mock.assert_called_once()
