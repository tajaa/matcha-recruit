"""Pure and fake-connection coverage for shoutout radar safety invariants."""
import asyncio
import inspect
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.tellus.models.shoutouts import ShoutoutTestPostIn
from app.tellus.services.shoutout import grounding, scan_service


def test_url_fingerprint_collapses_social_variants():
    assert grounding.url_fingerprint("instagram", "https://www.instagram.com/p/post/?utm_source=x") == grounding.url_fingerprint(
        "instagram", "https://instagram.com/p/post"
    )
    assert grounding.url_fingerprint("x", "https://twitter.com/a/status/1") == grounding.url_fingerprint(
        "x", "https://x.com/a/status/1"
    )
    assert grounding.url_fingerprint("youtube", "https://youtu.be/abc") == grounding.url_fingerprint(
        "youtube", "https://youtube.com/watch?v=abc"
    )


def test_grounding_gate_drops_model_url_absent_from_search_response():
    result = grounding.corroborated_candidates(
        [{"platform": "instagram", "url": "https://instagram.com/p/hallucinated"}],
        ["https://instagram.com/p/real"],
    )
    assert result.accepted == []
    assert result.source_mismatch == 1


def test_grounding_gate_accepts_matching_result():
    result = grounding.corroborated_candidates(
        [{"platform": "instagram", "url": "https://www.instagram.com/p/real/?utm_source=search"}],
        ["https://instagram.com/p/real"],
    )
    assert result.source_mismatch == 0
    assert result.accepted[0]["canonical_url"] == "https://instagram.com/p/real"
    assert result.accepted[0]["grounding_uri"] == "https://instagram.com/p/real"


def test_grounding_gate_accepts_three_candidates_from_three_sources():
    result = grounding.corroborated_candidates(
        [
            {"platform": "instagram", "url": "https://instagram.com/p/one"},
            {"platform": "instagram", "url": "https://instagram.com/p/two"},
            {"platform": "instagram", "url": "https://instagram.com/p/three"},
        ],
        [
            "https://instagram.com/p/one?utm_source=openai",
            "https://instagram.com/p/two?utm_source=openai",
            "https://instagram.com/p/three?utm_source=openai",
        ],
    )
    assert len(result.accepted) == 3
    assert result.invalid_url == 0
    assert result.source_mismatch == 0


def test_grounding_gate_separates_invalid_urls_from_source_mismatches():
    result = grounding.corroborated_candidates(
        [
            {"platform": "instagram", "url": "https://x.com/customer/status/1"},
            {"platform": "instagram", "url": "https://instagram.com/p/missing"},
        ],
        ["https://instagram.com/p/real"],
    )
    assert result.invalid_url == 1
    assert result.source_mismatch == 1


def test_manual_query_scopes_to_the_handles_platform_and_result_limit():
    from app.tellus.services.shoutout.prompt import build_query

    query = build_query(
        brand_name="Cafe", handles=[{"platform": "instagram", "handle": "cafe"}], brand_terms=[],
        city=None, state=None, lookback_days=14, focus="manual_handle", max_results=10,
    )
    assert "site:instagram.com" in query.q
    assert '"@cafe"' in query.q
    assert "cafe" in query.match_terms
    assert query.num == 10


def test_handles_and_terms_queries_cover_all_platforms_and_exclusions():
    from app.tellus.services.shoutout.prompt import build_query

    query = build_query(
        brand_name="Cafe", handles=[{"platform": "instagram", "handle": "cafe"}], brand_terms=["matcha latte"],
        exclude_terms=["giveaway"], city="Austin", state="TX", lookback_days=14, focus="terms",
    )
    assert "site:tiktok.com" in query.q
    assert "site:youtube.com" in query.q
    assert '"matcha latte"' in query.q
    assert "Austin" in query.q and "TX" in query.q
    assert '-"giveaway"' in query.q


def test_brand_own_handle_scores_zero_and_terms_must_be_in_excerpt():
    assert scan_service.score_candidate(
        {"author_handle": "Brand", "confidence": 99, "excerpt": "great", "matched_terms": ["great"]}, {"brand"}
    ) == 0
    assert scan_service.score_candidate(
        {"author_handle": "fan", "confidence": 50, "excerpt": "Lovely place", "matched_terms": ["not present"]}, set()
    ) == 50


