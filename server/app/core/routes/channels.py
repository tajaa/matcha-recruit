"""Channel routes for Slack-style group chat in Matcha Work."""

import json
import os
import re
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import get_current_user
from ..models.auth import CurrentUser
from ...matcha.dependencies import resolve_accessible_company_scope, require_admin_or_client
from ..services.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

_USER_NAME_EXPR = "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"


class ChannelMember(BaseModel):
    user_id: UUID
    name: str
    email: str
    role: str  # user's global role
    channel_role: str = "member"  # owner, moderator, member
    avatar_url: Optional[str] = None
    joined_at: datetime


class ChannelAttachment(BaseModel):
    url: str
    filename: str
    content_type: str
    size: int


class ChannelReaction(BaseModel):
    emoji: str
    user_ids: list[UUID] = []
    count: int = 0


class ReplyPreview(BaseModel):
    id: UUID
    sender_name: str
    content: str
    attachments: list[ChannelAttachment] = []


class ChannelMessage(BaseModel):
    id: UUID
    channel_id: UUID
    sender_id: UUID
    sender_name: str
    sender_avatar_url: Optional[str] = None
    content: str
    attachments: list[ChannelAttachment] = []
    reply_to_id: Optional[UUID] = None
    reply_preview: Optional[ReplyPreview] = None
    reactions: list[ChannelReaction] = []
    created_at: datetime
    edited_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[UUID] = None


def _row_to_message(m, reactions_map: dict | None = None) -> "ChannelMessage":
    """Shared row → ChannelMessage transform that tombstones deleted rows.

    Deleted messages return with empty content + attachments and the
    deleted_at/deleted_by fields set so the client can render a tombstone
    instead of the original text.
    """
    is_deleted = m["deleted_at"] is not None
    attachments = (
        []
        if is_deleted
        else (
            json.loads(m["attachments"])
            if isinstance(m["attachments"], str)
            else (m["attachments"] or [])
        )
    )
    # Build reply preview if this message is a reply
    reply_preview = None
    reply_to_id = m.get("reply_to_id")
    if reply_to_id and m.get("reply_sender_name"):
        reply_atts = []
        if not m.get("reply_deleted"):
            raw = m.get("reply_attachments")
            if raw:
                reply_atts = json.loads(raw) if isinstance(raw, str) else (raw or [])
        reply_preview = ReplyPreview(
            id=reply_to_id,
            sender_name=m["reply_sender_name"],
            content="" if m.get("reply_deleted") else (m.get("reply_content") or ""),
            attachments=reply_atts,
        )

    # Build reactions list
    msg_reactions = []
    if reactions_map and m["id"] in reactions_map:
        msg_reactions = reactions_map[m["id"]]

    return ChannelMessage(
        id=m["id"],
        channel_id=m["channel_id"],
        sender_id=m["sender_id"],
        sender_name=m["sender_name"],
        sender_avatar_url=m["sender_avatar_url"],
        content="" if is_deleted else m["content"],
        attachments=attachments,
        reply_to_id=reply_to_id,
        reply_preview=reply_preview,
        reactions=msg_reactions,
        created_at=m["created_at"],
        edited_at=m["edited_at"],
        deleted_at=m["deleted_at"],
        deleted_by=m["deleted_by"],
    )


