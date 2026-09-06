"""Pure + fake-connection tests for the per-location scheduling profile."""

import json

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.matcha.services.huume import schedule_profile_skill
from app.matcha.services.scheduling import location_profile
from app.matcha.services.scheduling.location_profile import (
    bundle_leader_jobs, hours_answered, missing_fields, open_weekdays,
    profile_context_lines, validate_operating_hours, week_rules_established,
    week_rules_refusal,
)


COMPANY_ID = UUID("11111111-1111-1111-1111-111111111111")
LOCATION_ID = UUID("66666666-6666-6666-6666-666666666666")
TEMPLATE_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("88888888-8888-8888-8888-888888888888")
ACTOR_ID = UUID("77777777-7777-7777-7777-777777777777")


# A week's worth of answered hours: closed Sunday/Saturday, open the rest.
# `missing_fields` wants every weekday answered, so a one-day dict is NOT a
# location whose hours are on file.
FULL_WEEK_HOURS = {
    "0": None, "6": None,
    **{str(day): {"open": "08:00", "close": "17:00"} for day in range(1, 6)},
}


def _bundle(*, hours=None, blocks=None, leader=None, week_start=None, notes=None,
            leader_required=None):
    if leader_required is None and leader:
        leader_required = True
    return {
        "profile": {
            "operating_hours": hours if hours is not None else {},
            "leader_job_id": JOB_ID if leader else None,
            "leader_required": leader_required,
            "week_start_weekday": week_start,
            "notes": notes,
        },
        "template": {"id": str(TEMPLATE_ID), "name": "Downtown default week",
                     "blocks": blocks or []} if blocks is not None else None,
        "leader_job_name": leader,
    }


# --- validate_operating_hours -------------------------------------------------

def test_validate_operating_hours_normalizes_and_keeps_closed_days():
    hours = validate_operating_hours({0: None, "1": {"open": "8:00", "close": "17:30"}})
    assert hours == {"0": None, "1": {"open": "08:00", "close": "17:30"}}


def test_validate_operating_hours_allows_an_overnight_window():
    """Bars and 24h stores close after midnight; close <= open is not an error."""
    hours = validate_operating_hours({"5": {"open": "20:00", "close": "02:00"}})
    assert hours["5"] == {"open": "20:00", "close": "02:00"}


@pytest.mark.parametrize("payload", [
    {"sunday": {"open": "08:00", "close": "17:00"}},
    {"7": {"open": "08:00", "close": "17:00"}},
    {"-1": {"open": "08:00", "close": "17:00"}},
    {"1": {"open": "8am", "close": "5pm"}},
    {"1": {"open": "08:00"}},
    {"1": "08:00-17:00"},
    ["08:00"],
])
def test_validate_operating_hours_rejects_malformed_input(payload):
    with pytest.raises(ValueError):
        validate_operating_hours(payload)


def test_open_weekdays_ignores_closed_and_unknown_days():
    assert open_weekdays({"0": None, "1": {"open": "08:00", "close": "17:00"}}) == [1]


# --- missing_fields / context lines ------------------------------------------

def test_missing_fields_lists_all_three_for_a_fresh_location():
    assert missing_fields({"profile": None, "template": None}) == [
        "operating_hours", "staffing_pattern", "leader_rule",
    ]


