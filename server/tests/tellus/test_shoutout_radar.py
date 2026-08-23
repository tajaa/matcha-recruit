"""Pure and fake-connection coverage for shoutout radar safety invariants."""
import asyncio
import inspect
import json
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
    accepted, rejected = grounding.corroborated_candidates(
        [{"platform": "instagram", "url": "https://instagram.com/p/hallucinated"}],
        ["https://instagram.com/p/real"],
    )
    assert accepted == []
    assert rejected == 1


def test_grounding_gate_accepts_matching_result():
    accepted, rejected = grounding.corroborated_candidates(
        [{"platform": "instagram", "url": "https://www.instagram.com/p/real/?utm_source=search"}],
        ["https://instagram.com/p/real"],
    )
    assert rejected == 0
    assert accepted[0]["canonical_url"] == "https://instagram.com/p/real"
    assert accepted[0]["grounding_uri"] == "https://instagram.com/p/real"


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


def test_provider_handles_a_response_without_candidates(monkeypatch):
    class FakeLimiter:
        async def check_limit(self, *_):
            return None

        async def record_call(self, *_):
            return None

    class FakeModels:
        async def generate_content(self, **_):
            return type("Response", (), {"text": None, "candidates": None})()

    class FakeClient:
        aio = type("Aio", (), {"models": FakeModels()})()

    from app.tellus.services.shoutout import provider

    monkeypatch.setattr(provider, "get_rate_limiter", lambda: FakeLimiter())
    monkeypatch.setattr(provider, "get_genai_client", lambda: FakeClient())

    import asyncio
    result = asyncio.run(provider.GeminiGroundingProvider().search("test"))
    assert result.mentions == []
    assert result.grounding_uris == []
    assert result.grounding_resolved == 0


def test_scan_run_uses_real_resolution_count_and_failure_backoff():
    source = inspect.getsource(scan_service.scan_brand)
    assert "grounding_resolved = sum" in source
    assert "gemini_calls=2" in source
    assert "asyncio.gather" in source
    assert "next_scan_after=NOW()" in source


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
