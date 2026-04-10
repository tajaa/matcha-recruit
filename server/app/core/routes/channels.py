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


class ChannelMessage(BaseModel):
    id: UUID
    channel_id: UUID
    sender_id: UUID
    sender_name: str
    content: str
    attachments: list[ChannelAttachment] = []
    created_at: datetime
    edited_at: Optional[datetime] = None


class ChannelSummary(BaseModel):
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    visibility: str = "public"
    is_paid: bool = False
    member_count: int = 0
    unread_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    is_member: bool = True


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
                   cm.user_id IS NOT NULL AS is_member
            FROM channels ch
            LEFT JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $1
            WHERE ch.company_id = $2 AND ch.is_archived = false
              AND (COALESCE(ch.visibility, 'public') != 'private' OR cm.user_id IS NOT NULL)
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

        name_filter_2 = f"""AND (
                    c.name ILIKE $2
                    OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $2
                    OR a.name ILIKE $2
                    OR u.email ILIKE $2
                  )""" if has_search else ""
        name_filter_3 = f"""AND (
                    c.name ILIKE $3
                    OR CONCAT(e.first_name, ' ', e.last_name) ILIKE $3
                    OR a.name ILIKE $3
                    OR u.email ILIKE $3
                  )""" if has_search else ""

        if company_id and not is_personal:
            rows = await conn.fetch(
                f"""
                SELECT u.id, u.email, u.role, u.avatar_url,
                       {_USER_NAME_EXPR} AS name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id != $1 AND u.is_active = true
                  AND (c.company_id = $2 OR e.org_id = $2)
                  {name_filter_3}
                ORDER BY {_USER_NAME_EXPR}
                LIMIT 20
                """,
                current_user.id, company_id, *([search] if has_search else []),
            )
        else:
            # Personal account: show inbox contacts
            rows = await conn.fetch(
                f"""
                SELECT DISTINCT u.id, u.email, u.role, u.avatar_url,
                       {_USER_NAME_EXPR} AS name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                JOIN inbox_participants ip ON ip.user_id = u.id
                JOIN inbox_participants my ON my.conversation_id = ip.conversation_id AND my.user_id = $1
                WHERE u.id != $1 AND u.is_active = true
                  {name_filter_2}
                ORDER BY {_USER_NAME_EXPR}
                LIMIT 20
                """,
                current_user.id, *([search] if has_search else []),
            )

        return [
            InvitableUser(
                id=r["id"], name=r["name"], email=r["email"],
                role=r["role"], avatar_url=r["avatar_url"],
            )
            for r in rows
        ]


