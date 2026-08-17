"""Pure model tests for Tell-Us friends (no DB).

Covers: TellusAccount/TellusProfileUpdate carry the new friends fields, the
two _load_account-shaped loaders (dependencies.py and routes/auth.py) both
select every new column, and TellusPublicReview still exposes no account
identity — the exact invariant a friend feed must not violate.

DB-touching paths are integration-level — run manually per the repo's DB-test
policy. See server/app/tellus/CLAUDE.md.
"""
import inspect

from app.tellus import dependencies as tellus_dependencies
from app.tellus.models.tellus import (
    TellusAccount,
    TellusFriendActivityItem,
    TellusFriendRequest,
    TellusFriendRequestCreate,
    TellusFriendship,
    TellusHandleAvailability,
    TellusPersonProfile,
    TellusPersonSummary,
    TellusProfileUpdate,
    TellusPublicReview,
)
from app.tellus.routes import auth as auth_routes


def test_tellus_account_has_friends_fields():
    account = TellusAccount(id="00000000-0000-0000-0000-000000000001", email="a@example.com")
    assert account.handle is None
    assert account.profile_visibility == "friends"
    assert account.discoverable is True
    assert account.avatar_url is None
    assert account.handle_set_at is None


def test_tellus_profile_update_accepts_visibility_fields():
    update = TellusProfileUpdate(profile_visibility="everyone", discoverable=False)
    assert update.profile_visibility == "everyone"
    assert update.discoverable is False
    # Omitted fields stay None so a COALESCE UPDATE leaves them unchanged.
    assert update.display_name is None
    assert update.leaderboard_opt_in is None


def test_load_account_selects_are_kept_in_sync():
    """The single most likely omission in this feature: the columns exist,
    the model has them, but a loader's SELECT doesn't ask for them — every
    Depends(require_*) then silently returns model defaults. Two independent
    loaders construct TellusAccount (dependencies.py and routes/auth.py);
    both must select every new column."""
    new_columns = ["handle", "handle_set_at", "avatar_url", "profile_visibility", "discoverable"]

    dep_source = inspect.getsource(tellus_dependencies)
    auth_source = inspect.getsource(auth_routes)

    for column in new_columns:
        assert f"a.{column}" in dep_source, f"dependencies.py's SELECT is missing a.{column}"
        assert f"row[\"{column}\"]" in dep_source, f"dependencies.py's TellusAccount(...) is missing {column}"
        assert f"a.{column}" in auth_source, f"routes/auth.py's SELECT is missing a.{column}"
        assert f"row[\"{column}\"]" in auth_source, f"routes/auth.py's TellusAccount(...) is missing {column}"


def test_tellus_public_review_still_has_no_account_identity():
    """Pins the invariant a friend feed must not violate: reviewer_name is
    the ONLY identity field TellusPublicReview may ever carry. The friend
    feed needs account_id/handle/avatar_url on review rows — those belong on
    TellusFriendActivityItem, never bolted onto this model, or the
    unauthenticated /b/{slug} page starts leaking account ids (a
    de-anonymization vector, since reporter_account_id is nullable
    precisely because reviews can be anonymous)."""
    fields = TellusPublicReview.model_fields
    assert "account_id" not in fields
    assert "reporter_account_id" not in fields
    assert "reviewer_name" in fields


def test_friend_request_create_requires_exactly_one_target():
    ok_by_id = TellusFriendRequestCreate(account_id="00000000-0000-0000-0000-000000000002")
    assert ok_by_id.account_id is not None
    ok_by_handle = TellusFriendRequestCreate(handle="jane")
    assert ok_by_handle.handle == "jane"

    import pytest

    with pytest.raises(ValueError):
        TellusFriendRequestCreate()
    with pytest.raises(ValueError):
        TellusFriendRequestCreate(account_id="00000000-0000-0000-0000-000000000002", handle="jane")


def test_person_profile_sections_default_to_hidden_not_empty():
    """Absent-section-is-None (not []) is how the client tells "private" from
    "has none". A profile built with no section kwargs must decode to None
    on every section, never an implicit empty list."""
    profile = TellusPersonProfile(account_id="00000000-0000-0000-0000-000000000001", display_name="Jane")
    assert profile.reviews is None
    assert profile.followed_places is None
    assert profile.badges is None
    assert profile.boards is None


def test_person_summary_has_no_email_field():
    """Friend search/suggestions must never expose email."""
    assert "email" not in TellusPersonSummary.model_fields


def test_handle_availability_reason_optional():
    available = TellusHandleAvailability(handle="jane", available=True)
    assert available.reason is None
    taken = TellusHandleAvailability(handle="jane", available=False, reason="taken")
    assert taken.reason == "taken"


def test_friendship_and_activity_item_shapes():
    person = TellusPersonSummary(account_id="00000000-0000-0000-0000-000000000001", display_name="Jane")
    friendship = TellusFriendship(friend=person, created_at="2026-01-01T00:00:00Z")
    assert friendship.friend.account_id == person.account_id

    item = TellusFriendActivityItem(
        id="review:1", kind="review_published", actor=person, happened_at="2026-01-01T00:00:00Z"
    )
    assert item.kind == "review_published"
    assert item.rating is None
