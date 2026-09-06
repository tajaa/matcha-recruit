"""Per-location scheduling profile — the store's own setup, in one row.

The whole-week builder derives demand from draft shifts or a saved week
template and nothing else, so a store with an empty week and no template can
never be built. This profile is where Huume records the answers it interviews
the manager for: when the store is open, what the week normally looks like
(persisted as the location's default week template), and who has to be on the
floor. `week_start_weekday` rides along for the week-math work.

DB-facing helpers take an explicit `conn` and never open their own transaction;
the pure helpers below them are unit-tested without a database.
"""

import json
from datetime import time
from typing import Any, Optional
from uuid import UUID

from app.matcha.models.scheduling.employee_schedule import (
    WeekTemplateBlockReplace, WeekTemplateCreate,
)
from .week_template_writes import (
    create_week_template_core, replace_week_template_contents_core,
)


PROFILE_COLS = (
    "id, company_id, location_id, operating_hours, default_week_template_id, "
    "leader_job_id, notes, week_start_weekday, open_buffer_minutes, "
    "close_buffer_minutes, created_at, updated_at"
)

# Operational policy, NOT law: how long before open / after close somebody has
# to be on the schedule. Nothing statutory caps prep time, so the bound here is
# only a sanity rail on a typed number (matching the DB CHECK).
MAX_BUFFER_MINUTES = 240

# 0 = Sunday, the same index `days_of_week` masks and `sunday_indexed_weekday`
# use. Kept local so this module stays importable without the route layer.
WEEKDAY_NAMES = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")

# Distinguishes "caller did not mention this field" from "caller cleared it".
UNSET: Any = object()


def parse_clock(value) -> time:
    """HH:MM from a model- or user-supplied string.

    `time.fromisoformat` needs a zero-padded hour, and "8:00" is what a person
    (and the model quoting them) actually types.
    """
    if isinstance(value, time):
        return value
    text = str(value or "").strip()
    if len(text) >= 2 and text[1] == ":":
        text = f"0{text}"
    return time.fromisoformat(text)


def validate_buffer_minutes(value, *, label: str) -> int:
    """Minutes of prep before open / cleanup after close, 0–240.

    Operational policy, not a legal threshold — a store decides how long its
    open takes. Kept strict about the type because the chat surface hands over
    whatever the model typed, and a silent ``or 0`` would turn "sixty" into
    "no buffer at all" without anyone noticing.
    """
    if value in (None, ""):
        return 0
    try:
        minutes = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number of minutes.")
    if not 0 <= minutes <= MAX_BUFFER_MINUTES:
        raise ValueError(f"{label} must be between 0 and {MAX_BUFFER_MINUTES} minutes.")
    return minutes