def test_missing_fields_is_empty_once_everything_is_answered():
    bundle = _bundle(
        hours=FULL_WEEK_HOURS,
        blocks=[{"name": "Opener", "job_name": "Barista", "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        leader="Shift Lead",
    )
    assert missing_fields(bundle) == []
    assert week_rules_established(bundle) is True


@pytest.mark.parametrize("hours, answered", [
    (None, False),
    ({}, False),
    # One day answered is not the week: the other six still bound nothing.
    ({"1": {"open": "08:00", "close": "17:00"}}, False),
    # "Closed Sundays" and nothing else used to read as hours-on-file because
    # the check was truthiness of the whole dict.
    ({"0": None}, False),
    ({str(day): None for day in range(7)}, False),
    (FULL_WEEK_HOURS, True),
])
def test_hours_answered_needs_all_seven_days_and_one_open_day(hours, answered):
    assert hours_answered(hours) is answered


@pytest.mark.parametrize("leader_required, leader, missing", [
    (None, None, True),          # never asked
    (False, None, False),        # answered: no lead needed
    (True, None, True),          # required but nobody named the job
    (True, "Shift Lead", False),
])
def test_missing_fields_leader_rule_is_tri_state(leader_required, leader, missing):
    bundle = _bundle(
        hours=FULL_WEEK_HOURS,
        blocks=[{"name": "Opener", "job_name": "Barista", "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        leader=leader, leader_required=leader_required,
    )
    assert ("leader_rule" in missing_fields(bundle)) is missing


def test_missing_fields_reasks_when_the_only_leader_job_was_deleted():
    """`leader_job_ids` is a plain array with no per-element FK, so deleting a
    leader job leaves its uuid on the profile. The gate reads the RESOLVED set
    — otherwise the rule passes as answered while the coverage evaluator, which
    only ever sees ids that resolve, stops checking for a lead at all."""
    bundle = _bundle(
        hours=FULL_WEEK_HOURS,
        blocks=[{"name": "Opener", "job_name": "Barista", "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        leader_required=True,
    )
    bundle["profile"]["leader_job_ids"] = [JOB_ID]
    bundle["leader_jobs"] = []          # what load_profile_bundle resolved

    assert "leader_rule" in missing_fields(bundle)


def test_missing_fields_is_satisfied_while_one_leader_job_survives():
    """Any ONE of the set is lead coverage, so losing a second leader job is
    not a re-ask."""
    bundle = _bundle(
        hours=FULL_WEEK_HOURS,
        blocks=[{"name": "Opener", "job_name": "Barista", "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        leader_required=True,
    )
    bundle["profile"]["leader_job_ids"] = [JOB_ID, TEMPLATE_ID]
    bundle["leader_jobs"] = [{"id": str(JOB_ID), "name": "Shift Lead"}]

    assert missing_fields(bundle) == []


def test_bundle_leader_jobs_reads_a_whole_set_off_an_unresolved_bundle():
    """A bundle assembled outside `load_profile_bundle` carries no resolved
    list; its profile columns are the answer, and the set is not truncated to
    the mirror."""
    jobs = bundle_leader_jobs({
        "profile": {"leader_job_ids": [JOB_ID, TEMPLATE_ID], "leader_job_id": JOB_ID},
        "leader_job_name": "Shift Lead",
    })

    assert [job["id"] for job in jobs] == [str(JOB_ID), str(TEMPLATE_ID)]
    assert jobs[0]["name"] == "Shift Lead"


def test_week_rules_refusal_names_one_missing_answer_and_the_location():
    fresh = week_rules_refusal({"profile": None, "template": None}, location_name="Downtown")
    assert "Downtown" in fresh
    # One question at a time — a list of three is a wall, not an ask.
    assert "hours" in fresh and "staffing pattern" not in fresh

    hours_only = week_rules_refusal(_bundle(hours=FULL_WEEK_HOURS), location_name="Downtown")
    assert "staffing pattern" in hours_only

    complete = _bundle(
        hours=FULL_WEEK_HOURS,
        blocks=[{"name": "Opener", "job_name": "Barista", "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        leader_required=False,
    )
    assert week_rules_refusal(complete, location_name="Downtown") is None


def test_profile_context_lines_render_pattern_leader_and_gaps():
    lines = profile_context_lines(_bundle(
        hours=FULL_WEEK_HOURS,
        blocks=[{"name": "Opener", "job_name": "Barista", "days_of_week": [1, 2],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        week_start=0, notes="Busy on match days",
    ))
    text = "\n".join(lines)
    assert "Sun closed" in text
    assert "Mon 08:00–17:00" in text
    assert "Opener [Barista] Mon, Tue 08:00–16:00 x2" in text
    assert "Week starts: Sunday" in text
    assert "Busy on match days" in text
    # The leader rule is the one thing still unanswered here.
    assert "Missing: leader_rule" in text


def test_profile_context_lines_say_so_when_nothing_is_set():
    text = "\n".join(profile_context_lines({"profile": None, "template": None}))
    assert "Hours: not set" in text
    assert "Staffing pattern: not set" in text
    assert "Leader coverage: not set" in text


def test_profile_context_lines_distinguish_no_lead_needed_from_unasked():
    """An answered "no" must not read as an open question, or the interview
    asks it again on every turn."""
    text = "\n".join(profile_context_lines(_bundle(hours=FULL_WEEK_HOURS, leader_required=False)))
    assert "Leader coverage: not required" in text
    assert "leader_rule" not in text


# --- leader-rule materialization ---------------------------------------------

def test_leader_rule_becomes_real_blocks_grouped_by_window():
    """The planner only knows demand, so "a lead is always on" has to become
    staffing demand or it is silently ignored."""
    hours = {
        "1": {"open": "08:00", "close": "17:00"},
        "2": {"open": "08:00", "close": "17:00"},
        "6": {"open": "10:00", "close": "22:00"},
    }
    blocks = schedule_profile_skill._leader_blocks(
        hours, {"id": JOB_ID, "name": "Shift Lead"}, [],
    )
    assert len(blocks) == 2
    weekday_block = next(b for b in blocks if b["start_time"] == "08:00")
    assert weekday_block["days_of_week"] == [1, 2]
    assert weekday_block["required_staff"] == 1
    # str, not UUID: the staged action is persisted as thread JSONB.
    assert weekday_block["job_id"] == str(JOB_ID)
    assert weekday_block["role"] == "Shift Lead"


def test_leader_rule_adds_nothing_when_a_block_already_uses_that_job():
    blocks = schedule_profile_skill._leader_blocks(
        {"1": {"open": "08:00", "close": "17:00"}},
        {"id": JOB_ID, "name": "Shift Lead"},
        [{"name": "Opener", "job_id": JOB_ID}],
    )
    assert blocks == []


# --- replace_default_pattern --------------------------------------------------

@pytest.mark.asyncio
async def test_replace_default_pattern_maps_names_onto_existing_block_ids(monkeypatch):
    """Chat names blocks, it doesn't know their ids. Matching on
    (name, start, end) keeps generated shifts' template links intact."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={
        "id": UUID("55555555-5555-5555-5555-555555555555"),
        "default_week_template_id": TEMPLATE_ID,
    })
    existing_id = UUID("33333333-3333-3333-3333-333333333333")
    conn.fetch = AsyncMock(return_value=[
        {"id": existing_id, "name": "Opener", "start_time": "08:00", "end_time": "16:00"},
    ])
    core = AsyncMock(return_value=({}, [], {}))
    monkeypatch.setattr(location_profile, "replace_week_template_contents_core", core)

    template_id = await location_profile.replace_default_pattern(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        blocks=[
            {"name": "opener", "job_id": JOB_ID, "job_name": "Barista", "days_of_week": [1],
             "start_time": "08:00", "end_time": "16:00", "required_staff": 2},
            {"name": "Closer", "job_id": JOB_ID, "job_name": "Barista", "days_of_week": [1],
             "start_time": "16:00", "end_time": "22:00", "required_staff": 1},
        ],
    )

    assert template_id == TEMPLATE_ID
    sent = core.await_args.kwargs["blocks"]
    assert sent[0].id == existing_id      # matched case-insensitively
    assert sent[1].id is None             # genuinely new
    assert sent[0].job_id == JOB_ID


@pytest.mark.asyncio
async def test_replace_default_pattern_creates_a_location_scoped_template(monkeypatch):
    """A company-wide template (location_id NULL) shows in every store's
    picker — it must never become one store's default."""
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value={
        "id": UUID("55555555-5555-5555-5555-555555555555"),
        "default_week_template_id": None,
    })
    conn.fetchval = AsyncMock(return_value="Downtown")
    conn.fetch = AsyncMock(return_value=[])
    create = AsyncMock(return_value=({"id": TEMPLATE_ID}, []))
    monkeypatch.setattr(location_profile, "create_week_template_core", create)
    monkeypatch.setattr(location_profile, "replace_week_template_contents_core",
                        AsyncMock(return_value=({}, [], {})))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)

    await location_profile.replace_default_pattern(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        blocks=[{"name": "Opener", "job_id": JOB_ID, "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 1}],
    )

    body = create.await_args.kwargs["body"]
    assert body.location_id == LOCATION_ID
    assert body.name == "Downtown default week"
    assert upsert.await_args.kwargs["default_week_template_id"] == TEMPLATE_ID


# --- resolve_profile_args -----------------------------------------------------

def _resolver_conn(job_row):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[{"name": "Barista"}, {"name": "Shift Lead"}])
    # No saved profile yet: `resolve_profile_args` reads the stored setup so a
    # later turn can merge onto it rather than overwrite it.
    conn.fetchrow = AsyncMock(return_value=None)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=conn)
    context.__aexit__ = AsyncMock(return_value=False)
    return conn, context, job_row


@pytest.mark.asyncio
async def test_resolve_profile_args_clarifies_on_an_unknown_job(monkeypatch):
    conn, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name", AsyncMock(return_value=None))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"blocks": [{"name": "Opener", "job_name": "Barrista", "days_of_week": [1],
                          "start_time": "08:00", "end_time": "16:00", "required_staff": 1}]},
    )

    assert result["status"] == "clarify"
    assert result["job_options"] == ["Barista", "Shift Lead"]


@pytest.mark.asyncio
async def test_resolve_profile_args_labels_blocks_with_the_jobs_real_name(monkeypatch):
    """The job's own name is the canonical role label — same rule
    create_shift_core enforces on every generated shift."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": JOB_ID, "name": "Barista"}))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={
            "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
            "blocks": [{"name": "Opener", "job_name": "barista", "days_of_week": [1],
                        "start_time": "08:00", "end_time": "16:00", "required_staff": 2}],
        },
    )

    assert result["status"] == "ok"
    assert result["blocks"][0]["role"] == "Barista"
    assert result["blocks"][0]["job_id"] == str(JOB_ID)
    assert "1 shift block" in result["summary"]


@pytest.mark.asyncio
@pytest.mark.parametrize("block,fragment", [
    ({"name": "", "job_name": "Barista", "days_of_week": [1],
      "start_time": "08:00", "end_time": "16:00", "required_staff": 1}, "needs a name"),
    ({"name": "Opener", "job_name": "Barista", "days_of_week": [],
      "start_time": "08:00", "end_time": "16:00", "required_staff": 1}, "weekdays"),
    ({"name": "Opener", "job_name": "Barista", "days_of_week": [9],
      "start_time": "08:00", "end_time": "16:00", "required_staff": 1}, "weekdays"),
    ({"name": "Opener", "job_name": "Barista", "days_of_week": [1],
      "start_time": "8am", "end_time": "4pm", "required_staff": 1}, "HH:MM"),
    ({"name": "Opener", "job_name": "Barista", "days_of_week": [1],
      "start_time": "08:00", "end_time": "16:00", "required_staff": 0}, "1–99"),
])
async def test_resolve_profile_args_rejects_malformed_blocks(monkeypatch, block, fragment):
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": JOB_ID, "name": "Barista"}))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"blocks": [block]},
    )
    assert result["status"] == "clarify"
    assert fragment in result["message"]


@pytest.mark.asyncio
async def test_resolve_profile_args_refuses_an_entirely_empty_call(monkeypatch):
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={},
    )
    assert result["status"] == "clarify"


# --- resolve_profile_args merges onto what is already saved --------------------

def _patch_saved(monkeypatch, bundle):
    monkeypatch.setattr(location_profile, "load_profile_bundle", AsyncMock(return_value=bundle))


@pytest.mark.asyncio
async def test_resolve_profile_args_keeps_hours_saved_on_an_earlier_turn(monkeypatch):
    """The interview asks one question per turn, so the blocks turn carries no
    hours. Staging only what this turn said would blank the stored answer."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": JOB_ID, "name": "Barista"}))
    _patch_saved(monkeypatch, _bundle(hours={"1": {"open": "08:00", "close": "17:00"}, "0": None}))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"blocks": [{"name": "Opener", "job_name": "Barista", "days_of_week": [1],
                          "start_time": "08:00", "end_time": "16:00", "required_staff": 2}]},
    )

    assert result["status"] == "ok"
    assert result["operating_hours"] == {"1": {"open": "08:00", "close": "17:00"}, "0": None}


@pytest.mark.asyncio
async def test_resolve_profile_args_lets_a_new_answer_override_one_saved_day(monkeypatch):
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle(hours={
        "1": {"open": "08:00", "close": "17:00"},
        "2": {"open": "08:00", "close": "17:00"},
    }))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"operating_hours": {"2": {"open": "10:00", "close": "22:00"}}},
    )

    assert result["operating_hours"] == {
        "1": {"open": "08:00", "close": "17:00"},
        "2": {"open": "10:00", "close": "22:00"},
    }


