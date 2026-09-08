"""`app/matcha/dependencies.py:require_feature` — the paid-feature gate.

Root `CLAUDE.md` lists "Don't bypass `require_feature`" as a standing pitfall
("frontends will URL-hop to a feature page; the gate is what surfaces the
upsell instead of 403"), and every paid flag in the product is mounted through
this one factory — yet nothing exercised its branches. The interesting parts
are all edges: the admin bypass, the `individual`-user carve-out, the platform
visibility list checked BEFORE the company lookup, and the tier overlay, which
is why a Matcha-X company passes a `training` check whose stored
`enabled_features` says nothing about training.

    cd server && ./venv/bin/python -m pytest tests/dependencies/test_require_feature.py -q
"""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.matcha import dependencies
from tests._helpers.routes import QueryConn

COMPANY = uuid4()


def _run(coro):
    return asyncio.run(coro)


def _user(role="client"):
    return SimpleNamespace(id=uuid4(), role=role, email="admin@example.com")


def _company_conn(features: dict, signup_source="bespoke", visible=None):
    """A connection answering the two queries `require_feature` can issue.

    `visible=None` means "nothing is shelved" — several paid flags (incidents
    among them) are KNOWN_PLATFORM_ITEMS, so a default of `[]` would make the
    platform check refuse before the company flag is ever read, and every
    company-flag assertion below would pass for the wrong reason.
    """
    from app.core.routes.admin import KNOWN_PLATFORM_ITEMS

    visible_list = sorted(KNOWN_PLATFORM_ITEMS) if visible is None else visible
    return QueryConn(
        fetchval={"platform_settings": json.dumps(visible_list)},
        fetchrow={
            "FROM companies": {
                "enabled_features": features,
                "signup_source": signup_source,
            }
        },
    )


def _check(monkeypatch, feature, user, conn, *, company_id=COMPANY):
    monkeypatch.setattr(dependencies, "get_connection", lambda *a, **k: conn)
    monkeypatch.setattr(
        dependencies,
        "resolve_accessible_company_scope",
        _async_return({"company_id": company_id}),
    )
    return _run(dependencies.require_feature(feature)(current_user=user))


def _async_return(value):
    async def _inner(*_a, **_k):
        return value

    return _inner


class TestAdminBypass:
    def test_admin_passes_without_touching_the_database(self, monkeypatch):
        # A conn that raises on any query proves the bypass short-circuits
        # before the company lookup.
        exploding = QueryConn()
        user = _user(role="admin")
        assert _check(monkeypatch, "training", user, exploding) is user
        assert exploding.calls == []


class TestIndividualCarveOut:
    def test_individual_gets_matcha_work_without_a_company(self, monkeypatch):
        user = _user(role="individual")
        assert _check(monkeypatch, "matcha_work", user, QueryConn()) is user

    def test_the_carve_out_is_only_matcha_work(self, monkeypatch):
        # A personal user must NOT inherit every flag — the carve-out exists
        # for the personal workspace alone.
        user = _user(role="individual")
        conn = _company_conn({"training": False})
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, "training", user, conn)
        assert excinfo.value.status_code == 403


class TestCompanyFlags:
    def test_enabled_flag_passes(self, monkeypatch):
        user = _user()
        conn = _company_conn({"incidents": True})
        assert _check(monkeypatch, "incidents", user, conn) is user

    def test_disabled_flag_is_403_not_404(self, monkeypatch):
        # 403 is what surfaces the upsell; a 404 would read as "broken".
        user = _user()
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, "incidents", user, _company_conn({"incidents": False}))
        assert excinfo.value.status_code == 403
        assert "incidents" in excinfo.value.detail

    def test_unknown_flag_is_refused_rather_than_defaulting_open(self, monkeypatch):
        user = _user()
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, "a_flag_nobody_defined", user, _company_conn({}))
        assert excinfo.value.status_code == 403

    def test_missing_company_row_is_404(self, monkeypatch):
        user = _user()
        conn = _company_conn({})
        # Same visibility answer, but the company row is gone.
        conn.set("fetchrow", "FROM companies", None)
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, "incidents", user, conn)
        assert excinfo.value.status_code == 404

    def test_no_company_scope_is_403(self, monkeypatch):
        user = _user()
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, "incidents", user, _company_conn({}), company_id=None)
        assert excinfo.value.status_code == 403
        assert "No company" in excinfo.value.detail

    def test_the_company_lookup_is_scoped_by_id(self, monkeypatch):
        # Tenant scoping: the row must be fetched by the resolved company id,
        # never by anything the caller supplied.
        user = _user()
        conn = _company_conn({"incidents": True})
        _check(monkeypatch, "incidents", user, conn)
        assert conn.args_for("FROM companies")[0] == COMPANY


class TestTierOverlay:
    def test_matcha_x_gets_training_without_it_being_stored(self, monkeypatch):
        # The X bundle is a read-time overlay (TIER_REQUIRED_FEATURES), not
        # stored flags — a gate that read enabled_features raw would refuse a
        # paying X tenant.
        user = _user()
        conn = _company_conn({"incidents": True}, signup_source="matcha_x")
        assert _check(monkeypatch, "training", user, conn) is user

    def test_lite_is_still_refused_training(self, monkeypatch):
        # Lite force-asserts training OFF; the overlay must not leak upward.
        user = _user()
        conn = _company_conn({"incidents": True, "training": True}, signup_source="matcha_lite")
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, "training", user, conn)
        assert excinfo.value.status_code == 403


class TestPlatformVisibility:
    def test_a_shelved_platform_item_is_refused_before_the_company_lookup(self, monkeypatch):
        from app.core.routes.admin import KNOWN_PLATFORM_ITEMS

        if not KNOWN_PLATFORM_ITEMS:
            pytest.skip("no platform items declared")
        item = sorted(KNOWN_PLATFORM_ITEMS)[0]
        user = _user()
        # Company row says the flag is ON; platform visibility says the
        # feature is shelved, and that must win.
        conn = _company_conn({item: True}, visible=[])
        with pytest.raises(HTTPException) as excinfo:
            _check(monkeypatch, item, user, conn)
        assert excinfo.value.status_code == 403
        assert "not currently available" in excinfo.value.detail
        assert not any("FROM companies" in sql for sql in conn.sql_for("fetchrow"))

    def test_a_visible_platform_item_falls_through_to_the_company_flag(self, monkeypatch):
        from app.core.routes.admin import KNOWN_PLATFORM_ITEMS

        if not KNOWN_PLATFORM_ITEMS:
            pytest.skip("no platform items declared")
        item = sorted(KNOWN_PLATFORM_ITEMS)[0]
        user = _user()
        conn = _company_conn({item: True}, visible=[item])
        assert _check(monkeypatch, item, user, conn) is user