@router.get("/{channel_id}", response_model=ChannelDetail)
async def get_channel(
    channel_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get channel detail with members and recent messages."""
    company_id = await _get_company_id(current_user)

    async with get_connection() as conn:
        ch = await conn.fetchrow(
            "SELECT id, name, slug, description, is_archived, created_by, created_at, COALESCE(visibility, 'public') AS visibility, COALESCE(is_paid, false) AS is_paid, price_cents, COALESCE(currency, 'usd') AS currency FROM channels WHERE id = $1 AND company_id = $2",
            channel_id, company_id,
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

        # Recent messages
        messages = await conn.fetch(
            f"""
            SELECT m.id, m.channel_id, m.sender_id, m.content, m.attachments, m.created_at, m.edited_at,
                   {_USER_NAME_EXPR} AS sender_name
            FROM channel_messages m
            JOIN users u ON u.id = m.sender_id
            LEFT JOIN clients c ON c.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE m.channel_id = $1
            ORDER BY m.created_at DESC
            LIMIT 50
            """,
            channel_id,
        )

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
                ChannelMessage(
                    id=m["id"], channel_id=m["channel_id"], sender_id=m["sender_id"],
                    sender_name=m["sender_name"], content=m["content"],
                    attachments=json.loads(m["attachments"]) if isinstance(m["attachments"], str) else (m["attachments"] or []),
                    created_at=m["created_at"], edited_at=m["edited_at"],
                )
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
        # Verify channel + membership
        is_member = await conn.fetchval(
            """
            SELECT EXISTS(
                SELECT 1 FROM channels ch
                JOIN channel_members cm ON cm.channel_id = ch.id AND cm.user_id = $2
                WHERE ch.id = $1 AND ch.company_id = $3
            )
            """,
            channel_id, current_user.id, company_id,
        )
        if not is_member:
            raise HTTPException(status_code=404, detail="Channel not found or not a member")

        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid 'before' cursor format")
            rows = await conn.fetch(
                f"""
                SELECT m.id, m.channel_id, m.sender_id, m.content, m.attachments, m.created_at, m.edited_at,
                       {_USER_NAME_EXPR} AS sender_name
                FROM channel_messages m
                JOIN users u ON u.id = m.sender_id
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE m.channel_id = $1 AND m.created_at < $2
                ORDER BY m.created_at DESC
                LIMIT $3
                """,
                channel_id, before_dt, limit,
            )
        else:
            rows = await conn.fetch(
                f"""
                SELECT m.id, m.channel_id, m.sender_id, m.content, m.attachments, m.created_at, m.edited_at,
                       {_USER_NAME_EXPR} AS sender_name
                FROM channel_messages m
                JOIN users u ON u.id = m.sender_id
                LEFT JOIN clients c ON c.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE m.channel_id = $1
                ORDER BY m.created_at DESC
                LIMIT $2
                """,
                channel_id, limit,
            )

        return [
            ChannelMessage(
                id=r["id"], channel_id=r["channel_id"], sender_id=r["sender_id"],
                sender_name=r["sender_name"], content=r["content"],
                attachments=json.loads(r["attachments"]) if isinstance(r["attachments"], str) else (r["attachments"] or []),
                created_at=r["created_at"], edited_at=r["edited_at"],
            )
            for r in reversed(rows)
        ]


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

        # Verify all user_ids belong to the same company
        for uid in body.user_ids:
            in_company = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM users u
                    LEFT JOIN clients c ON c.user_id = u.id
                    LEFT JOIN employees e ON e.user_id = u.id
                    WHERE u.id = $1 AND u.is_active = true
                      AND (c.company_id = $2 OR e.org_id = $2)
                )
                """,
                uid, company_id,
            )
            if not in_company:
                continue  # silently skip users not in the company

            await conn.execute(
                """
                INSERT INTO channel_members (channel_id, user_id, role)
                VALUES ($1, $2, 'member')
                ON CONFLICT (channel_id, user_id) DO NOTHING
                """,
                channel_id, uid,
            )

        # Notify added members
        channel_name = await conn.fetchval("SELECT name FROM channels WHERE id = $1", channel_id)
        for uid in body.user_ids:
            if uid == current_user.id:
                continue
            try:
                from ...matcha.services import notification_service as notif_svc
                await notif_svc.create_notification(
                    user_id=uid,
                    company_id=company_id,
                    type="channel_added",
                    title=f"Added to #{channel_name or 'channel'}",
                    body=f"You've been added to the channel #{channel_name}",
                    link=f"/work/channels/{channel_id}",
                )
            except Exception:
                pass

    return {"ok": True}


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

        # Cancel Stripe subscription if active
        if member and member["stripe_subscription_id"]:
            try:
                from ..services.channel_payment_service import cancel_subscription
                await cancel_subscription(member["stripe_subscription_id"])
            except Exception:
                pass  # Still allow leaving even if Stripe call fails

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

        # Check if already subscribed
        existing_sub = await conn.fetchval(
            "SELECT subscription_status FROM channel_members WHERE channel_id = $1 AND user_id = $2",
            channel_id, current_user.id,
        )
        if existing_sub == "active":
            raise HTTPException(status_code=400, detail="You already have an active subscription")

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
            "SELECT removal_cooldown_until, subscription_status, removed_for_inactivity FROM channel_members WHERE channel_id = $1 AND user_id = $2",
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

        # Paid channel → redirect to checkout (DON'T consume invite use yet)
        if ch["is_paid"]:
            if ch["created_by"] == current_user.id:
                raise HTTPException(status_code=400, detail="Channel owners cannot subscribe to their own channel")
            if existing and existing.get("subscription_status") == "active":
                raise HTTPException(status_code=400, detail="You already have an active subscription")

            from ..services.channel_payment_service import create_checkout_session, ChannelPaymentError
            try:
                url = await create_checkout_session(
                    channel_id=channel_id,
                    channel_name=ch["name"],
                    stripe_price_id=ch["stripe_price_id"],
                    user_id=current_user.id,
                    invite_code=code,  # Pass invite code for deferred use_count increment
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
