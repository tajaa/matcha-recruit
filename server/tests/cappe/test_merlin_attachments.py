"""Chat image attachments — the SSRF guard and the fetch/downscale pipeline.

`load_attachments` is the one place a Merlin turn touches a URL the request
handed it. `storage.download_file` will fetch ANY `*.cloudfront.net` URL over
plain HTTP and falls through to reading local file paths, so the allowlist in
`_is_own_storage` is the actual security boundary — these tests are mostly
about proving that boundary holds, not the happy path.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_attachments.py -q
"""
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import merlin_attachments  # noqa: E402
from app.cappe.services.merlin_attachments import (  # noqa: E402
    caption_lines,
    load_attachments,
)

# `_is_own_storage` reads the DEPLOYED bucket/domain via get_settings(), which
# `load_dotenv()` (inside load_settings()) may have already populated from a
# real .env by the time this module runs in the full suite — an
# os.environ.setdefault() here would silently lose to that. Patching
# `get_settings` directly makes the test independent of import order and of
# whatever real values happen to be in the environment.
_FAKE_SETTINGS = SimpleNamespace(
    cloudfront_domain="assets.example.test", s3_bucket="matcha-test-bucket"
)


@pytest.fixture(autouse=True)
def _fixed_storage_settings(monkeypatch):
    monkeypatch.setattr(merlin_attachments, "get_settings", lambda: _FAKE_SETTINGS)


# --- the SSRF gate -------------------------------------------------------

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://assets.example.test/cappe/x.png", True),
        ("s3://matcha-test-bucket/cappe/x.png", True),
        # Attacker-registerable — *.cloudfront.net is not this deployment's.
        ("https://evil-bucket.cloudfront.net/x.png", False),
        # A different S3 bucket than ours.
        ("s3://someone-elses-bucket/x.png", False),
        # A local file path — download_file's other fallthrough.
        ("/etc/passwd", False),
        ("file:///etc/passwd", False),
        ("", False),
        (None, False),
        (123, False),
    ],
)
def test_is_own_storage(url, expected):
    assert merlin_attachments._is_own_storage(url) is expected


@pytest.mark.asyncio
async def test_load_attachments_drops_urls_outside_our_storage(monkeypatch):
    """The fetch must never even be attempted for a foreign URL."""
    called = []

    class _FakeStorage:
        async def download_file(self, url):
            called.append(url)
            return b"\xff\xd8\xffJFIF" + b"0" * 100

    monkeypatch.setattr(merlin_attachments, "get_storage", lambda: _FakeStorage())

    out = await load_attachments([{"url": "https://evil.cloudfront.net/x.png", "mime": "image/png"}])
    assert out == []
    assert called == []


@pytest.mark.asyncio
async def test_load_attachments_fetches_an_owned_url(monkeypatch):
    payload = b"\xff\xd8\xff" + b"fake-jpeg-bytes" * 10

    class _FakeStorage:
        async def download_file(self, url):
            return payload

    monkeypatch.setattr(merlin_attachments, "get_storage", lambda: _FakeStorage())
    # Skip the real Pillow decode — the fixture bytes aren't a valid image, and
    # _downscale already degrades to "return the original" on a decode failure,
    # which is exactly what we want asserted here without a real JPEG fixture.

    out = await load_attachments([
        {"url": "https://assets.example.test/cappe/x.jpg", "mime": "image/jpeg"}
    ])
    assert len(out) == 1
    assert out[0]["url"] == "https://assets.example.test/cappe/x.jpg"
    assert out[0]["data"] == payload


@pytest.mark.asyncio
async def test_load_attachments_caps_at_max_attachments(monkeypatch):
    class _FakeStorage:
        async def download_file(self, url):
            return b"\xff\xd8\xff" + b"x" * 50

    monkeypatch.setattr(merlin_attachments, "get_storage", lambda: _FakeStorage())

    urls = [
        {"url": f"https://assets.example.test/cappe/{i}.jpg", "mime": "image/jpeg"}
        for i in range(10)
    ]
    out = await load_attachments(urls)
    assert len(out) == merlin_attachments.MAX_ATTACHMENTS


@pytest.mark.asyncio
async def test_load_attachments_drops_oversized_files(monkeypatch):
    class _FakeStorage:
        async def download_file(self, url):
            return b"\xff\xd8\xff" + b"x" * (merlin_attachments.MAX_BYTES + 1)

    monkeypatch.setattr(merlin_attachments, "get_storage", lambda: _FakeStorage())

    out = await load_attachments([
        {"url": "https://assets.example.test/cappe/big.jpg", "mime": "image/jpeg"}
    ])
    assert out == []


@pytest.mark.asyncio
async def test_load_attachments_survives_a_fetch_error(monkeypatch):
    class _FakeStorage:
        async def download_file(self, url):
            raise RuntimeError("S3 unreachable")

    monkeypatch.setattr(merlin_attachments, "get_storage", lambda: _FakeStorage())

    out = await load_attachments([
        {"url": "https://assets.example.test/cappe/x.jpg", "mime": "image/jpeg"}
    ])
    assert out == []


@pytest.mark.asyncio
async def test_load_attachments_ignores_non_list_input():
    assert await load_attachments(None) == []
    assert await load_attachments("not a list") == []
    assert await load_attachments({}) == []


# --- captions --------------------------------------------------------------

def test_caption_lines_numbers_attachments_for_tool_reference():
    """The numbering is load-bearing: it's how a later generate_image
    attachment_index resolves to a URL."""
    text = caption_lines([
        {"url": "https://assets.example.test/a.jpg", "mime": "image/jpeg", "data": b""},
        {"url": "https://assets.example.test/b.jpg", "mime": "image/jpeg", "data": b""},
    ])
    assert "Attachment 1: https://assets.example.test/a.jpg" in text
    assert "Attachment 2: https://assets.example.test/b.jpg" in text


def test_caption_lines_is_none_for_no_attachments():
    assert caption_lines([]) is None
