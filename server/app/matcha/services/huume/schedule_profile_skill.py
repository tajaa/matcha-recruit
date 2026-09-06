"""Huume's location scheduling-profile intake, on the schedule-editor surface.

The whole-week builder refuses an empty week because it has no demand to plan
against, and telling the manager to "add draft shifts or a week template first"
is the loop this skill exists to break: Huume asks the two or three questions it
needs, stages one confirmable action, and the answers become the location's
default week template — which the builder then picks up on its own.

Job NAMES come from the model, ids are resolved server-side against
`schedule_jobs` — the model never invents an id, and a name that matches
nothing becomes a clarify with the real options rather than a silent free-text
block that would generate ungated shifts.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from app.database import get_connection
from app.matcha.services.scheduling import location_profile
from app.matcha.services.scheduling.shift_writes import log_audit, resolve_job_by_name
from app.matcha.services.scheduling.week_template_writes import JobUnavailable, WeekTemplateNotFound

logger = logging.getLogger(__name__)

_MAX_BLOCKS = 40
_MAX_JOB_OPTIONS = 6


def _clock(value) -> str:
    """HH:MM from whatever the model sent, or ValueError."""
    return location_profile.parse_clock(value).strftime("%H:%M")


def _summarize(operating_hours: dict, blocks: list[dict], leader_job_name: Optional[str]) -> str:
    parts = []
    open_days = location_profile.open_weekdays(operating_hours)
    if operating_hours:
        parts.append(f"hours on {len(open_days)} day{'s' if len(open_days) != 1 else ''}")
    if blocks:
        positions = sum(int(b.get("required_staff") or 1) for b in blocks)
        parts.append(f"{len(blocks)} shift block{'s' if len(blocks) != 1 else ''} ({positions} positions/day-slot)")
    if leader_job_name:
        parts.append(f"leader: {leader_job_name}")
    return ", ".join(parts) or "no changes"


def _leader_blocks(operating_hours: dict, leader_job: dict, blocks: list[dict]) -> list[dict]:
    """One leader block per distinct open-hours window not already covered.

    "A shift lead is always on" is a coverage rule, but the planner only knows
    about demand, so the rule has to become real staffing demand or it is
    silently ignored.
    """
    leader_id = str(leader_job["id"])
    # Saved blocks carry their job id as a string, freshly resolved ones as a
    # UUID — comparing the raw values would re-add coverage that already exists.
    if any(str(b.get("job_id")) == leader_id for b in blocks):
        return []
    windows: dict[tuple[str, str], list[int]] = {}
    for day in location_profile.open_weekdays(operating_hours):
        window = operating_hours[str(day)]
        windows.setdefault((window["open"], window["close"]), []).append(day)
    return [
        {
            "name": f"{leader_job['name']} coverage",
            "role": leader_job["name"],
            # str, not UUID: this dict is persisted into the thread's JSONB
            # state, and json.dumps has no UUID branch — a raw UUID here means
            # the whole staged action is silently dropped.
            "job_id": leader_id,
            "job_name": leader_job["name"],
            "days_of_week": days,
            "start_time": opens,
            "end_time": closes,
            "required_staff": 1,
            "break_minutes": 0,
        }
        for (opens, closes), days in sorted(windows.items())
    ]


def _saved_pattern_blocks(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """The location's saved pattern in the same shape `resolve_profile_args`
    emits, so a turn that only answers the leader question can still add leader
    coverage on top of it.

    Empty when any saved block predates job links: rewriting the pattern would
    stage blocks the every-block-needs-a-job gate refuses.
    """
    blocks = ((bundle.get("template") or {}).get("blocks") or [])
    if not blocks or any(not block.get("job_id") for block in blocks):
        return []
    return [
        {
            "name": block["name"],
            "role": block.get("role") or block.get("job_name"),
            "job_id": block["job_id"],
            "job_name": block.get("job_name"),
            "days_of_week": sorted(block.get("days_of_week") or []),
            "start_time": block["start_time"],
            "end_time": block["end_time"],
            "required_staff": block.get("required_staff") or 1,
            "break_minutes": block.get("break_minutes") or 0,
        }
        for block in blocks
    ]


async def _job_options(conn, *, company_id: UUID, location_id: UUID) -> list[str]:
    rows = await conn.fetch(
        """
        SELECT name FROM schedule_jobs
        WHERE company_id = $1 AND (location_id IS NULL OR location_id = $2)
        ORDER BY location_id NULLS LAST, name
        LIMIT $3
        """,
        company_id, location_id, _MAX_JOB_OPTIONS,
    )
    return [r["name"] for r in rows]


async def resolve_profile_args(
    *, company_id: UUID, location_id: UUID, args: dict[str, Any],
) -> dict[str, Any]:
    """Validate + resolve one `save_location_schedule_profile` call.

    Returns `{"status": "ok", ...staged fields}` or `{"status": "clarify",
    "message": ..., "job_options": [...]}`. Nothing is written here.
    """
    try:
        supplied_hours = location_profile.validate_operating_hours(args.get("operating_hours"))
    except ValueError as exc:
        return {"status": "clarify", "message": str(exc)}

    raw_blocks = args.get("blocks") or []
    if len(raw_blocks) > _MAX_BLOCKS:
        return {"status": "clarify", "message": f"That is more than {_MAX_BLOCKS} shift blocks — split the week up."}

    async with get_connection() as conn:
        # The interview runs one question per turn, so a later call carries
        # only that turn's answer. Everything staged here is the profile as it
        # will look AFTER the save — merged with what is already stored, never
        # a partial that overwrites an earlier answer with nothing.
        saved = await location_profile.load_profile_bundle(
            conn, company_id=company_id, location_id=location_id,
        )
        saved_hours = (saved.get("profile") or {}).get("operating_hours") or {}
        operating_hours = {**saved_hours, **supplied_hours}

        blocks: list[dict[str, Any]] = []
        for raw in raw_blocks:
            name = str(raw.get("name") or "").strip()
            if not name:
                return {"status": "clarify", "message": "Every shift block needs a name."}
            try:
                start_time = _clock(raw.get("start_time"))
                end_time = _clock(raw.get("end_time"))
            except (TypeError, ValueError):
                return {"status": "clarify", "message": f"Block '{name}' needs start and end times as HH:MM."}
            days = sorted({int(d) for d in (raw.get("days_of_week") or [])})
            if not days or any(d < 0 or d > 6 for d in days):
                return {
                    "status": "clarify",
                    "message": f"Block '{name}' needs the weekdays it runs on (0=Sunday … 6=Saturday).",
                }
            # Not `or 1`: that reads an explicit 0 as "unset" and silently
            # staffs the block with one person the manager never asked for.
            raw_staff = raw.get("required_staff")
            try:
                required_staff = 1 if raw_staff is None else int(raw_staff)
            except (TypeError, ValueError):
                return {"status": "clarify", "message": f"Block '{name}' needs 1–99 people."}
            if not 1 <= required_staff <= 99:
                return {"status": "clarify", "message": f"Block '{name}' needs 1–99 people."}

            job_name = str(raw.get("job_name") or "").strip()
            job = await resolve_job_by_name(conn, company_id, job_name, location_id=location_id)
            if job is None:
                options = await _job_options(conn, company_id=company_id, location_id=location_id)
                known = ", ".join(options) if options else "none set up yet"
                return {
                    "status": "clarify",
                    "message": (
                        f"There's no job named '{job_name}' at this location. Jobs here: {known}."
                        if job_name else
                        f"Block '{name}' needs a job. Jobs here: {known}."
                    ),
                    "job_options": options,
                }
            blocks.append({
                "name": name,
                # The job's own name is the canonical role label — same rule
                # create_shift_core enforces on every generated shift.
                "role": job["name"],
                # str for the same reason as _leader_blocks: staged actions
                # round-trip through JSONB.
                "job_id": str(job["id"]),
                "job_name": job["name"],
                "days_of_week": days,
                "start_time": start_time,
                "end_time": end_time,
                "required_staff": required_staff,
                "break_minutes": int(raw.get("break_minutes") or 0),
            })

        leader_job = None
        leader_name = str(args.get("leader_job_name") or "").strip()
        if leader_name:
            leader_row = await resolve_job_by_name(conn, company_id, leader_name, location_id=location_id)
            if leader_row is None:
                options = await _job_options(conn, company_id=company_id, location_id=location_id)
                known = ", ".join(options) if options else "none set up yet"
                return {
                    "status": "clarify",
                    "message": f"There's no job named '{leader_name}' at this location. Jobs here: {known}.",
                    "job_options": options,
                }
            leader_job = {"id": leader_row["id"], "name": leader_row["name"]}

    if leader_job:
        # A leader-only turn still has to produce demand, so the saved pattern
        # is re-staged with the coverage added rather than left untouched.
        pattern = blocks or _saved_pattern_blocks(saved)
        leader_coverage = _leader_blocks(operating_hours, leader_job, pattern) if pattern else []
        if leader_coverage:
            blocks = [*pattern, *leader_coverage]

    # Blank notes are "this turn had nothing to say", not "erase the note the
    # manager wrote" — the model fills the field with "" whether or not it was
    # ever discussed. Same reasoning as the empty operating_hours dict.
    raw_notes = args.get("notes")
    notes = raw_notes.strip() or None if isinstance(raw_notes, str) else raw_notes
    # Deliberately the SUPPLIED hours: merged hours are non-empty for any
    # location that answered once, and a turn that said nothing new is not a
    # save.
    if not supplied_hours and not blocks and not leader_job and not notes:
        return {
            "status": "clarify",
            "message": "Tell me the store's hours, its usual shift blocks, or who has to be on the floor.",
        }

    return {
        "status": "ok",
        "operating_hours": operating_hours,
        "blocks": blocks,
        "leader_job_id": str(leader_job["id"]) if leader_job else None,
        "leader_job_name": leader_job["name"] if leader_job else None,
        "notes": notes,
        "template_name": args.get("template_name"),
        "summary": _summarize(operating_hours, blocks, leader_job["name"] if leader_job else None),
    }


async def execute(*, company_id: UUID, actor_user_id: UUID, action: dict[str, Any]) -> dict[str, Any]:
    """Apply a confirmed profile: upsert the row, then rewrite its default
    week template's blocks. One transaction — a saved profile pointing at a
    half-written pattern is worse than neither."""
    try:
        location_id = UUID(str(action.get("location_id")))
    except (TypeError, ValueError):
        return {"status": "failed", "message": "That schedule location is not available."}

    blocks = action.get("blocks") or []
    leader_job_id = action.get("leader_job_id")
    fields: dict[str, Any] = {}
    # Truthiness, not `is not None`: `{}` means this turn carried no hours,
    # and writing it would blank out whatever an earlier turn saved.
    if action.get("operating_hours"):
        fields["operating_hours"] = action["operating_hours"]
    if leader_job_id:
        fields["leader_job_id"] = UUID(str(leader_job_id))
    if action.get("notes") is not None:
        fields["notes"] = action["notes"]

    try:
        async with get_connection() as conn:
            async with conn.transaction():
                profile = await location_profile.upsert_location_profile(
                    conn, company_id=company_id, location_id=location_id,
                    actor_user_id=actor_user_id, **fields,
                )
                template_id = None
                if blocks:
                    template_id = await location_profile.replace_default_pattern(
                        conn, company_id=company_id, location_id=location_id,
                        actor_user_id=actor_user_id, blocks=blocks,
                        template_name=action.get("template_name"),
                    )
                await log_audit(
                    conn, company_id, "schedule_location_profile", profile["id"], actor_user_id,
                    "schedule_location_profile.save",
                    {
                        "location_id": str(location_id),
                        "blocks": len(blocks),
                        "week_template_id": str(template_id) if template_id else None,
                        "fields": sorted(fields),
                    },
                )
    except (JobUnavailable, WeekTemplateNotFound, ValueError) as exc:
        return {"status": "failed", "message": str(exc)}
    except Exception:
        logger.exception("huume: saving location schedule profile failed")
        return {"status": "failed", "message": "I couldn't save the scheduling profile."}

    return {
        "status": "created",
        "message": "Saved this location's scheduling profile.",
        "record_id": str(profile["id"]),
        "week_template_id": str(template_id) if template_id else None,
    }


async def load_bundle(*, company_id: UUID, location_id: UUID) -> dict[str, Any]:
    async with get_connection() as conn:
        bundle = await location_profile.load_profile_bundle(
            conn, company_id=company_id, location_id=location_id,
        )
    return bundle


async def context_block(*, company_id: UUID, location_id: Optional[UUID]) -> str:
    """The profile summary injected into every schedule-surface system prompt.

    Never raises: a missing profile is the normal case on the first turn, and
    a read failure must not take down the whole turn.
    """
    if location_id is None:
        return ""
    try:
        bundle = await load_bundle(company_id=company_id, location_id=location_id)
    except Exception:
        logger.warning("huume: could not load location profile for prompt", exc_info=True)
        return ""
    return "\n".join(location_profile.profile_context_lines(bundle))