@pytest.mark.asyncio
async def test_resolve_profile_args_still_refuses_a_turn_that_says_nothing_new(monkeypatch):
    """Merged hours are non-empty for any location that answered once — the
    "nothing to save" gate has to read the SUPPLIED answer, not the merge."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle(hours={"1": {"open": "08:00", "close": "17:00"}}))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={},
    )
    assert result["status"] == "clarify"


@pytest.mark.asyncio
async def test_leader_rule_extends_the_saved_pattern_on_a_leader_only_turn(monkeypatch):
    """"A lead is always on", answered after the pattern was saved, still has
    to become demand — the saved blocks are re-staged with coverage added."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    lead_id = UUID("99999999-9999-9999-9999-999999999999")
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": lead_id, "name": "Shift Lead"}))
    _patch_saved(monkeypatch, _bundle(
        hours={"1": {"open": "08:00", "close": "17:00"}},
        blocks=[{"name": "Opener", "role": "Barista", "job_id": str(JOB_ID), "job_name": "Barista",
                 "days_of_week": [1], "start_time": "08:00", "end_time": "16:00",
                 "required_staff": 2, "break_minutes": 30}],
    ))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"leader_job_name": "Shift Lead"},
    )

    assert result["status"] == "ok"
    names = [block["name"] for block in result["blocks"]]
    assert names == ["Opener", "Shift Lead coverage"]
    assert result["blocks"][0]["job_id"] == str(JOB_ID)   # existing block survives
    assert result["leader_job_id"] == str(lead_id)


