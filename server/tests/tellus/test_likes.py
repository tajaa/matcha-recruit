"""Pure-function + source-guard tests for Tell-Us likes (no DB).

DB-touching paths (idempotency race, auth matrix, cascade delete, N+1
hydration) are integration-level — run manually against dev per the repo's
DB-test policy. See server/app/tellus/CLAUDE.md.
"""
import inspect
from typing import get_args

from app.tellus.models.tellus import (
    TellusBoardPost,
    TellusBoardReply,
    TellusListing,
    TellusLikeState,
    TellusMyReview,
    TellusPublicReview,
    TellusReport,
)
from app.tellus.routes import likes as likes_routes
from app.tellus.services import likes_service


def _code_only(obj) -> str:
    """inspect.getsource() includes comments and docstrings — this module's
    prose deliberately explains the exact anti-patterns these guards forbid
    (e.g. "don't use ON CONFLICT (...)"), which would otherwise self-trigger
    a naive substring search. Strip '#' comment lines and the object's own
    docstring before scanning, so only executable code is checked."""
    src = inspect.getsource(obj)
    doc = inspect.getdoc(obj)
    if doc:
        src = src.replace(doc, "")
    return "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))


class TestLikeTargetContract:
    def test_target_columns_match_literal_type(self):
        """Drift guard: the path-param Literal and the column map must agree,
        or LikeTargetType lets FastAPI accept a target _TARGET_COLUMNS can't
        resolve — the Literal is what's supposed to make that impossible."""
        assert set(likes_service._TARGET_COLUMNS) == set(get_args(likes_routes.LikeTargetType))

    def test_target_columns_match_migration_columns(self):
        assert set(likes_service._TARGET_COLUMNS.values()) == {
            "post_id", "reply_id", "report_id", "listing_id",
        }


class TestLikeStateModel:
    def test_defaults(self):
        state = TellusLikeState()
        assert state.like_count == 0
        assert state.liked_by_me is False


class TestResponseModelFields:
    """Fields added but never populated is the classic bug here — pin the
    defaults so a missed endpoint degrades to 'no likes', not a 500."""

    def test_board_post_defaults(self):
        assert TellusBoardPost.model_fields["like_count"].default == 0
        assert TellusBoardPost.model_fields["liked_by_me"].default is False

    def test_board_reply_defaults(self):
        assert TellusBoardReply.model_fields["like_count"].default == 0
        assert TellusBoardReply.model_fields["liked_by_me"].default is False

    def test_public_review_defaults(self):
        assert TellusPublicReview.model_fields["like_count"].default == 0
        assert TellusPublicReview.model_fields["liked_by_me"].default is False

    def test_my_review_defaults(self):
        assert TellusMyReview.model_fields["like_count"].default == 0
        assert TellusMyReview.model_fields["liked_by_me"].default is False

    def test_listing_defaults(self):
        assert TellusListing.model_fields["like_count"].default == 0
        assert TellusListing.model_fields["liked_by_me"].default is False

    def test_report_has_like_count_but_not_liked_by_me(self):
        """TellusReport is the brand-dashboard model — brands can't like, and
        pairing liked_by_me next to the existing hearted_at would invite the
        exact heart/like confusion this feature must avoid."""
        assert "like_count" in TellusReport.model_fields
        assert "liked_by_me" not in TellusReport.model_fields


class TestLikeRouteSourceGuards:
    """inspect.getsource off imported symbols — repo pattern; never
    spec_from_file_location (breaks silently on file moves)."""

    def test_like_uses_bare_on_conflict_do_nothing(self):
        src = _code_only(likes_routes.like)
        assert "ON CONFLICT DO NOTHING" in src
        # partial unique indexes mean an inference spec (ON CONFLICT (col, account_id))
        # would fail to match them — the clause must stay bare.
        assert "ON CONFLICT (" not in src

    def test_like_never_catches_unique_violation(self):
        """A caught unique violation inside an open transaction leaves it
        aborted and the next query 500s (tellus/CLAUDE.md ledger-idempotency
        note) — ON CONFLICT DO NOTHING is the sanctioned shape instead."""
        assert "UniqueViolationError" not in _code_only(likes_routes.like)

    def test_like_count_not_a_data_modifying_cte(self):
        """WITH ins AS (INSERT ... RETURNING 1) SELECT COUNT(*) ... shares one
        snapshot with the CTE, so it can't see the row just inserted — the
        count comes back stale by one. Must be two separate statements."""
        assert "WITH " not in _code_only(likes_routes.like)

    def test_like_rate_limits_before_connection(self):
        src = inspect.getsource(likes_routes.like)
        assert src.index("check_rate_limit") < src.index("get_connection(")

    def test_like_and_unlike_wrap_write_and_count_in_one_transaction(self):
        for fn in (likes_routes.like, likes_routes.unlike):
            assert "async with conn.transaction():" in inspect.getsource(fn)

    def test_unlike_is_self_scoped_no_target_authorization(self):
        src = inspect.getsource(likes_routes.unlike)
        assert "account_id = $1" in src
        assert "assert_can_like" not in src

    def test_unlike_rate_limits_before_connection(self):
        src = inspect.getsource(likes_routes.unlike)
        assert src.index("check_rate_limit") < src.index("get_connection(")


