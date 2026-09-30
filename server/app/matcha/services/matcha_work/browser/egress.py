"""The only way the browser reaches the network.

Chromium is launched with this local forward proxy as its proxy, so every
request it makes, for a page or for anything a page loads, arrives here
first. For each connection the proxy:

  * accepts ports 80 and 443 only;
  * resolves the host ONCE, through `safe_fetch.resolve_public_ip`, which
    refuses anything that is not a public address (loopback, private ranges,
    link-local and the cloud metadata address, CGNAT, NAT64 and friends);
  * connects to that resolved address, not to the name.

Pinning matters: checking the name and then letting the browser resolve it
again is a race a hostile DNS server wins (answer public, then private). Here
the address that was checked is the address that is dialled.

The proxy never reads or changes TLS traffic. It only decides where a tunnel
may go.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable
from urllib.parse import urlsplit

from app.core.services.safe_fetch import UnsafeURL, resolve_public_ip

logger = logging.getLogger(__name__)

ALLOWED_PORTS = frozenset({80, 443})
_MAX_HEAD_BYTES = 64 * 1024
_HEAD_SECONDS = 15.0
_CONNECT_SECONDS = 15.0
_IDLE_SECONDS = 120.0

Resolver = Callable[[str], Awaitable[str]]


class EgressRefused(Exception):
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.reason = reason


def parse_target(request_line: str) -> tuple[str, str, int, str]:
    """(method, host, port, the request line to send upstream)."""
    parts = request_line.strip().split(" ")
    if len(parts) != 3:
        raise EgressRefused(400, "Malformed request")
    method, target, version = parts
    if method.upper() == "CONNECT":
        host, sep, port_text = target.rpartition(":")
        if not sep or not port_text.isdigit():
            raise EgressRefused(400, "Malformed CONNECT target")
        return "CONNECT", host.strip("[]").lower(), int(port_text), ""
    try:
        url = urlsplit(target)
    except ValueError as exc:
        raise EgressRefused(400, "Malformed URL") from exc
    if url.scheme.lower() != "http" or not url.hostname:
        raise EgressRefused(400, "Only absolute http URLs are proxied")
    if url.username or url.password:
        raise EgressRefused(403, "URLs with credentials are refused")
    try:
        port = url.port or 80
    except ValueError as exc:
        raise EgressRefused(400, "Invalid port") from exc
    path = url.path or "/"
    if url.query:
        path = f"{path}?{url.query}"
    return method.upper(), url.hostname.lower(), port, f"{method} {path} {version}"


async def resolve_target(host: str, port: int, *, resolver: Resolver = resolve_public_ip) -> str:
    if port not in ALLOWED_PORTS:
        raise EgressRefused(403, "Only ports 80 and 443 are allowed")
    if not host:
        raise EgressRefused(400, "No host")
    try:
        return await resolver(host)
    except UnsafeURL as exc:
        raise EgressRefused(403, str(exc)) from exc


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), timeout=_IDLE_SECONDS)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except (asyncio.TimeoutError, ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


class EgressProxy:
    """One per browser session, bound to loopback on a port the OS picks."""

    def __init__(self, *, resolver: Resolver = resolve_public_ip) -> None:
        self._resolver = resolver
        self._server: asyncio.AbstractServer | None = None
        self.port: int | None = None
        self.refused: list[tuple[str, int, str]] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self) -> "EgressProxy":
        self._server = await asyncio.start_server(self._handle, host="127.0.0.1", port=0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=5)
            except Exception:
                pass
            self._server = None

    async def __aenter__(self) -> "EgressProxy":
        return await self.start()

    async def __aexit__(self, *_exc) -> None:
        await self.stop()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        host, port = "", 0
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=_HEAD_SECONDS)
            if len(head) > _MAX_HEAD_BYTES:
                raise EgressRefused(431, "Request head too large")
            request_line, _, rest = head.decode("latin-1").partition("\r\n")
            method, host, port, upstream_line = parse_target(request_line)
            address = await resolve_target(host, port, resolver=self._resolver)
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection(address, port), timeout=_CONNECT_SECONDS,
            )
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
            else:
                headers = "\r\n".join(
                    line for line in rest.split("\r\n")
                    if line and not line.lower().startswith(("proxy-connection:", "proxy-authorization:"))
                )
                upstream_writer.write(f"{upstream_line}\r\n{headers}\r\n\r\n".encode("latin-1"))
                await upstream_writer.drain()
            await asyncio.gather(_pipe(reader, upstream_writer), _pipe(upstream_reader, writer))
        except EgressRefused as exc:
            self.refused.append((host, port, exc.reason))
            logger.info("browser egress refused %s:%s (%s)", host, port, exc.reason)
            await self._reply(writer, exc.status, exc.reason)
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError,
                ConnectionError, OSError):
            await self._reply(writer, 502, "Upstream unavailable")
        finally:
            for stream in (writer, upstream_writer):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass

    @staticmethod
    async def _reply(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
        try:
            writer.write(f"HTTP/1.1 {status} {reason}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n".encode("latin-1"))
            await writer.drain()
        except Exception:
            pass
