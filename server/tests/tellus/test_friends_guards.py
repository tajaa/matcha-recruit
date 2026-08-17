"""Source guards for friends' privacy, moderation, and transaction invariants."""
import inspect


def _code_only(obj) -> str:
    source = inspect.getsource(obj)
    doc = inspect.getdoc(obj)
    if doc:
        source = source.replace(doc, "")
    return "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))


def test_feed_copies_public_review_predicate():
    from app.tellus.routes import friends

    source = _code_only(friends.friend_activity_feed)
    assert "review_state = 'held'" in source
    assert "publish_at <= NOW()" in source
    assert "moderation_status = 'visible'" in source


def test_friends_routes_never_select_email():
    from app.tellus.routes import friends

    assert "email" not in _code_only(friends)


def test_feed_uses_keyset_cursor_and_bounded_branch_limits():
    from app.tellus.routes import friends

    source = _code_only(friends.friend_activity_feed)
    assert "decode_cursor" in source
    assert "ORDER BY r.publish_at DESC, r.id DESC LIMIT $4" in source
    assert "ORDER BY bf.created_at DESC, bf.brand_id DESC LIMIT $4" in source


def test_person_summaries_gate_scores_and_cached_suggestions_are_refiltered():
    from app.tellus.routes import friends

    summary_source = _code_only(friends._person_summary)
    assert "visible_sections" in summary_source
    assert '"points" in sections' in summary_source

    suggestions_source = _code_only(friends.friend_suggestions)
    assert "filter_suggestion_ids" in suggestions_source


def test_friend_invite_redeem_is_idempotent_for_existing_friendship():
    from app.tellus.routes import friends

    source = _code_only(friends.redeem_friend_invite)
    assert "existing_friendship" in source
    assert "use_count = use_count + 1" in source
    assert source.index("existing_friendship") < source.index("use_count = use_count + 1")


def test_handle_requests_respect_discovery_privacy():
    from app.tellus.routes import friends

    source = _code_only(friends.create_friend_request)
    assert "AND discoverable" in source
    assert "profile_visibility <> 'private'" in source


def test_social_mutations_hold_the_pair_lock_inside_a_transaction():
    from app.tellus.routes import friends
    from app.tellus.services import friends_service

    for name in ("create_friendship", "remove_friendship", "block_account"):
        source = _code_only(getattr(friends_service, name))
        assert "async with conn.transaction()" in source
        assert "lock_pair" in source
    assert "lock_pair" in _code_only(friends.accept_friend_request)