class TestLikeAuthMatrixSourceGuards:
    def test_check_report_predicate(self):
        src = inspect.getsource(likes_service._check_report)
        assert "review_state = 'held'" in src
        assert "publish_at <= NOW()" in src
        assert "moderation_status = 'visible'" in src
        assert 'account_type != "consumer"' in src

    def test_check_board_post_predicate(self):
        src = inspect.getsource(likes_service._check_board_post)
        # Gated on moderation_status only for non-privileged callers; mods/owners
        # may preview (and like) their own not-yet-published or removed posts.
        assert "moderation_status" in src
        assert "is_privileged" in src

    def test_check_board_reply_predicate(self):
        src = inspect.getsource(likes_service._check_board_reply)
        assert "r.status = 'approved'" in src
        assert "p.moderation_status = 'visible'" in src

    def test_assert_board_access_checks_membership_and_pause(self):
        src = inspect.getsource(likes_service._assert_board_access)
        assert "tellus_brand_members" in src
        assert "get_approved_membership" in src
        assert "BOARD_PAUSED_DETAIL" in src

    def test_assert_board_access_exempts_privileged_from_is_active_pause(self):
        """Boards are born is_active=FALSE (board_service.ensure_board) — a
        moderator or owner previewing their own unpublished board must not
        409 on their own post. plan_status stays absolute for everyone."""
        src = _code_only(likes_service._assert_board_access)
        assert "is_privileged" in src
        assert 'row["plan_status"] != "active" or (not row["is_active"] and not is_privileged)' in src

    def test_check_listing_gates_on_active_and_visibility(self):
        src = inspect.getsource(likes_service._check_listing)
        assert "is_active" in src
        assert "visibility" in src

    def test_no_brand_heart_collision(self):
        """This is a consumer like, strictly disjoint from the brand's
        tellus_reports.hearted_at/hearted_by heart — neither symbol nor the
        require_paid_brand dependency should appear in this feature's CODE.
        (The module docstrings deliberately name hearted_at/hearted_by while
        explaining this exact disjointness — _code_only strips that prose.)"""
        for module in (likes_routes, likes_service):
            src = _code_only(module)
            assert "hearted_at" not in src
            assert "hearted_by" not in src
            assert "require_paid_brand" not in src


class TestPopulationSourceGuards:
    """Pins that every serving endpoint/serializer actually wires the like
    fields, not just that the model has defaults — the model default is what
    lets a missed one degrade quietly instead of 500ing, which is exactly
    why each one needs an explicit guard here."""

    def test_get_board_feed_populates_likes(self):
        from app.tellus.routes import board

        src = inspect.getsource(board.get_board)
        assert "tellus_likes" in src
        assert "liked_by_me" in src

    def test_update_post_populates_like_count(self):
        """The one most likely to be missed — a second counts fetchrow
        separate from the main feed query."""
        from app.tellus.routes import board

        src = inspect.getsource(board.update_post)
        assert "like_count" in src

    def test_list_and_create_reply_populate_likes(self):
        from app.tellus.routes import board

        assert "like" in inspect.getsource(board.list_replies)
        # create_reply constructs a brand-new reply — zero likes is correct
        # via the model default, so no query is required there.

    def test_shared_report_serializers_populate_likes(self):
        """serialize_report and serialize_reports are the chokepoint for
        every report-serving endpoint (~12) in feedback.py + admin/moderation.py."""
        from app.tellus.routes import _shared

        assert "tellus_likes" in inspect.getsource(_shared.serialize_report)
        assert "tellus_likes" in inspect.getsource(_shared.serialize_reports)

    def test_my_reviews_serializers_populate_likes(self):
        from app.tellus.routes import my_reviews

        assert "like_count" in inspect.getsource(my_reviews._serialize_my_review)
        assert "like_count" in inspect.getsource(my_reviews._serialize_my_reviews)

    def test_community_page_hydrates_likes_with_optional_auth(self):
        from app.tellus.routes import community

        src = inspect.getsource(community.public_brand_page)
        assert "hydrate_likes" in src
        assert "optional_consumer_account_id" in src

    def test_marketplace_hydrates_likes(self):
        from app.tellus.services import marketplace_service

        assert "tellus_likes" in inspect.getsource(marketplace_service.list_marketplace)
        assert "like_count" in inspect.getsource(marketplace_service.serialize_listing)

    def test_hydrate_likes_column_from_literal_dict_not_request_value(self):
        """The column name must come from the module-level _TARGET_COLUMNS
        dict, never be f-string'd directly from a request parameter."""
        src = inspect.getsource(likes_service.hydrate_likes)
        assert "_TARGET_COLUMNS[" in src
