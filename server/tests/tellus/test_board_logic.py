"""Pure-function + model tests for the Tell-Us Regulars board (no DB).

DB-touching paths (join/approve/reply/redeem atomicity, points award) are
integration-level — run manually against dev per the repo's DB-test policy.
"""
import inspect
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.tellus.models.tellus import (
    BoardMembershipStatus,
    BoardReplyStatus,
    BoardPostKind,
    TellusBoardManageReplyRow,
    TellusBoardPostCreate,
    TellusBoardPostUpdate,
    TellusBoardReplyCreate,
    TellusListingCreate,
)
from app.tellus.services.board_service import can_reply_transition, reply_visible_to

AUTHOR = uuid4()
OTHER_MEMBER = uuid4()


class TestReplyVisibility:
    def test_approved_visible_to_everyone(self):
        assert reply_visible_to("approved", AUTHOR, AUTHOR, False) is True
        assert reply_visible_to("approved", AUTHOR, OTHER_MEMBER, False) is True
        assert reply_visible_to("approved", AUTHOR, OTHER_MEMBER, True) is True

    def test_held_visible_to_author_only(self):
        assert reply_visible_to("held", AUTHOR, AUTHOR, False) is True
        assert reply_visible_to("held", AUTHOR, OTHER_MEMBER, False) is False

    def test_held_visible_to_mod(self):
        assert reply_visible_to("held", AUTHOR, OTHER_MEMBER, True) is True

    def test_rejected_author_and_mod_only(self):
        assert reply_visible_to("rejected", AUTHOR, AUTHOR, False) is True
        assert reply_visible_to("rejected", AUTHOR, OTHER_MEMBER, True) is True
        assert reply_visible_to("rejected", AUTHOR, OTHER_MEMBER, False) is False

    def test_removed_mod_only_not_author(self):
        assert reply_visible_to("removed", AUTHOR, AUTHOR, False) is False
        assert reply_visible_to("removed", AUTHOR, OTHER_MEMBER, True) is True

    def test_unknown_status_fails_closed(self):
        assert reply_visible_to("flagged", AUTHOR, OTHER_MEMBER, False) is False


class TestReplyTransitions:
    def test_held_to_approved(self):
        assert can_reply_transition("held", "approved") is True

    def test_held_to_rejected(self):
        assert can_reply_transition("held", "rejected") is True

    def test_approved_to_removed(self):
        assert can_reply_transition("approved", "removed") is True

    def test_no_unreject(self):
        assert can_reply_transition("rejected", "approved") is False

    def test_no_unremove(self):
        assert can_reply_transition("removed", "approved") is False

    def test_identity_transitions_false(self):
        for s in ("held", "approved", "rejected", "removed"):
            assert can_reply_transition(s, s) is False

    def test_full_matrix_size(self):
        statuses = ("held", "approved", "rejected", "removed")
        allowed = sum(
            can_reply_transition(a, b) for a in statuses for b in statuses
        )
        assert allowed == 3


class TestBoardModels:
    def test_deal_post_requires_listing(self):
        with pytest.raises(ValueError):
            TellusBoardPostCreate(kind="deal", title="50% off")

    def test_deal_post_with_listing_ok(self):
        post = TellusBoardPostCreate(kind="deal", title="50% off", listing_id=uuid4())
        assert post.listing_id is not None

    def test_reply_body_bounds(self):
        with pytest.raises(ValueError):
            TellusBoardReplyCreate(body="")
        with pytest.raises(ValueError):
            TellusBoardReplyCreate(body="x" * 4001)
        TellusBoardReplyCreate(body="x" * 4000)

    def test_membership_status_literals_match_migration(self):
        assert set(BoardMembershipStatus.__args__) == {
            "pending", "approved", "declined", "removed", "left", "cancelled",
        }

    def test_reply_status_literals_match_migration(self):
        assert set(BoardReplyStatus.__args__) == {"held", "approved", "rejected", "removed"}

    def test_post_kind_literals_match_migration(self):
        assert set(BoardPostKind.__args__) == {"update", "deal", "event", "question"}


class TestBoardPostUpdateContract:
    """update_post's model_fields_set-based UPDATE (routes/board.py) depends on
    Pydantic distinguishing an explicit null from an omitted field — pin that
    contract directly so a pydantic version bump or model refactor can't
    silently reintroduce the COALESCE bug (an explicit null becoming a no-op)."""

    def test_fields_set_distinguishes_omitted_from_explicit_null(self):
        assert TellusBoardPostUpdate().model_fields_set == set()
        assert TellusBoardPostUpdate(body=None).model_fields_set == {"body"}

    def test_event_fields_round_trip(self):
        start = datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)
        end = datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc)
        update = TellusBoardPostUpdate(event_starts_at=start, event_ends_at=end)
        assert update.event_starts_at == start
        assert update.event_ends_at == end
        assert update.model_fields_set == {"event_starts_at", "event_ends_at"}


