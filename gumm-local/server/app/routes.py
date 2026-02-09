import os
import re
import smtplib
from datetime import date, datetime
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from .config import get_settings
from .database import get_connection
from .schemas import (
    BusinessMediaUpdate,
    BusinessRegister,
    BusinessSettingsUpdate,
    CafeCreate,
    CafeUpdate,
    EmailCampaignCreate,
    LocalCreate,
    LocalUpdate,
    LoginRequest,
    RedemptionCreate,
    RewardProgramCreate,
    RewardProgramUpdate,
    TeamMemberCreate,
    VisitCreate,
)
from .security import AuthContext, create_access_token, hash_password, require_auth, verify_password

router = APIRouter()

_ALLOWED_IMAGE_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}
_MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB
_MAX_VIDEO_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB
_UPLOAD_CHUNK_BYTES = 1024 * 1024


def _serialize_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _row_to_dict(row: asyncpg.Record | None) -> dict | None:
    if row is None:
        return None
    return {key: _serialize_value(value) for key, value in row.items()}


def _rows_to_dict(rows: list[asyncpg.Record]) -> list[dict]:
    return [_row_to_dict(row) for row in rows if row is not None]


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "local-business"


async def _build_unique_business_slug(conn: asyncpg.Connection, name: str) -> str:
    base_slug = _slugify(name)
    candidate = base_slug
    index = 2
    while True:
        exists = await conn.fetchval("SELECT 1 FROM local_businesses WHERE slug = $1", candidate)
        if not exists:
            return candidate
        candidate = f"{base_slug}-{index}"
        index += 1


def _detect_media_type(content_type: str | None, filename: str | None) -> tuple[str, str, int]:
    normalized_type = (content_type or "").lower().strip()
    extension = Path(filename or "").suffix.lower()

    if normalized_type in _ALLOWED_IMAGE_MIME_TYPES:
        return "image", (_ALLOWED_IMAGE_MIME_TYPES[normalized_type] or extension), _MAX_IMAGE_UPLOAD_BYTES
    if normalized_type in _ALLOWED_VIDEO_MIME_TYPES:
        return "video", (_ALLOWED_VIDEO_MIME_TYPES[normalized_type] or extension), _MAX_VIDEO_UPLOAD_BYTES

    if extension in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return "image", extension, _MAX_IMAGE_UPLOAD_BYTES
    if extension in {".mp4", ".webm", ".mov"}:
        return "video", extension, _MAX_VIDEO_UPLOAD_BYTES

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported media type. Upload images (jpg/png/webp/gif) or short videos (mp4/webm/mov).",
    )


def _safe_media_storage_path(storage_path: str) -> Path:
    settings = get_settings()
    base_dir = Path(settings.upload_dir).resolve()
    resolved = (base_dir / storage_path).resolve()
    if not str(resolved).startswith(str(base_dir)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid media storage path")
    return resolved


def _to_media_url(storage_path: str) -> str:
    return f"/media/{storage_path.replace(os.sep, '/')}"


async def _save_media_file(upload: UploadFile, business_id: UUID) -> dict:
    settings = get_settings()
    media_type, extension, max_bytes = _detect_media_type(upload.content_type, upload.filename)
    business_dir = Path(settings.upload_dir) / str(business_id)
    business_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{uuid4().hex}{extension}"
    target_path = business_dir / file_name
    size_bytes = 0

    try:
        with target_path.open("wb") as out_file:
            while True:
                chunk = await upload.read(_UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"File too large. Max size for {media_type}s is {max_bytes // (1024 * 1024)}MB.",
                    )
                out_file.write(chunk)
    except HTTPException:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    if size_bytes <= 0:
        target_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    storage_path = str(target_path.relative_to(Path(settings.upload_dir)))
    return {
        "media_type": media_type,
        "storage_path": storage_path,
        "media_url": _to_media_url(storage_path),
        "mime_type": (upload.content_type or "").lower().strip() or "application/octet-stream",
        "original_filename": (upload.filename or "")[:255] or None,
        "size_bytes": size_bytes,
    }


def _require_roles(auth: AuthContext, allowed_roles: set[str]):
    if auth.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions for this action",
        )


async def _require_active_user(conn: asyncpg.Connection, auth: AuthContext) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT *
        FROM local_business_users
        WHERE id = $1 AND business_id = $2 AND is_active = true
        """,
        auth.user_id,
        auth.business_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User session is no longer valid")
    return row


async def _ensure_cafe_access(conn: asyncpg.Connection, business_id: UUID, cafe_id: UUID) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT c.*
        FROM local_cafes c
        INNER JOIN local_business_cafes bc ON bc.cafe_id = c.id
        WHERE bc.business_id = $1 AND c.id = $2
        """,
        business_id,
        cafe_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cafe not found")
    return row