def test_invalid_model_values_are_skipped_before_database_writes():
    assert scan_service.valid_candidate({"platform": "other", "url": "https://example.com", "confidence": 10}) is None
    assert scan_service.valid_candidate({"platform": "instagram", "url": "https://instagram.com/p/a", "confidence": "90"}) is None
    assert scan_service.valid_candidate({"platform": "instagram", "url": "https://instagram.com/p/a", "confidence": 90, "matched_terms": [1]}) is None
    assert scan_service.valid_candidate({
        "platform": "instagram", "url": "https://instagram.com/p/a", "confidence": 90,
        "matched_terms": ["coffee"], "excerpt": "Great coffee",
    }) is not None


def test_reseen_update_never_touches_status_or_catches_unique_violation():
    source = inspect.getsource(scan_service.scan_brand)
    assert "ON CONFLICT DO NOTHING" in source
    update = source[source.index("UPDATE tellus_shoutout_mentions"):]
    assert "status=" not in update.split('"""', 1)[0]
    assert "UniqueViolationError" not in inspect.getsource(scan_service)


def test_organic_results_are_parsed_into_mentions_with_matched_terms():
    from app.tellus.services.shoutout import provider

    result = provider._organic_results_to_mentions(
        {
            "organic_results": [
                {
                    "link": "https://www.instagram.com/p/real/",
                    "title": "Best matcha latte in town",
                    "snippet": "Just had the matcha latte at Cafe, so good!",
                },
                {"link": "https://example.com/blog/cafe-review", "title": "Cafe review", "snippet": "..."},
                {"link": "not-a-real-url"},
                None,
            ],
        },
        match_terms=["matcha latte", "cafe"],
    )
    assert len(result.mentions) == 1
    mention = result.mentions[0]
    assert mention["platform"] == "instagram"
    assert mention["url"] == "https://www.instagram.com/p/real/"
    assert mention["matched_terms"] == ["matcha latte", "cafe"]
    assert mention["confidence"] == 60
    assert result.grounding_uris == ["https://www.instagram.com/p/real/"]
    assert result.grounding_resolved == 1


def test_organic_results_platform_host_map_covers_all_known_domains():
    from app.tellus.services.shoutout import provider

    assert provider._platform_for_url("https://youtu.be/abc") == "youtube"
    assert provider._platform_for_url("https://www.tiktok.com/@cafe/video/1") == "tiktok"
    assert provider._platform_for_url("https://twitter.com/a/status/1") == "x"
    assert provider._platform_for_url("https://fb.com/cafe/posts/1") == "facebook"
    assert provider._platform_for_url("https://unrelated.com/post") is None


def test_provider_requests_google_engine_and_returns_grounding_uris(monkeypatch):
    from app.tellus.services.shoutout import provider
    from app.tellus.services.shoutout.prompt import SearchQuery

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "organic_results": [
                    {"link": "https://instagram.com/p/real", "title": "Cafe", "snippet": "matcha latte"},
                ],
            }

    class FakeClient:
        def __init__(self):
            self.params = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, _url, *, params):
            self.params = params
            return FakeResponse()

    client = FakeClient()
    monkeypatch.setattr(provider, "get_settings", lambda: SimpleNamespace(serp_api_key="test-key"))
    monkeypatch.setattr(provider.httpx, "AsyncClient", lambda **_: client)

    query = SearchQuery(q='site:instagram.com "matcha latte"', match_terms=["matcha latte"], num=20)
    result = asyncio.run(provider.SerpApiProvider().search(query))

    assert client.params["engine"] == "google"
    assert client.params["q"] == query.q
    assert client.params["num"] == 20
    assert client.params["api_key"] == "test-key"
    assert result.grounding_uris == ["https://instagram.com/p/real"]
    assert result.grounding_resolved == 1


def test_provider_requires_serp_api_key(monkeypatch):
    from app.tellus.services.shoutout import provider
    from app.tellus.services.shoutout.prompt import SearchQuery

    monkeypatch.setattr(provider, "get_settings", lambda: SimpleNamespace(serp_api_key=None))
    with pytest.raises(RuntimeError, match="SERP_API_KEY"):
        asyncio.run(provider.SerpApiProvider().search(SearchQuery(q="anything", match_terms=[], num=20)))


