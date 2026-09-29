import socket

import httpx
import pytest

from app.core.services import safe_fetch
from app.core.services.safe_fetch import UnsafeURL, fetch_public


def _resolve_to(monkeypatch, mapping: dict[str, list[str]]):
    def fake_getaddrinfo(host, *_args, **_kwargs):
        if host not in mapping:
            raise socket.gaierror("no such host")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in mapping[host]]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "ftp://example.com/x",
    "http://127.0.0.1/",
    "http://[::1]/",
    "http://[::ffff:10.0.0.1]/",
    "http://169.254.169.254/latest/meta-data/",
    "https://example.com:8443/",
    "https://user:pw@example.com/",
])
async def test_refuses_non_public_or_non_default_targets(url):
    with pytest.raises(UnsafeURL):
        await fetch_public(url, max_bytes=100, client=_client(lambda r: httpx.Response(200)))


@pytest.mark.asyncio
async def test_refuses_a_hostname_that_resolves_to_a_private_address(monkeypatch):
    _resolve_to(monkeypatch, {"rebind.example": ["93.184.216.34", "10.1.2.3"]})
    with pytest.raises(UnsafeURL, match="non-public"):
        await fetch_public("https://rebind.example/", max_bytes=100, client=_client(lambda r: httpx.Response(200)))


@pytest.mark.asyncio
async def test_connects_to_the_pinned_ip_with_host_header_and_sni(monkeypatch):
    _resolve_to(monkeypatch, {"shop.example": ["93.184.216.34"]})
    seen = {}

    def handler(request: httpx.Request):
        seen["host"] = request.url.host
        seen["header"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        seen["path"] = request.url.raw_path
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=b"<p>hi</p>")

    result = await fetch_public("https://shop.example/p/lip-balm?x=1", max_bytes=1000, client=_client(handler))
    assert seen == {"host": "93.184.216.34", "header": "shop.example", "sni": "shop.example", "path": b"/p/lip-balm?x=1"}
    assert result.status == 200
    assert result.content_type == "text/html"
    assert result.final_url == "https://shop.example/p/lip-balm?x=1"
    assert result.body == b"<p>hi</p>"


@pytest.mark.asyncio
async def test_revalidates_every_redirect_hop(monkeypatch):
    _resolve_to(monkeypatch, {"shop.example": ["93.184.216.34"], "internal.example": ["192.168.0.5"]})

    def handler(request):
        return httpx.Response(302, headers={"location": "http://internal.example/admin"})

    with pytest.raises(UnsafeURL, match="non-public"):
        await fetch_public("https://shop.example/", max_bytes=100, client=_client(handler))


@pytest.mark.asyncio
async def test_follows_a_public_redirect_and_reports_the_final_url(monkeypatch):
    _resolve_to(monkeypatch, {"a.example": ["93.184.216.34"], "b.example": ["93.184.216.35"]})

    def handler(request):
        if request.headers["host"] == "a.example":
            return httpx.Response(301, headers={"location": "https://b.example/final"})
        return httpx.Response(200, content=b"ok")

    result = await fetch_public("https://a.example/start", max_bytes=100, client=_client(handler))
    assert result.final_url == "https://b.example/final"
    assert result.url == "https://a.example/start"


@pytest.mark.asyncio
async def test_too_many_redirects(monkeypatch):
    _resolve_to(monkeypatch, {"loop.example": ["93.184.216.34"]})
    with pytest.raises(UnsafeURL, match="Too many redirects"):
        await fetch_public(
            "https://loop.example/", max_bytes=100, max_redirects=2,
            client=_client(lambda r: httpx.Response(302, headers={"location": "/again"})),
        )


@pytest.mark.asyncio
async def test_body_is_cut_at_max_bytes(monkeypatch):
    _resolve_to(monkeypatch, {"big.example": ["93.184.216.34"]})
    result = await fetch_public(
        "https://big.example/", max_bytes=10,
        client=_client(lambda r: httpx.Response(200, content=b"x" * 50)),
    )
    assert result.truncated and len(result.body) == 10


@pytest.mark.asyncio
async def test_unresolvable_host_is_refused(monkeypatch):
    _resolve_to(monkeypatch, {})
    with pytest.raises(UnsafeURL, match="does not resolve"):
        await fetch_public("https://nowhere.example/", max_bytes=10, client=_client(lambda r: httpx.Response(200)))


def test_ipv4_mapped_v6_is_unwrapped():
    import ipaddress

    assert not safe_fetch._ip_is_public(ipaddress.ip_address("::ffff:127.0.0.1"))
    assert safe_fetch._ip_is_public(ipaddress.ip_address("93.184.216.34"))