async def _ensure_local_exists(conn: asyncpg.Connection, cafe_id: UUID, local_id: UUID):
    exists = await conn.fetchval(
        "SELECT 1 FROM local_customers WHERE id = $1 AND cafe_id = $2",
        local_id,
        cafe_id,
    )
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local customer not found")


async def _ensure_program_belongs_to_cafe(conn: asyncpg.Connection, cafe_id: UUID, program_id: UUID):
    exists = await conn.fetchval(
        "SELECT 1 FROM local_reward_programs WHERE id = $1 AND cafe_id = $2 AND active = true",
        program_id,
        cafe_id,
    )
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reward program not found for this cafe")


async def _compute_program_progress(
    conn: asyncpg.Connection,
    cafe_id: UUID,
    local_id: UUID,
    program: asyncpg.Record,
) -> dict:
    visits_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM local_visits
        WHERE cafe_id = $1 AND customer_id = $2 AND program_id = $3
        """,
        cafe_id,
        local_id,
        program["id"],
    )
    redemptions_count = await conn.fetchval(
        """
        SELECT COUNT(*) FROM local_redemptions
        WHERE cafe_id = $1 AND customer_id = $2 AND program_id = $3
        """,
        cafe_id,
        local_id,
        program["id"],
    )

    visits_required = int(program["visits_required"])
    completed_cycles = int(visits_count) // visits_required
    available_rewards = max(completed_cycles - int(redemptions_count), 0)
    stamps_toward_next = int(visits_count) % visits_required

    if available_rewards > 0:
        visits_to_next_reward = 0
    else:
        visits_to_next_reward = visits_required - stamps_toward_next
        if visits_to_next_reward == 0:
            visits_to_next_reward = visits_required

    return {
        "program": _row_to_dict(program),
        "stamps_earned": int(visits_count),
        "stamps_toward_next_reward": stamps_toward_next,
        "rewards_redeemed": int(redemptions_count),
        "available_rewards": available_rewards,
        "visits_required": visits_required,
        "visits_to_next_reward": visits_to_next_reward,
    }


async def _build_local_progress(conn: asyncpg.Connection, cafe_id: UUID, local_id: UUID) -> dict:
    local_row = await conn.fetchrow(
        "SELECT * FROM local_customers WHERE id = $1 AND cafe_id = $2",
        local_id,
        cafe_id,
    )
    if local_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Local customer not found")

    programs = await conn.fetch(
        """
        SELECT *
        FROM local_reward_programs
        WHERE cafe_id = $1 AND active = true
        ORDER BY created_at ASC
        """,
        cafe_id,
    )

    program_progress = []
    for program in programs:
        program_progress.append(await _compute_program_progress(conn, cafe_id, local_id, program))

    total_visits = await conn.fetchval(
        "SELECT COUNT(*) FROM local_visits WHERE cafe_id = $1 AND customer_id = $2",
        cafe_id,
        local_id,
    )
    total_rewards = await conn.fetchval(
        "SELECT COUNT(*) FROM local_redemptions WHERE cafe_id = $1 AND customer_id = $2",
        cafe_id,
        local_id,
    )

    return {
        "local": _row_to_dict(local_row),
        "total_visits": int(total_visits),
        "total_rewards_redeemed": int(total_rewards),
        "program_progress": program_progress,
    }


async def _build_business_profile(conn: asyncpg.Connection, business_id: UUID, user_id: UUID | None = None) -> dict:
    business = await conn.fetchrow("SELECT * FROM local_businesses WHERE id = $1", business_id)
    settings = await conn.fetchrow("SELECT * FROM local_business_settings WHERE business_id = $1", business_id)
    media_rows = await conn.fetch(
        """
        SELECT id, business_id, uploaded_by, media_type, media_url, mime_type, original_filename,
               size_bytes, caption, sort_order, created_at
        FROM local_business_media
        WHERE business_id = $1
        ORDER BY sort_order ASC, created_at DESC
        """,
        business_id,
    )
    if business is None or settings is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business profile not found")

    payload = {
        "business": _row_to_dict(business),
        "settings": _row_to_dict(settings),
        "media": _rows_to_dict(media_rows),
    }

    if user_id is not None:
        user = await conn.fetchrow(
            """
            SELECT id, business_id, full_name, email, role, is_active, created_at, last_login_at
            FROM local_business_users
            WHERE id = $1 AND business_id = $2
            """,
            user_id,
            business_id,
        )
        payload["current_user"] = _row_to_dict(user)

    return payload


def _prepare_email_message(sender_name: str, sender_email: str, recipient_email: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = formataddr((sender_name, sender_email))
    message["To"] = recipient_email
    message["Subject"] = subject
    message.set_content(body)
    return message


def _send_blast_via_smtp(
    *,
    sender_name: str,
    sender_email: str,
    subject: str,
    body: str,
    recipients: list[dict],
) -> list[dict]:
    settings = get_settings()

    if not settings.smtp_host:
        return [{"recipient": recipient, "status": "simulated", "error": None} for recipient in recipients]

    results: list[dict] = []
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
            if settings.smtp_use_tls:
                client.starttls()
            if settings.smtp_username and settings.smtp_password:
                client.login(settings.smtp_username, settings.smtp_password)

            for recipient in recipients:
                recipient_email = recipient["email"]
                try:
                    message = _prepare_email_message(sender_name, sender_email, recipient_email, subject, body)
                    client.send_message(message)
                    results.append({"recipient": recipient, "status": "sent", "error": None})
                except Exception as exc:  # noqa: BLE001
                    results.append({"recipient": recipient, "status": "failed", "error": str(exc)[:400]})
    except Exception as exc:  # noqa: BLE001
        error_text = f"SMTP connection failed: {str(exc)[:320]}"
        return [{"recipient": recipient, "status": "failed", "error": error_text} for recipient in recipients]

    return results


async def _fetch_campaign_recipients(conn: asyncpg.Connection, cafe_id: UUID, segment: str) -> list[dict]:
    if segment in {"all", "vip", "regular"}:
        query = """
            SELECT c.id, c.full_name, c.email
            FROM local_customers c
            WHERE c.cafe_id = $1
              AND c.email IS NOT NULL
              AND c.email <> ''
              AND (
                $2 = 'all'
                OR ($2 = 'vip' AND c.is_vip = true)
                OR ($2 = 'regular' AND c.is_vip = false)
              )
            ORDER BY c.created_at ASC
        """
        rows = await conn.fetch(query, cafe_id, segment)
        return _rows_to_dict(rows)

    reward_ready_rows = await conn.fetch(
        """
        SELECT c.id, c.full_name, c.email
        FROM local_customers c
        WHERE c.cafe_id = $1
          AND c.email IS NOT NULL
          AND c.email <> ''
          AND EXISTS (
              SELECT 1
              FROM local_reward_programs p
              WHERE p.cafe_id = $1
                AND p.active = true
                AND FLOOR((
                    SELECT COUNT(*)::numeric
                    FROM local_visits v
                    WHERE v.cafe_id = $1
                      AND v.customer_id = c.id
                      AND v.program_id = p.id
                ) / p.visits_required) > (
                    SELECT COUNT(*)
                    FROM local_redemptions r
                    WHERE r.cafe_id = $1
                      AND r.customer_id = c.id
                      AND r.program_id = p.id
                )
          )
        ORDER BY c.created_at ASC
        """,
        cafe_id,
    )
    return _rows_to_dict(reward_ready_rows)


# ==========================================
# Authentication and Business Onboarding
# ==========================================


@router.post("/auth/register-business", status_code=201)
async def register_business(payload: BusinessRegister):
    owner_email = _normalize_email(str(payload.owner_email))

    async with get_connection() as conn:
        existing_user = await conn.fetchval("SELECT 1 FROM local_business_users WHERE email = $1", owner_email)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")

        business_id = uuid4()
        user_id = uuid4()
        cafe_id = uuid4()
        slug = await _build_unique_business_slug(conn, payload.business_name)

        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO local_businesses (id, name, slug)
                VALUES ($1, $2, $3)
                """,
                business_id,
                payload.business_name,
                slug,
            )

            await conn.execute(
                """
                INSERT INTO local_business_settings (
                    business_id,
                    sender_name,
                    sender_email,
                    loyalty_message,
                    vip_label
                )
                VALUES ($1, $2, $3, $4, $5)
                """,
                business_id,
                payload.business_name,
                owner_email,
                "Thanks for being one of our neighborhood regulars.",
                "Local VIP",
            )

            await conn.execute(
                """
                INSERT INTO local_business_users (id, business_id, full_name, email, password_hash, role)
                VALUES ($1, $2, $3, $4, $5, 'owner')
                """,
                user_id,
                business_id,
                payload.owner_name,
                owner_email,
                hash_password(payload.password),
            )

            await conn.execute(
                """
                INSERT INTO local_cafes (id, name, neighborhood, accent_color)
                VALUES ($1, $2, $3, $4)
                """,
                cafe_id,
                payload.initial_cafe_name,
                payload.initial_neighborhood,
                payload.initial_accent_color,
            )

            await conn.execute(
                """
                INSERT INTO local_business_cafes (business_id, cafe_id)
                VALUES ($1, $2)
                """,
                business_id,
                cafe_id,
            )

        token = create_access_token(
            user_id=user_id,
            business_id=business_id,
            role="owner",
            email=owner_email,
        )

        created_user = await conn.fetchrow(
            """
            SELECT id, business_id, full_name, email, role, is_active, created_at, last_login_at
            FROM local_business_users
            WHERE id = $1
            """,
            user_id,
        )
        business = await conn.fetchrow("SELECT * FROM local_businesses WHERE id = $1", business_id)

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": _row_to_dict(created_user),
            "business": _row_to_dict(business),
            "initial_cafe_id": str(cafe_id),
        }


