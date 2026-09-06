"""asyncpg pool + init_db() bootstrap (package split of the 6,551-line database.py).

Public surface unchanged: every symbol below was importable as
`app.database.<name>` before the split and still is. `_pool` and the
tenant/user/admin contextvars are intentionally NOT re-exported here (mutable
module-global state — re-exporting would hand out a stale binding); they
live only in app.database.pool.
"""
from app.database.pool import (  # noqa: F401
    set_tenant_id,
    get_tenant_id,
    set_user_id,
    get_user_id,
    set_is_admin,
    get_is_admin,
    _make_ssl_context,
    init_pool,
    get_pool,
    close_pool,
    has_pool,
    connection_or_direct,
    get_connection,
)
from app.database._json import decode_jsonb  # noqa: F401
from app.database.handbook import _ensure_handbook_tables  # noqa: F401
from app.database.bootstrap import init_db  # noqa: F401
