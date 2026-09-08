"""The shared route-test helpers, tested.

`tests/_helpers/routes.py` is infrastructure other tests trust silently: when
it hands back the wrong object, the test that depends on it does not error, it
passes for the wrong reason. Both of the bugs pinned below shipped that way.

    cd server && ./venv/bin/python -m pytest tests/_helpers -q
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, Depends

from tests._helpers.routes import Queue, QueryConn, UnexpectedQuery, connection_patch, route_client


def _dep():  # never runs — every test overrides it
    raise AssertionError("the real dependency was not overridden")


def _router() -> APIRouter:
    router = APIRouter()

    @router.get("/who")
    def who(user=Depends(_dep)):
        return {"id": str(getattr(user, "id", None)), "type": type(user).__name__}

    return router


class TestRouteClientOverrides:
    def test_a_mock_user_is_injected_not_invoked(self):
        # A MagicMock is callable, so the old `value if callable(value)` test
        # registered the mock itself as the PROVIDER: FastAPI called it, the
        # endpoint received `mock()`, and FastAPI turned the mock's
        # `(*args, **kwargs)` signature into two required query params — so the
        # request 422'd before the handler ran.
        user = MagicMock()
        user.id = "USER-42"
        with route_client(_router(), overrides={_dep: user}) as client:
            resp = client.get("/who")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == "USER-42"

    def test_an_async_mock_user_is_injected_not_awaited(self):
        user = AsyncMock()
        user.id = "USER-43"
        with route_client(_router(), overrides={_dep: user}) as client:
            resp = client.get("/who")
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == "USER-43"

    def test_a_plain_object_is_injected(self):
        user = SimpleNamespace(id="USER-7")
        with route_client(_router(), overrides={_dep: user}) as client:
            assert client.get("/who").json()["id"] == "USER-7"

    def test_a_lambda_is_used_as_the_provider(self):
        user = SimpleNamespace(id="USER-8")
        with route_client(_router(), overrides={_dep: lambda: user}) as client:
            assert client.get("/who").json()["id"] == "USER-8"

    def test_a_real_function_is_used_as_the_provider(self):
        def provide():
            return SimpleNamespace(id="USER-9")

        with route_client(_router(), overrides={_dep: provide}) as client:
            assert client.get("/who").json()["id"] == "USER-9"

    def test_overrides_do_not_leak_out_of_the_context(self):
        app_overrides = {}
        with route_client(_router(), overrides={_dep: SimpleNamespace(id="x")}) as client:
            app_overrides = client.app.dependency_overrides
            assert app_overrides
        assert app_overrides == {}


class TestQueryConnFetch:
    def test_a_registered_row_list_is_returned_whole(self):
        # The declared type of `fetch` is a row list. Treating any list as a
        # pop-queue returned row_a alone, and production's `for r in rows`
        # then iterated that dict's keys.
        rows = [{"id": 1}, {"id": 2}]
        conn = QueryConn(fetch={"FROM employees": rows})
        assert asyncio.run(conn.fetch("SELECT * FROM employees")) == rows
        # ...and again, unchanged: a plain list is not consumed.
        assert asyncio.run(conn.fetch("SELECT * FROM employees")) == rows

    def test_a_queue_is_consumed_one_call_at_a_time(self):
        conn = QueryConn(fetch={"FROM shifts": Queue([[{"id": 1}], []])})
        assert asyncio.run(conn.fetch("SELECT * FROM shifts")) == [{"id": 1}]
        assert asyncio.run(conn.fetch("SELECT * FROM shifts")) == []

    def test_an_exhausted_queue_says_so(self):
        conn = QueryConn(fetchrow={"FROM users": Queue([{"id": 1}])})
        asyncio.run(conn.fetchrow("SELECT 1 FROM users"))
        with pytest.raises(UnexpectedQuery, match="exhausted"):
            asyncio.run(conn.fetchrow("SELECT 1 FROM users"))


class TestQueryConnDispatch:
    def test_an_unregistered_query_names_the_sql_and_the_keys(self):
        conn = QueryConn(fetchrow={"FROM companies": {"id": 1}})
        with pytest.raises(UnexpectedQuery) as exc:
            asyncio.run(conn.fetchrow("SELECT * FROM widgets"))
        assert "FROM widgets" in str(exc.value)
        assert "'FROM companies'" in str(exc.value)

    def test_an_unregistered_fetch_raises_like_every_other_kind(self):
        with pytest.raises(UnexpectedQuery, match="unexpected fetch"):
            asyncio.run(QueryConn().fetch("SELECT 1 FROM widgets"))

    def test_writes_are_a_noop_until_a_test_opts_into_strict(self):
        assert asyncio.run(QueryConn().execute("UPDATE widgets SET x = 1")) == "OK"
        with pytest.raises(UnexpectedQuery, match="unexpected execute"):
            asyncio.run(QueryConn(strict_execute=True).execute("UPDATE widgets SET x = 1"))

    def test_calls_are_recorded_for_tenant_scoping_assertions(self):
        conn = QueryConn(fetchrow={"FROM employees": {"id": 1}})
        asyncio.run(conn.fetchrow("SELECT * FROM employees WHERE company_id = $1", "CO-1"))
        assert "company_id = $1" in conn.sql_for("fetchrow")[0]
        assert conn.args_for("FROM employees") == ("CO-1",)
        with pytest.raises(AssertionError, match="no query containing"):
            conn.args_for("FROM widgets")

    def test_it_is_its_own_async_context_manager(self):
        conn = QueryConn(fetchval={"SELECT 1": 7})

        async def _use():
            async with conn as c:
                return await c.fetchval("SELECT 1")

        assert asyncio.run(_use()) == 7


class TestConnectionPatch:
    def test_it_points_get_connection_at_the_fake(self, monkeypatch):
        module = SimpleNamespace(get_connection=lambda: "the real pool")
        conn = QueryConn(fetchval={"SELECT 1": 5})
        with connection_patch(monkeypatch, module, conn) as yielded:
            assert yielded is conn
            assert module.get_connection() is conn