async def _fetch_reactions_map(conn, message_ids: list[UUID]) -> dict[UUID, list[ChannelReaction]]:
    """Fetch reactions for a batch of messages, grouped by message → emoji → user_ids."""
    if not message_ids:
        return {}
    rows = await conn.fetch(
        "SELECT message_id, emoji, user_id FROM channel_reactions WHERE message_id = ANY($1) ORDER BY created_at",
        message_ids,
    )
    from collections import defaultdict
    grouped: dict[UUID, dict[str, list[UUID]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        grouped[r["message_id"]][r["emoji"]].append(r["user_id"])
    result: dict[UUID, list[ChannelReaction]] = {}
    for mid, emojis in grouped.items():
        result[mid] = [
            ChannelReaction(emoji=e, user_ids=uids, count=len(uids))
            for e, uids in emojis.items()
        ]
    return result


# SQL fragment for message queries — includes reply LEFT JOIN
_MSG_SELECT = f"""
    SELECT m.id, m.channel_id, m.sender_id, m.content, m.attachments,
           m.reply_to_id, m.created_at, m.edited_at, m.deleted_at, m.deleted_by,
           {{name_expr}} AS sender_name, u.avatar_url AS sender_avatar_url,
           rm.content AS reply_content, rm.attachments AS reply_attachments,
           rm.deleted_at IS NOT NULL AS reply_deleted,
           {{reply_name_expr}} AS reply_sender_name
    FROM channel_messages m
    JOIN users u ON u.id = m.sender_id
    LEFT JOIN clients c ON c.user_id = u.id
    LEFT JOIN employees e ON e.user_id = u.id
    LEFT JOIN admins a ON a.user_id = u.id
    LEFT JOIN channel_messages rm ON rm.id = m.reply_to_id
    LEFT JOIN users ru ON ru.id = rm.sender_id
    LEFT JOIN clients rc ON rc.user_id = ru.id
    LEFT JOIN employees re ON re.user_id = ru.id
    LEFT JOIN admins ra ON ra.user_id = ru.id
"""

def _msg_query(where: str, order: str = "m.created_at DESC", limit_param: str | None = None) -> str:
    """Build a channel messages query with reply joins."""
    q = _MSG_SELECT.format(
        name_expr=_USER_NAME_EXPR,
        reply_name_expr=_USER_NAME_EXPR.replace("c.", "rc.").replace("e.", "re.").replace("a.", "ra.").replace("u.", "ru."),
    )
    q += f" WHERE {where} ORDER BY {order}"
    if limit_param:
        q += f" LIMIT {limit_param}"
    return q


class ChannelSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    visibility: str = "public"
    is_paid: bool = False
    price_cents: Optional[int] = None
    currency: Optional[str] = None
    member_count: int = 0
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    is_member: bool = True
    my_role: Optional[str] = None  # current user's channel_role (owner/moderator/member)


class ChannelDetail(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    visibility: str = "public"
    is_paid: bool = False
    price_cents: Optional[int] = None
    currency: str = "usd"
    is_archived: bool = False
    created_by: UUID
    created_at: datetime
    member_count: int = 0
    is_member: bool = False
    my_role: Optional[str] = None  # current user's channel_role
    members: list[ChannelMember] = []
    messages: list[ChannelMessage] = []


class PaidChannelConfig(BaseModel):
    price_cents: int
    currency: str = "usd"
    inactivity_threshold_days: Optional[int] = None  # 7, 14, 21, 30
    inactivity_warning_days: int = 3


class CreateChannelRequest(BaseModel):
    name: str
    description: Optional[str] = None
    visibility: str = "public"
    paid_config: Optional[PaidChannelConfig] = None


class CreateInviteRequest(BaseModel):
    max_uses: Optional[int] = None
    expires_in_hours: Optional[int] = None
    note: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if self.max_uses is not None and self.max_uses <= 0:
            raise ValueError("max_uses must be positive")
        if self.expires_in_hours is not None and self.expires_in_hours <= 0:
            raise ValueError("expires_in_hours must be positive")
        if self.note and len(self.note) > 200:
            raise ValueError("note must be 200 characters or less")


class ChannelInvite(BaseModel):
    id: UUID
    code: str
    url: str
    max_uses: Optional[int] = None
    use_count: int = 0
    expires_at: Optional[datetime] = None
    note: Optional[str] = None
    is_active: bool = True
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'channel'


async def _get_company_id(current_user: CurrentUser) -> UUID:
    scope = await resolve_accessible_company_scope(current_user)
    company_id = scope.get("company_id")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No company associated with your account")
    return company_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ChannelSummary])
async def list_channels(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all channels in the user's company. Shows membership status."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT ch.id, ch.name, ch.slug, ch.description,
                   COALESCE(ch.visibility, 'public') AS visibility,
                   COALESCE(ch.is_paid, false) AS is_paid,
                   (SELECT COUNT(*) FROM channel_members WHERE channel_id = ch.id) AS member_count,
                   CASE WHEN cm.user_id IS NOT NULL THEN
                       (SELECT COUNT(*) FROM channel_messages msg
                        WHERE msg.channel_id = ch.id
                          AND msg.sender_id != $1
                          AND (cm.last_read_at IS NULL OR msg.created_at > cm.last_read_at))
                   ELSE 0 END AS unread_count,
                   (SELECT MAX(msg2.created_at) FROM channel_messages msg2
                    WHERE msg2.channel_id = ch.id) AS last_message_at,
                   (SELECT SUBSTRING(msg3.content, 1, 100) FROM channel_messages msg3
                    WHERE msg3.channel_id = ch.id
                    ORDER BY msg3.created_at DESC LIMIT 1) AS last_message_preview,
                   cm.user_id IS NOT NULL AS is_member,
                   cm.role AS my_role
            FROM channels ch
            LEFT JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $1
            WHERE ch.is_archived = false
              AND (
                -- Channels in the user's current tenant (excluding private ones they're not in)
                (ch.company_id = $2 AND (COALESCE(ch.visibility, 'public') != 'private' OR cm.user_id IS NOT NULL))
                -- OR any channel where the user is already a member (cross-tenant memberships)
                OR cm.user_id IS NOT NULL
              )
            ORDER BY last_message_at DESC NULLS LAST, ch.created_at DESC
            """,
            current_user.id,
            company_id,
        )

        return [
            ChannelSummary(
                id=r["id"],
                name=r["name"],
                slug=r["slug"],
                description=r["description"],
                visibility=r["visibility"],
                is_paid=r["is_paid"],
                member_count=r["member_count"],
                unread_count=r["unread_count"],
                last_message_at=r["last_message_at"],
                last_message_preview=r["last_message_preview"],
                is_member=r["is_member"],
                my_role=r["my_role"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Public discovery — paid + public channels across tenants
# ---------------------------------------------------------------------------

@router.get("/discover", response_model=list[ChannelSummary])
async def discover_public_channels(
    q: str = Query(default="", max_length=100),
    paid_only: bool = Query(default=False),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Surface public channels from any tenant that the user can subscribe
    to or join. Excludes archived channels, private channels, and channels
    where the user is already a member. Personal-account creators of paid
    channels live here — without this, no one outside their own personal
    workspace could find them.
    """
    async with get_connection() as conn:
        params: list = [current_user.id]
        clauses = [
            "ch.is_archived = false",
            "COALESCE(ch.visibility, 'public') = 'public'",
            "cm.user_id IS NULL",  # not already a member
        ]
        if paid_only:
            clauses.append("ch.is_paid = true")
        if q and len(q) >= 2:
            params.append(f"%{q}%")
            search_idx = len(params)
            clauses.append(f"(ch.name ILIKE ${search_idx} OR ch.description ILIKE ${search_idx})")

        rows = await conn.fetch(
            f"""
            SELECT ch.id, ch.name, ch.slug, ch.description,
                   COALESCE(ch.visibility, 'public') AS visibility,
                   COALESCE(ch.is_paid, false) AS is_paid,
                   ch.price_cents,
                   COALESCE(ch.currency, 'usd') AS currency,
                   (SELECT COUNT(*) FROM channel_members WHERE channel_id = ch.id) AS member_count,
                   0 AS unread_count,
                   (SELECT MAX(msg2.created_at) FROM channel_messages msg2
                    WHERE msg2.channel_id = ch.id) AS last_message_at,
                   NULL::text AS last_message_preview,
                   FALSE AS is_member,
                   NULL::text AS my_role
            FROM channels ch
            LEFT JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $1
            WHERE {' AND '.join(clauses)}
            ORDER BY ch.is_paid DESC, member_count DESC, ch.created_at DESC
            LIMIT 50
            """,
            *params,
        )
        return [
            ChannelSummary(
                id=r["id"],
                name=r["name"],
                slug=r["slug"],
                description=r["description"],
                visibility=r["visibility"],
                is_paid=r["is_paid"],
                price_cents=r["price_cents"],
                currency=r["currency"],
                member_count=r["member_count"],
                unread_count=r["unread_count"],
                last_message_at=r["last_message_at"],
                last_message_preview=r["last_message_preview"],
                is_member=r["is_member"],
                my_role=r["my_role"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Member billing / subscription management
# ---------------------------------------------------------------------------


@router.get("/billing")
async def get_my_channel_billing(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all paid channel subscriptions for the current user."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT cm.channel_id, cm.subscription_status, cm.paid_through,
                   cm.last_contributed_at, cm.removed_for_inactivity,
                   cm.removal_cooldown_until,
                   ch.name AS channel_name, ch.price_cents, ch.currency,
                   ch.inactivity_threshold_days
            FROM channel_members cm
            JOIN channels ch ON ch.id = cm.channel_id
            WHERE cm.user_id = $1 AND ch.is_paid = true
            ORDER BY cm.joined_at DESC
            """,
            current_user.id,
        )

    now = datetime.now(timezone.utc)
    result = []
    for r in rows:
        days_until_removal = None
        if r["inactivity_threshold_days"] and r["last_contributed_at"]:
            deadline = r["last_contributed_at"] + timedelta(days=r["inactivity_threshold_days"])
            remaining = (deadline - now).total_seconds() / 86400
            if remaining > 0:
                days_until_removal = round(remaining, 1)

        result.append({
            "channel_id": str(r["channel_id"]),
            "channel_name": r["channel_name"],
            "price_cents": r["price_cents"],
            "currency": r["currency"],
            "subscription_status": r["subscription_status"],
            "paid_through": r["paid_through"].isoformat() if r["paid_through"] else None,
            "days_until_removal": days_until_removal,
            "removed_for_inactivity": r["removed_for_inactivity"],
            "cooldown_until": r["removal_cooldown_until"].isoformat() if r["removal_cooldown_until"] else None,
        })

    return result


@router.get("/billing/history")
async def get_my_payment_history(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get payment event history for the current user."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT cpe.event_type, cpe.amount_cents, cpe.created_at,
                   cpe.channel_id, ch.name AS channel_name
            FROM channel_payment_events cpe
            JOIN channels ch ON ch.id = cpe.channel_id
            WHERE cpe.user_id = $1
            ORDER BY cpe.created_at DESC
            LIMIT 50
            """,
            current_user.id,
        )

    return [
        {
            "event_type": r["event_type"],
            "amount_cents": r["amount_cents"],
            "created_at": r["created_at"].isoformat(),
            "channel_id": str(r["channel_id"]),
            "channel_name": r["channel_name"],
        }
        for r in rows
    ]


@router.post("", response_model=ChannelDetail, status_code=status.HTTP_201_CREATED)
async def create_channel(
    body: CreateChannelRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new channel. Only client/admin roles."""
    company_id = await _get_company_id(current_user)
    name = body.name.strip()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Channel name must be 1-100 characters")

    # Paid channels: individual (personal) accounts only. Company users —
    # even admins of their own companies — are not allowed to be paid channel
    # creators. Admin platform role can override for testing. This is a
    # permanent product rule, not a feature-flagged behavior.
    if body.paid_config and current_user.role not in ("individual", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Paid channels are only available for individual (personal) accounts. Create a personal account to become a creator.",
        )

    slug = _slugify(name)

    async with get_connection() as conn:
        # Check slug uniqueness, append suffix if needed
        base_slug = slug
        suffix = 0
        while True:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM channels WHERE company_id = $1 AND slug = $2)",
                company_id, slug,
            )
            if not exists:
                break
            suffix += 1
            slug = f"{base_slug}-{suffix}"

        visibility = body.visibility if body.visibility in ("public", "private", "invite_only") else "public"

        # Handle paid channel setup
        is_paid = False
        price_cents = None
        currency = "usd"
        inactivity_threshold_days = None
        inactivity_warning_days = 3
        stripe_product_id = None
        stripe_price_id = None

        if body.paid_config:
            from ..services.channel_payment_service import (
                create_stripe_product_and_price,
                MIN_PRICE_CENTS,
                MAX_PRICE_CENTS,
                ChannelPaymentError,
            )
            pc = body.paid_config
            if pc.price_cents < MIN_PRICE_CENTS or pc.price_cents > MAX_PRICE_CENTS:
                raise HTTPException(status_code=400, detail=f"Price must be between ${MIN_PRICE_CENTS/100:.2f} and ${MAX_PRICE_CENTS/100:.2f}")
            if pc.inactivity_threshold_days and pc.inactivity_threshold_days not in (7, 14, 21, 30):
                raise HTTPException(status_code=400, detail="Inactivity threshold must be 7, 14, 21, or 30 days")

            is_paid = True
            price_cents = pc.price_cents
            currency = pc.currency
            inactivity_threshold_days = pc.inactivity_threshold_days
            inactivity_warning_days = pc.inactivity_warning_days

        # Insert channel first, then create Stripe product with real ID
        row = await conn.fetchrow(
            """
            INSERT INTO channels (company_id, name, slug, description, created_by, visibility,
                is_paid, price_cents, currency, inactivity_threshold_days, inactivity_warning_days)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id, name, slug, description, is_archived, created_by, created_at, visibility
            """,
            company_id, name, slug, body.description, current_user.id, visibility,
            is_paid, price_cents, currency, inactivity_threshold_days, inactivity_warning_days,
        )

        if is_paid:
            try:
                stripe_product_id, stripe_price_id = await create_stripe_product_and_price(
                    channel_id=row["id"],
                    channel_name=name,
                    price_cents=price_cents,
                    currency=currency,
                )
                await conn.execute(
                    "UPDATE channels SET stripe_product_id = $2, stripe_price_id = $3 WHERE id = $1",
                    row["id"], stripe_product_id, stripe_price_id,
                )
            except ChannelPaymentError as e:
                # Rollback: delete the channel we just created
                await conn.execute("DELETE FROM channels WHERE id = $1", row["id"])
                raise HTTPException(status_code=400, detail=str(e))

        # Auto-join creator as owner (no subscription needed)
        await conn.execute(
            "INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at) VALUES ($1, $2, 'owner', NOW())",
            row["id"], current_user.id,
        )

        return ChannelDetail(
            id=row["id"],
            name=row["name"],
            slug=row["slug"],
            description=row["description"],
            visibility=row["visibility"] or "public",
            is_paid=is_paid,
            price_cents=price_cents,
            currency=currency,
            is_archived=row["is_archived"],
            created_by=row["created_by"],
            created_at=row["created_at"],
            member_count=1,
            is_member=True,
            my_role="owner",
            members=[],
            messages=[],
        )


class InvitableUser(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    avatar_url: Optional[str] = None


@router.get("/invitable-users", response_model=list[InvitableUser])
async def search_invitable_users(
    q: str = Query(default="", max_length=100),
    channel_id: Optional[UUID] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Search for users that can be invited to a channel or project.

    Company accounts: returns users in the same company.
    Personal/individual accounts: returns users from inbox conversations.
    """
    async with get_connection() as conn:
        search = f"%{q}%" if q else "%%"
        has_search = len(q) >= 2

        # Determine if this is a real company or a personal workspace
        # Personal workspaces (is_personal=true) search inbox contacts
        # Real companies search company users
        company_id = None
        is_personal = True

        if current_user.role in ("client", "individual"):
            row = await conn.fetchrow(
                """
                SELECT c.company_id, COALESCE(comp.is_personal, false) AS is_personal
                FROM clients c JOIN companies comp ON c.company_id = comp.id
                WHERE c.user_id = $1
                """,
                current_user.id,
            )
            if row:
                company_id = row["company_id"]
                is_personal = row["is_personal"]
        elif current_user.role == "employee":
            company_id = await conn.fetchval(
                "SELECT org_id FROM employees WHERE user_id = $1", current_user.id
            )
            is_personal = False
        elif current_user.role == "admin":
            scope = await resolve_accessible_company_scope(current_user)
            company_id = scope.get("company_id")
            is_personal = False

        # Build params: $1=user_id, $2=company_id (UUID or NULL), $3=search-like
        # (optional, for partial name/email match), $4=exact-email (optional,
        # only set when q looks like an email — enables cross-tenant lookup
        # by exact address so personal users can invite each other without
        # needing a prior connection).
        include_company = bool(company_id and not is_personal)
        params: list = [current_user.id, company_id if include_company else None]

        name_filter = ""
        exact_email_clause = "FALSE"
        if has_search:
            params.append(search)
            search_idx = len(params)
            name_filter = f"AND ({_USER_NAME_EXPR} ILIKE ${search_idx} OR u.email ILIKE ${search_idx})"
            if "@" in q and "." in q.split("@", 1)[1]:
                params.append(q.strip().lower())
                exact_idx = len(params)
                exact_email_clause = f"LOWER(u.email) = ${exact_idx}"

        rows = await conn.fetch(
            f"""
            SELECT DISTINCT u.id, u.email, u.role, u.avatar_url,
                   {_USER_NAME_EXPR} AS name
            FROM users u
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id != $1 AND u.is_active = true
              {name_filter}
              AND (
                -- Source 1: Same company (real companies only, skipped when $2 is NULL)
                ($2::uuid IS NOT NULL AND (c.company_id = $2::uuid OR e.org_id = $2::uuid))
                -- Source 2: Inbox contacts
                OR EXISTS(
                  SELECT 1 FROM inbox_participants ip1
                  JOIN inbox_participants ip2 ON ip2.conversation_id = ip1.conversation_id
                  WHERE ip1.user_id = $1 AND ip2.user_id = u.id
                )
                -- Source 3: Previous project collaborators
                OR EXISTS(
                  SELECT 1 FROM mw_project_collaborators pc1
                  JOIN mw_project_collaborators pc2 ON pc2.project_id = pc1.project_id
                  WHERE pc1.user_id = $1 AND pc2.user_id = u.id
                  AND pc1.status = 'active' AND pc2.status = 'active'
                )
                -- Source 4: Admins always discoverable
                OR a.user_id IS NOT NULL
                -- Source 5: Accepted connections
                OR EXISTS(
                  SELECT 1 FROM user_connections uc
                  WHERE (uc.user_id = $1 AND uc.connected_user_id = u.id AND uc.status = 'accepted')
                  OR (uc.connected_user_id = $1 AND uc.user_id = u.id AND uc.status = 'accepted')
                )
                -- Source 6: Exact email match (cross-tenant lookup so personal
                -- users can invite each other when no prior relationship exists)
                OR {exact_email_clause}
              )
            ORDER BY {_USER_NAME_EXPR}
            LIMIT 20
            """,
            *params,
        )

        return [
            InvitableUser(
                id=r["id"], name=r["name"], email=r["email"],
                role=r["role"], avatar_url=r["avatar_url"],
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# Connections (friend/follow system)
# ---------------------------------------------------------------------------


class ConnectionRequest(BaseModel):
    user_id: UUID


class ConnectionUser(BaseModel):
    user_id: UUID
    name: str
    email: str
    avatar_url: Optional[str] = None
    created_at: datetime


@router.post("/connections/request")
async def send_connection_request(
    body: ConnectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Send a connection request to another user."""
    if body.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot connect with yourself")

    async with get_connection() as conn:
        # Check target user exists
        target = await conn.fetchrow("SELECT id FROM users WHERE id = $1 AND is_active = true", body.user_id)
        if not target:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if already connected or pending
        existing = await conn.fetchrow(
            "SELECT status FROM user_connections WHERE user_id = $1 AND connected_user_id = $2",
            current_user.id, body.user_id,
        )
        if existing:
            if existing["status"] == "accepted":
                raise HTTPException(status_code=400, detail="Already connected")
            if existing["status"] == "pending":
                raise HTTPException(status_code=400, detail="Request already pending")
            if existing["status"] == "blocked":
                raise HTTPException(status_code=400, detail="Cannot send request")

        # Check if they blocked us
        blocked = await conn.fetchval(
            "SELECT 1 FROM user_connections WHERE user_id = $1 AND connected_user_id = $2 AND status = 'blocked'",
            body.user_id, current_user.id,
        )
        if blocked:
            raise HTTPException(status_code=400, detail="Cannot send request")

        # Check if they already sent us a request -- auto-accept
        incoming = await conn.fetchrow(
            "SELECT id FROM user_connections WHERE user_id = $1 AND connected_user_id = $2 AND status = 'pending'",
            body.user_id, current_user.id,
        )
        if incoming:
            await conn.execute(
                "UPDATE user_connections SET status = 'accepted' WHERE user_id = $1 AND connected_user_id = $2",
                body.user_id, current_user.id,
            )
            await conn.execute(
                """INSERT INTO user_connections (user_id, connected_user_id, status)
                   VALUES ($1, $2, 'accepted')
                   ON CONFLICT (user_id, connected_user_id) DO UPDATE SET status = 'accepted'""",
                current_user.id, body.user_id,
            )
            # Notify both
            try:
                from ...matcha.services import notification_service as notif_svc
                sender_name = await conn.fetchval(
                    f"SELECT {_USER_NAME_EXPR} FROM users u LEFT JOIN clients c ON c.user_id = u.id LEFT JOIN employees e ON e.user_id = u.id LEFT JOIN admins a ON a.user_id = u.id WHERE u.id = $1",
                    current_user.id,
                )
                company_id = await conn.fetchval(
                    "SELECT COALESCE(c.company_id, e.org_id) FROM users u LEFT JOIN clients c ON c.user_id = u.id LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = $1",
                    body.user_id,
                )
                if company_id:
                    await notif_svc.create_notification(
                        user_id=body.user_id,
                        company_id=company_id,
                        type="connection_accepted",
                        title="Connection accepted",
                        body=f"{sender_name} is now connected with you",
                        link="/work/connections",
                    )
            except Exception:
                pass
            return {"ok": True, "status": "accepted"}

        await conn.execute(
            "INSERT INTO user_connections (user_id, connected_user_id, status) VALUES ($1, $2, 'pending')",
            current_user.id, body.user_id,
        )

        # Notify target
        try:
            from ...matcha.services import notification_service as notif_svc
            sender_name = await conn.fetchval(
                f"SELECT {_USER_NAME_EXPR} FROM users u LEFT JOIN clients c ON c.user_id = u.id LEFT JOIN employees e ON e.user_id = u.id LEFT JOIN admins a ON a.user_id = u.id WHERE u.id = $1",
                current_user.id,
            )
            company_id = await conn.fetchval(
                "SELECT COALESCE(c.company_id, e.org_id) FROM users u LEFT JOIN clients c ON c.user_id = u.id LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = $1",
                body.user_id,
            )
            if company_id:
                await notif_svc.create_notification(
                    user_id=body.user_id,
                    company_id=company_id,
                    type="connection_request",
                    title="New connection request",
                    body=f"{sender_name} wants to connect with you",
                    link="/work/connections",
                )
        except Exception:
            pass

    return {"ok": True, "status": "pending"}


@router.post("/connections/accept")
async def accept_connection(
    body: ConnectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Accept a pending incoming connection request."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM user_connections WHERE user_id = $1 AND connected_user_id = $2 AND status = 'pending'",
            body.user_id, current_user.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="No pending request from this user")

        await conn.execute(
            "UPDATE user_connections SET status = 'accepted' WHERE user_id = $1 AND connected_user_id = $2",
            body.user_id, current_user.id,
        )
        await conn.execute(
            """INSERT INTO user_connections (user_id, connected_user_id, status)
               VALUES ($1, $2, 'accepted')
               ON CONFLICT (user_id, connected_user_id) DO UPDATE SET status = 'accepted'""",
            current_user.id, body.user_id,
        )

        # Notify the requester
        try:
            from ...matcha.services import notification_service as notif_svc
            accepter_name = await conn.fetchval(
                f"SELECT {_USER_NAME_EXPR} FROM users u LEFT JOIN clients c ON c.user_id = u.id LEFT JOIN employees e ON e.user_id = u.id LEFT JOIN admins a ON a.user_id = u.id WHERE u.id = $1",
                current_user.id,
            )
            company_id = await conn.fetchval(
                "SELECT COALESCE(c.company_id, e.org_id) FROM users u LEFT JOIN clients c ON c.user_id = u.id LEFT JOIN employees e ON e.user_id = u.id WHERE u.id = $1",
                body.user_id,
            )
            if company_id:
                await notif_svc.create_notification(
                    user_id=body.user_id,
                    company_id=company_id,
                    type="connection_accepted",
                    title="Connection accepted",
                    body=f"{accepter_name} accepted your connection request",
                    link="/work/connections",
                )
        except Exception:
            pass

    return {"ok": True}


@router.post("/connections/decline")
async def decline_connection(
    body: ConnectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Decline or remove a connection."""
    async with get_connection() as conn:
        await conn.execute(
            "DELETE FROM user_connections WHERE (user_id = $1 AND connected_user_id = $2) OR (user_id = $2 AND connected_user_id = $1)",
            body.user_id, current_user.id,
        )
    return {"ok": True}


@router.get("/connections", response_model=list[ConnectionUser])
async def list_connections(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all accepted connections for the current user."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT u.id AS user_id, u.email, u.avatar_url, uc.created_at,
                   {_USER_NAME_EXPR} AS name
            FROM user_connections uc
            JOIN users u ON u.id = uc.connected_user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE uc.user_id = $1 AND uc.status = 'accepted'
            ORDER BY {_USER_NAME_EXPR}
            """,
            current_user.id,
        )
        return [ConnectionUser(user_id=r["user_id"], name=r["name"], email=r["email"], avatar_url=r["avatar_url"], created_at=r["created_at"]) for r in rows]


@router.get("/connections/pending", response_model=list[ConnectionUser])
async def list_pending_connections(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List pending incoming connection requests."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT u.id AS user_id, u.email, u.avatar_url, uc.created_at,
                   {_USER_NAME_EXPR} AS name
            FROM user_connections uc
            JOIN users u ON u.id = uc.user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE uc.connected_user_id = $1 AND uc.status = 'pending'
            ORDER BY uc.created_at DESC
            """,
            current_user.id,
        )
        return [ConnectionUser(user_id=r["user_id"], name=r["name"], email=r["email"], avatar_url=r["avatar_url"], created_at=r["created_at"]) for r in rows]


@router.get("/connections/sent", response_model=list[ConnectionUser])
async def list_sent_connections(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List pending outgoing connection requests sent by the current user."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT u.id AS user_id, u.email, u.avatar_url, uc.created_at,
                   {_USER_NAME_EXPR} AS name
            FROM user_connections uc
            JOIN users u ON u.id = uc.connected_user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE uc.user_id = $1 AND uc.status = 'pending'
            ORDER BY uc.created_at DESC
            """,
            current_user.id,
        )
        return [ConnectionUser(user_id=r["user_id"], name=r["name"], email=r["email"], avatar_url=r["avatar_url"], created_at=r["created_at"]) for r in rows]


@router.post("/connections/block")
async def block_connection(
    body: ConnectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Block a user. Removes any existing connection."""
    async with get_connection() as conn:
        # Remove any existing connection in both directions
        await conn.execute(
            "DELETE FROM user_connections WHERE (user_id = $1 AND connected_user_id = $2) OR (user_id = $2 AND connected_user_id = $1)",
            current_user.id, body.user_id,
        )
        # Insert block row
        await conn.execute(
            """INSERT INTO user_connections (user_id, connected_user_id, status)
               VALUES ($1, $2, 'blocked')
               ON CONFLICT (user_id, connected_user_id) DO UPDATE SET status = 'blocked'""",
            current_user.id, body.user_id,
        )
    return {"ok": True}


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get channel detail with members and recent messages."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        ch = await conn.fetchrow(
            "SELECT id, name, slug, description, is_archived, created_by, created_at, company_id, COALESCE(visibility, 'public') AS visibility, COALESCE(is_paid, false) AS is_paid, price_cents, COALESCE(currency, 'usd') AS currency FROM channels WHERE id = $1",
            channel_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Check membership + get role
        my_membership = await conn.fetchrow(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        is_member = my_membership is not None
        my_role = my_membership["role"] if my_membership else None

        # Access control: must either be in the channel's tenant, be a member,
        # or be a platform admin. Otherwise 404 (don't reveal existence).
        if (
            not is_member
            and ch["company_id"] != company_id
            and current_user.role != "admin"
        ):
            raise HTTPException(status_code=404, detail="Channel not found")

        # Private channels in your own tenant are still gated to members
        if (
            ch["visibility"] == "private"
            and not is_member
            and current_user.role != "admin"
        ):
            raise HTTPException(status_code=404, detail="Channel not found")

        # Members
        members = await conn.fetch(
            f"""
            SELECT cm.user_id, cm.joined_at, cm.role AS channel_role, u.email, u.role, u.avatar_url,
                   {_USER_NAME_EXPR} AS name
            FROM channel_members cm
            JOIN users u ON u.id = cm.user_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE cm.channel_id = $1
            ORDER BY cm.joined_at
            """,
            channel_id,
        )

        # Recent messages (with reply joins)
        messages = await conn.fetch(
            _msg_query("m.channel_id = $1", limit_param="50"),
            channel_id,
        )
        msg_ids = [m["id"] for m in messages]
        reactions_map = await _fetch_reactions_map(conn, msg_ids)

        # Mark as read (only if member)
        if is_member:
            await conn.execute(
                "UPDATE channel_members SET last_read_at = NOW() WHERE channel_id = $1 AND user_id = $2",
                channel_id, current_user.id,
            )

        return ChannelDetail(
            id=ch["id"],
            name=ch["name"],
            slug=ch["slug"],
            description=ch["description"],
            visibility=ch["visibility"],
            is_paid=ch["is_paid"],
            price_cents=ch["price_cents"],
            currency=ch["currency"],
            is_archived=ch["is_archived"],
            created_by=ch["created_by"],
            created_at=ch["created_at"],
            member_count=len(members),
            is_member=is_member,
            my_role=my_role,
            members=[
                ChannelMember(
                    user_id=m["user_id"], name=m["name"], email=m["email"],
                    role=m["role"], channel_role=m["channel_role"] or "member",
                    avatar_url=m["avatar_url"], joined_at=m["joined_at"],
                )
                for m in members
            ],
            messages=[
                _row_to_message(m, reactions_map)
                for m in reversed(messages)  # Return chronological order
            ],
        )


@router.get("/{channel_id}/messages", response_model=list[ChannelMessage])
async def get_channel_messages(
    channel_id: UUID,
    before: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get paginated message history for a channel."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        # Verify channel + membership (allows cross-tenant memberships)
        is_member = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM channel_members cm
                WHERE cm.channel_id = $1 AND cm.user_id = $2
            )
            """,
            channel_id, current_user.id,
        )
        if not is_member and current_user.role != "admin":
            raise HTTPException(status_code=404, detail="Channel not found or not a member")

        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid 'before' cursor format")
            rows = await conn.fetch(
                _msg_query("m.channel_id = $1 AND m.created_at < $2", limit_param="$3"),
                channel_id, before_dt, limit,
            )
        else:
            rows = await conn.fetch(
                _msg_query("m.channel_id = $1", limit_param="$2"),
                channel_id, limit,
            )

        msg_ids = [r["id"] for r in rows]
        reactions_map = await _fetch_reactions_map(conn, msg_ids)
        return [_row_to_message(r, reactions_map) for r in reversed(rows)]


@router.delete("/{channel_id}/messages/{message_id}", status_code=status.HTTP_200_OK)
async def delete_channel_message(
    channel_id: UUID,
    message_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a channel message. Allowed for the message author, the
    channel owner, or any channel moderator. Deleted messages remain in
    the DB with deleted_at/deleted_by set so we can audit and render a
    tombstone on the client.
    """
    async with get_connection() as conn:
        msg = await conn.fetchrow(
            "SELECT id, sender_id, deleted_at FROM channel_messages WHERE id = $1 AND channel_id = $2",
            message_id, channel_id,
        )
        if not msg:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg["deleted_at"] is not None:
            return {"ok": True, "already_deleted": True}

        member_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        is_author = msg["sender_id"] == current_user.id
        is_mod = member_role in ("owner", "moderator")
        if not is_author and not is_mod:
            raise HTTPException(status_code=403, detail="You can only delete your own messages")

        await conn.execute(
            """
            UPDATE channel_messages
            SET deleted_at = NOW(),
                deleted_by = $2
            WHERE id = $1
            """,
            message_id, current_user.id,
        )

    # Fan out deletion over the channel WebSocket so every connected
    # member updates their view without needing to refetch.
    try:
        from .channels_ws import broadcast_message_deleted
        await broadcast_message_deleted(
            channel_id=str(channel_id),
            message_id=str(message_id),
            deleted_by=str(current_user.id),
        )
    except Exception as exc:
        logger.warning("Failed to broadcast channel message deletion: %s", exc)

    return {"ok": True, "deleted_by": str(current_user.id)}


class ReactionToggleRequest(BaseModel):
    emoji: str


@router.post("/{channel_id}/messages/{message_id}/react")
async def toggle_reaction(
    channel_id: UUID,
    message_id: UUID,
    body: ReactionToggleRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Toggle a reaction on a message. If the user already reacted with the
    same emoji, remove it; otherwise add it."""
    emoji = body.emoji.strip()
    if not emoji or len(emoji) > 10:
        raise HTTPException(status_code=400, detail="Invalid emoji")

    async with get_connection() as conn:
        # Verify membership
        is_member = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2)",
            channel_id, current_user.id,
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member")

        # Verify message exists in this channel
        msg_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM channel_messages WHERE id = $1 AND channel_id = $2)",
            message_id, channel_id,
        )
        if not msg_exists:
            raise HTTPException(status_code=404, detail="Message not found")

        # Toggle: try insert, if conflict delete
        existing = await conn.fetchval(
            "SELECT id FROM channel_reactions WHERE message_id = $1 AND user_id = $2 AND emoji = $3",
            message_id, current_user.id, emoji,
        )
        if existing:
            await conn.execute("DELETE FROM channel_reactions WHERE id = $1", existing)
            action = "removed"
        else:
            await conn.execute(
                "INSERT INTO channel_reactions (message_id, user_id, emoji) VALUES ($1, $2, $3)",
                message_id, current_user.id, emoji,
            )
            action = "added"

        # Fetch updated reactions for this message
        reaction_rows = await conn.fetch(
            "SELECT emoji, user_id FROM channel_reactions WHERE message_id = $1 ORDER BY created_at",
            message_id,
        )

    # Build reaction list
    from collections import defaultdict
    grouped: dict[str, list[UUID]] = defaultdict(list)
    for r in reaction_rows:
        grouped[r["emoji"]].append(r["user_id"])
    reactions = [
        ChannelReaction(emoji=e, user_ids=uids, count=len(uids))
        for e, uids in grouped.items()
    ]

    # Broadcast via WS
    try:
        from .channels_ws import broadcast_reaction_update
        await broadcast_reaction_update(
            channel_id=str(channel_id),
            message_id=str(message_id),
            reactions=[r.model_dump(mode="json") for r in reactions],
        )
    except Exception as exc:
        logger.warning("Failed to broadcast reaction update: %s", exc)

    return {"action": action, "reactions": reactions}


@router.post("/{channel_id}/join", status_code=status.HTTP_200_OK)
async def join_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Join a channel in the user's company."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        ch = await conn.fetchrow(
            "SELECT id, COALESCE(visibility, 'public') AS visibility, is_paid FROM channels WHERE id = $1 AND company_id = $2 AND is_archived = false",
            channel_id, company_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        if ch["visibility"] in ("private", "invite_only"):
            raise HTTPException(status_code=403, detail="This channel requires an invitation to join")

        # Paid channels require checkout flow, not direct join
        if ch["is_paid"]:
            raise HTTPException(
                status_code=400,
                detail="This is a paid channel. Use the checkout endpoint to subscribe and join.",
            )

        # Check cooldown for previously removed members
        existing = await conn.fetchrow(
            "SELECT removal_cooldown_until FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if existing and existing["removal_cooldown_until"]:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            if existing["removal_cooldown_until"] > now:
                raise HTTPException(
                    status_code=403,
                    detail=f"You cannot rejoin until {existing['removal_cooldown_until'].strftime('%b %d, %Y')}",
                )

        await conn.execute(
            """
            INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at)
            VALUES ($1, $2, 'member', NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                removed_for_inactivity = false,
                removal_cooldown_until = NULL,
                last_contributed_at = NOW()
            """,
            channel_id, current_user.id,
        )

    return {"ok": True}


class AddMembersRequest(BaseModel):
    user_ids: list[UUID]


@router.post("/{channel_id}/members", status_code=status.HTTP_200_OK)
async def add_members(
    channel_id: UUID,
    body: AddMembersRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Add members to a channel. Only owner, moderator, or platform admin can invite."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        # Verify channel exists + requester has permission
        member_row = await conn.fetchrow(
            """
            SELECT cm.role FROM channels ch
            JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $2
            WHERE ch.id = $1 AND ch.company_id = $3
            """,
            channel_id, current_user.id, company_id,
        )
        if not member_row and current_user.role != "admin":
            raise HTTPException(status_code=404, detail="Channel not found or not a member")

        my_role = member_row["role"] if member_row else None
        if current_user.role != "admin" and my_role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can add members")

        # Allow adding any user the inviter is connected to: same company,
        # accepted connection, shared inbox conversation, or project collaborator.
        # This matches the eligibility logic in /channels/invitable-users.
        added_uids = []
        rejected_uids = []
        for uid in body.user_ids:
            eligible = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    LEFT JOIN admins a ON a.user_id = u.id
                    WHERE u.id = $1 AND u.is_active = true
                      AND (
                        -- Source 1: same company
                        ($2::uuid IS NOT NULL AND (c.company_id = $2::uuid OR e.org_id = $2::uuid))
                        -- Source 2: shared inbox conversation
                        OR EXISTS(
                          SELECT 1 FROM inbox_participants ip1
                          JOIN inbox_participants ip2 ON ip2.conversation_id = ip1.conversation_id
                          WHERE ip1.user_id = $3 AND ip2.user_id = u.id
                        )
                        -- Source 3: shared project collaborator
                        OR EXISTS(
                          SELECT 1 FROM mw_project_collaborators pc1
                          JOIN mw_project_collaborators pc2 ON pc2.project_id = pc1.project_id
                          WHERE pc1.user_id = $3 AND pc2.user_id = u.id
                            AND pc1.status = 'active' AND pc2.status = 'active'
                        )
                        -- Source 4: admin user
                        OR a.user_id IS NOT NULL
                        -- Source 5: accepted connection
                        OR EXISTS(
                          SELECT 1 FROM user_connections uc
                          WHERE uc.status = 'accepted'
                            AND ((uc.user_id = $3 AND uc.connected_user_id = u.id)
                              OR (uc.connected_user_id = $3 AND uc.user_id = u.id))
                        )
                      )
                )
                """,
                uid, company_id, current_user.id,
            )
            if not eligible:
                rejected_uids.append(uid)
                continue

            await conn.execute(
                """
                INSERT INTO channel_members (channel_id, user_id, role)
                VALUES ($1, $2, 'member')
                ON CONFLICT (channel_id, user_id) DO NOTHING
                """,
                channel_id, uid,
            )
            added_uids.append(uid)

        # Notify users who were actually added. Use the RECIPIENT's company_id
        # (not the inviter's) so the notification is visible in their tenant.
        channel_name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", channel_id)
        for uid in added_uids:
            if uid == current_user.id:
                continue
            try:
                recipient_company_id = await conn.fetchval(
                    """
                    SELECT COALESCE(c.company_id, e.org_id)
                    FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    WHERE u.id = $1
                    """,
                    uid,
                )
                from ...matcha.services import notification_service as notif_svc
                await notif_svc.create_notification(
                    user_id=uid,
                    company_id=recipient_company_id,
                    type="channel_added",
                    title=f"Added to #{channel_name or 'channel'}",
                    body=f"You've been added to the channel #{channel_name}",
                    link=f"/work/channels/{channel_id}",
                )
            except Exception:
                logger.warning("Failed to send channel_added notification to %s", uid, exc_info=True)

    return {
        "ok": True,
        "added": [str(u) for u in added_uids],
        "rejected": [str(u) for u in rejected_uids],
    }


class UpdateChannelRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visibility: Optional[str] = None


@router.patch("/{channel_id}", response_model=ChannelSummary)
async def update_channel(
    channel_id: UUID,
    body: UpdateChannelRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a channel. Owner/moderator can change name/description. Only owner can change visibility."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT company_id FROM channels WHERE id = $1", channel_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Channel not found")

        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        is_admin = current_user.role == "admin"
        if not is_admin and my_role not in ("owner", "moderator"):
            raise HTTPException(status_code=403, detail="Only channel owners and moderators can update this channel")

        # Only owner can change visibility
        if body.visibility is not None and my_role != "owner" and not is_admin:
            raise HTTPException(status_code=403, detail="Only the channel owner can change visibility")

        sets = []
        params: list = []
        idx = 1

        if body.name is not None:
            name = body.name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="Channel name cannot be empty")
            slug = _slugify(name)
            sets.append(f"name = ${idx}")
            params.append(name)
            idx += 1
            sets.append(f"slug = ${idx}")
            params.append(slug)
            idx += 1

        if body.description is not None:
            sets.append(f"description = ${idx}")
            params.append(body.description.strip() or None)
            idx += 1

        if body.visibility is not None:
            if body.visibility not in ("public", "private", "invite_only"):
                raise HTTPException(status_code=400, detail="Visibility must be public, private, or invite_only")
            sets.append(f"visibility = ${idx}")
            params.append(body.visibility)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No updates provided")

        params.append(channel_id)
        await conn.execute(
            f"UPDATE channels SET {', '.join(sets)} WHERE id = ${idx}",
            *params,
        )

        # Return updated channel summary
        ch = await conn.fetchrow(
            """
            SELECT c.id, c.name, c.slug, c.description,
                   (SELECT COUNT(*) FROM channel_members WHERE channel_id = c.id) AS member_count,
                   0 AS unread_count,
                   NULL::timestamptz AS last_message_at,
                   NULL AS last_message_preview,
                   TRUE AS is_member
            FROM channels c WHERE c.id = $1
            """,
            channel_id,
        )
        return dict(ch)


@router.post("/{channel_id}/leave", status_code=status.HTTP_200_OK)
async def leave_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Leave a channel. Owners must transfer ownership first."""
    async with get_connection() as conn:
        member = await conn.fetchrow(
            "SELECT role, stripe_subscription_id FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if member and member["role"] == "owner":
            raise HTTPException(status_code=400, detail="Channel owners must transfer ownership before leaving")

        # Cancel Stripe subscription if active. We Stripe-cancel first so a
        # success here means the user really stops getting charged. If Stripe
        # is down or returns an error we still let the leave proceed (the
        # alternative is trapping the user in a channel they want out of) but
        # we log loudly and audit-log so ops can reconcile orphaned subs.
        if member and member["stripe_subscription_id"]:
            try:
                from ..services.channel_payment_service import cancel_subscription
                await cancel_subscription(member["stripe_subscription_id"])
            except Exception as exc:
                logger.warning(
                    "Stripe cancel failed during leave (channel=%s user=%s sub=%s): %s",
                    channel_id, current_user.id, member["stripe_subscription_id"], exc,
                )
                try:
                    import json as _json
                    await conn.execute(
                        """
                        INSERT INTO channel_payment_events (channel_id, user_id, event_type, metadata)
                        VALUES ($1, $2, 'leave_cancel_failed', $3::jsonb)
                        """,
                        channel_id, current_user.id,
                        _json.dumps({
                            "stripe_subscription_id": member["stripe_subscription_id"],
                            "error": str(exc)[:500],
                        }),
                    )
                except Exception:
                    pass  # event-log failure shouldn't block the leave either

        await conn.execute(
            "DELETE FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )

    return {"ok": True}


# ---------------------------------------------------------------------------
# Member management (kick, role change, ownership transfer)
# ---------------------------------------------------------------------------


class SetRoleRequest(BaseModel):
    role: str  # "moderator" or "member"


class TransferOwnershipRequest(BaseModel):
    user_id: UUID


@router.patch("/{channel_id}/members/{user_id}")
async def set_member_role(
    channel_id: UUID,
    user_id: UUID,
    body: SetRoleRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Change a member's channel role. Only the owner can promote/demote."""
    if body.role not in ("moderator", "member"):
        raise HTTPException(status_code=400, detail="Role must be 'moderator' or 'member'")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the channel owner can change roles")

        target = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, user_id,
        )
        if not target:
            raise HTTPException(status_code=404, detail="User is not a member of this channel")
        if target == "owner":
            raise HTTPException(status_code=400, detail="Cannot change the owner's role. Use transfer-ownership instead.")

        await conn.execute(
            "UPDATE channel_members SET role = $3 WHERE channel_id = $1 AND user_id = $2",
            channel_id, user_id, body.role,
        )

    return {"ok": True, "role": body.role}


@router.delete("/{channel_id}/members/{user_id}")
async def kick_member(
    channel_id: UUID,
    user_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Remove a member from a channel. Owner can kick anyone, moderator can kick members."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot kick yourself. Use /leave instead.")

    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role not in ("owner", "moderator") and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only owners and moderators can remove members")

        target_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, user_id,
        )
        if not target_role:
            raise HTTPException(status_code=404, detail="User is not a member")
        if target_role == "owner":
            raise HTTPException(status_code=403, detail="Cannot kick the channel owner")
        if target_role == "moderator" and my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the owner can remove moderators")

        await conn.execute(
            "DELETE FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, user_id,
        )

        # Send notification
        try:
            company_id = await _get_company_id(current_user)
            channel_name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", channel_id)
            from ...matcha.services import notification_service as notif_svc
            await notif_svc.create_notification(
                user_id=user_id,
                company_id=company_id,
                type="channel_removed",
                title=f"Removed from #{channel_name}",
                body=f"You were removed from the channel #{channel_name}",
                link="/work",
            )
        except Exception:
            pass

    return {"ok": True}


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Soft-delete a channel (mark archived). Owner or admin only. Cancels any active paid subscriptions."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT name, is_archived, is_paid FROM channels WHERE id = $1",
            channel_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Channel not found")
        if row["is_archived"]:
            return {"ok": True, "already_archived": True}

        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the channel owner can delete this channel")

        channel_name = row["name"]
        is_paid = bool(row["is_paid"])

        member_ids = [r["user_id"] for r in await conn.fetch(
            "SELECT user_id FROM channel_members WHERE channel_id = $1",
            channel_id,
        )]

        active_subs = []
        if is_paid:
            active_subs = [r["stripe_subscription_id"] for r in await conn.fetch(
                """
                SELECT stripe_subscription_id FROM channel_members
                WHERE channel_id = $1
                  AND stripe_subscription_id IS NOT NULL
                  AND subscription_status IN ('active', 'trialing', 'past_due')
                """,
                channel_id,
            )]

    if active_subs:
        from ..services.channel_payment_service import cancel_subscription, ChannelPaymentError
        for sub_id in active_subs:
            try:
                await cancel_subscription(sub_id)
            except ChannelPaymentError:
                pass

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE channels SET is_archived = true, updated_at = NOW() WHERE id = $1",
            channel_id,
        )
        if active_subs:
            await conn.execute(
                """
                UPDATE channel_members SET subscription_status = 'canceled'
                WHERE channel_id = $1 AND stripe_subscription_id IS NOT NULL
                """,
                channel_id,
            )

    try:
        company_id = await _get_company_id(current_user)
        from ...matcha.services import notification_service as notif_svc
        for uid in member_ids:
            if uid == current_user.id:
                continue
            await notif_svc.create_notification(
                user_id=uid,
                company_id=company_id,
                type="channel_deleted",
                title=f"#{channel_name} was deleted",
                body=f"The channel #{channel_name} was deleted by the owner",
                link="/work",
            )
    except Exception:
        pass

    return {"ok": True}


@router.post("/{channel_id}/transfer-ownership")
async def transfer_ownership(
    channel_id: UUID,
    body: TransferOwnershipRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Transfer channel ownership to another member."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the current owner can transfer ownership")

        target = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, body.user_id,
        )
        if not target:
            raise HTTPException(status_code=404, detail="Target user is not a member of this channel")

        # Transfer: old owner → moderator, new owner → owner
        await conn.execute(
            "UPDATE channel_members SET role = 'moderator' WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        await conn.execute(
            "UPDATE channel_members SET role = 'owner' WHERE channel_id = $1 AND user_id = $2",
            channel_id, body.user_id,
        )
        # Update channels.created_by for consistency
        await conn.execute(
            "UPDATE channels SET created_by = $2 WHERE id = $1",
            channel_id, body.user_id,
        )

    return {"ok": True}


# ---------------------------------------------------------------------------
# File uploads for channel messages
# ---------------------------------------------------------------------------

_MAX_CHANNEL_FILE_COUNT = 5
_MAX_CHANNEL_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_ALLOWED_CHANNEL_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif",
    ".pdf", ".txt", ".csv", ".doc", ".docx", ".mp4", ".mov", ".mp3",
}


@router.post("/{channel_id}/upload")
async def upload_channel_files(
    channel_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload files for a channel message. Returns attachment metadata to include with the message."""
    if len(files) > _MAX_CHANNEL_FILE_COUNT:
        raise HTTPException(status_code=400, detail=f"Maximum {_MAX_CHANNEL_FILE_COUNT} files per message")

    async with get_connection() as conn:
        is_member = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2)",
            channel_id, current_user.id,
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="Not a member of this channel")
        # Track file upload as contribution activity
        await conn.execute(
            "UPDATE channel_members SET last_contributed_at = NOW() WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )

    storage = get_storage()
    attachments = []

    for f in files:
        file_bytes = await f.read()
        filename = f.filename or "upload"
        ct = f.content_type or "application/octet-stream"
        ext = os.path.splitext(filename)[1].lower()
        size = len(file_bytes)

        if ext not in _ALLOWED_CHANNEL_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"File type not allowed: {filename}")
        if size > _MAX_CHANNEL_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"File too large: {filename}")

        url = await storage.upload_file(file_bytes, filename, prefix=f"channels/{channel_id}", content_type=ct)
        attachments.append({
            "url": url,
            "filename": filename,
            "content_type": ct,
            "size": size,
        })

    return {"attachments": attachments}


# ---------------------------------------------------------------------------
# Paid channel endpoints
# ---------------------------------------------------------------------------


@router.get("/{channel_id}/payment-info")
async def get_channel_payment_info(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get payment info for a channel from the current user's perspective."""
    from ..services.channel_payment_service import get_payment_info
    return await get_payment_info(channel_id, current_user.id)


@router.post("/{channel_id}/checkout")
async def create_channel_checkout(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a Stripe checkout session for subscribing to a paid channel."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        ch = await conn.fetchrow(
            "SELECT id, name, is_paid, stripe_price_id, created_by FROM channels WHERE id = $1 AND company_id = $2",
            channel_id, company_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")
        if not ch["is_paid"]:
            raise HTTPException(status_code=400, detail="This channel is free to join")
        if not ch["stripe_price_id"]:
            raise HTTPException(status_code=500, detail="Channel payment not configured")

        # Block owner from subscribing to own channel
        if ch["created_by"] == current_user.id:
            raise HTTPException(status_code=400, detail="Channel owners cannot subscribe to their own channel")

        # Check cooldown
        from ..services.channel_payment_service import check_rejoin_eligibility
        eligibility = await check_rejoin_eligibility(channel_id, current_user.id)
        if not eligibility["can_rejoin"]:
            raise HTTPException(
                status_code=403,
                detail=f"You cannot rejoin until {eligibility['cooldown_until']}",
            )

        # Check if already subscribed. `canceling` means the user clicked
        # cancel but Stripe will still charge until `paid_through` — they
        # already have access. Letting a new checkout through here would
        # create a second Stripe subscription and double-charge them; the
        # activation handler would overwrite stripe_subscription_id and
        # orphan the old sub. Block both states until the period ends.
        existing = await conn.fetchrow(
            "SELECT subscription_status, paid_through FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if existing:
            existing_status = existing["subscription_status"]
            paid_through = existing["paid_through"]
            now = datetime.now(timezone.utc)
            if existing_status == "active":
                raise HTTPException(status_code=400, detail="You already have an active subscription")
            if existing_status == "canceling" and paid_through and paid_through > now:
                raise HTTPException(
                    status_code=400,
                    detail=f"Your subscription is canceling and remains active until {paid_through.strftime('%b %d, %Y')}. You can re-subscribe after that date.",
                )

    from ..services.channel_payment_service import create_checkout_session, ChannelPaymentError
    try:
        url = await create_checkout_session(
            channel_id=channel_id,
            channel_name=ch["name"],
            stripe_price_id=ch["stripe_price_id"],
            user_id=current_user.id,
        )
    except ChannelPaymentError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"checkout_url": url}


@router.post("/{channel_id}/cancel-subscription")
async def cancel_channel_subscription(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel the current user's subscription to a paid channel."""
    async with get_connection() as conn:
        member = await conn.fetchrow(
            "SELECT stripe_subscription_id, subscription_status FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if not member or not member["stripe_subscription_id"]:
            raise HTTPException(status_code=400, detail="No active subscription found")
        if member["subscription_status"] != "active":
            raise HTTPException(status_code=400, detail="Subscription is not active")

    from ..services.channel_payment_service import cancel_subscription, ChannelPaymentError
    try:
        paid_through = await cancel_subscription(member["stripe_subscription_id"])
    except ChannelPaymentError as e:
        raise HTTPException(status_code=500, detail=str(e))

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE channel_members SET subscription_status = 'canceling', paid_through = $3 WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id, paid_through,
        )

    return {"ok": True, "paid_through": paid_through.isoformat()}


class UpdateChannelPriceRequest(BaseModel):
    price_cents: int


@router.patch("/{channel_id}/price")
async def update_channel_price_route(
    channel_id: UUID,
    body: UpdateChannelPriceRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update the monthly subscription price for a paid channel. Owner only.
    Existing subscribers continue paying their original price — Stripe binds
    that amount to each subscription. Only new subscribers get the new price.
    """
    async with get_connection() as conn:
        ch = await conn.fetchrow(
            """
            SELECT is_paid, stripe_product_id, stripe_price_id, currency,
                   created_by, price_cents
            FROM channels
            WHERE id = $1
            """,
            channel_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")
        if not ch["is_paid"]:
            raise HTTPException(status_code=400, detail="This channel is free; no price to update")
        if not ch["stripe_product_id"]:
            raise HTTPException(status_code=500, detail="Channel has no Stripe product configured")

        # Owner-only (or admin)
        if ch["created_by"] != current_user.id and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the channel owner can change the price")

        if body.price_cents == ch["price_cents"]:
            return {"ok": True, "price_cents": body.price_cents, "unchanged": True}

    from ..services.channel_payment_service import update_channel_price, ChannelPaymentError
    try:
        new_price_id = await update_channel_price(
            stripe_product_id=ch["stripe_product_id"],
            new_price_cents=body.price_cents,
            old_price_id=ch["stripe_price_id"],
            currency=ch["currency"] or "usd",
        )
    except ChannelPaymentError as e:
        raise HTTPException(status_code=500, detail=str(e))

    async with get_connection() as conn:
        await conn.execute(
            "UPDATE channels SET stripe_price_id = $2, price_cents = $3, updated_at = NOW() WHERE id = $1",
            channel_id, new_price_id, body.price_cents,
        )

    return {"ok": True, "price_cents": body.price_cents, "stripe_price_id": new_price_id}


class UpdatePaidSettingsRequest(BaseModel):
    inactivity_threshold_days: Optional[int] = None
    inactivity_warning_days: Optional[int] = None


@router.patch("/{channel_id}/paid-settings")
async def update_paid_settings(
    channel_id: UUID,
    body: UpdatePaidSettingsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update inactivity settings for a paid channel. Owner only."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the channel owner can update paid settings")

        sets = []
        params: list = []
        idx = 1

        if body.inactivity_threshold_days is not None:
            if body.inactivity_threshold_days not in (0, 7, 14, 21, 30):
                raise HTTPException(status_code=400, detail="Threshold must be 0 (disabled), 7, 14, 21, or 30")
            val = body.inactivity_threshold_days if body.inactivity_threshold_days > 0 else None
            sets.append(f"inactivity_threshold_days = ${idx}")
            params.append(val)
            idx += 1

        if body.inactivity_warning_days is not None:
            if body.inactivity_warning_days not in (1, 2, 3, 5, 7):
                raise HTTPException(status_code=400, detail="Warning period must be 1, 2, 3, 5, or 7 days")
            sets.append(f"inactivity_warning_days = ${idx}")
            params.append(body.inactivity_warning_days)
            idx += 1

        if not sets:
            raise HTTPException(status_code=400, detail="No updates provided")

        params.append(channel_id)
        await conn.execute(
            f"UPDATE channels SET {', '.join(sets)} WHERE id = ${idx}",
            *params,
        )

    return {"ok": True}


@router.get("/{channel_id}/member-activity")
async def get_member_activity(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get member activity data for a paid channel. Owner/moderator only."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role not in ("owner", "moderator") and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only owners and moderators can view member activity")

    from ..services.channel_payment_service import get_member_activity as _get_activity
    return await _get_activity(channel_id)


@router.get("/{channel_id}/revenue")
async def get_channel_revenue(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get revenue summary for a paid channel. Owner only."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the channel owner can view revenue")

        ch = await conn.fetchrow(
            "SELECT price_cents, currency FROM channels WHERE id = $1",
            channel_id,
        )

        subscriber_count = await conn.fetchval(
            "SELECT COUNT(*) FROM channel_members WHERE channel_id = $1 AND subscription_status = 'active'",
            channel_id,
        )

        total_revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(amount_cents), 0) FROM channel_payment_events WHERE channel_id = $1 AND event_type = 'payment_success'",
            channel_id,
        )

        recent_events = await conn.fetch(
            """
            SELECT event_type, amount_cents, created_at, user_id
            FROM channel_payment_events
            WHERE channel_id = $1
            ORDER BY created_at DESC
            LIMIT 20
            """,
            channel_id,
        )

    mrr = (ch["price_cents"] or 0) * subscriber_count

    return {
        "subscriber_count": subscriber_count,
        "mrr_cents": mrr,
        "total_revenue_cents": total_revenue,
        "currency": ch["currency"],
        "recent_events": [
            {
                "event_type": e["event_type"],
                "amount_cents": e["amount_cents"],
                "created_at": e["created_at"].isoformat(),
                "user_id": str(e["user_id"]),
            }
            for e in recent_events
        ],
    }


@router.get("/{channel_id}/analytics")
async def get_channel_analytics(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Comprehensive analytics dashboard for paid channel owners."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role != "owner" and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only the channel owner can view analytics")

        ch = await conn.fetchrow(
            "SELECT price_cents, currency, inactivity_threshold_days FROM channels WHERE id = $1",
            channel_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        # ── Subscribers ──
        sub_counts = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE subscription_status = 'active') AS active,
                COUNT(*) FILTER (WHERE subscription_status = 'past_due') AS past_due,
                COUNT(*) FILTER (WHERE subscription_status = 'canceled' OR removed_for_inactivity = true) AS canceled
            FROM channel_members
            WHERE channel_id = $1
            """,
            channel_id,
        )

        # ── Revenue ──
        revenue_row = await conn.fetchrow(
            """
            SELECT
                COALESCE(SUM(amount_cents) FILTER (WHERE event_type = 'payment_success'), 0) AS total_subscription_cents,
                COALESCE(SUM(amount_cents) FILTER (WHERE event_type = 'tip_received'), 0) AS total_tips_cents
            FROM channel_payment_events
            WHERE channel_id = $1
            """,
            channel_id,
        )
        active_subs = sub_counts["active"]
        mrr_cents = (ch["price_cents"] or 0) * active_subs
        total_sub = revenue_row["total_subscription_cents"]
        total_tips = revenue_row["total_tips_cents"]

        # ── Activity (messages) ──
        now = datetime.now(timezone.utc)
        activity_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE created_at >= $2) AS messages_today,
                COUNT(*) FILTER (WHERE created_at >= $3) AS messages_this_week,
                COUNT(*) FILTER (WHERE created_at >= $4) AS messages_this_month
            FROM channel_messages
            WHERE channel_id = $1
            """,
            channel_id,
            now - timedelta(days=1),
            now - timedelta(weeks=1),
            now - timedelta(days=30),
        )

        # Top 5 most active members (last 30 days)
        most_active_rows = await conn.fetch(
            f"""
            SELECT m.sender_id AS user_id,
                   {_USER_NAME_EXPR} AS name,
                   COUNT(*) AS message_count,
                   MAX(m.created_at) AS last_active
            FROM channel_messages m
            JOIN users u ON u.id = m.sender_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE m.channel_id = $1 AND m.created_at >= $2
            GROUP BY m.sender_id, c.name, e.first_name, e.last_name, a.name, u.email
            ORDER BY message_count DESC
            LIMIT 5
            """,
            channel_id, now - timedelta(days=30),
        )

        # ── Engagement ──
        avg_row = await conn.fetchval(
            """
            SELECT COUNT(*)::float / GREATEST(1, 30)
            FROM channel_messages
            WHERE channel_id = $1 AND created_at >= $2
            """,
            channel_id, now - timedelta(days=30),
        )

        threshold_days = ch["inactivity_threshold_days"]
        members_at_risk = 0
        if threshold_days:
            # Members whose last activity is past 50% of the threshold
            risk_cutoff = now - timedelta(days=threshold_days * 0.5)
            members_at_risk = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM channel_members
                WHERE channel_id = $1
                  AND subscription_status = 'active'
                  AND removed_for_inactivity = false
                  AND last_contributed_at IS NOT NULL
                  AND last_contributed_at < $2
                """,
                channel_id, risk_cutoff,
            )

        recent_removals = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM channel_members
            WHERE channel_id = $1
              AND removed_for_inactivity = true
              AND inactivity_warned_at >= $2
            """,
            channel_id, now - timedelta(days=30),
        )

        # ── Tips ──
        tips_row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(amount_cents), 0) AS total_cents, COUNT(*) AS tip_count
            FROM channel_payment_events
            WHERE channel_id = $1 AND event_type = 'tip_received'
            """,
            channel_id,
        )

        recent_tips = await conn.fetch(
            f"""
            SELECT pe.amount_cents, pe.created_at,
                   pe.metadata->>'message' AS message,
                   {_USER_NAME_EXPR} AS sender_name
            FROM channel_payment_events pe
            JOIN users u ON u.id = (pe.metadata->>'sender_id')::uuid
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE pe.channel_id = $1 AND pe.event_type = 'tip_received'
            ORDER BY pe.created_at DESC
            LIMIT 5
            """,
            channel_id,
        )

    return {
        "subscribers": {
            "total": sub_counts["total"],
            "active": sub_counts["active"],
            "past_due": sub_counts["past_due"],
            "canceled": sub_counts["canceled"],
        },
        "revenue": {
            "mrr_cents": mrr_cents,
            "total_subscription_cents": total_sub,
            "total_tips_cents": total_tips,
            "total_cents": total_sub + total_tips,
        },
        "activity": {
            "messages_today": activity_row["messages_today"],
            "messages_this_week": activity_row["messages_this_week"],
            "messages_this_month": activity_row["messages_this_month"],
            "most_active_members": [
                {
                    "user_id": str(r["user_id"]),
                    "name": r["name"],
                    "message_count": r["message_count"],
                    "last_active": r["last_active"].isoformat(),
                }
                for r in most_active_rows
            ],
        },
        "engagement": {
            "avg_messages_per_day": round(avg_row or 0, 1),
            "members_at_risk": members_at_risk,
            "recent_removals": recent_removals or 0,
        },
        "tips": {
            "total_cents": tips_row["total_cents"],
            "tip_count": tips_row["tip_count"],
            "recent": [
                {
                    "sender_name": r["sender_name"],
                    "amount_cents": r["amount_cents"],
                    "message": r["message"] or "",
                    "created_at": r["created_at"].isoformat(),
                }
                for r in recent_tips
            ],
        },
    }


# ---------------------------------------------------------------------------
# Channel invite links
# ---------------------------------------------------------------------------

def _invite_to_dict(row, base_url: str) -> dict:
    return ChannelInvite(
        id=row["id"],
        code=row["code"],
        url=f"{base_url}/work/channels/join/{row['code']}",
        max_uses=row["max_uses"],
        use_count=row["use_count"],
        expires_at=row["expires_at"],
        note=row["note"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    ).model_dump(mode="json")


@router.post("/{channel_id}/invites", status_code=status.HTTP_201_CREATED)
async def create_invite(
    channel_id: UUID,
    body: CreateInviteRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create an invite link for a channel. Owner/moderator only."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        # Verify channel belongs to user's company
        ch_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM channels WHERE id = $1 AND company_id = $2)",
            channel_id, company_id,
        )
        if not ch_exists:
            raise HTTPException(status_code=404, detail="Channel not found")

        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role not in ("owner", "moderator") and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only owners and moderators can create invite links")

        expires_at = None
        if body.expires_in_hours:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=body.expires_in_hours)

        # Generate code with collision retry
        row = None
        for _ in range(3):
            code = secrets.token_urlsafe(12)
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO channel_invites (channel_id, code, created_by, max_uses, expires_at, note)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id, channel_id, code, max_uses, use_count, expires_at, note, is_active, created_at
                    """,
                    channel_id, code, current_user.id, body.max_uses, expires_at, body.note,
                )
                break
            except Exception as e:
                if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                    continue
                raise
        if not row:
            raise HTTPException(status_code=500, detail="Failed to generate unique invite code")

    from ...config import get_settings
    settings = get_settings()
    return _invite_to_dict(row, settings.app_base_url)


@router.get("/{channel_id}/invites", response_model=list[ChannelInvite])
async def list_invites(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List active invite links for a channel. Owner/moderator only."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role not in ("owner", "moderator") and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only owners and moderators can view invite links")

        rows = await conn.fetch(
            """
            SELECT id, channel_id, code, max_uses, use_count, expires_at, note, is_active, created_at
            FROM channel_invites
            WHERE channel_id = $1 AND is_active = true
            ORDER BY created_at DESC
            """,
            channel_id,
        )

    from ...config import get_settings
    settings = get_settings()
    return [_invite_to_dict(r, settings.app_base_url) for r in rows]


@router.delete("/{channel_id}/invites/{invite_id}", status_code=status.HTTP_200_OK)
async def revoke_invite(
    channel_id: UUID,
    invite_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke an invite link. Owner/moderator only."""
    async with get_connection() as conn:
        my_role = await conn.fetchval(
            "SELECT role FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if my_role not in ("owner", "moderator") and current_user.role != "admin":
            raise HTTPException(status_code=403, detail="Only owners and moderators can revoke invite links")

        result = await conn.execute(
            "UPDATE channel_invites SET is_active = false WHERE id = $1 AND channel_id = $2",
            invite_id, channel_id,
        )
        if result == "UPDATE 0":
            raise HTTPException(status_code=404, detail="Invite not found")

    return {"ok": True}


@router.post("/join-by-invite/{code}")
async def join_by_invite(
    code: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Join a channel via an invite link. Works for invite_only and paid channels."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        # Look up invite (basic existence check, no use_count validation yet)
        invite = await conn.fetchrow(
            """
            SELECT ci.id, ci.channel_id, ci.is_active, ci.expires_at
            FROM channel_invites ci WHERE ci.code = $1
            """,
            code,
        )
        if not invite:
            raise HTTPException(status_code=404, detail="Invalid invite link")
        if not invite["is_active"]:
            raise HTTPException(status_code=410, detail="This invite link has been revoked")
        if invite["expires_at"] and invite["expires_at"] < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="This invite link has expired")

        channel_id = invite["channel_id"]

        # Verify channel belongs to user's company
        ch = await conn.fetchrow(
            "SELECT id, is_paid, stripe_price_id, name, created_by FROM channels WHERE id = $1 AND company_id = $2 AND is_archived = false",
            channel_id, company_id,
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found in your company")

        # Check if already an active member — don't consume an invite use
        existing = await conn.fetchrow(
            "SELECT removal_cooldown_until, subscription_status, removed_for_inactivity, paid_through FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if existing and not existing["removed_for_inactivity"] and existing.get("subscription_status") in ("active", None):
            # Already a member, just redirect
            return {"ok": True, "channel_id": str(channel_id)}

        # Check cooldown
        if existing and existing["removal_cooldown_until"]:
            now = datetime.now(timezone.utc)
            if existing["removal_cooldown_until"] > now:
                raise HTTPException(
                    status_code=403,
                    detail=f"You cannot rejoin until {existing['removal_cooldown_until'].strftime('%b %d, %Y')}",
                )

        # Paid channel → atomically claim the invite use first, then
        # redirect to checkout. Pre-claim is required because letting two
        # users start checkout on the last available seat would let both
        # of them pay and join (the activation handler can't reject the
        # second payer cleanly — they've already been charged). Burning
        # an invite use on an abandoned checkout is the lesser cost.
        if ch["is_paid"]:
            if ch["created_by"] == current_user.id:
                raise HTTPException(status_code=400, detail="Channel owners cannot subscribe to their own channel")
            if existing and existing.get("subscription_status") == "active":
                raise HTTPException(status_code=400, detail="You already have an active subscription")
            if existing and existing.get("subscription_status") == "canceling" \
                    and existing.get("paid_through") and existing["paid_through"] > datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=400,
                    detail=f"Your subscription is canceling and remains active until {existing['paid_through'].strftime('%b %d, %Y')}. You can re-subscribe after that date.",
                )

            # Atomic claim — same pattern as the free-channel branch below.
            claimed = await conn.fetchrow(
                """
                UPDATE channel_invites SET use_count = use_count + 1
                WHERE code = $1 AND is_active = true
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND (max_uses IS NULL OR use_count < max_uses)
                RETURNING id
                """,
                code,
            )
            if not claimed:
                raise HTTPException(status_code=410, detail="This invite link has expired or reached its maximum uses")

            from ..services.channel_payment_service import create_checkout_session, ChannelPaymentError
            try:
                url = await create_checkout_session(
                    channel_id=channel_id,
                    channel_name=ch["name"],
                    stripe_price_id=ch["stripe_price_id"],
                    user_id=current_user.id,
                    invite_code=code,  # Tracked in metadata for analytics; no longer increments use_count
                )
            except ChannelPaymentError as e:
                raise HTTPException(status_code=500, detail=str(e))

            return {"requires_payment": True, "channel_id": str(channel_id), "checkout_url": url}

        # Free channel → atomic use_count increment (race-safe)
        claimed = await conn.fetchrow(
            """
            UPDATE channel_invites SET use_count = use_count + 1
            WHERE code = $1 AND is_active = true
              AND (expires_at IS NULL OR expires_at > NOW())
              AND (max_uses IS NULL OR use_count < max_uses)
            RETURNING id
            """,
            code,
        )
        if not claimed:
            raise HTTPException(status_code=410, detail="This invite link has expired or reached its maximum uses")

        # Join the channel
        await conn.execute(
            """
            INSERT INTO channel_members (channel_id, user_id, role, last_contributed_at)
            VALUES ($1, $2, 'member', NOW())
            ON CONFLICT (channel_id, user_id) DO UPDATE SET
                removed_for_inactivity = false,
                removal_cooldown_until = NULL,
                last_contributed_at = NOW()
            """,
            channel_id, current_user.id,
        )

    return {"ok": True, "channel_id": str(channel_id)}


# ---------------------------------------------------------------------------
# Tipping
# ---------------------------------------------------------------------------

class SendTipRequest(BaseModel):
    amount_cents: int  # minimum 100 ($1.00), maximum 50000 ($500.00)
    message: Optional[str] = None  # optional thank-you message, max 200 chars


@router.post("/{channel_id}/tip")
async def send_tip(
    channel_id: UUID,
    body: SendTipRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a Stripe checkout session to tip the channel creator."""
    if body.amount_cents < 100 or body.amount_cents > 50000:
        raise HTTPException(status_code=400, detail="Tip must be between $1.00 and $500.00")
    if body.message and len(body.message) > 200:
        raise HTTPException(status_code=400, detail="Message must be 200 characters or fewer")

    async with get_connection() as conn:
        # Verify membership
        is_member = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM channel_members WHERE channel_id = $1 AND user_id = $2)",
            channel_id, current_user.id,
        )
        if not is_member:
            raise HTTPException(status_code=403, detail="You must be a member of this channel")

        # Get channel info
        ch = await conn.fetchrow(
            "SELECT name, created_by FROM channels WHERE id = $1", channel_id
        )
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        creator_id = ch["created_by"]
        if creator_id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot tip yourself")

    from ..services.channel_payment_service import create_tip_checkout, ChannelPaymentError
    try:
        url = await create_tip_checkout(
            channel_id=channel_id,
            channel_name=ch["name"],
            sender_id=current_user.id,
            creator_id=creator_id,
            amount_cents=body.amount_cents,
            message=body.message,
        )
    except ChannelPaymentError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"checkout_url": url}