class TestBoardManageReplyRow:
    def test_constructs_from_row_shape(self):
        row = TellusBoardManageReplyRow(
            id=uuid4(), post_id=uuid4(), post_title="Happy hour", author_name="Jane",
            body="Count me in", status="held", created_at=datetime.now(timezone.utc),
        )
        assert row.status == "held"

    def test_status_rejects_unknown_value(self):
        with pytest.raises(ValidationError):
            TellusBoardManageReplyRow(
                id=uuid4(), post_id=uuid4(), post_title="Happy hour", author_name="Jane",
                body="Count me in", status="aproved", created_at=datetime.now(timezone.utc),
            )


class TestListingVisibility:
    def test_default_public(self):
        listing = TellusListingCreate(title="Free coffee", points_cost=100)
        assert listing.visibility == "public"

    def test_board_roundtrip(self):
        listing = TellusListingCreate(title="Regulars only", points_cost=100, visibility="board")
        assert listing.visibility == "board"


class TestBoardSourceGuards:
    """inspect.getsource off imported symbols — repo pattern; never
    spec_from_file_location (breaks silently on file moves)."""

    def test_approve_award_uses_engagement_reason(self):
        from app.tellus.services.board_service import approve_reply_and_award

        src = inspect.getsource(approve_reply_and_award)
        assert "earn_engagement" in src
        assert "bypass_cooldown=True" in src

    def test_no_caught_unique_violation_around_reply_approve(self):
        from app.tellus import routes

        src = inspect.getsource(routes.board)
        # Join/team inserts MAY catch UniqueViolationError (they do, by
        # design); pin that the approve handlers specifically don't wrap
        # bs.approve_reply_and_award in one — a caught error there would
        # abort the enclosing savepoint instead of returning a clean 409.
        approve_fn_src = inspect.getsource(routes.board.approve_reply)
        assert "except asyncpg.UniqueViolationError" not in approve_fn_src

    def test_marketplace_filters_public(self):
        from app.tellus.services.marketplace_service import list_marketplace

        assert "visibility = 'public'" in inspect.getsource(list_marketplace)

    def test_join_precheck_before_insert(self):
        """The duplicate-membership pre-check must run BEFORE the INSERT, not
        just live in an except block — a caught UniqueViolationError inside
        an already-open (non-savepoint) transaction aborts it and turns the
        next query in the handler into a 500 (see tellus/CLAUDE.md's ledger-
        idempotency note). Pin that the pre-check SELECT precedes the INSERT,
        and that the INSERT itself opens its own nested transaction."""
        from app.tellus import routes

        src = inspect.getsource(routes.board.request_join)
        precheck_idx = src.index("SELECT status FROM tellus_board_memberships")
        insert_idx = src.index("INSERT INTO tellus_board_memberships")
        assert precheck_idx < insert_idx
        # the INSERT must be inside its own nested `async with conn.transaction():`
        # (a savepoint), not the outer one opened at the top of the handler
        between = src[precheck_idx:insert_idx]
        assert "async with conn.transaction():" in between

    def test_nondeal_posts_cannot_carry_listing(self):
        from app.tellus import routes

        src = inspect.getsource(routes.board.create_post)
        assert 'listing_id = body.listing_id if body.kind == "deal" else None' in src

    def test_feed_listing_embed_brand_scoped(self):
        from app.tellus import routes

        src = inspect.getsource(routes.board.get_board)
        assert "AND l.brand_id = $2" in src

    def test_reply_transitions_wired_into_moderator_routes(self):
        """can_reply_transition must actually gate approve/reject/remove_reply,
        not just exist as a tested-but-uncalled pure function (the gap this PR
        closed — see tellus/CLAUDE.md's Regulars board section)."""
        from app.tellus import routes

        for fn in (routes.board.approve_reply, routes.board.reject_reply, routes.board.remove_reply):
            assert "can_reply_transition(" in inspect.getsource(fn)

    def test_board_management_requires_active_board_capability(self):
        from app.tellus.services import board_service

        src = inspect.getsource(board_service.resolve_moderated_brand)
        assert "status = 'active'" in src
        assert '"board.manage"' in src
        assert "account.account_type" not in src
        assert "account.brand_id" not in src

    def test_board_feed_uses_capability_for_moderator_visibility(self):
        from app.tellus import routes

        for fn in (routes.board.get_board, routes.board.list_replies, routes.board.create_reply):
            src = inspect.getsource(fn)
            assert "find_brand_access" in src
            assert '"board.manage"' in src

    def test_request_join_blocks_declined_and_removed(self):
        from app.tellus import routes

        src = inspect.getsource(routes.board.request_join)
        assert '"declined", "removed"' in src or "'declined', 'removed'" in src

    def test_notification_fanout_casts_params(self):
        """asyncpg can fail to infer parameter types inside an INSERT...SELECT
        target list — the ::text casts on $2-$6 are load-bearing, not
        decoration. See services/board_service.py's notify_board_members
        docstring."""
        from app.tellus.services import board_service

        for fn in (board_service.notify_board_members, board_service.notify_board_team):
            src = inspect.getsource(fn)
            assert "$2::text" in src
            assert "$6::text" in src