@pytest.mark.asyncio
async def test_leader_only_turn_leaves_a_jobless_saved_pattern_alone(monkeypatch):
    """Re-staging a pre-job-link pattern would fail the every-block-needs-a-job
    gate, so the pattern is left untouched instead."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": JOB_ID, "name": "Shift Lead"}))
    _patch_saved(monkeypatch, _bundle(
        hours={"1": {"open": "08:00", "close": "17:00"}},
        blocks=[{"name": "Opener", "job_id": None, "job_name": None, "days_of_week": [1],
                 "start_time": "08:00", "end_time": "16:00", "required_staff": 1}],
    ))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"leader_job_name": "Shift Lead"},
    )

    assert result["status"] == "ok"
    assert result["blocks"] == []


def test_leader_rule_reads_a_saved_blocks_string_job_id():
    """Saved blocks carry the id as a string, freshly resolved ones as a UUID."""
    assert schedule_profile_skill._leader_blocks(
        {"1": {"open": "08:00", "close": "17:00"}},
        {"id": JOB_ID, "name": "Shift Lead"},
        [{"name": "Lead cover", "job_id": str(JOB_ID)}],
    ) == []


# --- execute ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_never_blanks_hours_a_turn_did_not_carry(monkeypatch):
    """`{}` means "this turn said nothing about hours". Writing it would erase
    the answer an earlier turn already saved."""
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_null_context())
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=_null_context(conn)))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)
    monkeypatch.setattr(schedule_profile_skill, "log_audit", AsyncMock())

    result = await schedule_profile_skill.execute(
        company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        action={"type": "schedule_location_profile", "confirm_id": "ab12cd34",
                "location_id": str(LOCATION_ID), "operating_hours": {},
                "blocks": [], "notes": "Busy on match days"},
    )

    assert result["status"] == "created"
    assert "operating_hours" not in upsert.await_args.kwargs
    assert upsert.await_args.kwargs["notes"] == "Busy on match days"


@pytest.mark.asyncio
async def test_resolve_profile_args_treats_blank_notes_as_unsaid(monkeypatch):
    """The model fills `notes` with "" whether or not notes were discussed —
    writing that would erase what the manager actually wrote."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle(notes="Front desk covers phones from 8."))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"operating_hours": {"1": {"open": "08:00", "close": "17:00"}}, "notes": "   "},
    )
    assert result["status"] == "ok"
    assert result["notes"] is None