@router.post("/auth/login")
async def login(payload: LoginRequest):
    email = _normalize_email(str(payload.email))

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                u.id AS user_id,
                u.business_id,
                u.full_name,
                u.email,
                u.role,
                u.is_active,
                u.password_hash,
                b.name AS business_name,
                b.slug AS business_slug
            FROM local_business_users u
            INNER JOIN local_businesses b ON b.id = u.business_id
            WHERE u.email = $1
            """,
            email,
        )

        if row is None or not row["is_active"] or not verify_password(payload.password, row["password_hash"]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

        await conn.execute(
            "UPDATE local_business_users SET last_login_at = NOW() WHERE id = $1",
            row["user_id"],
        )

        token = create_access_token(
            user_id=row["user_id"],
            business_id=row["business_id"],
            role=row["role"],
            email=row["email"],
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": str(row["user_id"]),
                "business_id": str(row["business_id"]),
                "full_name": row["full_name"],
                "email": row["email"],
                "role": row["role"],
                "is_active": row["is_active"],
            },
            "business": {
                "id": str(row["business_id"]),
                "name": row["business_name"],
                "slug": row["business_slug"],
            },
        }


@router.get("/auth/me")
async def auth_me(auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        profile = await _build_business_profile(conn, auth.business_id, user_id=auth.user_id)
        return profile


@router.get("/business/profile")
async def business_profile(auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        return await _build_business_profile(conn, auth.business_id, user_id=auth.user_id)


@router.patch("/business/settings")
async def update_business_settings(payload: BusinessSettingsUpdate, auth: AuthContext = Depends(require_auth)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No settings fields provided")

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        _require_roles(auth, {"owner", "admin"})

        async with conn.transaction():
            if "business_name" in updates:
                await conn.execute(
                    "UPDATE local_businesses SET name = $1 WHERE id = $2",
                    updates["business_name"],
                    auth.business_id,
                )
                updates.pop("business_name")

            if updates:
                set_parts = ["updated_at = NOW()"]
                values: list[object] = [auth.business_id]
                for idx, (field, value) in enumerate(updates.items(), start=2):
                    set_parts.append(f"{field} = ${idx}")
                    values.append(value)

                sql = f"""
                    UPDATE local_business_settings
                    SET {', '.join(set_parts)}
                    WHERE business_id = $1
                """
                await conn.execute(sql, *values)

        return await _build_business_profile(conn, auth.business_id, user_id=auth.user_id)


@router.get("/business/team")
async def list_team(auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)

        rows = await conn.fetch(
            """
            SELECT id, business_id, full_name, email, role, is_active, created_at, last_login_at
            FROM local_business_users
            WHERE business_id = $1
            ORDER BY
                CASE role
                    WHEN 'owner' THEN 1
                    WHEN 'admin' THEN 2
                    ELSE 3
                END,
                created_at ASC
            """,
            auth.business_id,
        )
        return _rows_to_dict(rows)


@router.post("/business/team", status_code=201)
async def create_team_member(payload: TeamMemberCreate, auth: AuthContext = Depends(require_auth)):
    _require_roles(auth, {"owner", "admin"})

    email = _normalize_email(str(payload.email))
    async with get_connection() as conn:
        await _require_active_user(conn, auth)

        existing_user = await conn.fetchval("SELECT 1 FROM local_business_users WHERE email = $1", email)
        if existing_user:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

        row = await conn.fetchrow(
            """
            INSERT INTO local_business_users (id, business_id, full_name, email, password_hash, role)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, business_id, full_name, email, role, is_active, created_at, last_login_at
            """,
            uuid4(),
            auth.business_id,
            payload.full_name,
            email,
            hash_password(payload.password),
            payload.role,
        )

        return _row_to_dict(row)


# ==========================================
# Business Media
# ==========================================


@router.get("/business/media")
async def list_business_media(auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        rows = await conn.fetch(
            """
            SELECT id, business_id, uploaded_by, media_type, media_url, mime_type, original_filename,
                   size_bytes, caption, sort_order, created_at
            FROM local_business_media
            WHERE business_id = $1
            ORDER BY sort_order ASC, created_at DESC
            """,
            auth.business_id,
        )
        return _rows_to_dict(rows)


@router.post("/business/media", status_code=201)
async def upload_business_media(
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    sort_order: int = Form(default=0),
    auth: AuthContext = Depends(require_auth),
):
    _require_roles(auth, {"owner", "admin", "staff"})

    if caption and len(caption) > 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Caption must be 500 characters or less")
    if sort_order < 0 or sort_order > 999:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="sort_order must be between 0 and 999")

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        saved_file = await _save_media_file(file, auth.business_id)

        try:
            row = await conn.fetchrow(
                """
                INSERT INTO local_business_media (
                    id,
                    business_id,
                    uploaded_by,
                    media_type,
                    storage_path,
                    media_url,
                    mime_type,
                    original_filename,
                    size_bytes,
                    caption,
                    sort_order
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING id, business_id, uploaded_by, media_type, media_url, mime_type, original_filename,
                          size_bytes, caption, sort_order, created_at
                """,
                uuid4(),
                auth.business_id,
                auth.user_id,
                saved_file["media_type"],
                saved_file["storage_path"],
                saved_file["media_url"],
                saved_file["mime_type"],
                saved_file["original_filename"],
                saved_file["size_bytes"],
                caption.strip() if caption else None,
                sort_order,
            )
        except Exception:
            file_path = _safe_media_storage_path(saved_file["storage_path"])
            file_path.unlink(missing_ok=True)
            raise

        return _row_to_dict(row)


@router.patch("/business/media/{media_id}")
async def update_business_media(
    media_id: UUID,
    payload: BusinessMediaUpdate,
    auth: AuthContext = Depends(require_auth),
):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No media fields provided for update")
    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)

        exists = await conn.fetchval(
            "SELECT 1 FROM local_business_media WHERE id = $1 AND business_id = $2",
            media_id,
            auth.business_id,
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business media not found")

        if "caption" in updates and updates["caption"] is not None:
            updates["caption"] = updates["caption"].strip() or None
            if updates["caption"] and len(updates["caption"]) > 500:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Caption must be 500 characters or less")

        set_parts = []
        values: list[object] = [media_id, auth.business_id]
        for idx, (field, value) in enumerate(updates.items(), start=3):
            set_parts.append(f"{field} = ${idx}")
            values.append(value)

        sql = f"""
            UPDATE local_business_media
            SET {', '.join(set_parts)}
            WHERE id = $1 AND business_id = $2
            RETURNING id, business_id, uploaded_by, media_type, media_url, mime_type, original_filename,
                      size_bytes, caption, sort_order, created_at
        """
        row = await conn.fetchrow(sql, *values)
        return _row_to_dict(row)


@router.delete("/business/media/{media_id}", status_code=204)
async def delete_business_media(media_id: UUID, auth: AuthContext = Depends(require_auth)):
    _require_roles(auth, {"owner", "admin"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        row = await conn.fetchrow(
            """
            SELECT storage_path
            FROM local_business_media
            WHERE id = $1 AND business_id = $2
            """,
            media_id,
            auth.business_id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business media not found")

        await conn.execute(
            "DELETE FROM local_business_media WHERE id = $1 AND business_id = $2",
            media_id,
            auth.business_id,
        )

        file_path = _safe_media_storage_path(row["storage_path"])
        file_path.unlink(missing_ok=True)


# ==========================================
# Cafes, Loyalty, and Regulars
# ==========================================


@router.get("/cafes")
async def list_cafes(auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)

        rows = await conn.fetch(
            """
            SELECT c.*
            FROM local_cafes c
            INNER JOIN local_business_cafes bc ON bc.cafe_id = c.id
            WHERE bc.business_id = $1
            ORDER BY c.created_at DESC
            """,
            auth.business_id,
        )
        return _rows_to_dict(rows)


@router.post("/cafes", status_code=201)
async def create_cafe(payload: CafeCreate, auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        _require_roles(auth, {"owner", "admin"})

        cafe_id = uuid4()
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO local_cafes (id, name, neighborhood, accent_color)
                VALUES ($1, $2, $3, $4)
                RETURNING *
                """,
                cafe_id,
                payload.name,
                payload.neighborhood,
                payload.accent_color,
            )
            await conn.execute(
                """
                INSERT INTO local_business_cafes (business_id, cafe_id)
                VALUES ($1, $2)
                """,
                auth.business_id,
                cafe_id,
            )

        return _row_to_dict(row)


