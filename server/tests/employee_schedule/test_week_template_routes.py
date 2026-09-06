"""Route-level invariants for atomic week-template editing and deletion."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import BlockCreate, BlockUpdate, WeekTemplateReplace
from app.matcha.routes.employee_schedule import week_templates
from app.matcha.services.scheduling import week_template_writes


COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
TEMPLATE_ID = UUID("22222222-2222-2222-2222-222222222222")
EXISTING_BLOCK_ID = UUID("33333333-3333-3333-3333-333333333333")
REMOVED_BLOCK_ID = UUID("44444444-4444-4444-4444-444444444444")
RULE_ID = UUID("55555555-5555-5555-5555-555555555555")
LOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")
ACTOR_ID = UUID("77777777-7777-7777-7777-777777777777")


class _AsyncContext:
    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *_args):
        return False

    def __init__(self, value):
        self.value = value


def _connection_factory(conn):
    return lambda: _AsyncContext(conn)


def _transaction():
    return _AsyncContext(None)


@pytest.mark.asyncio
async def test_replace_template_delegates_to_the_core_in_one_transaction(monkeypatch):
    """The route owns auth, the transaction and the audit row; the reconcile
    itself lives in services/scheduling/week_template_writes so Huume's
    location-profile executor can share it (services must not import routes)."""
    conn = MagicMock()
    conn.transaction.return_value = _transaction()
    audit = AsyncMock()
    core = AsyncMock(return_value=(
        {"id": TEMPLATE_ID, "name": "Weekday coverage", "location_id": LOCATION_ID,
         "color": None, "notes": None},
        [],
        {"added": 1, "updated": 1, "removed": 1},
    ))

    monkeypatch.setattr(week_templates, "get_connection", _connection_factory(conn))
    monkeypatch.setattr(week_templates, "require_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(week_templates, "replace_week_template_contents_core", core)
    monkeypatch.setattr(week_templates, "log_audit", audit)

    body = WeekTemplateReplace(name="Weekday coverage", blocks=[
        {
            "id": str(EXISTING_BLOCK_ID), "name": "Front-door opening shift",
            "role": "Usher", "start_time": "09:00", "end_time": "17:00",
            "days_of_week": [1, 2, 3, 4, 5],
        },
        {
            "name": "Weekend crew", "start_time": "10:00", "end_time": "18:00",
            "days_of_week": [0, 6],
        },
    ])
    await week_templates.replace_week_template_contents(
        TEMPLATE_ID, body, SimpleNamespace(id=ACTOR_ID),
    )

    assert conn.transaction.call_count == 1
    core.assert_awaited_once()
    assert core.await_args.kwargs["company_id"] == COMPANY_ID
    assert core.await_args.kwargs["week_template_id"] == TEMPLATE_ID
    assert core.await_args.kwargs["blocks"] == body.blocks
    assert audit.await_args.args[5] == "week_template.reconcile_blocks"
    assert audit.await_args.args[6] == {"added": 1, "updated": 1, "removed": 1}


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [
    (week_template_writes.WeekTemplateNotFound("Week template not found"), 404),
    (week_template_writes.JobUnavailable("Job is not available at this location"), 422),
])
async def test_replace_template_maps_core_errors_to_status_codes(monkeypatch, error, status):
    """The cores raise ValueErrors (no HTTPException in services); the route is
    what turns them back into HTTP."""
    conn = MagicMock()
    conn.transaction.return_value = _transaction()

    monkeypatch.setattr(week_templates, "get_connection", _connection_factory(conn))
    monkeypatch.setattr(week_templates, "require_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(
        week_templates, "replace_week_template_contents_core", AsyncMock(side_effect=error),
    )
    monkeypatch.setattr(week_templates, "log_audit", AsyncMock())

    body = WeekTemplateReplace(name="Weekday coverage", blocks=[])
    with pytest.raises(HTTPException) as excinfo:
        await week_templates.replace_week_template_contents(
            TEMPLATE_ID, body, SimpleNamespace(id=ACTOR_ID),
        )
    assert excinfo.value.status_code == status


@pytest.mark.asyncio
async def test_each_block_mutation_locks_its_parent_template(monkeypatch):
    conn = MagicMock()
    conn.transaction.return_value = _transaction()
    conn.fetchrow = AsyncMock(return_value={"id": EXISTING_BLOCK_ID})
    conn.execute = AsyncMock(return_value="DELETE 1")
    lock_template = AsyncMock(return_value={"id": TEMPLATE_ID, "location_id": LOCATION_ID})

    monkeypatch.setattr(week_templates, "get_connection", _connection_factory(conn))
    monkeypatch.setattr(week_templates, "require_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(week_templates, "_fetch_week_template_for_update_or_404", lock_template)
    monkeypatch.setattr(
        week_templates, "insert_block_core", AsyncMock(return_value={"id": EXISTING_BLOCK_ID}),
    )
    monkeypatch.setattr(week_templates, "assert_job_in_company", AsyncMock())
    monkeypatch.setattr(week_templates, "serialize_block", lambda row: row)
    monkeypatch.setattr(week_templates, "log_audit", AsyncMock())

    user = SimpleNamespace(id=ACTOR_ID)
    await week_templates.add_block(
        TEMPLATE_ID,
        BlockCreate(name="Opening", start_time="09:00", end_time="17:00"),
        user,
    )
    await week_templates.update_block(
        TEMPLATE_ID, EXISTING_BLOCK_ID, BlockUpdate(role="Usher"), user,
    )
    await week_templates.delete_block(TEMPLATE_ID, EXISTING_BLOCK_ID, user)

    assert lock_template.await_count == 3
    assert all(
        call.args == (conn, COMPANY_ID, TEMPLATE_ID)
        for call in lock_template.await_args_list
    )
    assert conn.transaction.call_count == 3


@pytest.mark.asyncio
async def test_delete_template_pauses_and_invalidates_dependent_auto_schedules(monkeypatch):
    conn = MagicMock()
    conn.transaction.return_value = _transaction()
    conn.fetch = AsyncMock(return_value=[{"id": RULE_ID, "location_id": LOCATION_ID}])
    conn.execute = AsyncMock(return_value="DELETE 1")
    audit = AsyncMock()
    lock_template = AsyncMock(return_value={"id": TEMPLATE_ID})

    monkeypatch.setattr(week_templates, "get_connection", _connection_factory(conn))
    monkeypatch.setattr(week_templates, "require_company_id", AsyncMock(return_value=COMPANY_ID))
    monkeypatch.setattr(week_templates, "_fetch_week_template_for_update_or_404", lock_template)
    monkeypatch.setattr(week_templates, "log_audit", audit)

    result = await week_templates.delete_week_template(TEMPLATE_ID, SimpleNamespace(id=ACTOR_ID))

    assert result == {"ok": True, "id": str(TEMPLATE_ID), "paused_auto_schedules": 1}
    lock_template.assert_awaited_once_with(conn, COMPANY_ID, TEMPLATE_ID)
    pause_sql = conn.fetch.await_args.args[0]
    assert "enabled = false" in pause_sql
    assert "schedule_version = schedule_version + 1" in pause_sql
    assert "next_run_at = NULL" in pause_sql
    assert audit.await_args_list[1].args[5] == "schedule_automation.pause_template_deleted"
