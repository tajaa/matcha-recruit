"""Cappe ↔ matcha feature bridge (parallel entitlement).

Lets a Cappe (gummfit) account use selected matcha features WITHOUT merging
the two identity models. Follows the broker precedent (`brokers.plan` +
`require_broker_pro`): the entitlement lives on `cappe_accounts.matcha_features`
and is enforced by a cappe-native gate — matcha's `require_feature` /
`enabled_features` chain is never involved in authorization.

The one place the firewall bends is the DATA layer: matcha tables (`ir_*`)
hard-FK into `companies` / `users` and sit under RLS keyed on company_id. So
each cappe account that enables a matcha feature gets a **backing tenant**:

- one `companies` row  (signup_source='cappe', owner_id NULL — owner_id NULL
  keeps it out of the admin companies roster, which filters on
  `owner_id IS NOT NULL`)
- one `users` row      (role='client', bridge email on a reserved .invalid
  domain, random discarded password — it can never log in)
- one `clients` row    linking the two, so matcha's
  `resolve_accessible_company_scope` resolves it like any client and sets the
  RLS tenant.

These rows are plumbing, not identity: auth stays scope=cappe end to end, and
matcha's `get_current_user` keeps rejecting cappe tokens (the bridge user's
id is only ever minted server-side into a `CurrentUser` by
`require_matcha_feature` after the cappe token + entitlement checks pass).

Adding a bridgeable feature = extend `MATCHA_BRIDGEABLE_FEATURES` + write an
adapter router under `app/cappe/routes/` that wraps the matcha handlers with
`require_matcha_feature("<flag>")` (see `routes/ir.py` for the template).
"""
import json
import logging
import secrets
from uuid import UUID

from fastapi import Depends, HTTPException, status

from ...core.models.auth import CurrentUser
from ...core.services.auth import hash_password
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount

logger = logging.getLogger(__name__)

# Matcha flags a cappe account is allowed to hold. Deliberately a whitelist —
# most matcha features assume an employee roster / handbook profile / broker
# graph that cappe accounts don't have. Widen this only together with an
# adapter router that actually serves the feature under /api/cappe.
MATCHA_BRIDGEABLE_FEATURES = frozenset({"incidents"})

CAPPE_COMPANY_SIGNUP_SOURCE = "cappe"


def bridge_email(account_id: UUID | str) -> str:
    """Synthetic, undeliverable email for the backing users row.

    `.invalid` is RFC 2606 reserved, so the email guard in
    `core/services/email.py` hard-blocks any accidental send, and the address
    can never collide with the cappe account's real email in `users`.
    """
    return f"cappe+{account_id}@bridge.matcha.invalid"