@pytest.mark.asyncio
async def test_resolve_profile_args_stages_json_serializable_values(monkeypatch):
    """The staged dict is persisted as thread JSONB. A raw UUID in it fails
    json.dumps for the WHOLE state update, so the confirm card silently never
    appears — caught live, not by a fake that already used strings."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": JOB_ID, "name": "Opener"}))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={
            "operating_hours": {"1": {"open": "08:00", "close": "17:00"}},
            "blocks": [{"name": "Opener", "job_name": "Opener", "days_of_week": [1],
                        "start_time": "08:00", "end_time": "13:00", "required_staff": 2}],
            "leader_job_name": "Opener",
        },
    )

    json.dumps(result)   # would raise TypeError on a UUID
    assert result["blocks"][0]["job_id"] == str(JOB_ID)
    assert all(isinstance(block["job_id"], str) for block in result["blocks"])


def _null_context(value=None):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=value)
    context.__aexit__ = AsyncMock(return_value=False)
    return context


# --- open/close buffers -------------------------------------------------------
#
# Operational policy, not law: how long the store's own open and close take.
# The coverage evaluator widens each open day's required window by these.

@pytest.mark.parametrize("value,expected", [
    (None, 0), ("", 0), (0, 0), (30, 30), ("30", 30), (" 45 ", 45), (240, 240),
])
def test_validate_buffer_minutes_accepts_real_answers(value, expected):
    assert location_profile.validate_buffer_minutes(value, label="Prep") == expected


@pytest.mark.parametrize("value", [-1, 241, "abc", "30m", 3.5])
def test_validate_buffer_minutes_rejects_the_rest(value):
    with pytest.raises(ValueError):
        location_profile.validate_buffer_minutes(value, label="Prep")


def test_profile_context_lines_state_the_buffers_either_way():
    bundle = _bundle(hours={"1": {"open": "08:00", "close": "17:00"}})
    bundle["profile"]["open_buffer_minutes"] = 30
    bundle["profile"]["close_buffer_minutes"] = 20
    assert "Prep/close buffer: 30m before open, 20m after close" in profile_context_lines(bundle)

    assert "Prep/close buffer: none set" in profile_context_lines(_bundle())


@pytest.mark.asyncio
async def test_resolve_profile_args_stages_a_zero_buffer_as_a_real_answer(monkeypatch):
    """0 is "nobody comes in early", which is different from "this turn said
    nothing" — collapsing the two would silently keep an old buffer."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"open_buffer_minutes": 30, "close_buffer_minutes": 0},
    )

    assert result["status"] == "ok"
    assert result["open_buffer_minutes"] == 30
    assert result["close_buffer_minutes"] == 0
    assert "prep 30m" in result["summary"] and "close 0m" in result["summary"]


@pytest.mark.asyncio
async def test_resolve_profile_args_clarifies_an_out_of_range_buffer(monkeypatch):
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID,
        args={"open_buffer_minutes": 600},
    )

    assert result["status"] == "clarify"
    assert "0 and 240" in result["message"]


@pytest.mark.asyncio
async def test_execute_writes_a_buffer_only_when_the_turn_carried_one(monkeypatch):
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_null_context())
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=_null_context(conn)))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)
    monkeypatch.setattr(schedule_profile_skill, "log_audit", AsyncMock())

    await schedule_profile_skill.execute(
        company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        action={"type": "schedule_location_profile", "confirm_id": "ab12cd34",
                "location_id": str(LOCATION_ID), "operating_hours": {}, "blocks": [],
                "open_buffer_minutes": 0, "close_buffer_minutes": None},
    )

    kwargs = upsert.await_args.kwargs
    assert kwargs["open_buffer_minutes"] == 0
    assert "close_buffer_minutes" not in kwargs


# --- the leader answer ("no lead needed" is an answer) ------------------------

