"""Cappe route-helper unit tests — no DB, no app boot.

Covers the pure/pieces extracted from routes/_shared.py and the shared
scoped-auth revocation comparator during the xhigh review fix pass:
`build_patch` (model_fields_set-driven PATCH builder), `read_capped`
(bounded upload reads), and `is_token_revoked`'s same-second floor.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_route_helpers.py -q
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.models.bookings import CappeStaffUpdate  # noqa: E402
from app.cappe.routes._shared import build_patch, read_capped  # noqa: E402
from app.core.services.scoped_auth import is_token_revoked  # noqa: E402


# --- build_patch --------------------------------------------------------------


def test_build_patch_absent_field_untouched():
    body = CappeStaffUpdate(name="Jamie")
    sets, args = build_patch(body, ("name", "bio", "location_id"))
    assert sets == ["name = $1"]
    assert args == ["Jamie"]


def test_build_patch_explicit_null_clears():
    body = CappeStaffUpdate(bio=None)
    # Pydantic marks a field as "set" when it's passed to the constructor at
    # all, even with value None — that's the whole point: this is how the
    # route tells "the caller sent null" apart from "the caller said nothing".
    assert "bio" in body.model_fields_set
    sets, args = build_patch(body, ("name", "bio", "location_id"))
    assert sets == ["bio = $1"]
    assert args == [None]


def test_build_patch_nullable_allowlist_accepts_null():
    body = CappeStaffUpdate(bio=None)
    sets, args = build_patch(body, ("name", "bio"), nullable={"bio"})
    assert sets == ["bio = $1"] and args == [None]


def test_build_patch_nullable_rejects_not_null_field():
    body = CappeStaffUpdate(name=None)
    with pytest.raises(HTTPException) as exc:
        build_patch(body, ("name", "bio"), nullable={"bio"})
    assert exc.value.status_code == 422
    assert "name" in exc.value.detail


def test_build_patch_no_fields_set_is_empty():
    body = CappeStaffUpdate()
    sets, args = build_patch(body, ("name", "bio", "location_id"))
    assert sets == []
    assert args == []


def test_build_patch_multiple_fields_number_in_declared_order():
    body = CappeStaffUpdate(name="Jamie", active=False)
    sets, args = build_patch(
        body, ("name", "bio", "image_url", "active", "sort_order", "location_id")
    )
    assert sets == ["name = $1", "active = $2"]
    assert args == ["Jamie", False]


def test_build_patch_start_offsets_placeholder_numbering():
    """`start` lets a caller bind earlier $1.. args (e.g. the row id lookup)
    before calling build_patch for the SET clause."""
    body = CappeStaffUpdate(name="Jamie")
    sets, args = build_patch(body, ("name", "bio"), start=2)
    assert sets == ["name = $3"]
    assert args == ["Jamie"]


def test_build_patch_nullable_allowlist_accepts_null():
    body = CappeStaffUpdate(bio=None)
    sets, args = build_patch(body, ("name", "bio"), nullable={"bio"})
    assert sets == ["bio = $1"]
    assert args == [None]


def test_build_patch_nullable_rejects_non_nullable_null():
    body = CappeStaffUpdate(name=None)
    with pytest.raises(HTTPException) as exc_info:
        build_patch(body, ("name", "bio"), nullable={"bio"})
    assert exc_info.value.status_code == 422
    assert "name" in exc_info.value.detail


def test_build_patch_nullable_none_preserves_legacy_behavior():
    body = CappeStaffUpdate(name=None)
    sets, args = build_patch(body, ("name", "bio"))
    assert sets == ["name = $1"]
    assert args == [None]


# --- read_capped ---------------------------------------------------------------


class _FakeUploadFile:
    """Minimal stand-in for fastapi.UploadFile — read_capped only calls
    `await file.read(n)` and expects b"" at EOF."""

    def __init__(self, data: bytes, chunk_size: int):
        self._data = data
        self._chunk_size = chunk_size
        self._pos = 0
        self.read_calls = 0

    async def read(self, n: int = -1) -> bytes:
        self.read_calls += 1
        size = n if n and n > 0 else self._chunk_size
        chunk = self._data[self._pos : self._pos + size]
        self._pos += len(chunk)
        return chunk


@pytest.mark.asyncio
async def test_read_capped_returns_bytes_under_cap():
    data = b"x" * 100
    f = _FakeUploadFile(data, chunk_size=32)
    out = await read_capped(f, max_bytes=200, detail="too big")
    assert out == data


@pytest.mark.asyncio
async def test_read_capped_raises_413_over_cap():
    data = b"x" * (5 * 1024 * 1024)  # 5 MiB
    f = _FakeUploadFile(data, chunk_size=1024 * 1024)
    with pytest.raises(HTTPException) as exc_info:
        await read_capped(f, max_bytes=1024, detail="too big")
    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == "too big"


@pytest.mark.asyncio
async def test_read_capped_stops_reading_past_the_cap():
    """Peak memory is bounded — it must not read() the entire body before
    raising, which is exactly the bug this helper replaces."""
    data = b"x" * (50 * 1024 * 1024)  # 50 MiB
    f = _FakeUploadFile(data, chunk_size=1024 * 1024)  # 1 MiB chunks
    with pytest.raises(HTTPException):
        await read_capped(f, max_bytes=1024, detail="too big")
    # Should trip on the very first chunk, not read all 50 chunks.
    assert f.read_calls == 1


# --- is_token_revoked: same-second logout/login -------------------------------


def test_token_from_truncated_second_of_watermark_not_revoked():
    """A login in the same wall-clock second as a logout mints a token whose
    whole-second `iat` must NOT read as predating a microsecond-precision
    watermark from that same second."""
    watermark = datetime(
        2026, 1, 1, 12, 0, 0, 900_000, tzinfo=timezone.utc
    )  # :00.900000
    iat = int(
        datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    )  # :00 (floor)
    assert is_token_revoked(iat, watermark) is False


def test_token_from_strictly_earlier_second_is_revoked():
    watermark = datetime(2026, 1, 1, 12, 0, 1, 0, tzinfo=timezone.utc)
    iat = int(datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp())
    assert is_token_revoked(iat, watermark) is True


def test_token_after_watermark_not_revoked():
    watermark = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    iat = int((datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)).timestamp())
    assert is_token_revoked(iat, watermark) is False


def test_no_watermark_never_revoked():
    assert is_token_revoked(int(datetime.now(timezone.utc).timestamp()), None) is False


def test_no_iat_never_revoked():
    assert is_token_revoked(None, datetime.now(timezone.utc)) is False
