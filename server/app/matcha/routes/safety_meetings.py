"""Safety meeting recording, transcription, review, and sign-off routes."""

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.core.services.redis_cache import check_rate_limit
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.safety_meetings import (
    ChunkResult,
    LocationListResponse,
    LocationOption,
    SafetyMeetingCreate,
    SafetyMeetingListItem,
    SafetyMeetingListResponse,
    SafetyMeetingOut,
    SafetyMeetingSign,
    SafetyMeetingUpdate,
)
from app.matcha.services._shared.uploads import read_wav_or_400
from app.matcha.services.safety_meetings.summary import summarize_meeting
from app.matcha.services.safety_meetings.transcription import transcribe_meeting_chunk

logger = logging.getLogger(__name__)
router = APIRouter()


def _json_value(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return fallback
    return value if value is not None else fallback


def _segments(row: Any) -> list[dict]:
    value = _json_value(row["transcript_segments"], [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and isinstance(item.get("idx"), int)]


def _row_to_out(row: Any) -> SafetyMeetingOut:
    data = dict(row)
    data["transcript_segments"] = sorted(_segments(row), key=lambda item: item["idx"])
    data["topics"] = _json_value(data.get("topics"), [])
    data["action_items"] = _json_value(data.get("action_items"), [])
    data["attendee_names"] = _json_value(data.get("attendee_names"), [])
    return SafetyMeetingOut(**data)


async def _get_meeting(conn, meeting_id: UUID, company_id: UUID):
    row = await conn.fetchrow(
        """SELECT sm.*, bl.name AS location_name
           FROM safety_meetings sm
           LEFT JOIN business_locations bl ON bl.id = sm.location_id
           WHERE sm.id = $1 AND sm.company_id = $2""",
        meeting_id,
        company_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Safety meeting not found.")
    return row


def _transcript_from_segments(segments: list[dict]) -> str:
    return "\n\n".join(
        item["text"].strip()
        for item in sorted(segments, key=lambda item: item["idx"])
        if isinstance(item.get("text"), str) and item["text"].strip()
    )


@router.get("/locations", response_model=LocationListResponse)
async def list_locations(
    company_id: UUID = Depends(get_client_company_id),
    _user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, COALESCE(name, 'Location') AS name, city, state
               FROM business_locations
               WHERE company_id = $1 AND COALESCE(is_active, true) = true
               ORDER BY name NULLS LAST, city""",
            company_id,
        )
    return LocationListResponse(locations=[LocationOption(**dict(row)) for row in rows])


@router.post("", response_model=SafetyMeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    body: SafetyMeetingCreate,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    async with get_connection() as conn:
        if body.location_id is not None:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2)",
                body.location_id,
                company_id,
            )
            if not exists:
                raise HTTPException(status_code=404, detail="Location not found.")
        row = await conn.fetchrow(
            """INSERT INTO safety_meetings
                 (company_id, location_id, title, topic, attendee_names, created_by)
               VALUES ($1, $2, $3, $4, $5::jsonb, $6)
               RETURNING *""",
            company_id,
            body.location_id,
            body.title.strip(),
            (body.topic.strip() or None) if body.topic else None,
            json.dumps(body.attendee_names),
            user.id,
        )
        row = await _get_meeting(conn, row["id"], company_id)
    return _row_to_out(row)


@router.get("", response_model=SafetyMeetingListResponse)
async def list_meetings(
    company_id: UUID = Depends(get_client_company_id),
    _user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT sm.id, sm.title, sm.status, bl.name AS location_name,
                      COALESCE(jsonb_array_length(sm.attendee_names), 0) AS attendee_count,
                      sm.started_at, sm.ended_at, sm.signed_at, sm.signature_name
               FROM safety_meetings sm
               LEFT JOIN business_locations bl ON bl.id = sm.location_id
               WHERE sm.company_id = $1
               ORDER BY sm.started_at DESC
               LIMIT 200""",
            company_id,
        )
    return SafetyMeetingListResponse(
        meetings=[SafetyMeetingListItem(**dict(row)) for row in rows]
    )


@router.get("/{meeting_id}", response_model=SafetyMeetingOut)
async def get_meeting(
    meeting_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    _user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    async with get_connection() as conn:
        row = await _get_meeting(conn, meeting_id, company_id)
    return _row_to_out(row)


@router.post("/{meeting_id}/chunks", response_model=ChunkResult)
async def upload_chunk(
    meeting_id: UUID,
    file: UploadFile = File(...),
    chunk_index: int = Form(..., ge=0, le=10000),
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    user_key = f"user:{user.id}"
    await check_rate_limit(user_key, "safety_meeting_chunk_burst", 12, 60)
    await check_rate_limit(str(company_id), "safety_meeting_chunk_company", 500, 3600)

    async with get_connection() as conn:
        row = await _get_meeting(conn, meeting_id, company_id)
        if row["status"] != "recording":
            raise HTTPException(status_code=409, detail="This meeting is no longer recording.")

    audio = await read_wav_or_400(file)
    audio_path = None
    try:
        audio_path = await get_storage().upload_private_file(
            audio,
            f"chunk_{chunk_index}.wav",
            prefix=f"safety-meetings/{company_id}/{meeting_id}",
            content_type="audio/wav",
        )
    except Exception as exc:
        # Do not interrupt a live meeting because S3 is temporarily unavailable.
        # The transcript still remains useful; the missing path is visible only
        # to the server and can be retried by a future retention job.
        logger.warning("safety meeting audio retention failed for %s/%s: %s", meeting_id, chunk_index, exc)

    context = row["title"]
    if row["topic"]:
        context += f"; planned topic: {row['topic']}"
    result = await transcribe_meeting_chunk(
        audio,
        (file.content_type or "audio/wav").lower(),
        context=context,
    )

    async with get_connection() as conn:
        async with conn.transaction():
            row = await _get_meeting(conn, meeting_id, company_id, for_update=True)
            if row["status"] != "recording":
                raise HTTPException(status_code=409, detail="This meeting is no longer recording.")
            segments = _segments(row)
            segments = [item for item in segments if item["idx"] != chunk_index]
            segments.append({
                "idx": chunk_index,
                "text": result["transcript"] or "",
                "audio_path": audio_path,
            })
            segments.sort(key=lambda item: item["idx"])
            await conn.execute(
                """UPDATE safety_meetings
                   SET transcript_segments = $1::jsonb,
                       transcript = $2,
                       updated_at = NOW()
                   WHERE id = $3 AND company_id = $4""",
                json.dumps(segments),
                _transcript_from_segments(segments),
                meeting_id,
                company_id,
            )
    return ChunkResult(
        idx=chunk_index,
        transcript=result["transcript"],
        available=result["available"],
    )


@router.post("/{meeting_id}/finish", response_model=SafetyMeetingOut)
async def finish_meeting(
    meeting_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    await check_rate_limit(f"user:{user.id}", "safety_meeting_finish_burst", 10, 60)
    await check_rate_limit(str(company_id), "safety_meeting_finish_company", 100, 3600)

    async with get_connection() as conn:
        row = await _get_meeting(conn, meeting_id, company_id)
        if row["status"] != "recording":
            raise HTTPException(status_code=409, detail="This meeting has already been finished.")
        location_name = row["location_name"]
        transcript = row["transcript"] or _transcript_from_segments(_segments(row))
        attendees = _json_value(row["attendee_names"], [])

    draft = await summarize_meeting(
        title=row["title"],
        topic=row["topic"],
        location_name=location_name,
        attendee_names=attendees if isinstance(attendees, list) else [],
        transcript=transcript,
    )
    final_attendees = attendees if isinstance(attendees, list) else []
    if not final_attendees:
        final_attendees = draft["attendees_mentioned"]

    async with get_connection() as conn:
        await conn.execute(
            """UPDATE safety_meetings
               SET status = 'review', ended_at = NOW(), transcript = $1,
                   summary = $2, topics = $3::jsonb, action_items = $4::jsonb,
                   attendee_names = $5::jsonb, summary_model = $6,
                   updated_at = NOW()
               WHERE id = $7 AND company_id = $8 AND status = 'recording'""",
            transcript,
            draft["summary"],
            json.dumps(draft["topics"]),
            json.dumps(draft["action_items"]),
            json.dumps(final_attendees),
            draft["model"] if draft["available"] else None,
            meeting_id,
            company_id,
        )
        row = await _get_meeting(conn, meeting_id, company_id)
    return _row_to_out(row)


@router.patch("/{meeting_id}", response_model=SafetyMeetingOut)
async def update_meeting(
    meeting_id: UUID,
    body: SafetyMeetingUpdate,
    company_id: UUID = Depends(get_client_company_id),
    _user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    values = body.model_dump(exclude_unset=True)
    if "title" in values:
        values["title"] = values["title"].strip()
    if "topic" in values and values["topic"] is not None:
        values["topic"] = values["topic"].strip() or None
    if "summary" in values and values["summary"] is not None:
        values["summary"] = values["summary"].strip()
    if "manager_notes" in values and values["manager_notes"] is not None:
        values["manager_notes"] = values["manager_notes"].strip()
    if "action_items" in values:
        values["action_items"] = [item.model_dump() for item in values["action_items"]]

    allowed = {"title", "topic", "summary", "manager_notes", "attendee_names", "topics", "action_items"}
    values = {key: value for key, value in values.items() if key in allowed}
    if not values:
        async with get_connection() as conn:
            return _row_to_out(await _get_meeting(conn, meeting_id, company_id))

    assignments = []
    args: list[Any] = []
    for key, value in values.items():
        args.append(json.dumps(value) if key in {"attendee_names", "topics", "action_items"} else value)
        placeholder = f"${len(args)}"
        assignments.append(
            f"{key} = {placeholder}::jsonb" if key in {"attendee_names", "topics", "action_items"}
            else f"{key} = {placeholder}"
        )
    args.extend([meeting_id, company_id])
    assignments.append("updated_at = NOW()")
    query = (
        f"UPDATE safety_meetings SET {', '.join(assignments)} "
        f"WHERE id = ${len(args) - 1} AND company_id = ${len(args)} AND status = 'review'"
    )
    async with get_connection() as conn:
        result = await conn.execute(query, *args)
        if result == "UPDATE 0":
            row = await _get_meeting(conn, meeting_id, company_id)
            raise HTTPException(status_code=409, detail="Only meetings awaiting review can be edited.")
        return _row_to_out(await _get_meeting(conn, meeting_id, company_id))


@router.post("/{meeting_id}/sign", response_model=SafetyMeetingOut)
async def sign_meeting(
    meeting_id: UUID,
    body: SafetyMeetingSign,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirm that the record is accurate before signing.")
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE safety_meetings
               SET status = 'signed', signed_by = $1, signed_at = NOW(),
                   signature_name = $2, updated_at = NOW()
               WHERE id = $3 AND company_id = $4 AND status = 'review'""",
            user.id,
            body.signature_name,
            meeting_id,
            company_id,
        )
        if result == "UPDATE 0":
            row = await _get_meeting(conn, meeting_id, company_id)
            if row["status"] == "signed":
                raise HTTPException(status_code=409, detail="This meeting is already signed.")
            raise HTTPException(status_code=409, detail="Only meetings awaiting review can be signed.")
        return _row_to_out(await _get_meeting(conn, meeting_id, company_id))


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: UUID,
    company_id: UUID = Depends(get_client_company_id),
    _user=Depends(require_admin_or_client),
):
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    async with get_connection() as conn:
        row = await _get_meeting(conn, meeting_id, company_id)
        if row["status"] == "signed":
            raise HTTPException(status_code=409, detail="Signed safety meeting records cannot be deleted.")
        paths = [item.get("audio_path") for item in _segments(row) if item.get("audio_path")]
        await conn.execute(
            "DELETE FROM safety_meetings WHERE id = $1 AND company_id = $2",
            meeting_id,
            company_id,
        )
    for path in paths:
        try:
            await get_storage().delete_private_file(path)
        except Exception as exc:
            logger.warning("safety meeting audio cleanup failed for %s: %s", path, exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
