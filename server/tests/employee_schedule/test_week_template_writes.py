"""Invariants of the week-template create/reconcile cores.

These moved out of `routes/employee_schedule/week_templates.py` so Huume's
location-profile executor can reuse them; the SQL-shape assertions the route
test used to own live here now.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.matcha.models.scheduling.employee_schedule import (
    WeekTemplateBlockReplace, WeekTemplateCreate,
)
from app.matcha.services.scheduling import week_template_writes
from app.matcha.services.scheduling.week_template_writes import (
    JobUnavailable, WeekTemplateNotFound,
    create_week_template_core, replace_week_template_contents_core,
)


COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
TEMPLATE_ID = UUID("22222222-2222-2222-2222-222222222222")
EXISTING_BLOCK_ID = UUID("33333333-3333-3333-3333-333333333333")
REMOVED_BLOCK_ID = UUID("44444444-4444-4444-4444-444444444444")
LOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")
OTHER_LOCATION_ID = UUID("99999999-9999-9999-9999-999999999999")
ACTOR_ID = UUID("77777777-7777-7777-7777-777777777777")
JOB_ID = UUID("88888888-8888-8888-8888-888888888888")


def _template_row(name="Weekday coverage"):
    return {"id": TEMPLATE_ID, "name": name, "location_id": LOCATION_ID,
            "color": None, "notes": None}


def _conn(*, template=None, existing=None, job_row=None):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(side_effect=list(template or [_template_row()]))
    conn.fetch = AsyncMock(side_effect=[list(existing or []), []])
    conn.execute = AsyncMock()
    return conn


def _block(**overrides):
    payload = {
        "name": "Front-door opening shift", "role": "Usher",
        "start_time": "09:00", "end_time": "17:00", "days_of_week": [1, 2, 3, 4, 5],
    }
    payload.update(overrides)
    return WeekTemplateBlockReplace(**payload)


@pytest.mark.asyncio
async def test_replace_core_updates_existing_and_deletes_omitted(monkeypatch):
    conn = _conn(
        template=[_template_row("Old name"), _template_row()],
        existing=[{"id": EXISTING_BLOCK_ID}, {"id": REMOVED_BLOCK_ID}],
    )
    insert = AsyncMock(return_value={"id": JOB_ID})
    monkeypatch.setattr(week_template_writes, "insert_block_core", insert)
    monkeypatch.setattr(week_template_writes, "assert_job_available", AsyncMock())

    _, _, counts = await replace_week_template_contents_core(
        conn, company_id=COMPANY_ID, week_template_id=TEMPLATE_ID,
        name="Weekday coverage", actor_user_id=ACTOR_ID,
        blocks=[
            _block(id=EXISTING_BLOCK_ID),
            _block(name="Weekend crew", start_time="10:00", end_time="18:00", days_of_week=[0, 6]),
        ],
    )

    assert counts == {"added": 1, "updated": 1, "removed": 1}
    assert insert.await_count == 1
    executed_sql = "\n".join(call.args[0] for call in conn.execute.await_args_list)
    assert "UPDATE schedule_shift_templates" in executed_sql
    assert "DELETE FROM schedule_shift_templates WHERE id = ANY" in executed_sql
    update_sql = conn.execute.await_args_list[0].args[0]
    # Still not editable through this shape — owned elsewhere.
    for hidden_field in ("department", "color", "notes"):
        assert hidden_field not in update_sql
    assert "Front-door opening shift" in conn.execute.await_args_list[0].args


@pytest.mark.asyncio
async def test_replace_core_writes_job_id_on_an_updated_block(monkeypatch):
    """Without this the editor's own save strips the job link off a block an
    agent created, and the generated shifts lose their job-derived role."""
    conn = _conn(
        template=[_template_row("Old name"), _template_row()],
        existing=[{"id": EXISTING_BLOCK_ID}],
    )
    monkeypatch.setattr(week_template_writes, "assert_job_available", AsyncMock())

    await replace_week_template_contents_core(
        conn, company_id=COMPANY_ID, week_template_id=TEMPLATE_ID,
        name=None, actor_user_id=ACTOR_ID,
        blocks=[_block(id=EXISTING_BLOCK_ID, job_id=JOB_ID)],
    )

    update_call = conn.execute.await_args_list[0]
    assert "job_id = $10" in update_call.args[0]
    assert JOB_ID in update_call.args


@pytest.mark.asyncio
async def test_replace_core_rejects_a_block_id_from_another_template():
    conn = _conn(existing=[{"id": EXISTING_BLOCK_ID}])
    with pytest.raises(WeekTemplateNotFound):
        await replace_week_template_contents_core(
            conn, company_id=COMPANY_ID, week_template_id=TEMPLATE_ID,
            name=None, actor_user_id=ACTOR_ID, blocks=[_block(id=REMOVED_BLOCK_ID)],
        )


@pytest.mark.asyncio
async def test_replace_core_raises_not_found_for_a_foreign_template():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(WeekTemplateNotFound):
        await replace_week_template_contents_core(
            conn, company_id=COMPANY_ID, week_template_id=TEMPLATE_ID,
            name=None, actor_user_id=ACTOR_ID, blocks=[],
        )


@pytest.mark.asyncio
async def test_assert_job_available_rejects_another_locations_job():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"name": "Barista", "location_id": OTHER_LOCATION_ID})
    with pytest.raises(JobUnavailable):
        await week_template_writes.assert_job_available(
            conn, COMPANY_ID, JOB_ID, location_id=LOCATION_ID,
        )


@pytest.mark.asyncio
async def test_assert_job_available_allows_a_company_wide_job():
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={"name": "Barista", "location_id": None})
    row = await week_template_writes.assert_job_available(
        conn, COMPANY_ID, JOB_ID, location_id=LOCATION_ID,
    )
    assert row["name"] == "Barista"


@pytest.mark.asyncio
async def test_create_core_inserts_parent_then_each_block(monkeypatch):
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=_template_row())
    insert = AsyncMock(return_value={"id": EXISTING_BLOCK_ID})
    monkeypatch.setattr(week_template_writes, "insert_block_core", insert)

    tpl, blocks = await create_week_template_core(
        conn, company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        body=WeekTemplateCreate(
            name="Downtown default week", location_id=LOCATION_ID,
            blocks=[{"name": "Opening", "start_time": "09:00", "end_time": "17:00"}],
        ),
    )

    assert tpl["id"] == TEMPLATE_ID
    assert len(blocks) == 1
    assert insert.await_args.kwargs["location_id"] == LOCATION_ID