@pytest.mark.asyncio
async def test_resolve_profile_args_accepts_a_leader_only_no(monkeypatch):
    """`leader_required=false` is the answer that finishes the setup, so a turn
    carrying only it is a save — not the "tell me something" clarify."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle(hours=FULL_WEEK_HOURS))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"leader_required": False},
    )

    assert result["status"] == "ok"
    assert result["leader_required"] is False
    assert result["leader_job_id"] is None
    assert "no lead required on every shift" in result["summary"]


@pytest.mark.asyncio
async def test_resolve_profile_args_naming_a_leader_answers_the_question(monkeypatch):
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    monkeypatch.setattr(schedule_profile_skill, "resolve_job_by_name",
                        AsyncMock(return_value={"id": JOB_ID, "name": "Shift Lead"}))
    _patch_saved(monkeypatch, _bundle(hours=FULL_WEEK_HOURS))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"leader_job_name": "Shift Lead"},
    )

    assert result["leader_required"] is True
    assert result["leader_job_id"] == str(JOB_ID)


@pytest.mark.asyncio
async def test_resolve_profile_args_asks_which_job_leads_on_a_bare_yes(monkeypatch):
    """"Yes, a lead is required" with no job named and none saved cannot be
    written — the DB CHECK refuses it — so ask instead of staging it."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle(hours=FULL_WEEK_HOURS))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"leader_required": True},
    )

    assert result["status"] == "clarify"
    assert result["job_options"] == ["Barista", "Shift Lead"]


@pytest.mark.asyncio
async def test_execute_writes_leader_required_false_as_an_answer(monkeypatch):
    """Truthiness would drop the "no", leaving the question unanswered forever
    while the confirm card said it was saved — the buffers' bug."""
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_null_context())
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=_null_context(conn)))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)
    monkeypatch.setattr(schedule_profile_skill, "log_audit", AsyncMock())

    await schedule_profile_skill.execute(
        company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        action={"type": "schedule_location_profile", "confirm_id": "ab12cd34",
                "location_id": str(LOCATION_ID), "operating_hours": {}, "blocks": [],
                "leader_required": False},
    )

    assert upsert.await_args.kwargs["leader_required"] is False


@pytest.mark.asyncio
async def test_execute_leaves_the_leader_answer_alone_when_a_turn_omits_it(monkeypatch):
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_null_context())
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=_null_context(conn)))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)
    monkeypatch.setattr(schedule_profile_skill, "log_audit", AsyncMock())

    await schedule_profile_skill.execute(
        company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        action={"type": "schedule_location_profile", "confirm_id": "ab12cd34",
                "location_id": str(LOCATION_ID), "operating_hours": {}, "blocks": [],
                "leader_required": None, "notes": "Busy on match days"},
    )

    assert "leader_required" not in upsert.await_args.kwargs


# --- retracting the leader rule ----------------------------------------------
#
# "Yes, a lead is always on" materializes real demand: `_leader_blocks` writes a
# `<Job> coverage` block into the location's default week template. A later "no"
# has to take BOTH halves back — the named job on the profile row and the demand
# it created — or the coverage evaluator, the prompt and the template keep
# arguing with the answer the manager just gave.

_LEAD_ID = UUID("99999999-9999-9999-9999-999999999999")


def _bundle_with_saved_lead(*extra_blocks):
    bundle = _bundle(
        hours=FULL_WEEK_HOURS, leader="Shift Lead",
        blocks=[
            {"name": "Opener", "role": "Barista", "job_id": str(JOB_ID), "job_name": "Barista",
             "days_of_week": [1], "start_time": "08:00", "end_time": "16:00",
             "required_staff": 2, "break_minutes": 30},
            *extra_blocks,
        ],
    )
    bundle["profile"]["leader_job_id"] = _LEAD_ID
    return bundle


@pytest.mark.asyncio
async def test_a_leader_no_strips_the_coverage_a_yes_materialized(monkeypatch):
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle_with_saved_lead(
        {"name": "Shift Lead coverage", "role": "Shift Lead", "job_id": str(_LEAD_ID),
         "job_name": "Shift Lead", "days_of_week": [1, 2, 3, 4, 5],
         "start_time": "08:00", "end_time": "17:00", "required_staff": 1,
         "break_minutes": 0},
    ))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"leader_required": False},
    )

    assert result["status"] == "ok"
    assert result["leader_required"] is False
    assert [block["name"] for block in result["blocks"]] == ["Opener"]


@pytest.mark.asyncio
async def test_a_leader_no_keeps_a_manager_written_block_on_the_lead_job(monkeypatch):
    """Only the generated `<Job> coverage` block goes. A real shift the manager
    wrote that happens to use the lead job is theirs, not ours to delete."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    _patch_saved(monkeypatch, _bundle_with_saved_lead(
        {"name": "Friday close", "role": "Shift Lead", "job_id": str(_LEAD_ID),
         "job_name": "Shift Lead", "days_of_week": [5], "start_time": "14:00",
         "end_time": "22:00", "required_staff": 1, "break_minutes": 0},
    ))

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"leader_required": False},
    )

    assert result["status"] == "ok"
    # Nothing generated to strip, so the pattern is left entirely alone rather
    # than re-staged.
    assert result["blocks"] == []


@pytest.mark.asyncio
async def test_execute_clears_the_named_job_when_the_answer_is_no(monkeypatch):
    """Without this the profile still names a lead: `_coverage_profile` keeps
    emitting leader gaps and `profile_context_lines` keeps telling the manager
    a lead is required, both contradicting the confirm card they just OK'd."""
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_null_context())
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=_null_context(conn)))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)
    monkeypatch.setattr(schedule_profile_skill, "log_audit", AsyncMock())

    await schedule_profile_skill.execute(
        company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        action={"type": "schedule_location_profile", "confirm_id": "ab12cd34",
                "location_id": str(LOCATION_ID), "operating_hours": {}, "blocks": [],
                "leader_required": False, "leader_job_id": None},
    )

    kwargs = upsert.await_args.kwargs
    assert kwargs["leader_required"] is False
    assert kwargs["leader_job_id"] is None


