from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.requests import Request

from app.cappe.routes import render


TOKEN = "0123456789abcdef0123456789abcdef"


class _Conn:
    def __init__(self, *, scheme="ahnimal", order=True, subscription=False):
        self.scheme = scheme
        self.order = order
        self.subscription = subscription

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def fetchval(self, query, *_args):
        if "app_url_scheme" in query:
            return self.scheme
        if "FROM cappe_orders" in query:
            return uuid4() if self.order else None
        if "FROM cappe_shopper_subscriptions" in query:
            return uuid4() if self.subscription else None
        raise AssertionError(query)


def _request():
    return Request({"type": "http", "method": "GET", "path": "/__cappe/app-return", "headers": [(b"host", b"ahnimal.gummfit.com")]})


def _wire(monkeypatch, conn):
    async def site(_conn, _host):
        return {"id": uuid4()}

    monkeypatch.setattr(render, "get_connection", lambda: conn)
    monkeypatch.setattr(render, "_resolve_published_site", site)


@pytest.mark.asyncio
async def test_app_return_redirects_only_to_configured_scheme(monkeypatch):
    _wire(monkeypatch, _Conn())
    response = await render.app_return(_request(), o=TOKEN, r="success")
    assert isinstance(response, RedirectResponse)
    assert response.status_code == 302
    assert response.headers["location"] == f"ahnimal://order/{TOKEN}?r=success"
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["https", "http", "javascript", "data", "file"])
async def test_app_return_never_redirects_to_web_or_script_schemes(monkeypatch, scheme):
    # A row that predates the write-side denylist must fall back to the
    # close-window page rather than 302 the shopper to a browser-executed URL.
    _wire(monkeypatch, _Conn(scheme=scheme))
    response = await render.app_return(_request(), o=TOKEN, r="success")
    assert isinstance(response, HTMLResponse)
    assert "location" not in response.headers


def test_site_update_rejects_web_and_script_app_schemes():
    from pydantic import ValidationError

    from app.cappe.models.sites import CappeSiteUpdate

    for bad in ("https", "javascript", "data", "Ahnimal", "1app", "a"):
        with pytest.raises(ValidationError):
            CappeSiteUpdate(app_url_scheme=bad)
    assert CappeSiteUpdate(app_url_scheme="ahnimal").app_url_scheme == "ahnimal"
    assert CappeSiteUpdate(app_url_scheme=None).app_url_scheme is None


@pytest.mark.asyncio
async def test_app_return_without_scheme_serves_close_window_page(monkeypatch):
    _wire(monkeypatch, _Conn(scheme=None, order=False, subscription=True))
    response = await render.app_return(_request(), o=TOKEN, r="cancel")
    assert isinstance(response, HTMLResponse)
    assert b"close this window" in response.body


@pytest.mark.asyncio
async def test_app_return_rejects_bad_or_cross_site_token(monkeypatch):
    with pytest.raises(HTTPException) as invalid:
        await render.app_return(_request(), o="javascript:alert(1)", r="success")
    assert invalid.value.status_code == 400

    _wire(monkeypatch, _Conn(order=False, subscription=False))
    with pytest.raises(HTTPException) as missing:
        await render.app_return(_request(), o=TOKEN, r="success")
    assert missing.value.status_code == 404
