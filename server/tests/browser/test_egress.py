import asyncio

import pytest

from app.core.services.safe_fetch import UnsafeURL
from app.matcha.services.matcha_work.browser import egress
from app.matcha.services.matcha_work.browser.egress import EgressProxy, EgressRefused


def test_a_connect_target_is_a_host_and_a_port():
    assert egress.parse_target("CONNECT tables.example:443 HTTP/1.1") == ("CONNECT", "tables.example", 443, "")
    assert egress.parse_target("CONNECT [2001:db8::1]:443 HTTP/1.1")[1] == "2001:db8::1"
    for bad in ("CONNECT tables.example HTTP/1.1", "CONNECT tables.example:https HTTP/1.1", "CONNECT", "a b"):
        with pytest.raises(EgressRefused) as exc:
            egress.parse_target(bad)
        assert exc.value.status == 400


def test_a_plain_request_is_rewritten_for_the_origin():
    method, host, port, line = egress.parse_target("GET http://Tables.Example/r/nopa?x=1 HTTP/1.1")
    assert (method, host, port, line) == ("GET", "tables.example", 80, "GET /r/nopa?x=1 HTTP/1.1")
    assert egress.parse_target("GET http://tables.example HTTP/1.1")[3] == "GET / HTTP/1.1"
    assert egress.parse_target("GET http://tables.example:8080/ HTTP/1.1")[2] == 8080
    refused = {
        "GET /relative HTTP/1.1": 400,
        "GET https://tables.example/ HTTP/1.1": 400,
        "GET http://user:pw@tables.example/ HTTP/1.1": 403,
        "GET http://tables.example:notaport/ HTTP/1.1": 400,
    }
    for line, status in refused.items():
        with pytest.raises(EgressRefused) as exc:
            egress.parse_target(line)
        assert exc.value.status == status, line


@pytest.mark.asyncio
async def test_only_default_ports_pass():
    async def resolver(host):
        return "93.184.216.34"

    assert await egress.resolve_target("tables.example", 443, resolver=resolver) == "93.184.216.34"
    assert await egress.resolve_target("tables.example", 80, resolver=resolver) == "93.184.216.34"
    for port in (22, 8080, 6379, 5432, 0):
        with pytest.raises(EgressRefused) as exc:
            await egress.resolve_target("tables.example", port, resolver=resolver)
        assert exc.value.status == 403
    with pytest.raises(EgressRefused):
        await egress.resolve_target("", 443, resolver=resolver)


@pytest.mark.asyncio
async def test_the_proxy_refuses_private_and_metadata_addresses():
    # The real resolver, on literal addresses: nothing is looked up.
    for host in ("127.0.0.1", "10.0.0.5", "192.168.1.1", "172.16.0.1", "169.254.169.254",
                 "100.64.0.1", "::1", "fe80::1", "0.0.0.0", "64:ff9b::a00:1"):
        with pytest.raises(EgressRefused) as exc:
            await egress.resolve_target(host, 443)
        assert exc.value.status == 403, host
    assert await egress.resolve_target("93.184.216.34", 443) == "93.184.216.34"


async def _exchange(proxy, request: bytes) -> bytes:
    reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
    writer.write(request)
    await writer.drain()
    data = await asyncio.wait_for(reader.read(65536), timeout=5)
    writer.close()
    return data


@pytest.mark.asyncio
async def test_the_proxy_pins_the_resolved_address():
    """The address that was checked is the address that is dialled: the name
    is resolved once, by the proxy, and the tunnel goes to that address."""
    seen = {}

    async def origin(reader, writer):
        seen["hello"] = await reader.read(5)
        writer.write(b"world")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(origin, "127.0.0.1", 0)
    origin_port = server.sockets[0].getsockname()[1]
    resolved = []

    async def resolver(host):
        resolved.append(host)
        return "127.0.0.1"  # stands in for the public address the name resolved to

    dialled = []
    real_open = asyncio.open_connection

    async def open_connection(host, port, *a, **k):
        dialled.append((host, port))
        return await real_open(host, origin_port, *a, **k)

    proxy = EgressProxy(resolver=resolver)
    try:
        async with proxy:
            assert proxy.url == f"http://127.0.0.1:{proxy.port}"
            reader, writer = await real_open("127.0.0.1", proxy.port)
            import unittest.mock as mock

            with mock.patch.object(egress.asyncio, "open_connection", open_connection):
                writer.write(b"CONNECT tables.example:443 HTTP/1.1\r\nHost: tables.example:443\r\n\r\n")
                await writer.drain()
                established = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
                writer.write(b"hello")
                await writer.drain()
                answer = await asyncio.wait_for(reader.read(5), timeout=5)
            writer.close()
    finally:
        server.close()
        await server.wait_closed()
    assert established.startswith(b"HTTP/1.1 200")
    assert answer == b"world" and seen["hello"] == b"hello"
    assert resolved == ["tables.example"]
    assert dialled == [("127.0.0.1", 443)]


@pytest.mark.asyncio
async def test_a_refused_tunnel_gets_a_403_and_is_recorded():
    async def resolver(host):
        raise UnsafeURL("Host resolves to a non-public address")

    async with EgressProxy(resolver=resolver) as proxy:
        reply = await _exchange(proxy, b"CONNECT internal.example:443 HTTP/1.1\r\n\r\n")
        wrong_port = await _exchange(proxy, b"CONNECT tables.example:6379 HTTP/1.1\r\n\r\n")
        malformed = await _exchange(proxy, b"NONSENSE\r\n\r\n")
        refused = list(proxy.refused)
    assert reply.startswith(b"HTTP/1.1 403") and wrong_port.startswith(b"HTTP/1.1 403")
    assert malformed.startswith(b"HTTP/1.1 400")
    assert ("internal.example", 443, "Host resolves to a non-public address") in refused
    assert ("tables.example", 6379, "Only ports 80 and 443 are allowed") in refused


