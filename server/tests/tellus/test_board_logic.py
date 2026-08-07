"""Pure-function + model tests for the Tell-Us Regulars board (no DB).

DB-touching paths (join/approve/reply/redeem atomicity, points award) are
integration-level — run manually against dev per the repo's DB-test policy.
"""
import inspect
from uuid import uuid4

import pytest

from app.tellus.models.tellus import (
    BoardMembershipStatus,
    BoardReplyStatus,
    BoardPostKind,
    TellusBoardPostCreate,
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
