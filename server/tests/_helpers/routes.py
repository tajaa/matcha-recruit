"""Shared helpers for testing a router as an HTTP surface.

Only ~18 of this suite's 553 files exercise anything over HTTP, so route-level
authorization, feature gating, tenant scoping and status codes are mostly
unasserted. The pattern for doing it already existed — mount ONE router on a
bare `FastAPI()` and override its auth dependency, as
`tests/employee_schedule/test_planning_routes.py` and the cappe billing tests
do — it was just copy-pasted rather than shared. This is that pattern, factored
out. Mounting one router (not `app.main`) keeps the test off the real
dependency graph: no pool, no settings, no lifespan.

    from tests._helpers.routes import QueryConn, route_client

    def test_denies_other_tenant():
        with route_client(widgets.router, overrides={widgets.require_client: user}) as client:
            assert client.get("/widgets/other-company-id").status_code == 404

`QueryConn` is the other half. The suite's dominant fake is a positional queue
(`conn.fetchrow.side_effect = [row_a, row_b]`), which silently mis-binds the
moment production adds, removes or reorders a query — that is precisely how 26
tests in the channels family rotted into `KeyError: 'channel_scope'` and
`unexpected fetchrow: SELECT id, role, email ...`. `QueryConn` matches on the
SQL instead, so an added query is an explicit, readable failure and an
unrelated one cannot shift every later row by one.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping, Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient


@contextmanager
def route_client(
    router: Any,
    *,
    overrides: Mapping[Callable, Any] | None = None,
    prefix: str = "",
) -> Iterator[TestClient]:
    """Mount `router` alone and yield a `TestClient` for it.

    `overrides` maps a dependency callable to the value it should resolve to —
    usually the route module's own auth dependency to a fake user, e.g.
    `{planning.require_company_member: user}`. A non-callable value is wrapped,
    so `{dep: user}` and `{dep: lambda: user}` both work.
    """
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    for dependency, value in (overrides or {}).items():
        app.dependency_overrides[dependency] = value if callable(value) else (lambda v=value: v)
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


class UnexpectedQuery(AssertionError):
    """Raised when production issues a query the test never described."""


class QueryConn:
    """An asyncpg-shaped fake connection that dispatches on the SQL text.

    Register each query by a substring distinctive enough to identify it:

        conn = QueryConn(fetchrow={
            "FROM companies": {"enabled_features": {...}, "signup_source": "bespoke"},
            "FROM users": {"id": user_id, "role": "client"},
        })

    A value that is a list is consumed one call at a time (for a query the code
    genuinely issues more than once with different results); anything else is
    returned on every match. Unmatched queries raise `UnexpectedQuery` naming
    the SQL and every registered key — the failure tells you what production
    started asking for, instead of handing back the wrong row.
    """

    def __init__(
        self,
        *,
        fetchrow: Mapping[str, Any] | None = None,
        fetchval: Mapping[str, Any] | None = None,
        fetch: Mapping[str, Sequence[Any]] | None = None,
        execute: Mapping[str, Any] | None = None,
        strict_execute: bool = False,
    ) -> None:
        self._tables = {
            "fetchrow": dict(fetchrow or {}),
            "fetchval": dict(fetchval or {}),
            "fetch": dict(fetch or {}),
            "execute": dict(execute or {}),
        }
        # Writes are usually incidental to what a test asserts, so an
        # unregistered execute() is a no-op unless the test opts in.
        self._strict_execute = strict_execute
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []

    def _dispatch(self, kind: str, sql: str, args: tuple[Any, ...]) -> Any:
        self.calls.append((kind, sql, args))
        table = self._tables[kind]
        for needle, value in table.items():
            if needle in sql:
                if isinstance(value, list):
                    if not value:
                        raise UnexpectedQuery(
                            f"{kind} matched {needle!r} but its queued results are exhausted"
                        )
                    return value.pop(0)
                return value
        if kind == "execute" and not self._strict_execute:
            return "OK"
        if kind == "fetch":
            registered = ", ".join(repr(k) for k in table) or "nothing"
            raise UnexpectedQuery(
                f"unexpected {kind}: {sql.strip()[:160]!r}\nregistered: {registered}"
            )
        registered = ", ".join(repr(k) for k in table) or "nothing"
        raise UnexpectedQuery(
            f"unexpected {kind}: {sql.strip()[:160]!r}\nregistered: {registered}"
        )

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        return self._dispatch("fetchrow", sql, args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        return self._dispatch("fetchval", sql, args)

    async def fetch(self, sql: str, *args: Any) -> Any:
        return self._dispatch("fetch", sql, args)

    async def execute(self, sql: str, *args: Any) -> Any:
        return self._dispatch("execute", sql, args)

    def set(self, kind: str, needle: str, value: Any) -> "QueryConn":
        """Register or replace one answer after construction. Returns self so a
        shared fixture can be adjusted inline for a single test."""
        self._tables[kind][needle] = value
        return self

    def sql_for(self, kind: str) -> list[str]:
        """Every SQL string this connection saw for `kind` — for asserting that
        a tenant filter was actually applied."""
        return [sql for called_kind, sql, _ in self.calls if called_kind == kind]

    def args_for(self, needle: str) -> tuple[Any, ...]:
        """Bound parameters of the first call whose SQL contains `needle`."""
        for _, sql, args in self.calls:
            if needle in sql:
                return args
        raise AssertionError(f"no query containing {needle!r} was issued")

    # asyncpg connections are used as `async with get_connection() as conn`
    # in most of this codebase; support being the context manager itself so a
    # test can patch get_connection with `lambda: conn`.
    async def __aenter__(self) -> "QueryConn":
        return self

    async def __aexit__(self, *_exc: Any) -> bool:
        return False


@contextmanager
def connection_patch(monkeypatch: Any, module: Any, conn: QueryConn) -> Iterator[QueryConn]:
    """Point `module.get_connection` at `conn`.

    Patch the module that DEFINES the caller, never a package facade that
    re-exports it — `server/CLAUDE.md` documents the silent no-op that results,
    and two tests in this suite were failing on exactly that
    (`app.matcha.routes.employees has no attribute get_connection`).
    """
    monkeypatch.setattr(module, "get_connection", lambda *a, **k: conn)
    yield conn