@pytest.mark.asyncio
async def test_a_plain_request_is_forwarded_without_proxy_headers():
    got = {}

    async def origin(reader, writer):
        got["request"] = await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(origin, "127.0.0.1", 0)
    origin_port = server.sockets[0].getsockname()[1]
    real_open = asyncio.open_connection

    async def open_connection(host, port, *a, **k):
        return await real_open(host, origin_port, *a, **k)

    async def resolver(host):
        return "127.0.0.1"

    import unittest.mock as mock

    try:
        async with EgressProxy(resolver=resolver) as proxy:
            reader, writer = await real_open("127.0.0.1", proxy.port)
            with mock.patch.object(egress.asyncio, "open_connection", open_connection):
                writer.write(b"GET http://tables.example/r/nopa HTTP/1.1\r\nHost: tables.example\r\n"
                             b"Proxy-Connection: keep-alive\r\nProxy-Authorization: Basic x\r\n\r\n")
                await writer.drain()
                reply = await asyncio.wait_for(reader.read(65536), timeout=5)
            writer.close()
    finally:
        server.close()
        await server.wait_closed()
    assert reply.endswith(b"ok")
    assert got["request"].startswith(b"GET /r/nopa HTTP/1.1\r\nHost: tables.example\r\n")
    assert b"Proxy-" not in got["request"]


@pytest.mark.asyncio
async def test_an_unreachable_origin_is_a_502():
    async def resolver(host):
        return "127.0.0.1"

    async def refuse(*_a, **_k):
        raise ConnectionRefusedError()

    import unittest.mock as mock

    async with EgressProxy(resolver=resolver) as proxy:
        reader, writer = await asyncio.open_connection("127.0.0.1", proxy.port)
        with mock.patch.object(egress.asyncio, "open_connection", refuse):
            writer.write(b"CONNECT tables.example:443 HTTP/1.1\r\n\r\n")
            await writer.drain()
            reply = await asyncio.wait_for(reader.read(65536), timeout=5)
        writer.close()
    assert reply.startswith(b"HTTP/1.1 502")
    await proxy.stop()  # stopping twice is harmless


@pytest.mark.asyncio
async def test_a_plain_request_gets_its_own_connection_both_ways():
    """A browser reusing the proxy connection for a second host must not have
    that request delivered to the first host's pinned address."""
    requests = []

    async def origin(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        body = await reader.readexactly(4) if b"Content-Length: 4" in head else b""
        requests.append((head, body))
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        await writer.drain()
        # A keep-alive origin would wait here for more; anything that arrives
        # is recorded as a leak.
        try:
            extra = await asyncio.wait_for(reader.read(65536), timeout=0.3)
            if extra:
                requests.append((extra, b""))
        except asyncio.TimeoutError:
            pass
        writer.close()

    server = await asyncio.start_server(origin, "127.0.0.1", 0)
    origin_port = server.sockets[0].getsockname()[1]
    real_open = asyncio.open_connection

    async def open_connection(host, port, *a, **k):
        return await real_open(host, origin_port, *a, **k)

    async def resolver(host):
        return "127.0.0.1"

    import unittest.mock as mock

    try:
        async with EgressProxy(resolver=resolver) as proxy:
            reader, writer = await real_open("127.0.0.1", proxy.port)
            with mock.patch.object(egress.asyncio, "open_connection", open_connection):
                writer.write(b"POST http://a.example/form HTTP/1.1\r\nHost: a.example\r\n"
                             b"Connection: keep-alive\r\nKeep-Alive: timeout=5\r\n"
                             b"Content-Length: 4\r\n\r\nx=12"
                             b"GET http://cdn.b.example/x.js HTTP/1.1\r\nHost: cdn.b.example\r\n\r\n")
                await writer.drain()
                reply = await asyncio.wait_for(reader.read(65536), timeout=5)
                closed = await asyncio.wait_for(reader.read(1), timeout=5)
            writer.close()
    finally:
        server.close()
        await server.wait_closed()
    assert reply.endswith(b"ok") and closed == b""
    assert len(requests) == 1
    head, body = requests[0]
    assert body == b"x=12"
    assert head.endswith(b"Content-Length: 4\r\nConnection: close\r\n\r\n")
    assert b"keep-alive" not in head.lower() and b"cdn.b.example" not in head


@pytest.mark.asyncio
async def test_a_chunked_or_oversized_plain_body_is_refused():
    dialled = []

    async def resolver(host):
        dialled.append(host)
        return "127.0.0.1"

    async with EgressProxy(resolver=resolver) as proxy:
        chunked = await _exchange(proxy, b"POST http://a.example/ HTTP/1.1\r\n"
                                         b"Transfer-Encoding: chunked\r\n\r\n")
        huge = await _exchange(proxy, b"POST http://a.example/ HTTP/1.1\r\n"
                                      b"Content-Length: 999999999\r\n\r\n")
        bad = await _exchange(proxy, b"POST http://a.example/ HTTP/1.1\r\n"
                                     b"Content-Length: nope\r\n\r\n")
    assert chunked.startswith(b"HTTP/1.1 411")
    assert huge.startswith(b"HTTP/1.1 413") and bad.startswith(b"HTTP/1.1 400")
    assert dialled == []  # refused before anything was resolved or dialled