def test_source_field_yields_the_author_username():
    from app.tellus.services.shoutout.provider import _author_handle_from_source

    assert _author_handle_from_source("Instagram · faelpt") == "faelpt"
    assert _author_handle_from_source("Instagram") is None
    assert _author_handle_from_source("Instagram · __balancedwithbritt") == "__balancedwithbritt"
    assert _author_handle_from_source("YouTube · Some Channel Name") is None
    assert _author_handle_from_source(None) is None


def test_displayed_link_parses_like_count_and_age():
    from app.tellus.services.shoutout.provider import _engagement_from_displayed_link

    assert _engagement_from_displayed_link("12K+ likes · 6 days ago") == (12000, "6 days ago")
    assert _engagement_from_displayed_link("1.2K+ likes · 2 weeks ago") == (1200, "2 weeks ago")
    assert _engagement_from_displayed_link("847 likes") == (847, None)
    assert _engagement_from_displayed_link("1,234 likes · 1 day ago") == (1234, "1 day ago")
    assert _engagement_from_displayed_link("291.4M+ followers") == (None, None)
    assert _engagement_from_displayed_link("https://www.instagram.com › nike") == (None, None)


def test_profile_and_tab_urls_are_not_post_urls():
    from app.tellus.services.shoutout.grounding import is_post_url

    assert is_post_url("instagram", "https://www.instagram.com/nike/") is False
    assert is_post_url("instagram", "https://www.instagram.com/nike/reels/") is False
    assert is_post_url("instagram", "https://www.instagram.com/explore/tags/nike/") is False
    assert is_post_url("instagram", "https://www.instagram.com/p/ABC/") is True
    assert is_post_url("instagram", "https://www.instagram.com/reel/ABC/") is True
    assert is_post_url("instagram", "https://www.instagram.com/someuser/p/ABC/") is True
    assert is_post_url("youtube", "https://youtu.be/abc") is True
    assert is_post_url("youtube", "https://www.youtube.com/watch") is False
    assert is_post_url("youtube", "https://www.youtube.com/watch?v=abc") is True
    assert is_post_url("x", "https://x.com/user/status/1") is True
    assert is_post_url("x", "https://x.com/user") is False


def test_organic_results_drop_profile_pages_and_keep_posts():
    from app.tellus.services.shoutout import provider

    payload = {
        "organic_results": [
            {"position": 1, "source": "Instagram · nike", "displayed_link": "291.4M+ followers", "link": "https://www.instagram.com/nike/", "title": "Nike (@nike)", "snippet": "291M followers"},
            {"position": 2, "source": "Instagram · faelpt", "displayed_link": "12K+ likes · 6 days ago", "link": "https://www.instagram.com/p/DcJGYgYN8mu/", "title": "Pick Nike's best year", "snippet": "nike shoutout"},
            {"position": 4, "source": "Instagram", "displayed_link": "https://www.instagram.com › nike", "link": "https://www.instagram.com/nike/reels/", "title": "Nike (@nike)", "snippet": "reels"},
        ],
    }
    result = provider._organic_results_to_mentions(payload, match_terms=["nike"])
    urls = [mention["url"] for mention in result.mentions]
    assert urls == ["https://www.instagram.com/p/DcJGYgYN8mu/"]
    assert result.grounding_uris == ["https://www.instagram.com/p/DcJGYgYN8mu/"]


def test_organic_results_carry_handle_like_count_and_age():
    from app.tellus.services.shoutout import provider

    payload = {
        "organic_results": [
            {"source": "Instagram · faelpt", "displayed_link": "12K+ likes · 6 days ago", "link": "https://www.instagram.com/p/DcJGYgYN8mu/", "title": "nike", "snippet": "nike shoutout"},
        ],
    }
    result = provider._organic_results_to_mentions(payload, match_terms=["nike"])
    mention = result.mentions[0]
    assert mention["author_handle"] == "faelpt"
    assert mention["like_count"] == 12000
    assert mention["posted_age"] == "6 days ago"
    assert mention["stats_source"] == "search"


def test_instagram_shortcode_extraction():
    from app.tellus.services.shoutout.grounding import instagram_shortcode

    assert instagram_shortcode("https://www.instagram.com/p/DcJGYgYN8mu/") == "DcJGYgYN8mu"
    assert instagram_shortcode("https://www.instagram.com/reel/DbtWjltNpkX/") == "DbtWjltNpkX"
    assert instagram_shortcode("https://www.instagram.com/nike/") is None