@pytest.mark.asyncio
async def test_execute_leaves_the_named_job_alone_when_the_turn_omits_the_answer(monkeypatch):
    conn = MagicMock()
    conn.transaction = MagicMock(return_value=_null_context())
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=_null_context(conn)))
    upsert = AsyncMock(return_value={"id": TEMPLATE_ID})
    monkeypatch.setattr(location_profile, "upsert_location_profile", upsert)
    monkeypatch.setattr(schedule_profile_skill, "log_audit", AsyncMock())

    await schedule_profile_skill.execute(
        company_id=COMPANY_ID, actor_user_id=ACTOR_ID,
        action={"type": "schedule_location_profile", "confirm_id": "ab12cd34",
                "location_id": str(LOCATION_ID), "operating_hours": {}, "blocks": [],
                "notes": "Busy on match days"},
    )

    assert "leader_job_id" not in upsert.await_args.kwargs


# --- upsert_location_profile: the leader auto-answer is symmetric -------------

class _CapturingConn:
    """Enough of an asyncpg connection for `upsert_location_profile`: the
    ownership check passes and the INSERT is captured instead of run."""

    def __init__(self):
        self.sql = ""
        self.values: tuple = ()

    async def fetchval(self, *args, **kwargs):
        return 1

    async def fetchrow(self, sql, *values):
        self.sql = sql
        self.values = values
        return {"id": TEMPLATE_ID, "operating_hours": "{}"}


def _written(conn: _CapturingConn) -> dict:
    header = conn.sql.split("INSERT INTO schedule_location_profiles (", 1)[1].split(")", 1)[0]
    return dict(zip([column.strip() for column in header.split(",")], conn.values))


@pytest.mark.asyncio
async def test_naming_the_job_alone_answers_the_leader_question():
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_id=JOB_ID,
    )
    written = _written(conn)
    assert written["leader_job_id"] == JOB_ID
    assert written["leader_required"] is True


@pytest.mark.asyncio
async def test_clearing_the_job_alone_un_answers_it_rather_than_violating_the_check():
    """`leader_required=true` with no job named is the one state the DB CHECK
    refuses. A caller that clears only the job would otherwise get a 422 on a
    PUT that looked perfectly reasonable."""
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_id=None,
    )
    written = _written(conn)
    assert written["leader_job_id"] is None
    assert written["leader_required"] is None


@pytest.mark.asyncio
async def test_an_explicit_leader_required_still_wins_over_the_auto_answer():
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_id=None, leader_required=False,
    )
    written = _written(conn)
    assert written["leader_job_id"] is None
    assert written["leader_required"] is False


# --- the leader rule is a SET -------------------------------------------------

SECOND_JOB_ID = UUID("99999999-9999-9999-9999-999999999999")


@pytest.mark.asyncio
async def test_several_leader_jobs_are_written_as_the_set_plus_a_mirror():
    """`leader_job_ids` is the rule; `leader_job_id` is its first entry, kept
    so the FK and any reader that predates the set still see a value."""
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_ids=[JOB_ID, SECOND_JOB_ID, JOB_ID],
    )
    written = _written(conn)
    assert written["leader_job_ids"] == [JOB_ID, SECOND_JOB_ID]   # deduped, order kept
    assert written["leader_job_id"] == JOB_ID
    assert written["leader_required"] is True
    assert "::uuid[]" in conn.sql


@pytest.mark.asyncio
async def test_the_legacy_scalar_is_the_one_element_spelling_of_the_set():
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_id=str(JOB_ID),
    )
    written = _written(conn)
    assert written["leader_job_ids"] == [JOB_ID]
    assert written["leader_job_id"] == JOB_ID


@pytest.mark.asyncio
async def test_the_set_wins_when_both_spellings_are_sent():
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_id=SECOND_JOB_ID, leader_job_ids=[JOB_ID],
    )
    written = _written(conn)
    assert written["leader_job_ids"] == [JOB_ID]
    assert written["leader_job_id"] == JOB_ID


@pytest.mark.asyncio
async def test_an_empty_set_clears_the_mirror_and_un_answers_the_question():
    conn = _CapturingConn()
    await location_profile.upsert_location_profile(
        conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
        leader_job_ids=[],
    )
    written = _written(conn)
    assert written["leader_job_ids"] == []
    assert written["leader_job_id"] is None
    assert written["leader_required"] is None


@pytest.mark.asyncio
async def test_an_oversized_leader_set_is_refused():
    conn = _CapturingConn()
    too_many = [UUID(int=index + 1) for index in range(location_profile.MAX_LEADER_JOBS + 1)]
    with pytest.raises(ValueError):
        await location_profile.upsert_location_profile(
            conn, company_id=COMPANY_ID, location_id=LOCATION_ID, actor_user_id=ACTOR_ID,
            leader_job_ids=too_many,
        )


