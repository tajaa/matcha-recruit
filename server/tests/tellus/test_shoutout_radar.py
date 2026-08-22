"""Pure and source-guard coverage for shoutout radar safety invariants."""
import inspect

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


def test_brand_own_handle_scores_zero_and_terms_must_be_in_excerpt():
    assert scan_service.score_candidate(
        {"author_handle": "Brand", "confidence": 99, "excerpt": "great", "matched_terms": ["great"]}, {"brand"}
    ) == 0
    assert scan_service.score_candidate(
        {"author_handle": "fan", "confidence": 50, "excerpt": "Lovely place", "matched_terms": ["not present"]}, set()
    ) == 50


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
    mentions, uris = asyncio.run(provider.GeminiGroundingProvider().search("test"))
    assert mentions == []
    assert uris == []