def _loads(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value or {}


def validate_operating_hours(value) -> dict[str, Optional[dict]]:
    """Normalize `{"0": {"open": "08:00", "close": "17:00"} | None, ...}`.

    Keys are weekday indexes 0–6 as strings; a null value means the store is
    closed that day and an absent key means nobody has said yet. An overnight
    window (close <= open) is allowed — bars and 24h stores are real.
    """
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("operating_hours must be an object keyed by weekday 0-6")
    out: dict[str, Optional[dict]] = {}
    for raw_key, raw_window in value.items():
        try:
            day = int(raw_key)
        except (TypeError, ValueError):
            raise ValueError(f"operating_hours has a non-numeric weekday key: {raw_key!r}")
        if not 0 <= day <= 6:
            raise ValueError(f"operating_hours weekday must be 0-6, got {day}")
        if raw_window is None:
            out[str(day)] = None
            continue
        if not isinstance(raw_window, dict):
            raise ValueError(f"operating_hours[{day}] must be an object or null")
        try:
            opens = parse_clock(raw_window["open"])
            closes = parse_clock(raw_window["close"])
        except KeyError as exc:
            raise ValueError(f"operating_hours[{day}] needs both open and close") from exc
        except ValueError as exc:
            raise ValueError(f"operating_hours[{day}] has an unparseable time") from exc
        out[str(day)] = {"open": opens.strftime("%H:%M"), "close": closes.strftime("%H:%M")}
    return out


def open_weekdays(operating_hours: dict) -> list[int]:
    """Weekday indexes the store is explicitly open on."""
    return sorted(
        int(day) for day, window in (operating_hours or {}).items()
        if isinstance(window, dict)
    )


def missing_fields(bundle: dict) -> list[str]:
    """Which of the three intake answers Huume still has to ask for."""
    profile = bundle.get("profile") or {}
    template = bundle.get("template") or {}
    missing = []
    if not (profile.get("operating_hours") or {}):
        missing.append("operating_hours")
    if not (template.get("blocks") or []):
        missing.append("staffing_pattern")
    if not profile.get("leader_job_id"):
        missing.append("leader_rule")
    return missing


def _format_window(window: Optional[dict]) -> str:
    if window is None:
        return "closed"
    return f"{window['open']}–{window['close']}"


def _format_days(days: list[int]) -> str:
    if not days:
        return "no days"
    return ", ".join(WEEKDAY_NAMES[d][:3] for d in sorted(set(days)) if 0 <= d <= 6)


def profile_context_lines(bundle: dict) -> list[str]:
    """Human-readable profile summary for the system prompt. Pure."""
    profile = bundle.get("profile") or {}
    template = bundle.get("template") or {}
    hours = profile.get("operating_hours") or {}
    lines: list[str] = []

    if hours:
        rendered = [
            f"{WEEKDAY_NAMES[d][:3]} {_format_window(hours[str(d)])}"
            for d in range(7) if str(d) in hours
        ]
        lines.append(f"Hours: {'; '.join(rendered)}")
    else:
        lines.append("Hours: not set")

    blocks = template.get("blocks") or []
    if blocks:
        lines.append(f"Staffing pattern ({template.get('name')}):")
        for b in blocks:
            job = f" [{b['job_name']}]" if b.get("job_name") else ""
            lines.append(
                f"  - {b['name']}{job} {_format_days(b.get('days_of_week') or [])} "
                f"{b['start_time']}–{b['end_time']} x{b.get('required_staff', 1)}"
            )
    else:
        lines.append("Staffing pattern: not set")

    open_buffer = int(profile.get("open_buffer_minutes") or 0)
    close_buffer = int(profile.get("close_buffer_minutes") or 0)
    if open_buffer or close_buffer:
        lines.append(
            f"Prep/close buffer: {open_buffer}m before open, {close_buffer}m after close"
        )
    else:
        lines.append("Prep/close buffer: none set")

    leader = bundle.get("leader_job_name")
    lines.append(f"Leader coverage: {leader} on every open shift" if leader else "Leader coverage: not set")

    week_start = profile.get("week_start_weekday")
    if week_start is not None:
        lines.append(f"Week starts: {WEEKDAY_NAMES[int(week_start)]}")
    if profile.get("notes"):
        lines.append(f"Notes: {profile['notes']}")

    missing = missing_fields(bundle)
    if missing:
        lines.append(f"Missing: {', '.join(missing)}")
    return lines


def _row_to_profile(row) -> Optional[dict]:
    if row is None:
        return None
    profile = dict(row)
    profile["operating_hours"] = _loads(profile.get("operating_hours"))
    return profile


async def get_location_profile(conn, *, company_id: UUID, location_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {PROFILE_COLS} FROM schedule_location_profiles "
        "WHERE company_id = $1 AND location_id = $2",
        company_id, location_id,
    )
    return _row_to_profile(row)


async def resolve_week_start_weekday(conn, *, company_id: UUID, location_id: Optional[UUID]) -> int:
    """The location's week start day, defaulting to Sunday when unset."""
    if location_id is None:
        return 0
    value = await conn.fetchval(
        "SELECT week_start_weekday FROM schedule_location_profiles "
        "WHERE company_id = $1 AND location_id = $2",
        company_id, location_id,
    )
    return int(value) if value is not None else 0


async def load_profile_bundle(conn, *, company_id: UUID, location_id: UUID) -> dict:
    """Profile + its default week template's blocks + the leader job's name."""
    profile = await get_location_profile(conn, company_id=company_id, location_id=location_id)
    bundle: dict = {"profile": profile, "template": None, "leader_job_name": None}
    if not profile:
        return bundle

    if profile.get("default_week_template_id"):
        tpl = await conn.fetchrow(
            "SELECT id, name FROM schedule_week_templates WHERE id = $1 AND company_id = $2",
            profile["default_week_template_id"], company_id,
        )
        if tpl:
            rows = await conn.fetch(
                """
                SELECT b.id, b.name, b.role, b.job_id, b.days_of_week, b.start_time,
                       b.end_time, b.required_staff, b.break_minutes, j.name AS job_name
                FROM schedule_shift_templates b
                LEFT JOIN schedule_jobs j ON j.id = b.job_id
                WHERE b.week_template_id = $1
                ORDER BY b.start_time ASC
                """,
                tpl["id"],
            )
            bundle["template"] = {
                "id": str(tpl["id"]),
                "name": tpl["name"],
                "blocks": [
                    {
                        "id": str(r["id"]),
                        "name": r["name"],
                        "role": r["role"],
                        "job_id": str(r["job_id"]) if r["job_id"] else None,
                        "job_name": r["job_name"],
                        "days_of_week": _loads(r["days_of_week"]) or [],
                        "start_time": r["start_time"].strftime("%H:%M") if r["start_time"] else None,
                        "end_time": r["end_time"].strftime("%H:%M") if r["end_time"] else None,
                        "required_staff": r["required_staff"],
                        "break_minutes": r["break_minutes"],
                    }
                    for r in rows
                ],
            }

    if profile.get("leader_job_id"):
        bundle["leader_job_name"] = await conn.fetchval(
            "SELECT name FROM schedule_jobs WHERE id = $1 AND company_id = $2",
            profile["leader_job_id"], company_id,
        )
    return bundle


async def upsert_location_profile(
    conn, *, company_id: UUID, location_id: UUID, actor_user_id: Optional[UUID],
    operating_hours: Any = UNSET, default_week_template_id: Any = UNSET,
    leader_job_id: Any = UNSET, notes: Any = UNSET, week_start_weekday: Any = UNSET,
    open_buffer_minutes: Any = UNSET, close_buffer_minutes: Any = UNSET,
) -> dict:
    """Create or patch the location's profile. Only supplied fields are written."""
    owns = await conn.fetchval(
        "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not owns:
        raise ValueError("Location not found")

    supplied: dict[str, Any] = {}
    if operating_hours is not UNSET:
        supplied["operating_hours"] = json.dumps(validate_operating_hours(operating_hours))
    if default_week_template_id is not UNSET:
        supplied["default_week_template_id"] = default_week_template_id
    if leader_job_id is not UNSET:
        supplied["leader_job_id"] = leader_job_id
    if notes is not UNSET:
        supplied["notes"] = notes
    if week_start_weekday is not UNSET:
        day = int(week_start_weekday)
        if not 0 <= day <= 6:
            raise ValueError("week_start_weekday must be 0-6")
        supplied["week_start_weekday"] = day
    if open_buffer_minutes is not UNSET:
        supplied["open_buffer_minutes"] = validate_buffer_minutes(
            open_buffer_minutes, label="Opening prep buffer",
        )
    if close_buffer_minutes is not UNSET:
        supplied["close_buffer_minutes"] = validate_buffer_minutes(
            close_buffer_minutes, label="Closing buffer",
        )

    columns =["company_id", "location_id", "created_by", "updated_by", *supplied]
    values = [company_id, location_id, actor_user_id, actor_user_id, *supplied.values()]
    placeholders = ", ".join(
        f"${i}::jsonb" if col == "operating_hours" else f"${i}"
        for i, col in enumerate(columns, start=1)
    )
    updates = ", ".join(f"{col} = EXCLUDED.{col}" for col in supplied)
    update_sql = (
        f"UPDATE SET {updates}, updated_by = EXCLUDED.updated_by, updated_at = NOW()"
        if supplied else
        "UPDATE SET updated_by = EXCLUDED.updated_by, updated_at = NOW()"
    )
    row = await conn.fetchrow(
        f"""
        INSERT INTO schedule_location_profiles ({", ".join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (location_id) DO {update_sql}
        RETURNING {PROFILE_COLS}
        """,
        *values,
    )
    return _row_to_profile(row)


def _block_signature(name: Optional[str], start, end) -> tuple:
    def _clock(value) -> str:
        if isinstance(value, time):
            return value.strftime("%H:%M")
        return str(value or "")[:5]
    return ((name or "").strip().lower(), _clock(start), _clock(end))


async def replace_default_pattern(
    conn, *, company_id: UUID, location_id: UUID, actor_user_id: Optional[UUID],
    blocks: list[dict], template_name: Optional[str] = None,
) -> UUID:
    """Persist the location's staffing pattern as its default week template.

    The chat surface names blocks, it does not know their ids, so incoming
    blocks are mapped onto existing ones by `(name, start, end)` before the
    id-based reconcile core runs — matched blocks keep their ids, and the
    generated shifts that point at them keep their template link.

    Caller owns the transaction.
    """
    profile = await conn.fetchrow(
        "SELECT id, default_week_template_id FROM schedule_location_profiles "
        "WHERE company_id = $1 AND location_id = $2 FOR UPDATE",
        company_id, location_id,
    )
    template_id = profile["default_week_template_id"] if profile else None

    if template_id is None:
        location_name = await conn.fetchval(
            "SELECT name FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if location_name is None:
            raise ValueError("Location not found")
        # Always location-scoped: a company-wide template (location_id NULL) is
        # visible from every store's picker and must never become one store's
        # default.
        tpl, _ = await create_week_template_core(
            conn, company_id=company_id, actor_user_id=actor_user_id,
            body=WeekTemplateCreate(
                name=(template_name or f"{location_name} default week")[:150],
                location_id=location_id, blocks=[],
            ),
        )
        template_id = tpl["id"]
        await upsert_location_profile(
            conn, company_id=company_id, location_id=location_id,
            actor_user_id=actor_user_id, default_week_template_id=template_id,
        )

    existing = await conn.fetch(
        "SELECT id, name, start_time, end_time FROM schedule_shift_templates "
        "WHERE week_template_id = $1",
        template_id,
    )
    by_signature = {
        _block_signature(r["name"], r["start_time"], r["end_time"]): r["id"]
        for r in existing
    }

    replacements: list[WeekTemplateBlockReplace] = []
    claimed: set = set()
    for block in blocks:
        signature = _block_signature(block.get("name"), block.get("start_time"), block.get("end_time"))
        existing_id = by_signature.get(signature)
        if existing_id in claimed:
            existing_id = None
        if existing_id is not None:
            claimed.add(existing_id)
        replacements.append(WeekTemplateBlockReplace(
            id=existing_id,
            name=block["name"],
            role=block.get("role") or block.get("job_name"),
            start_time=block["start_time"],
            end_time=block["end_time"],
            break_minutes=block.get("break_minutes") or 0,
            required_staff=block.get("required_staff") or 1,
            days_of_week=sorted(set(block.get("days_of_week") or [])),
            job_id=block.get("job_id"),
        ))

    await replace_week_template_contents_core(
        conn, company_id=company_id, week_template_id=template_id,
        name=template_name, blocks=replacements, actor_user_id=actor_user_id,
    )
    return template_id
