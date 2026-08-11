"""Brand membership and store authorization primitives."""
from dataclasses import dataclass
from typing import Mapping, Sequence
from uuid import UUID

from fastapi import HTTPException, status

from ..models.access import (
    BrandCapability,
    BrandRole,
    TellusBusinessMembership,
    TellusBusinessStoreGrant,
)
from ..models.tellus import TellusAccount


ALL_CAPABILITIES: frozenset[BrandCapability] = frozenset(
    {
        "brand.update",
        "billing.manage",
        "team.manage",
        "stores.manage",
        "board.manage",
        "feedback.read",
        "feedback.manage",
        "comms.read",
        "comms.reply",
        "comms.assign",
        "comms.settings",
        "promos.manage",
        "scanners.manage",
        "rewards.manage",
        "redemptions.redeem",
    }
)

ROLE_CAPABILITIES: dict[BrandRole, frozenset[BrandCapability]] = {
    "owner": ALL_CAPABILITIES,
    "admin": ALL_CAPABILITIES,
    "location_manager": frozenset(
        {
            "feedback.read",
            "feedback.manage",
            "comms.read",
            "comms.reply",
            "comms.assign",
            "promos.manage",
            "scanners.manage",
            "rewards.manage",
            "redemptions.redeem",
        }
    ),
    "staff": frozenset(
        {
            "feedback.read",
            "comms.read",
            "comms.reply",
            "redemptions.redeem",
        }
    ),
}


@dataclass(frozen=True)
class BrandAccessContext:
    account: TellusAccount
    brand_id: UUID
    membership_id: UUID
    role: BrandRole
    plan_status: str
    all_stores: bool
    store_ids: frozenset[UUID]
    capabilities: frozenset[BrandCapability]


@dataclass(frozen=True)
class StoreAccessContext:
    brand: BrandAccessContext
    store_id: UUID
    store_name: str


def default_capabilities(role: BrandRole) -> frozenset[BrandCapability]:
    return ROLE_CAPABILITIES[role]


def apply_capability_overrides(
    defaults: frozenset[BrandCapability],
    overrides: Sequence[Mapping[str, str]],
) -> frozenset[BrandCapability]:
    """Apply normalized grant/deny rows without mutating the role defaults."""
    capabilities = set(defaults)
    for override in overrides:
        capability = override.get("capability")
        if capability not in ALL_CAPABILITIES:
            continue
        if override.get("effect") == "grant":
            capabilities.add(capability)
        elif override.get("effect") == "deny":
            capabilities.discard(capability)
    return frozenset(capabilities)


def assert_capability(context: BrandAccessContext, capability: BrandCapability) -> None:
    if capability not in context.capabilities:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission for this business action.",
        )


def assert_paid_brand(context: BrandAccessContext) -> None:
    if context.plan_status != "active":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="This business does not have an active subscription.",
        )