def test_match_post_returns_exact_counts():
    from app.tellus.services.shoutout.instagram_stats import match_post

    payload = {
        "profile_results": {
            "followers": 95095,
            "is_verified": True,
            "posts": [
                {
                    "shortcode": "Db3wmd8FyUx", "liked_by_count": 1754, "comments_count": 8,
                    "comments_disabled": False, "like_and_view_counts_disabled": False,
                    "display_url": "https://instagram.frst1-1.fna.fbcdn.net/signed-and-expiring.jpg",
                    "serpapi_display_url": "https://serpapi.com/images/url/stable-proxy.jpg",
                },
                {"shortcode": "DbtWjltNpkX", "liked_by_count": 1181, "comments_count": 20, "comments_disabled": False, "like_and_view_counts_disabled": False},
            ],
        },
    }
    stats = match_post(payload, "Db3wmd8FyUx")
    assert stats.liked_by_count == 1754
    assert stats.comments_count == 8
    assert stats.followers == 95095
    assert stats.is_verified is True
    assert stats.image_url == "https://serpapi.com/images/url/stable-proxy.jpg"
    assert match_post(payload, "unknown") is None
    assert match_post(payload, "DbtWjltNpkX").image_url is None


def test_valid_candidate_rejects_bad_stat_types():
    base = {
        "platform": "instagram", "url": "https://instagram.com/p/a", "confidence": 90,
        "matched_terms": ["coffee"], "excerpt": "Great coffee",
    }
    assert scan_service.valid_candidate({**base, "like_count": "12"}) is None
    assert scan_service.valid_candidate({**base, "like_count": True}) is None
    assert scan_service.valid_candidate({**base, "like_count": -1}) is None
    assert scan_service.valid_candidate({**base, "like_count": None}) is not None
    assert scan_service.valid_candidate({**base, "like_count": 12}) is not None
    assert scan_service.valid_candidate({**base, "posted_age": 5}) is None
    assert scan_service.valid_candidate({**base, "posted_age": "6 days ago"}) is not None


def test_duplicate_scan_backfills_handle_without_clobbering_exact_counts():
    source = inspect.getsource(scan_service.scan_brand)
    assert "author_handle=COALESCE(author_handle,$4::text)" in source
    assert "WHEN stats_source='profile_api' THEN like_count" in source


def test_stats_fetch_skips_the_provider_for_unsupported_mentions():
    from app.tellus.services.shoutout import instagram_stats

    class _ExplodingProvider:
        pass

    async def _exploding_fetch(handle):
        raise AssertionError("provider must not be called for an unsupported mention")

    class _Conn:
        def __init__(self, row):
            self.row = row

        async def fetchrow(self, query, *args):
            if "SELECT platform, canonical_url" in query:
                return self.row
            return {
                "like_count": None, "comment_count": None, "author_followers": None, "author_verified": None,
                "posted_age": None, "stats_source": None, "stats_status": "unsupported", "stats_fetched_at": None,
            }

        async def execute(self, *_):
            return None

    import app.tellus.services.shoutout.instagram_stats as mod
    original = mod.fetch_profile_posts
    mod.fetch_profile_posts = _exploding_fetch
    try:
        tiktok_mention = {
            "platform": "tiktok", "canonical_url": "https://tiktok.com/@x/video/1",
            "author_handle": "x", "stats_source": None, "stats_fetched_at": None,
        }
        result = asyncio.run(instagram_stats.fetch_mention_stats(_Conn(tiktok_mention), brand_id=uuid4(), mention_id=uuid4()))
        assert result["stats_status"] == "unsupported"

        no_handle_mention = {
            "platform": "instagram", "canonical_url": "https://instagram.com/p/a",
            "author_handle": None, "stats_source": None, "stats_fetched_at": None,
        }
        result = asyncio.run(instagram_stats.fetch_mention_stats(_Conn(no_handle_mention), brand_id=uuid4(), mention_id=uuid4()))
        assert result["stats_status"] == "unsupported"
    finally:
        mod.fetch_profile_posts = original