def test_missing_fields_reads_the_set_not_just_the_mirror():
    """A row whose mirror was nulled by the FK (job deleted) but whose set still
    names another job has answered the question."""
    bundle = _bundle(hours=FULL_WEEK_HOURS, blocks=[{"name": "Opener"}], leader_required=True)
    bundle["profile"]["leader_job_id"] = None
    bundle["profile"]["leader_job_ids"] = [SECOND_JOB_ID]
    assert "leader_rule" not in missing_fields(bundle)

    bundle["profile"]["leader_job_ids"] = []
    assert "leader_rule" in missing_fields(bundle)


def test_profile_context_lines_name_every_leader_job():
    bundle = _bundle(hours=FULL_WEEK_HOURS, leader="Shift Lead")
    bundle["leader_jobs"] = [
        {"id": str(JOB_ID), "name": "Shift Lead"},
        {"id": str(SECOND_JOB_ID), "name": "Assistant Manager"},
    ]
    text = "\n".join(profile_context_lines(bundle))
    assert "Leader coverage: Shift Lead or Assistant Manager on every open shift" in text


def test_bundle_leader_jobs_reads_a_scalar_only_bundle_as_a_one_element_set():
    assert location_profile.bundle_leader_jobs(_bundle(leader="Shift Lead")) == [
        {"id": str(JOB_ID), "name": "Shift Lead"},
    ]
    assert location_profile.bundle_leader_jobs(_bundle()) == []


@pytest.mark.parametrize("names, expected", [
    ([], ""),
    (["Shift Lead"], "Shift Lead"),
    (["Shift Lead", "AM"], "Shift Lead or AM"),
    (["Shift Lead", "AM", "GM"], "Shift Lead, AM or GM"),
])
def test_join_or(names, expected):
    assert location_profile.join_or(names) == expected


@pytest.mark.asyncio
async def test_load_profile_bundle_resolves_every_leader_in_profile_order_and_drops_the_dead():
    """The FK nulls the mirror when a job is deleted; nothing can do that inside
    the array, so an id that no longer resolves is dropped on read."""
    dead = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

    class _Conn:
        async def fetchrow(self, sql, *args):
            return {
                "id": TEMPLATE_ID, "operating_hours": "{}", "default_week_template_id": None,
                "leader_job_id": SECOND_JOB_ID, "leader_job_ids": [SECOND_JOB_ID, dead, JOB_ID],
                "leader_required": True,
            }

        async def fetch(self, sql, *args):
            assert "ANY($2::uuid[])" in sql
            return [{"id": JOB_ID, "name": "Shift Lead"}, {"id": SECOND_JOB_ID, "name": "AM"}]

    bundle = await location_profile.load_profile_bundle(
        _Conn(), company_id=COMPANY_ID, location_id=LOCATION_ID,
    )
    assert bundle["leader_jobs"] == [
        {"id": str(SECOND_JOB_ID), "name": "AM"}, {"id": str(JOB_ID), "name": "Shift Lead"},
    ]
    assert bundle["leader_job_name"] == "AM"


@pytest.mark.asyncio
async def test_retracting_the_rule_strips_coverage_for_every_saved_leader_job(monkeypatch):
    """Two leader jobs, each with generated `<Job> coverage` blocks: a "no lead
    needed" has to take back both, and leave the manager's own blocks alone."""
    _, context, _ = _resolver_conn(None)
    monkeypatch.setattr(schedule_profile_skill, "get_connection", MagicMock(return_value=context))
    bundle = _bundle(
        hours={"1": {"open": "08:00", "close": "17:00"}},
        blocks=[
            {"name": "Opener", "role": "Barista", "job_id": "b0000000-0000-4000-8000-000000000001",
             "job_name": "Barista", "days_of_week": [1], "start_time": "08:00", "end_time": "16:00",
             "required_staff": 2, "break_minutes": 30},
            {"name": "Shift Lead coverage", "role": "Shift Lead", "job_id": str(JOB_ID),
             "job_name": "Shift Lead", "days_of_week": [1], "start_time": "08:00",
             "end_time": "17:00", "required_staff": 1, "break_minutes": 0},
            {"name": "AM coverage", "role": "AM", "job_id": str(SECOND_JOB_ID),
             "job_name": "AM", "days_of_week": [1], "start_time": "08:00",
             "end_time": "17:00", "required_staff": 1, "break_minutes": 0},
        ],
        leader="Shift Lead",
    )
    bundle["profile"]["leader_job_ids"] = [JOB_ID, SECOND_JOB_ID]
    bundle["leader_jobs"] = [
        {"id": str(JOB_ID), "name": "Shift Lead"}, {"id": str(SECOND_JOB_ID), "name": "AM"},
    ]
    _patch_saved(monkeypatch, bundle)

    result = await schedule_profile_skill.resolve_profile_args(
        company_id=COMPANY_ID, location_id=LOCATION_ID, args={"leader_required": False},
    )

    assert result["status"] == "ok"
    assert [block["name"] for block in result["blocks"]] == ["Opener"]