async def resolve_brand_access(
    conn,
    account_id: UUID,
    brand_id: UUID,
) -> BrandAccessContext:
    context = await find_brand_access(conn, account_id, brand_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return context


async def find_brand_access(
    conn,
    account_id: UUID,
    brand_id: UUID,
) -> BrandAccessContext | None:
    """Resolve active membership access without raising for a missing member."""
    row = await conn.fetchrow(
        """SELECT m.id AS membership_id, m.role, m.status, m.all_stores,
                  b.id AS brand_id, b.plan_status
             FROM tellus_brand_members m
             JOIN tellus_brands b ON b.id = m.brand_id
            WHERE m.account_id = $1 AND m.brand_id = $2""",
        account_id,
        brand_id,
    )
    if row is None or row["status"] != "active":
        return None

    role = row["role"]
    if role not in ROLE_CAPABILITIES:
        return None

    store_rows = await conn.fetch(
        """SELECT s.id
             FROM tellus_stores s
            WHERE s.brand_id = $1
              AND ($2::boolean OR EXISTS (
                    SELECT 1
                      FROM tellus_brand_member_stores ms
                     WHERE ms.member_id = $3 AND ms.store_id = s.id
                  ))""",
        brand_id,
        row["all_stores"],
        row["membership_id"],
    )
    overrides = await conn.fetch(
        """SELECT capability, effect
             FROM tellus_brand_member_capabilities
            WHERE member_id = $1""",
        row["membership_id"],
    )
    capabilities = apply_capability_overrides(
        default_capabilities(role),
        overrides,
    )
    return BrandAccessContext(
        account=TellusAccount(id=account_id, email="", status="active"),
        brand_id=row["brand_id"],
        membership_id=row["membership_id"],
        role=role,
        plan_status=row["plan_status"],
        all_stores=bool(row["all_stores"]),
        store_ids=frozenset(store["id"] for store in store_rows),
        capabilities=capabilities,
    )


async def resolve_store_access(
    conn,
    brand: BrandAccessContext,
    store_id: UUID,
) -> StoreAccessContext:
    if not brand.all_stores and store_id not in brand.store_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    row = await conn.fetchrow(
        """SELECT id, name
             FROM tellus_stores
            WHERE id = $1 AND brand_id = $2""",
        store_id,
        brand.brand_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return StoreAccessContext(brand=brand, store_id=row["id"], store_name=row["name"])


async def list_business_memberships(conn, account_id: UUID) -> list[TellusBusinessMembership]:
    """Materialize all non-revoked business memberships for /me/businesses."""
    memberships = await conn.fetch(
        """SELECT m.id, m.brand_id, m.role, m.status, m.all_stores,
                  b.name AS brand_name, b.slug AS brand_slug, b.plan_status
             FROM tellus_brand_members m
             JOIN tellus_brands b ON b.id = m.brand_id
            WHERE m.account_id = $1 AND m.status <> 'revoked'
            ORDER BY b.name""",
        account_id,
    )
    if not memberships:
        return []

    member_ids = [row["id"] for row in memberships]
    stores = await conn.fetch(
        """SELECT m.id AS member_id, s.id, s.name, s.city, s.state,
                         'active'::text AS status
             FROM tellus_brand_members m
            JOIN tellus_stores s ON s.brand_id = m.brand_id
            WHERE m.id = ANY($1::uuid[])
              AND (m.all_stores OR EXISTS (
                    SELECT 1 FROM tellus_brand_member_stores ms
                     WHERE ms.member_id = m.id AND ms.store_id = s.id
                  ))""",
        member_ids,
    )
    overrides = await conn.fetch(
        """SELECT member_id, capability, effect
             FROM tellus_brand_member_capabilities
            WHERE member_id = ANY($1::uuid[])""",
        member_ids,
    )
    stores_by_member: dict[UUID, list[TellusBusinessStoreGrant]] = {member_id: [] for member_id in member_ids}
    for store in stores:
        stores_by_member[store["member_id"]].append(
            TellusBusinessStoreGrant(
                id=store["id"],
                name=store["name"],
                city=store["city"],
                state=store["state"],
                status=store["status"],
            )
        )
    overrides_by_member: dict[UUID, list[Mapping[str, str]]] = {member_id: [] for member_id in member_ids}
    for override in overrides:
        overrides_by_member[override["member_id"]].append(dict(override))

    result: list[TellusBusinessMembership] = []
    for row in memberships:
        role = row["role"]
        capabilities = apply_capability_overrides(
            default_capabilities(role),
            overrides_by_member[row["id"]],
        )
        if row["status"] != "active":
            capabilities = frozenset()
        result.append(
            TellusBusinessMembership(
                id=row["id"],
                brand_id=row["brand_id"],
                brand_name=row["brand_name"],
                brand_slug=row["brand_slug"],
                plan_status=row["plan_status"],
                role=role,
                status=row["status"],
                all_stores=bool(row["all_stores"]),
                stores=stores_by_member[row["id"]],
                capabilities=set(capabilities),
            )
        )
    return result