def test_stats_fetch_is_cached_for_24_hours():
    from datetime import datetime, timedelta, timezone
    from app.tellus.services.shoutout import instagram_stats

    fresh = datetime.now(timezone.utc) - timedelta(hours=1)
    cached_row = {
        "like_count": 100, "comment_count": 5, "author_followers": 1000, "author_verified": True,
        "posted_age": "1 day ago", "stats_source": "profile_api", "stats_status": "ok", "stats_fetched_at": fresh,
    }

    class _Conn:
        async def fetchrow(self, query, *args):
            if "SELECT platform, canonical_url" in query:
                return {
                    "platform": "instagram", "canonical_url": "https://instagram.com/p/a",
                    "author_handle": "x", "stats_source": "profile_api", "stats_fetched_at": fresh,
                }
            return cached_row

        async def execute(self, *_):
            raise AssertionError("must not write when serving from cache")

    async def _exploding_fetch(handle):
        raise AssertionError("provider must not be called when serving from cache")

    original = instagram_stats.fetch_profile_posts
    instagram_stats.fetch_profile_posts = _exploding_fetch
    try:
        result = asyncio.run(instagram_stats.fetch_mention_stats(_Conn(), brand_id=uuid4(), mention_id=uuid4()))
        assert result == cached_row
    finally:
        instagram_stats.fetch_profile_posts = original


def test_scan_run_uses_real_resolution_count_and_failure_backoff():
    source = inspect.getsource(scan_service.scan_brand)
    assert "grounding_resolved = sum" in source
    assert "gemini_calls=$2" in source
    assert "source_mismatch_rejected=$7" in source
    assert "invalid_candidates_rejected=$8" in source
    assert "below_confidence_rejected=$9" in source
    assert "asyncio.gather" in source
    assert "next_scan_after=NOW()" in source
    assert "mentions = mentions[:manual_max_results]" in source
    assert 'mention.get("platform") == manual_handle["platform"]' in source


class _ManualCooldownConn:
    def transaction(self):
        return _Transaction()

    async def execute(self, *_):
        return None

    async def fetchval(self, *_):
        return 1


def test_manual_scan_enforces_its_cooldown_before_a_provider_call():
    with pytest.raises(scan_service.ManualScanError, match="Wait 30 seconds") as error:
        asyncio.run(scan_service.scan_brand(_ManualCooldownConn(), uuid4(), trigger="manual", force=True))
    assert error.value.status == 429
    assert error.value.code == "manual_scan_cooldown"


def test_manual_scan_allows_an_immediate_retry_after_a_failure():
    source = inspect.getsource(scan_service.scan_brand)
    assert "status <> 'failed'" in source


def test_config_enablement_returns_the_actual_primary_key_and_dedupes_handles():
    from app.tellus.services.shoutout import config_service

    source = inspect.getsource(config_service)
    assert "RETURNING brand_id" in source
    assert "seen_handles" in source


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False


class _TestPostConn:
    def __init__(self):
        self.run_id = uuid4()
        self.mention_id = uuid4()
        self.queries = []

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if "SELECT brand_terms" in query:
            return {"brand_terms": ["matcha"]}
        if "INSERT INTO tellus_shoutout_scan_runs" in query:
            return {"id": self.run_id}
        if "INSERT INTO tellus_shoutout_mentions" in query:
            return {"id": self.mention_id}
        raise AssertionError(f"Unexpected query: {query}")

    async def execute(self, query, *args):
        self.queries.append((query, args))


def test_test_post_creates_a_labeled_ungrounded_run_and_mention():
    conn = _TestPostConn()
    data = ShoutoutTestPostIn(
        platform="instagram", post_url="https://instagram.com/p/example?utm_source=test",
        author_handle="@HappyCustomer", excerpt="I loved Matcha today.",
    )

    result = asyncio.run(scan_service.submit_test_post(conn, brand_id=uuid4(), actor_id=uuid4(), data=data))

    assert result == {"run_id": conn.run_id, "mention_id": conn.mention_id, "created": True}
    mention_query, mention_args = next(item for item in conn.queries if "INSERT INTO tellus_shoutout_mentions" in item[0])
    assert "'uncorroborated'" in mention_query
    assert mention_args[2] == "https://instagram.com/p/example"
    assert mention_args[4] == "happycustomer"
    assert mention_args[6] == ["matcha"]
    assert json.loads(mention_args[7])["source"] == "brand_test"


def test_test_post_rejects_a_url_for_the_wrong_platform():
    data = ShoutoutTestPostIn(
        platform="instagram", post_url="https://x.com/customer/status/1", author_handle="customer", excerpt="Great",
    )

    with pytest.raises(scan_service.TestPostError, match="does not match"):
        asyncio.run(scan_service.submit_test_post(None, brand_id=uuid4(), actor_id=uuid4(), data=data))
