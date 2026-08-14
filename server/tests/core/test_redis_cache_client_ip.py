"""Proxy-aware client IP tests for public rate limits."""
import os
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.core.services import redis_cache  # noqa: E402


def _request(xff: str, *, secret: str | None = None):
    headers = {"x-forwarded-for": xff}
    if secret is not None:
        headers["x-cappe-origin-verify"] = secret
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host="socket-peer"),
    )


def test_direct_nginx_uses_rightmost_forwarded_address(monkeypatch):
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    monkeypatch.delenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", raising=False)
    assert redis_cache.client_ip(_request("spoofed, 198.51.100.10")) == "198.51.100.10"


def test_authenticated_cloudfront_adds_one_trusted_hop(monkeypatch):
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", "edge-secret")
    request = _request("spoofed, 198.51.100.10, 203.0.113.5", secret="edge-secret")
    assert redis_cache.client_ip(request) == "198.51.100.10"


def test_missing_or_wrong_cloudfront_secret_cannot_trust_extra_hop(monkeypatch):
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", "edge-secret")
    assert redis_cache.client_ip(_request("spoofed, 198.51.100.10, 203.0.113.5")) == "203.0.113.5"
    assert redis_cache.client_ip(
        _request("spoofed, 198.51.100.10, 203.0.113.5", secret="wrong")
    ) == "203.0.113.5"
