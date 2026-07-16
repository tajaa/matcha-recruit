"""The `tenant_codified_only` setting — fail-closed under every bad input.

The failure modes are asymmetric, which is the whole reason this file exists.
Gating wrongly shows a business fewer laws than we hold: visible, reported,
fixed in minutes. Opening wrongly presents unvetted Gemini research as verified
law: indistinguishable from the real thing on screen, nobody reports it, and it
is exactly the claim the gate was built to prevent. So every ambiguity resolves
to ON.
"""
import asyncio

import pytest

from app.core.services import platform_settings as ps


def _normalize(value):
    return ps._normalize_tenant_codified_only(value)


class TestNormalize:
    def test_absent_setting_uses_the_default(self):
        # No row in platform_settings — the shipped default decides.
        assert _normalize(None) is ps.DEFAULT_TENANT_CODIFIED_ONLY

    def test_default_is_on(self):
        assert ps.DEFAULT_TENANT_CODIFIED_ONLY is True

    def test_admin_route_shape(self):
        # What PUT /platform-settings/tenant-codified-only writes.
        assert _normalize({"enabled": True}) is True
        assert _normalize({"enabled": False}) is False

    def test_bare_bool(self):
        # asyncpg hands JSONB back as str, and a hand-written row may be bare.
        assert _normalize(True) is True
        assert _normalize(False) is False

    def test_json_string_payloads(self):
        assert _normalize('{"enabled": false}') is False
        assert _normalize('{"enabled": true}') is True
        assert _normalize("false") is False

    @pytest.mark.parametrize("bad", [
        "not json at all",
        '{"enabled": "false"}',   # string, not bool — no truthiness shortcuts
        '{"enabled": null}',
        '{"enabled": 0}',         # 0 is falsy in Python; it is not `false` here
        '{"typo": false}',
        "[]",
        '"maybe"',
        "42",
    ])
    def test_every_malformed_value_keeps_the_gate_on(self, bad):
        assert _normalize(bad) is True


class TestGetter:
    def setup_method(self):
        ps.invalidate_tenant_codified_only_cache()

    def teardown_method(self):
        ps.invalidate_tenant_codified_only_cache()

    def test_a_db_failure_does_not_open_the_gate(self, monkeypatch):
        class Boom:
            async def fetchval(self, *a, **k):
                raise RuntimeError("connection reset")

        assert asyncio.run(ps.get_tenant_codified_only(conn=Boom())) is True

    def test_a_db_failure_is_not_cached(self, monkeypatch):
        """A blip must not pin the gate for the cache TTL — including pinning a
        wrong value once the DB recovers."""
        class Boom:
            async def fetchval(self, *a, **k):
                raise RuntimeError("connection reset")

        class Off:
            async def fetchval(self, *a, **k):
                return '{"enabled": false}'

        assert asyncio.run(ps.get_tenant_codified_only(conn=Boom())) is True
        assert asyncio.run(ps.get_tenant_codified_only(conn=Off())) is False

    def test_priming_short_circuits_the_read(self):
        class Explode:
            async def fetchval(self, *a, **k):
                raise AssertionError("cache should have answered")

        ps.prime_tenant_codified_only_cache(False)
        assert asyncio.run(ps.get_tenant_codified_only(conn=Explode())) is False

    def test_priming_false_is_cached_not_treated_as_absent(self):
        """`False` is a real value, not a cache miss — the `is not None` guard in
        the getter is what keeps a disabled gate from re-querying every call."""
        ps.prime_tenant_codified_only_cache(False)
        assert ps._tenant_codified_only_cache is False
