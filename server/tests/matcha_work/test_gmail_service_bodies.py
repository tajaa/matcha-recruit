"""GmailService bodies: plain text for the AI actions and card snapshots,
the raw HTML for the reader, charset-aware, attachments never mistaken for
the body. Test addresses are RFC 2606 reserved domains only."""

import base64
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work import gmail_service
from app.matcha.services.matcha_work.gmail_service import GmailService


def _b64(data) -> str:
    raw = data.encode() if isinstance(data, str) else data
    return base64.urlsafe_b64encode(raw).decode()


def _part(mime, data, charset=None, filename=""):
    content_type = f"{mime}; charset={charset}" if charset else mime
    return {
        "mimeType": mime,
        "filename": filename,
        "headers": [{"name": "Content-Type", "value": content_type}],
        "body": {"data": _b64(data)},
    }


def _alternative(*parts):
    return {"mimeType": "multipart/alternative", "filename": "", "parts": list(parts)}


def _svc():
    return GmailService(uuid4())


def test_alternative_gives_the_plain_body_and_the_raw_html():
    payload = _alternative(_part("text/plain", "Hi Alice"), _part("text/html", "<p>Hi <b>Alice</b></p>"))
    svc = _svc()
    assert svc._extract_body(payload) == "Hi Alice"
    assert svc._find_part(payload, "text/html") == "<p>Hi <b>Alice</b></p>"


def test_an_html_only_body_keeps_its_paragraphs():
    markup = (
        "<html><head><style>p{color:red}</style><title>t</title></head><body>"
        "<header>Top</header><!-- tracking --><p>One &amp; two</p><p>Three<br>Four</p>"
        "<script>x()</script></body></html>"
    )
    text = _svc()._extract_body(_part("text/html", markup))
    # <header> is not <head>: its text survives; style/script/comments do not.
    assert text == "Top\nOne & two\nThree\nFour"


def test_the_declared_charset_is_honoured():
    payload = _part("text/plain", "café".encode("iso-8859-1"), charset="iso-8859-1")
    assert _svc()._extract_body(payload) == "café"


def test_an_unknown_charset_falls_back_to_utf8():
    payload = _part("text/plain", "café".encode("utf-8"), charset="x-made-up")
    assert _svc()._extract_body(payload) == "café"


def test_unpadded_base64_still_decodes():
    payload = {"mimeType": "text/plain", "filename": "", "body": {"data": _b64("hello!").rstrip("=")}}
    assert _svc()._extract_body(payload) == "hello!"


def test_attachment_parts_are_never_the_body():
    payload = {
        "mimeType": "multipart/mixed",
        "filename": "",
        "parts": [
            _alternative(_part("text/html", "<p>real</p>")),
            _part("text/plain", "attached notes", filename="notes.txt"),
            _part("text/html", "<p>attached page</p>", filename="page.html"),
        ],
    }
    svc = _svc()
    assert svc._extract_body(payload) == "real"
    assert svc._find_part(payload, "text/html") == "<p>real</p>"


def test_a_message_with_no_text_part_says_so():
    payload = {"mimeType": "multipart/mixed", "filename": "", "parts": [_part("image/png", b"\x89PNG", filename="a.png")]}
    assert _svc()._extract_body(payload) == "(no readable body)"


@pytest.mark.asyncio
async def test_get_message_carries_snippet_html_and_unread():
    svc = _svc()
    svc._gmail_get = AsyncMock(return_value={
        "threadId": "t1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "Tom &amp; Jerry&#39;s plan",
        "payload": {
            **_alternative(_part("text/plain", "plain"), _part("text/html", "<p>rich</p>")),
            "headers": [{"name": "Subject", "value": "Hi"}, {"name": "From", "value": "alice@example.com"}],
        },
    })
    msg = await svc.get_message("m1")
    assert msg["snippet"] == "Tom & Jerry's plan"
    assert msg["body"] == "plain"
    assert msg["body_html"] == "<p>rich</p>"
    assert msg["is_unread"] is True


@pytest.mark.asyncio
async def test_oversize_html_is_left_to_the_text_body(monkeypatch):
    monkeypatch.setattr(gmail_service, "BODY_HTML_MAX_CHARS", 10)
    svc = _svc()
    svc._gmail_get = AsyncMock(return_value={"payload": _part("text/html", "<p>" + "x" * 50 + "</p>")})
    msg = await svc.get_message("m1")
    assert msg["body_html"] is None
    assert msg["body"] == "x" * 50
    assert msg["is_unread"] is False
    assert msg["snippet"] == ""


@pytest.mark.asyncio
async def test_fetch_unread_leaves_the_html_out_of_the_list():
    svc = _svc()
    svc.load_token = AsyncMock()

    async def fake_get(path, params=None):
        if path == "/users/me/messages":
            return {"messages": [{"id": "m1"}]}
        return {
            "labelIds": ["UNREAD"],
            "payload": _alternative(_part("text/plain", "p"), _part("text/html", "<p>h</p>")),
        }

    svc._gmail_get = fake_get
    out = await svc.fetch_unread()
    assert len(out) == 1
    assert "body_html" not in out[0]
    assert out[0]["body"] == "p" and out[0]["is_unread"] is True
