"""Pure friends-domain tests; no database or network access."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.tellus.models.tellus import TellusHandleClaim
from app.tellus.services.friends_service import (
    FRIEND_DECLINE_COOLDOWN,
    can_request,
    decode_cursor,
    display_name_for,
    encode_cursor,
    handle_rejection_reason,
    normalize_handle,
    pair_key,
    visible_sections,
)


NOW = datetime(2026, 8, 16, tzinfo=timezone.utc)
ACCOUNT_A = UUID("00000000-0000-0000-0000-000000000001")
ACCOUNT_B = UUID("00000000-0000-0000-0000-000000000002")


def test_handle_normalization_and_boundaries():
    assert normalize_handle("  Finch_42 ") == "finch_42"
    assert TellusHandleClaim(handle="  Finch_42 ").handle == "finch_42"
    assert handle_rejection_reason("ab") == "format"
    assert handle_rejection_reason("a" * 21) == "format"
    assert handle_rejection_reason("member_a1b2") == "reserved"
    assert handle_rejection_reason("tellus_team") == "reserved"
    assert handle_rejection_reason("tellus_anything") == "reserved"
    assert handle_rejection_reason("finch", taken=True) == "taken"
    assert handle_rejection_reason("finch") is None


def test_pair_key_is_symmetric_and_stable():
    assert pair_key(ACCOUNT_A, ACCOUNT_B) == pair_key(ACCOUNT_B, ACCOUNT_A)
    assert pair_key(ACCOUNT_A, ACCOUNT_B) == (
        "00000000-0000-0000-0000-000000000001:"
        "00000000-0000-0000-0000-000000000002"
    )


def test_can_request_decline_cooldown():
    declined = NOW - FRIEND_DECLINE_COOLDOWN
    assert can_request("declined", declined + timedelta(days=1), NOW - timedelta(days=1)) is False
    assert can_request("declined", declined, NOW) is True
    assert can_request("pending", NOW, NOW) is False
    assert can_request("accepted", NOW, NOW) is False
    assert can_request("cancelled", NOW, NOW) is True
    assert can_request(None, None, NOW) is True


def test_visible_sections_truth_table():
    expected_profile = frozenset({"reviews", "followed_places", "boards"})
    expected_all = expected_profile | {"points", "badges"}
    for leaderboard_opt_in in (True, False):
        for visibility in ("private", "friends", "everyone"):
            for relationship, is_self, is_friend in (
                ("self", True, False),
                ("friend", False, True),
                ("stranger", False, False),
            ):
                visible = visible_sections(
                    is_self=is_self,
                    is_friend=is_friend,
                    profile_visibility=visibility,
                    leaderboard_opt_in=leaderboard_opt_in,
                )
                should_show = relationship == "self" or visibility == "everyone" or (
                    visibility == "friends" and relationship == "friend"
                )
                expected = expected_all if leaderboard_opt_in else expected_profile
                assert visible == (expected if should_show else frozenset())


def test_cursor_round_trip_and_malformed_input():
    cursor = encode_cursor(NOW, ACCOUNT_A)
    assert decode_cursor(cursor) == (NOW, ACCOUNT_A)
    assert decode_cursor("not-a-cursor") is None
    assert decode_cursor("") is None


def test_display_name_fallback_never_uses_email():
    assert display_name_for("Jane", "jane", ACCOUNT_A) == "Jane"
    assert display_name_for(None, "jane", ACCOUNT_A) == "jane"
    assert display_name_for(None, None, ACCOUNT_A) == "Member-0000"
