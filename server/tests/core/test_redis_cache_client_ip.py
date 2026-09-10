"""Proxy-aware client IP tests for public rate limits."""
import os
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.core.services import redis_cache  # noqa: E402


def _request(xff: str, *, secret: str | None = None, matcha_secret: str | None = None):
    headers = {"x-forwarded-for": xff}
    if secret is not None:
        headers["x-cappe-origin-verify"] = secret
    if matcha_secret is not None:
        headers["x-matcha-origin-verify"] = matcha_secret
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host="socket-peer"),
    )


def _clear_origin_secrets(monkeypatch):
    for _header, env_var in redis_cache._ORIGIN_VERIFY_HEADERS:
        monkeypatch.delenv(env_var, raising=False)


def test_direct_nginx_uses_rightmost_forwarded_address(monkeypatch):
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    _clear_origin_secrets(monkeypatch)
    assert redis_cache.client_ip(_request("spoofed, 198.51.100.10")) == "198.51.100.10"


def test_authenticated_cloudfront_adds_one_trusted_hop(monkeypatch):
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    _clear_origin_secrets(monkeypatch)
    monkeypatch.setenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", "edge-secret")
    request = _request("spoofed, 198.51.100.10, 203.0.113.5", secret="edge-secret")
    assert redis_cache.client_ip(request) == "198.51.100.10"


def test_missing_or_wrong_cloudfront_secret_cannot_trust_extra_hop(monkeypatch):
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    _clear_origin_secrets(monkeypatch)
    monkeypatch.setenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", "edge-secret")
    assert redis_cache.client_ip(_request("spoofed, 198.51.100.10, 203.0.113.5")) == "203.0.113.5"
    assert redis_cache.client_ip(
        _request("spoofed, 198.51.100.10, 203.0.113.5", secret="wrong")
    ) == "203.0.113.5"


def test_matcha_origin_header_authenticates_the_same_edge_hop(monkeypatch):
    """Matcha traffic must not depend on the Cappe secret. One shared
    CloudFront distribution fronts both today; if they are ever split, the
    matcha header alone still identifies the edge hop."""
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    _clear_origin_secrets(monkeypatch)
    monkeypatch.setenv("MATCHA_CLOUDFRONT_ORIGIN_SECRET", "matcha-edge-secret")
    request = _request("spoofed, 198.51.100.10, 203.0.113.5", matcha_secret="matcha-edge-secret")
    assert redis_cache.client_ip(request) == "198.51.100.10"
    # Wrong value earns nothing.
    assert redis_cache.client_ip(
        _request("spoofed, 198.51.100.10, 203.0.113.5", matcha_secret="nope")
    ) == "203.0.113.5"


def test_both_origin_headers_still_add_exactly_one_hop(monkeypatch):
    """The shared distribution injects both headers on every request. They name
    the same hop, so trusting each of them separately would skip a real entry."""
    monkeypatch.setattr(redis_cache, "_TRUSTED_PROXY_COUNT", 1)
    monkeypatch.setenv("CAPPE_CLOUDFRONT_ORIGIN_SECRET", "edge-secret")
    monkeypatch.setenv("MATCHA_CLOUDFRONT_ORIGIN_SECRET", "matcha-edge-secret")
    request = _request(
        "spoofed, 198.51.100.10, 203.0.113.5",
        secret="edge-secret",
        matcha_secret="matcha-edge-secret",
    )
    assert redis_cache.client_ip(request) == "198.51.100.10"