@router.patch("/cafes/{cafe_id}")
async def update_cafe(cafe_id: UUID, payload: CafeUpdate, auth: AuthContext = Depends(require_auth)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    _require_roles(auth, {"owner", "admin"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        set_parts = []
        values: list[object] = [cafe_id]
        for idx, (field, value) in enumerate(updates.items(), start=2):
            set_parts.append(f"{field} = ${idx}")
            values.append(value)

        sql = f"""
            UPDATE local_cafes
            SET {', '.join(set_parts)}
            WHERE id = $1
            RETURNING *
        """
        row = await conn.fetchrow(sql, *values)
        return _row_to_dict(row)


@router.get("/cafes/{cafe_id}/programs")
async def list_programs(cafe_id: UUID, auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        rows = await conn.fetch(
            """
            SELECT *
            FROM local_reward_programs
            WHERE cafe_id = $1
            ORDER BY created_at ASC
            """,
            cafe_id,
        )
        return _rows_to_dict(rows)


@router.post("/cafes/{cafe_id}/programs", status_code=201)
async def create_program(cafe_id: UUID, payload: RewardProgramCreate, auth: AuthContext = Depends(require_auth)):
    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        try:
            row = await conn.fetchrow(
                """
                INSERT INTO local_reward_programs (id, cafe_id, name, visits_required, reward_description)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
                """,
                uuid4(),
                cafe_id,
                payload.name,
                payload.visits_required,
                payload.reward_description,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Program name already exists for this cafe") from exc

        return _row_to_dict(row)


@router.patch("/cafes/{cafe_id}/programs/{program_id}")
async def update_program(cafe_id: UUID, program_id: UUID, payload: RewardProgramUpdate, auth: AuthContext = Depends(require_auth)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        exists = await conn.fetchval(
            "SELECT 1 FROM local_reward_programs WHERE id = $1 AND cafe_id = $2",
            program_id,
            cafe_id,
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reward program not found")

        set_parts = []
        values: list[object] = [program_id, cafe_id]
        for idx, (field, value) in enumerate(updates.items(), start=3):
            set_parts.append(f"{field} = ${idx}")
            values.append(value)

        sql = f"""
            UPDATE local_reward_programs
            SET {', '.join(set_parts)}
            WHERE id = $1 AND cafe_id = $2
            RETURNING *
        """
        row = await conn.fetchrow(sql, *values)
        return _row_to_dict(row)


@router.get("/cafes/{cafe_id}/locals")
async def list_locals(cafe_id: UUID, auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        rows = await conn.fetch(
            """
            SELECT
                c.*,
                COALESCE(v.total_visits, 0) AS total_visits,
                COALESCE(r.total_rewards_redeemed, 0) AS total_rewards_redeemed
            FROM local_customers c
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_visits
                FROM local_visits
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) v ON v.customer_id = c.id
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_rewards_redeemed
                FROM local_redemptions
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) r ON r.customer_id = c.id
            WHERE c.cafe_id = $1
            ORDER BY c.is_vip DESC, COALESCE(v.total_visits, 0) DESC, c.created_at DESC
            """,
            cafe_id,
        )
        return _rows_to_dict(rows)


@router.post("/cafes/{cafe_id}/locals", status_code=201)
async def create_local(cafe_id: UUID, payload: LocalCreate, auth: AuthContext = Depends(require_auth)):
    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        row = await conn.fetchrow(
            """
            INSERT INTO local_customers (id, cafe_id, full_name, phone, email, favorite_order, notes, is_vip)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            uuid4(),
            cafe_id,
            payload.full_name,
            payload.phone,
            _normalize_email(str(payload.email)) if payload.email else None,
            payload.favorite_order,
            payload.notes,
            payload.is_vip,
        )
        return _row_to_dict(row)


@router.patch("/cafes/{cafe_id}/locals/{local_id}")
async def update_local(cafe_id: UUID, local_id: UUID, payload: LocalUpdate, auth: AuthContext = Depends(require_auth)):
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")

    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)
        await _ensure_local_exists(conn, cafe_id, local_id)

        if "email" in updates and updates["email"]:
            updates["email"] = _normalize_email(str(updates["email"]))

        set_parts = []
        values: list[object] = [local_id, cafe_id]
        for idx, (field, value) in enumerate(updates.items(), start=3):
            set_parts.append(f"{field} = ${idx}")
            values.append(value)

        sql = f"""
            UPDATE local_customers
            SET {', '.join(set_parts)}
            WHERE id = $1 AND cafe_id = $2
            RETURNING *
        """
        row = await conn.fetchrow(sql, *values)
        return _row_to_dict(row)


@router.post("/cafes/{cafe_id}/locals/{local_id}/visits", status_code=201)
async def record_visit(cafe_id: UUID, local_id: UUID, payload: VisitCreate, auth: AuthContext = Depends(require_auth)):
    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)
        await _ensure_local_exists(conn, cafe_id, local_id)

        if payload.program_id is not None:
            await _ensure_program_belongs_to_cafe(conn, cafe_id, payload.program_id)

        row = await conn.fetchrow(
            """
            INSERT INTO local_visits (id, cafe_id, customer_id, program_id, order_total, visit_note)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            uuid4(),
            cafe_id,
            local_id,
            payload.program_id,
            payload.order_total,
            payload.visit_note,
        )

        return {
            "visit": _row_to_dict(row),
            "progress": await _build_local_progress(conn, cafe_id, local_id),
        }


@router.get("/cafes/{cafe_id}/locals/{local_id}/progress")
async def local_progress(cafe_id: UUID, local_id: UUID, auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)
        await _ensure_local_exists(conn, cafe_id, local_id)
        return await _build_local_progress(conn, cafe_id, local_id)


@router.post("/cafes/{cafe_id}/locals/{local_id}/redeem", status_code=201)
async def redeem_reward(cafe_id: UUID, local_id: UUID, payload: RedemptionCreate, auth: AuthContext = Depends(require_auth)):
    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)
        await _ensure_local_exists(conn, cafe_id, local_id)
        await _ensure_program_belongs_to_cafe(conn, cafe_id, payload.program_id)

        program_row = await conn.fetchrow(
            "SELECT * FROM local_reward_programs WHERE id = $1",
            payload.program_id,
        )
        if program_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reward program not found")

        progress = await _compute_program_progress(conn, cafe_id, local_id, program_row)
        if progress["available_rewards"] <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No available reward to redeem for this local on this program",
            )

        redemption_row = await conn.fetchrow(
            """
            INSERT INTO local_redemptions (id, cafe_id, customer_id, program_id, redemption_note)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
            """,
            uuid4(),
            cafe_id,
            local_id,
            payload.program_id,
            payload.redemption_note,
        )

        return {
            "redemption": _row_to_dict(redemption_row),
            "progress": await _build_local_progress(conn, cafe_id, local_id),
        }


@router.get("/cafes/{cafe_id}/dashboard")
async def cafe_dashboard(cafe_id: UUID, auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        totals_row = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM local_customers WHERE cafe_id = $1) AS total_locals,
                (SELECT COUNT(*) FROM local_customers WHERE cafe_id = $1 AND is_vip = true) AS vip_locals,
                (SELECT COUNT(*) FROM local_visits WHERE cafe_id = $1) AS total_visits,
                (SELECT COUNT(*) FROM local_redemptions WHERE cafe_id = $1) AS rewards_redeemed
            """,
            cafe_id,
        )

        program_rows = await conn.fetch(
            """
            SELECT
                p.id,
                p.name,
                p.visits_required,
                p.reward_description,
                p.active,
                COALESCE(v.total_visits_logged, 0) AS total_visits_logged,
                COALESCE(v.participating_locals, 0) AS participating_locals,
                COALESCE(r.total_redemptions, 0) AS total_redemptions
            FROM local_reward_programs p
            LEFT JOIN (
                SELECT
                    program_id,
                    COUNT(*) AS total_visits_logged,
                    COUNT(DISTINCT customer_id) AS participating_locals
                FROM local_visits
                WHERE cafe_id = $1 AND program_id IS NOT NULL
                GROUP BY program_id
            ) v ON v.program_id = p.id
            LEFT JOIN (
                SELECT
                    program_id,
                    COUNT(*) AS total_redemptions
                FROM local_redemptions
                WHERE cafe_id = $1
                GROUP BY program_id
            ) r ON r.program_id = p.id
            WHERE p.cafe_id = $1
            ORDER BY p.created_at ASC
            """,
            cafe_id,
        )

        top_locals_rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.full_name,
                c.is_vip,
                COALESCE(v.total_visits, 0) AS total_visits,
                COALESCE(r.total_rewards_redeemed, 0) AS total_rewards_redeemed
            FROM local_customers c
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_visits
                FROM local_visits
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) v ON v.customer_id = c.id
            LEFT JOIN (
                SELECT customer_id, COUNT(*) AS total_rewards_redeemed
                FROM local_redemptions
                WHERE cafe_id = $1
                GROUP BY customer_id
            ) r ON r.customer_id = c.id
            WHERE c.cafe_id = $1
            ORDER BY c.is_vip DESC, COALESCE(v.total_visits, 0) DESC, c.created_at ASC
            LIMIT 10
            """,
            cafe_id,
        )

        return {
            "totals": _row_to_dict(totals_row),
            "programs": _rows_to_dict(program_rows),
            "top_locals": _rows_to_dict(top_locals_rows),
        }


# ==========================================
# Email Campaigns
# ==========================================


@router.get("/cafes/{cafe_id}/email-campaigns")
async def list_email_campaigns(cafe_id: UUID, auth: AuthContext = Depends(require_auth)):
    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        rows = await conn.fetch(
            """
            SELECT
                c.*,
                u.full_name AS created_by_name
            FROM local_email_campaigns c
            INNER JOIN local_business_users u ON u.id = c.created_by
            WHERE c.business_id = $1 AND c.cafe_id = $2
            ORDER BY c.created_at DESC
            LIMIT 100
            """,
            auth.business_id,
            cafe_id,
        )

        return _rows_to_dict(rows)


@router.post("/cafes/{cafe_id}/email-campaigns", status_code=201)
async def create_email_campaign(
    cafe_id: UUID,
    payload: EmailCampaignCreate,
    auth: AuthContext = Depends(require_auth),
):
    _require_roles(auth, {"owner", "admin", "staff"})

    async with get_connection() as conn:
        await _require_active_user(conn, auth)
        await _ensure_cafe_access(conn, auth.business_id, cafe_id)

        campaign_id = uuid4()
        campaign_status = "draft" if not payload.send_now else "simulated"

        await conn.execute(
            """
            INSERT INTO local_email_campaigns (
                id,
                business_id,
                cafe_id,
                created_by,
                title,
                subject,
                body,
                target_segment,
                status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            campaign_id,
            auth.business_id,
            cafe_id,
            auth.user_id,
            payload.title,
            payload.subject,
            payload.body,
            payload.target_segment,
            campaign_status,
        )

        if not payload.send_now:
            row = await conn.fetchrow("SELECT * FROM local_email_campaigns WHERE id = $1", campaign_id)
            return {
                "campaign": _row_to_dict(row),
                "delivery_summary": {
                    "sent": 0,
                    "failed": 0,
                    "simulated": 0,
                },
            }

        recipients = await _fetch_campaign_recipients(conn, cafe_id, payload.target_segment)

        settings_row = await conn.fetchrow(
            """
            SELECT s.sender_name, s.sender_email, b.name AS business_name
            FROM local_business_settings s
            INNER JOIN local_businesses b ON b.id = s.business_id
            WHERE s.business_id = $1
            """,
            auth.business_id,
        )
        if settings_row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Business email settings are missing")

        sender_name = (settings_row["sender_name"] or settings_row["business_name"] or "gumm-local").strip()
        sender_email = (settings_row["sender_email"] or auth.email).strip().lower()

        send_results = _send_blast_via_smtp(
            sender_name=sender_name,
            sender_email=sender_email,
            subject=payload.subject,
            body=payload.body,
            recipients=recipients,
        )

        deliveries = []
        sent_count = 0
        failure_count = 0
        simulated_count = 0

        for item in send_results:
            recipient = item["recipient"]
            status_text = item["status"]
            error_text = item["error"]

            if status_text == "sent":
                sent_count += 1
            elif status_text == "failed":
                failure_count += 1
            else:
                simulated_count += 1

            deliveries.append(
                (
                    uuid4(),
                    campaign_id,
                    UUID(str(recipient["id"])),
                    recipient["email"],
                    status_text,
                    error_text,
                )
            )

        if deliveries:
            await conn.executemany(
                """
                INSERT INTO local_email_deliveries (
                    id,
                    campaign_id,
                    customer_id,
                    recipient_email,
                    status,
                    error_message
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                deliveries,
            )

        if failure_count > 0 and sent_count == 0 and simulated_count == 0:
            final_status = "failed"
        elif simulated_count > 0 and sent_count == 0 and failure_count == 0:
            final_status = "simulated"
        else:
            final_status = "sent"

        await conn.execute(
            """
            UPDATE local_email_campaigns
            SET status = $2,
                sent_count = $3,
                failure_count = $4,
                sent_at = NOW()
            WHERE id = $1
            """,
            campaign_id,
            final_status,
            sent_count + simulated_count,
            failure_count,
        )

        campaign = await conn.fetchrow(
            """
            SELECT c.*, u.full_name AS created_by_name
            FROM local_email_campaigns c
            INNER JOIN local_business_users u ON u.id = c.created_by
            WHERE c.id = $1
            """,
            campaign_id,
        )

        return {
            "campaign": _row_to_dict(campaign),
            "delivery_summary": {
                "sent": sent_count,
                "failed": failure_count,
                "simulated": simulated_count,
                "total_recipients": len(recipients),
            },
        }
