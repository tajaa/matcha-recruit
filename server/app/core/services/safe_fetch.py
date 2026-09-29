"""SSRF-guarded HTTP GET for URLs an untrusted party chose.

For server-side fetches where the URL came from a model or a web page (the
agent-card `fetch_page` tool, product-image rehosting). Stronger than
`sso._assert_safe_external_url`, which validates a hostname and then lets the
HTTP library resolve it again — a DNS-rebinding window. Here the host is
resolved ONCE, every address is checked, and the connection goes to the pinned
IP with the original name carried in the Host header and TLS SNI. Redirects are
followed by hand so every hop gets the same treatment.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

_ALLOWED_PORTS = {"http": 80, "https": 443}
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 MatchaAgent/1.0"
)


class UnsafeURL(ValueError):
    """The URL is not one the server will fetch."""


@dataclass(frozen=True)
class FetchedResponse:
    url: str
    final_url: str
    status: int
    content_type: str
    body: bytes
    truncated: bool


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Globally routable unicast only.

    `is_global` (not `not is_private`) is the test: it also excludes the
    CGNAT range 100.64.0.0/10 and the other special-purpose blocks. The
    explicit flags stay because IPv4 multicast still reports global. IPv6
    forms that embed an IPv4 address are unwrapped or refused, since they can
    reach an internal IPv4 host through a translator.
    """
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip in _NAT64 or ip.sixtofour is not None or ip.teredo is not None:
            return False
    return bool(ip.is_global) and not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    )


def _validate_url(url: str) -> tuple[str, str, str]:
    """(scheme, host, path+query) or UnsafeURL. Only default ports pass."""
    try:
        parts = urlsplit(url.strip())
    except ValueError as exc:
        raise UnsafeURL("Malformed URL") from exc
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_PORTS:
        raise UnsafeURL("Only http(s) URLs can be fetched")
    host = parts.hostname
    if not host:
        raise UnsafeURL("URL has no host")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with credentials are not fetched")
    try:
        port = parts.port or _ALLOWED_PORTS[scheme]
    except ValueError as exc:
        raise UnsafeURL("Invalid port") from exc
    if port != _ALLOWED_PORTS[scheme]:
        raise UnsafeURL("Only the default http(s) ports are fetched")
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    return scheme, host.lower(), path


async def resolve_public_ip(host: str) -> str:
    """Resolve once; every returned address must be public. Returns one to pin."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _ip_is_public(literal):
            raise UnsafeURL("URL points at a non-public address")
        return str(literal)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeURL("Host does not resolve") from exc
    addresses: list[str] = []
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if not _ip_is_public(ip):
            raise UnsafeURL("Host resolves to a non-public address")
        addresses.append(str(ip))
    if not addresses:
        raise UnsafeURL("Host does not resolve")
    return addresses[0]


def _pinned_url(scheme: str, ip: str, path: str) -> str:
    """The request URL with the host swapped for the already-validated IP."""
    netloc = f"[{ip}]" if ":" in ip else ip
    route, _, query = path.partition("?")
    return urlunsplit((scheme, netloc, route, query, ""))


async def fetch_public(
    url: str,
    *,
    max_bytes: int,
    timeout: float = 10.0,
    accept: str = "*/*",
    max_redirects: int = 3,
    total_timeout: float = 30.0,
    client: httpx.AsyncClient | None = None,
) -> FetchedResponse:
    """GET `url` if (and only if) every hop resolves to a public address.

    The body is streamed and cut at `max_bytes` (`truncated=True`). Non-2xx
    final responses are returned, not raised — callers decide what a 404 means.

    `timeout` is httpx's per-socket-operation limit, which a host that drips one
    byte at a time never trips; `total_timeout` bounds the whole call, every
    redirect hop included, and raises TimeoutError.

    Responses are requested uncompressed and a compressed one is refused: the
    byte cap counts decoded bytes, so a small gzip/brotli bomb would inflate
    past it inside a single chunk before the cap could act.
    """
    async with asyncio.timeout(total_timeout):
        return await _fetch_public(
            url, max_bytes=max_bytes, timeout=timeout, accept=accept,
            max_redirects=max_redirects, client=client,
        )


async def _fetch_public(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
    accept: str,
    max_redirects: int,
    client: httpx.AsyncClient | None,
) -> FetchedResponse:
    owns_client = client is None
    http = client or httpx.AsyncClient(follow_redirects=False, timeout=timeout)
    current = url
    try:
        for _hop in range(max_redirects + 1):
            scheme, host, path = _validate_url(current)
            ip = await resolve_public_ip(host)
            headers = {
                "Host": host,
                "User-Agent": _USER_AGENT,
                "Accept": accept,
                "Accept-Encoding": "identity",
                "Accept-Language": "en-US,en;q=0.8",
            }
            extensions = {"sni_hostname": host} if scheme == "https" else {}
            request = http.build_request(
                "GET", _pinned_url(scheme, ip, path),
                headers=headers, extensions=extensions, timeout=timeout,
            )
            response = await http.send(request, stream=True)
            try:
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeURL("Redirect without a location")
                    current = urljoin(current, location)
                    continue
                encoding = (response.headers.get("content-encoding") or "identity").strip().lower()
                if encoding not in ("", "identity"):
                    raise UnsafeURL("Compressed responses are not fetched")
                body = bytearray()
                truncated = False
                async for chunk in response.aiter_bytes():
                    remaining = max_bytes - len(body)
                    if len(chunk) > remaining:
                        body.extend(chunk[:remaining])
                        truncated = True
                        break
                    body.extend(chunk)
                return FetchedResponse(
                    url=url,
                    final_url=current,
                    status=response.status_code,
                    content_type=(response.headers.get("content-type") or "").split(";")[0].strip().lower(),
                    body=bytes(body),
                    truncated=truncated,
                )
            finally:
                await response.aclose()
        raise UnsafeURL("Too many redirects")
    finally:
        if owns_client:
            await http.aclose()