async def ensure_backing_tenant(conn, account_id: UUID, account_name: str | None) -> tuple[UUID, UUID]:
    """Idempotently create the backing companies/users/clients rows.

    Returns (company_id, user_id). Safe to call repeatedly; reuses rows already
    stamped on the cappe account.
    """
    row = await conn.fetchrow(
        "SELECT matcha_company_id, matcha_user_id FROM cappe_accounts WHERE id = $1",
        account_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    if row["matcha_company_id"] and row["matcha_user_id"]:
        return row["matcha_company_id"], row["matcha_user_id"]

    display_name = (account_name or "").strip() or f"Cappe account {str(account_id)[:8]}"

    async with conn.transaction():
        company_id = row["matcha_company_id"]
        if company_id is None:
            company_id = await conn.fetchval(
                """
                INSERT INTO companies (name, status, signup_source, enabled_features)
                VALUES ($1, 'approved', $2, '{}'::jsonb)
                RETURNING id
                """,
                display_name,
                CAPPE_COMPANY_SIGNUP_SOURCE,
            )

        user_id = row["matcha_user_id"]
        if user_id is None:
            # Random password, hashed then discarded — the row exists purely to
            # satisfy users(id) FKs (created_by / audit actors) and the clients
            # membership join. Nobody can ever authenticate as it.
            throwaway = secrets.token_urlsafe(48)
            user_id = await conn.fetchval(
                """
                INSERT INTO users (email, password_hash, role, is_active)
                VALUES ($1, $2, 'client', true)
                ON CONFLICT (email) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                bridge_email(account_id),
                hash_password(throwaway),
            )
            await conn.execute(
                """
                INSERT INTO clients (user_id, company_id, name)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id) DO NOTHING
                """,
                user_id,
                company_id,
                display_name,
            )

        await conn.execute(
            "UPDATE cappe_accounts SET matcha_company_id = $2, matcha_user_id = $3 WHERE id = $1",
            account_id,
            company_id,
            user_id,
        )

    logger.info(
        "cappe matcha-bridge: backing tenant ready account=%s company=%s user=%s",
        account_id, company_id, user_id,
    )
    return company_id, user_id


async def set_matcha_features(conn, account_id: UUID, features: dict[str, bool]) -> dict[str, bool]:
    """Replace the account's bridged matcha flags (admin-toggled, like matcha's
    admin feature toggles). Creates the backing tenant on first enable and
    mirrors the granted flags onto the backing company's `enabled_features` so
    matcha-side consumers of that column (workers, shared services) see a
    consistent tenant.
    """
    unknown = set(features) - MATCHA_BRIDGEABLE_FEATURES
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Not bridgeable to cappe accounts: {', '.join(sorted(unknown))}",
        )
    granted = {k: bool(v) for k, v in features.items()}

    row = await conn.fetchrow(
        "SELECT name, matcha_company_id FROM cappe_accounts WHERE id = $1", account_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")

    company_id = row["matcha_company_id"]
    if any(granted.values()) and company_id is None:
        company_id, _ = await ensure_backing_tenant(conn, account_id, row["name"])

    await conn.execute(
        "UPDATE cappe_accounts SET matcha_features = $2::jsonb WHERE id = $1",
        account_id,
        json.dumps(granted),
    )
    if company_id is not None:
        await conn.execute(
            "UPDATE companies SET enabled_features = $2::jsonb WHERE id = $1",
            company_id,
            json.dumps(granted),
        )
    return granted


class CappeBridgeContext:
    """What `require_matcha_feature` yields to adapter routes: the cappe
    account plus a server-minted matcha `CurrentUser` for the backing tenant.
    """

    __slots__ = ("account", "matcha_user", "company_id")

    def __init__(self, account: CappeAccount, matcha_user: CurrentUser, company_id: UUID):
        self.account = account
        self.matcha_user = matcha_user
        self.company_id = company_id


def require_matcha_feature(flag: str):
    """Cappe-native gate for a bridged matcha feature.

    cappe bearer token → account → `matcha_features[flag]` → backing tenant →
    bridged CurrentUser (role='client'). 403 with an upgrade-style message when
    the flag is off — mirrors matcha's require_feature UX so the frontend can
    upsell instead of erroring.
    """
    if flag not in MATCHA_BRIDGEABLE_FEATURES:  # fail fast at import time
        raise ValueError(f"{flag!r} is not a cappe-bridgeable matcha feature")

    async def checker(account: CappeAccount = Depends(require_cappe_account)) -> CappeBridgeContext:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT matcha_features, matcha_company_id, matcha_user_id "
                "FROM cappe_accounts WHERE id = $1",
                account.id,
            )
        features = row["matcha_features"] if row else None
        if isinstance(features, str):
            features = json.loads(features or "{}")
        if not row or not (features or {}).get(flag):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"The '{flag}' feature is not enabled for this account. "
                "Contact support to add it to your plan.",
            )
        if not row["matcha_company_id"] or not row["matcha_user_id"]:
            # Flag on but tenant missing — shouldn't happen (set_matcha_features
            # creates it), but self-heal rather than 500.
            async with get_connection() as conn:
                company_id, user_id = await ensure_backing_tenant(conn, account.id, account.name)
        else:
            company_id, user_id = row["matcha_company_id"], row["matcha_user_id"]

        matcha_user = CurrentUser(id=user_id, email=account.email, role="client")
        return CappeBridgeContext(account=account, matcha_user=matcha_user, company_id=company_id)

    return checker
