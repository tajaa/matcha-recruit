"""auth/register_business.py (split of the pre-2026-07-25 auth.py monolith)."""


import asyncio
import json
import logging
import re
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Depends, Request, UploadFile, File, status
from pydantic import BaseModel, EmailStr, Field

from app.database import get_connection
from uuid import UUID

from app.core.models.auth import (
    LoginRequest, TokenResponse, RefreshTokenRequest, UserResponse,
    AdminRegister, ClientRegister, CandidateRegister, EmployeeRegister,
    BusinessRegister, TestAccountRegister, TestAccountProvisionResponse,
    AdminProfile, ClientProfile, CandidateProfile, EmployeeProfile,
    BrokerTermsAcceptanceRequest, BrokerTermsAcceptanceResponse,
    BrokerClientInviteDetailsResponse, BrokerClientInviteAcceptRequest,
    BrokerBrandingRuntimeResponse,
    CurrentUser, TokenPayload,
    ChangePasswordRequest, ChangeEmailRequest, UpdateProfileRequest,
    CandidateBetaInfo, CandidateBetaListResponse, BetaToggleRequest,
    TokenAwardRequest, AllowedRolesRequest, CandidateSessionSummary
)
from app.core.services.auth import (
    hash_password, verify_password, verify_password_async,
    create_access_token, create_refresh_token, decode_token,
    create_email_verify_token, decode_email_verify_token,
)
from app.core.dependencies import (
    get_current_user, require_admin, require_broker, get_token_payload,
    session_revoked, revoke_user_sessions,
)
from app.core.feature_flags import (
    DEFAULT_COMPANY_FEATURES,
    default_company_features_json,
    merge_company_features,
)
from app.core.services.platform_settings import get_visible_features
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.config import get_settings


from app.core.routes.auth._shared import *  # noqa: F401,F403


@router.post("/register/business")
async def register_business(request: BusinessRegister, http_request: Request):
    """
    Register a new business with first admin/client user.
    This creates:
    1. A new company (status='approved' if invite token provided, else 'pending')
    2. A client user linked to that company
    3. Returns auth tokens for immediate login

    If no invite_token, the business will need admin approval before accessing full features.

    NOTE: resources_free tier short-circuits to a deferred-create flow — we
    sign the signup data into a verification JWT and email a confirmation
    link instead of creating any DB rows. The /verify-email endpoint
    completes the signup once the user clicks the link.
    """
    ip = client_ip(http_request)
    await check_rate_limit(ip, "register_business", 10, 3600)
    from ..services.email import get_email_service

    # ---- resources_free deferred-create path -----------------------------
    # We do NOT touch users/companies until the user confirms their email.
    # Just verify the email isn't already taken, sign the registration data
    # into a short-lived JWT, and send the verification link.
    if request.tier == "resources_free":
        async with get_connection() as conn:
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

        password_hash = hash_password(request.password)
        token = create_email_verify_token({
            "email": request.email,
            "name": request.name,
            "password_hash": password_hash,
            "company_name": request.company_name,
            "industry": request.industry,
            "company_size": request.company_size,
            "headcount": request.headcount,
            "phone": request.phone,
            "job_title": request.job_title,
            "tier": "resources_free",
        })

        settings = get_settings()
        verification_url = f"{settings.app_base_url}/auth/verify-email?token={token}"
        email_service = get_email_service()
        await email_service.send_email_verification_email(
            to_email=request.email,
            to_name=request.name,
            verification_url=verification_url,
        )

        return {
            "status": "verification_sent",
            "email": request.email,
            "message": "Check your inbox to confirm your email and finish creating your account.",
        }
    # ----------------------------------------------------------------------

    async with get_connection() as conn:
        async with conn.transaction():
            # Check if email already exists
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email)
            if existing:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Validate and atomically reserve invite token if provided
            invitation = None
            if request.invite_token:
                invitation = await conn.fetchrow(
                    """UPDATE business_invitations
                       SET status = 'used', used_at = NOW()
                       WHERE token = $1 AND status = 'pending' AND expires_at > NOW()
                       RETURNING id""",
                    request.invite_token,
                )
                if not invitation:
                    raise HTTPException(status_code=400, detail="Invalid, expired, or already-used invite link")

            # Resolve broker referral (slug lookup — ignore silently if invalid)
            referring_broker_id = None
            if request.broker_ref:
                broker_row = await conn.fetchrow(
                    "SELECT id FROM brokers WHERE slug = $1 AND status = 'active'",
                    request.broker_ref.strip().lower(),
                )
                if broker_row:
                    referring_broker_id = broker_row["id"]

            # Resolve Lite referral token — non-blocking if invalid/expired
            lite_broker_pays = False
            broker_seat_count = None  # set when a company-pinned broker seat invite is redeemed
            if request.lite_broker_token and request.tier in ("matcha_lite", "matcha_x", "matcha_compliance", "custom_product") and referring_broker_id is None:
                lite_ref_row = await conn.fetchrow(
                    """
                    UPDATE broker_lite_referral_tokens
                    SET use_count    = use_count + 1,
                        last_used_at = NOW()
                    WHERE token     = $1
                      AND is_active  = true
                      AND redeemed_company_id IS NULL
                      AND (expires_at IS NULL OR expires_at > NOW())
                    RETURNING broker_id, payer, seat_count, intended_company_name
                    """,
                    request.lite_broker_token.strip(),
                )
                if lite_ref_row:
                    referring_broker_id = lite_ref_row["broker_id"]
                    lite_broker_pays = lite_ref_row["payer"] == "broker"
                    broker_seat_count = lite_ref_row["seat_count"]

            # Admin invite token — activates Matcha Lite immediately (no Stripe).
            # Atomic UPDATE-RETURNING so concurrent signups with the same link
            # can't both pass (matches business_invitations pattern above).
            lite_invite_activated = False
            lite_invite_id = None
            if request.lite_invite_token and request.tier in ("matcha_lite", "matcha_x", "matcha_compliance", "custom_product"):
                invite_row = await conn.fetchrow(
                    """UPDATE matcha_lite_invite_tokens
                       SET used_at = NOW()
                       WHERE token = $1 AND used_at IS NULL
                       RETURNING id""",
                    request.lite_invite_token.strip(),
                )
                if not invite_row:
                    raise HTTPException(status_code=400, detail="Invalid or already-used invite link")
                lite_invite_activated = True
                lite_invite_id = invite_row["id"]

            # IR-only self-serve signup auto-approves and narrows the
            # feature set to incidents only. Bypasses the bespoke pending
            # queue. Other tier values fall through to standard behavior.
            is_ir_only = request.tier == "ir_only"
            is_resources_free = request.tier == "resources_free"
            is_matcha_lite = request.tier == "matcha_lite"
            is_matcha_x = request.tier == "matcha_x"
            is_matcha_compliance = request.tier == "matcha_compliance"
            # Admin-composed product from the /admin/products builder. The
            # product row (not this module) defines the features, the paid
            # gate, and the price — resolved here so the headcount cap below
            # and the feature materialization use the same row.
            is_custom_product = request.tier == "custom_product"
            custom_product = None
            if is_custom_product:
                from ..services.product_definitions import get_product_by_slug
                custom_product = await get_product_by_slug(
                    conn, (request.product_slug or "").strip().lower(), published_only=True
                )
                if custom_product is None:
                    raise HTTPException(status_code=404, detail="Product not found or not available")

            # Broker seat invites carry their own allocation, so they bypass the
            # self-serve headcount cap (same as an admin comp invite).
            if not lite_invite_activated and broker_seat_count is None:
                if is_custom_product and custom_product.is_paid and request.headcount > custom_product.max_headcount:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Headcount over {custom_product.max_headcount} — please contact us for pricing at matcha.work",
                    )
                if is_matcha_x and request.headcount > 300:
                    raise HTTPException(
                        status_code=400,
                        detail="Headcount over 300 — please contact us for pricing at matcha.work",
                    )
                elif is_matcha_lite or is_matcha_compliance:
                    # Lite/Essentials/Compliance share the DB-backed, admin-
                    # configurable pricing table (matcha_lite_pricing) — read
                    # its max_headcount rather than a hardcoded 300, so the
                    # cap here can't drift from what /checkout/lite and
                    # /checkout/compliance actually enforce.
                    from ..services.matcha_lite_pricing import get_matcha_lite_pricing
                    product_code = (
                        "matcha_compliance" if is_matcha_compliance
                        else "matcha_lite_essentials" if request.lite_essentials
                        else "matcha_lite"
                    )
                    reg_pricing = await get_matcha_lite_pricing(conn, product_code=product_code)
                    if request.headcount > reg_pricing.max_headcount:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Headcount over {reg_pricing.max_headcount} — please contact us for pricing at matcha.work",
                        )

            if is_custom_product:
                # Admin-composed product. The row is the source of truth for
                # what this tenant gets; signup_source carries the slug so
                # /auth/me, the sidebar and the webhook can resolve it back.
                #
                # Features are MATERIALIZED here (not overlaid at read time
                # like TIER_REQUIRED_FEATURES) because merge_company_features
                # is pure + sync and runs in the pool-free Celery workers.
                # Editing the product later doesn't reach this company —
                # POST /admin/products/{id}/sync-tenants is the catch-up.
                #
                # Stripe-billed products start with EVERY flag off (the paid
                # gate flips on checkout.session.completed, same as `incidents`
                # for Lite). Free products and comped signups (broker-pays or
                # admin invite) activate immediately. `contact_sales` also
                # starts off — it has no self-serve payment path, so an admin
                # activates it via /admin/products/{id}/activate-tenant.
                from ..services.product_definitions import (
                    materialize_features as _materialize_product_features,
                    pending_features as _pending_product_features,
                )
                company_status = "approved"
                signup_source = custom_product.signup_source
                if custom_product.activates_on_signup or lite_broker_pays or lite_invite_activated:
                    enabled_features_json = json.dumps(_materialize_product_features(custom_product))
                else:
                    enabled_features_json = json.dumps(_pending_product_features(custom_product))
            elif is_ir_only:
                company_status = "approved"
                signup_source = "ir_only_self_serve"
                # Matcha Cap bundle: incidents + employees + discipline.
                # `incidents` is the headline feature; `employees` is on
                # because IR fundamentally needs employees to report on
                # (otherwise /employees 403s and onboarding can't add
                # anyone). `discipline` ships as part of Cap so the
                # progressive-warning + signature workflow is available
                # alongside incident tracking. Every other default flag
                # is explicitly False so merge_company_features doesn't
                # hydrate handbooks/accommodations/risk_assessment back
                # on for Cap tenants.
                ir_features = {k: False for k in DEFAULT_COMPANY_FEATURES}
                ir_features["incidents"] = True
                ir_features["employees"] = True
                ir_features["discipline"] = True
                # ir_only_self_serve = legacy alias for matcha_lite — same
                # surface (handbooks + training auto-enabled).
                ir_features["handbooks"] = True
                ir_features["training"] = True
                enabled_features_json = json.dumps(ir_features)
            elif is_resources_free:
                # Resources-tier signup: auto-approved so they can immediately
                # download templates / run the audit / use calculators.
                # No paid features enabled — gating on `client` role alone.
                company_status = "approved"
                signup_source = "resources_free"
                rf_features = {k: False for k in DEFAULT_COMPANY_FEATURES}
                enabled_features_json = json.dumps(rf_features)
            elif is_matcha_lite:
                # Matcha Lite is a paid bundle — IR + Resources.
                # Broker-pays signups skip Stripe entirely → enable
                # incidents immediately. Business-pays signups must
                # complete Stripe checkout first; the webhook flips
                # `incidents=true` on `checkout.session.completed`.
                # Until then, isMatchaLitePending() routes the user
                # to MatchaLitePendingSidebar with a Subscribe CTA
                # so they can resume checkout.
                # customer.subscription.deleted flips it back off on
                # cancellation. The IR system runs standalone — no
                # employees feature dependency.
                company_status = "approved"
                # Essentials is a signup-time choice on this same page/checkout,
                # not a separate product — no employee roster (no CSV/HRIS
                # import, no OSHA logs), just incident reporting. Routed via a
                # distinct signup_source so it gets its own TIER_REQUIRED_FEATURES
                # overlay + matcha_lite_pricing row, cheaper than standard Lite.
                is_lite_essentials = bool(request.lite_essentials)
                signup_source = "matcha_lite_essentials" if is_lite_essentials else "matcha_lite"
                # Lite (entry tier) = IR + employees + handbook GENERATION.
                # training/discipline/handbook_audit/credentialing moved up to
                # Matcha-X — not granted here. The matcha_lite tier overlay
                # also force-asserts training/discipline off at read time,
                # covering existing rows.
                lite_features = {k: False for k in DEFAULT_COMPANY_FEATURES}
                lite_features["handbooks"] = True
                if lite_broker_pays or lite_invite_activated:
                    lite_features["incidents"] = True
                    if not is_lite_essentials:
                        lite_features["employees"] = True
                enabled_features_json = json.dumps(lite_features)
            elif is_matcha_x:
                # Matcha-X is the paid mid tier — a clone of Matcha Lite at
                # Lite parity (extra modules layered later). Same payment
                # model: broker-pays/invite signups activate immediately;
                # business-pays signups complete Stripe checkout first and
                # the webhook flips `incidents=true`. handbooks/training/
                # employees/discipline are the always-on bundle (the latter
                # two also overlaid via TIER_REQUIRED_FEATURES["matcha_x"],
                # so business-pays tenants converge to the same shape after
                # payment — Lite's discipline path-dependency is fixed here).
                company_status = "approved"
                signup_source = "matcha_x"
                x_features = {k: False for k in DEFAULT_COMPANY_FEATURES}
                x_features["handbooks"] = True
                x_features["training"] = True
                if lite_broker_pays or lite_invite_activated:
                    x_features["incidents"] = True
                    x_features["employees"] = True
                    x_features["discipline"] = True
                enabled_features_json = json.dumps(x_features)
            elif is_matcha_compliance:
                # Standalone self-serve Compliance product. Same payment model
                # as Lite/X: broker-pays/invite signups activate immediately;
                # business-pays signups complete Stripe checkout first and the
                # webhook flips the full `compliance` flag. Nothing else is
                # bundled — every other default flag stays off. `compliance` is
                # NOT in any TIER_REQUIRED overlay, so it's the live paid gate
                # (mirrors how `incidents` gates Lite/X), not force-asserted on.
                company_status = "approved"
                signup_source = "matcha_compliance"
                compliance_features = {k: False for k in DEFAULT_COMPANY_FEATURES}
                if lite_broker_pays or lite_invite_activated:
                    compliance_features["compliance"] = True
                enabled_features_json = json.dumps(compliance_features)
            else:
                # Bespoke/platform tier from a PUBLIC endpoint. Only an
                # admin-issued invite token may provision a full Pro company
                # here. A broker referral (`broker_ref`) is a public marketing
                # slug (no secret) — it attributes the lead but must NEVER grant
                # approval or paid features. Previously `broker_ref` flipped
                # status→approved AND the branch stored the full Pro feature set,
                # which let anyone self-provision a free Pro platform tenant.
                company_status = "approved" if invitation else "pending"
                if invitation:
                    signup_source = "invite"
                elif referring_broker_id:
                    signup_source = "broker"
                else:
                    signup_source = "bespoke"

                if invitation:
                    # Invited (admin-issued) bespoke companies get the full
                    # platform: IR on by default, plus handbook audit +
                    # credentialing (Pro, toggleable per-company). Personal
                    # Matcha-work companies are created elsewhere
                    # (is_personal=true) and never reach this branch.
                    bespoke_features = dict(DEFAULT_COMPANY_FEATURES)
                    bespoke_features["incidents"] = True
                    bespoke_features["handbook_audit"] = True
                    bespoke_features["credential_templates"] = True
                    # Labor Relations (union / CBA admin) is a Pro-bundled gate.
                    bespoke_features["labor_relations"] = True
                    # Handbook Pilot (conversational handbook/policy generation)
                    # is a Pro-bundled gate.
                    bespoke_features["handbook_pilot"] = True
                    enabled_features_json = json.dumps(bespoke_features)
                else:
                    # Self-serve / broker-referred lead with no invite: stay
                    # pending with NO paid features until an admin verifies/closes
                    # the sale. No tier escalation from a public request.
                    enabled_features_json = json.dumps(
                        {k: False for k in DEFAULT_COMPANY_FEATURES}
                    )

            # Step 1: Create company
            company = await conn.fetchrow(
                """INSERT INTO companies (name, industry, size, healthcare_specialties, status, approved_at, enabled_features, signup_source)
                   VALUES ($1, $2, $3, $4::text[], $5, $6, $7::jsonb, $8)
                   RETURNING id, name""",
                request.company_name, request.industry, request.company_size,
                request.healthcare_specialties,
                company_status,
                datetime.utcnow() if company_status == "approved" else None,
                enabled_features_json,
                signup_source,
            )
            company_id = company["id"]

            # Grant free token budget (1M tokens)
            from ...matcha.services.billing.token_budget_service import FREE_TOKEN_GRANT
            await conn.execute(
                """INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
                   VALUES ($1, 0, $2)
                   ON CONFLICT (company_id) DO NOTHING""",
                company_id, FREE_TOKEN_GRANT,
            )

            # Step 2: Create user with 'client' role
            password_hash = hash_password(request.password)
            user = await conn.fetchrow(
                """INSERT INTO users (email, password_hash, role)
                   VALUES ($1, $2, 'client')
                   RETURNING id, email, role, is_active, created_at""",
                request.email, password_hash
            )

            # Step 3: Create client profile linked to company
            await conn.execute(
                """INSERT INTO clients (user_id, company_id, name, phone, job_title)
                   VALUES ($1, $2, $3, $4, $5)""",
                user["id"], company_id, request.name, request.phone, request.job_title
            )

            # Step 4: Update company.owner_id to link back to user
            await conn.execute(
                "UPDATE companies SET owner_id = $1 WHERE id = $2",
                user["id"], company_id
            )

            # Step 4b: Seed training_requirements for tenants whose bundle
            # includes training — Matcha-X + ir_only_self_serve (Cap). Lite no
            # longer has training, so it's excluded. Idempotent — no-op when no
            # templates exist (e.g. fresh dev DB before generate_training_templates.py).
            if is_matcha_x or is_ir_only:
                await conn.execute(
                    """
                    INSERT INTO training_requirements
                      (company_id, title, description, training_type, jurisdiction,
                       frequency_months, applies_to, template_id, required_minutes,
                       pass_score_percent, is_active)
                    SELECT $1,
                           t.title,
                           NULL,
                           t.training_type,
                           t.jurisdiction,
                           t.frequency_months,
                           CASE t.variant
                               WHEN 'supervisor' THEN 'supervisor'
                               ELSE 'nonsupervisor'
                           END,
                           t.id,
                           t.required_minutes,
                           t.pass_score_percent,
                           TRUE
                    FROM training_lesson_templates t
                    WHERE t.is_active = TRUE
                      AND NOT EXISTS (
                          SELECT 1 FROM training_requirements tr
                          WHERE tr.company_id = $1
                            AND tr.template_id = t.id
                      )
                    """,
                    company_id,
                )

            # Seed profile data used by handbook/compliance flows.
            await _upsert_business_headcount_profile(
                conn,
                company_id=company_id,
                company_name=request.company_name,
                owner_name=request.name,
                headcount=request.headcount,
                jurisdiction_count=request.jurisdiction_count,
                updated_by=user["id"],
            )

            # Step 5: Link invitation to the new company
            if invitation:
                await conn.execute(
                    "UPDATE business_invitations SET used_by_company_id = $1 WHERE id = $2",
                    company_id, invitation["id"],
                )

            if lite_invite_activated:
                await conn.execute(
                    """UPDATE matcha_lite_invite_tokens
                       SET used_by_company_id = $1
                       WHERE id = $2""",
                    company_id, lite_invite_id,
                )

            # Step 6: Create broker referral link if the company came via a broker slug
            if referring_broker_id:
                await conn.execute(
                    """
                    INSERT INTO broker_company_links
                        (broker_id, company_id, status, linked_at, activated_at, created_by, updated_at)
                    VALUES ($1, $2, 'active', NOW(), NOW(), $3, NOW())
                    ON CONFLICT (broker_id, company_id) DO UPDATE
                        SET status = 'active',
                            activated_at = COALESCE(broker_company_links.activated_at, NOW()),
                            terminated_at = NULL,
                            updated_at = NOW()
                    """,
                    referring_broker_id, company_id, user["id"],
                )

                # Redeem a company-pinned broker seat invite: record the granted seat
                # count on the company (track/display) and single-use the token.
                if broker_seat_count is not None:
                    await conn.execute(
                        "UPDATE companies SET seat_limit = $1 WHERE id = $2",
                        broker_seat_count, company_id,
                    )
                    await conn.execute(
                        """
                        UPDATE broker_lite_referral_tokens
                        SET redeemed_company_id = $1, is_active = false
                        WHERE token = $2
                        """,
                        company_id, request.lite_broker_token.strip(),
                    )

            # Generate tokens
            settings = get_settings()
            access_token = create_access_token(user["id"], user["email"], user["role"])
            refresh_token = create_refresh_token(user["id"], user["email"], user["role"])

            # Send appropriate email
            email_service = get_email_service()
            if is_custom_product:
                # Admin-composed products reuse the Lite transactional emails:
                # active accounts get the approved email, Stripe-pending ones
                # the payment-required email. contact_sales lands in the
                # pending copy too — an admin activates it by hand.
                if custom_product.activates_on_signup or lite_broker_pays or lite_invite_activated:
                    await email_service.send_business_approved_email(
                        to_email=user["email"],
                        to_name=request.name,
                        company_name=request.company_name,
                    )
                else:
                    await email_service.send_lite_payment_pending_email(
                        to_email=user["email"],
                        to_name=request.name,
                        company_name=request.company_name,
                        headcount=request.headcount,
                    )
            elif is_matcha_lite or is_matcha_x or is_matcha_compliance:
                # matcha_x + matcha_compliance reuse the Lite transactional
                # emails for now — swap in branded copy when each productizes.
                if lite_broker_pays or lite_invite_activated:
                    # Broker or admin invite — account is fully active.
                    await email_service.send_business_approved_email(
                        to_email=user["email"],
                        to_name=request.name,
                        company_name=request.company_name,
                    )
                else:
                    # Business pays via Stripe — features stay off until
                    # the webhook confirms payment. Different email so
                    # the user knows what's still required.
                    await email_service.send_lite_payment_pending_email(
                        to_email=user["email"],
                        to_name=request.name,
                        company_name=request.company_name,
                        headcount=request.headcount,
                    )
            elif is_resources_free:
                # Free-tier copy — does NOT promise the full platform.
                await email_service.send_resources_free_welcome_email(
                    to_email=user["email"],
                    to_name=request.name,
                    company_name=request.company_name
                )
            elif is_ir_only or invitation or referring_broker_id:
                await email_service.send_business_approved_email(
                    to_email=user["email"],
                    to_name=request.name,
                    company_name=request.company_name
                )
            else:
                await email_service.send_business_registration_pending_email(
                    to_email=user["email"],
                    to_name=request.name,
                    company_name=request.company_name
                )

            if is_custom_product:
                if custom_product.activates_on_signup or lite_broker_pays or lite_invite_activated:
                    next_route = "/app"
                    msg = f"Welcome to {custom_product.name}."
                elif custom_product.is_paid:
                    # Client SPA chains the Stripe call directly; this hint is
                    # for any caller that doesn't.
                    next_route = "/checkout/product"
                    msg = f"Account created. Complete payment to activate {custom_product.name}."
                else:
                    next_route = None
                    msg = f"Account created. Our team will be in touch to activate {custom_product.name}."
            elif is_matcha_compliance and (lite_broker_pays or lite_invite_activated):
                next_route = "/compliance/onboarding"
                msg = "Welcome to Matcha Compliance. Let's set up your locations."
            elif is_matcha_compliance:
                # Client SPA chains the Stripe call directly; this hint is for
                # any caller that doesn't.
                next_route = "/checkout/compliance"
                msg = "Account created. Complete payment to activate Matcha Compliance."
            elif is_matcha_x and (lite_broker_pays or lite_invite_activated):
                next_route = "/matcha-x/onboarding"
                msg = "Welcome to Matcha-X. Let's set up your team."
            elif is_matcha_x:
                next_route = "/checkout/x"
                msg = "Account created. Complete payment to activate Matcha-X."
            elif is_matcha_lite and (lite_broker_pays or lite_invite_activated):
                next_route = "/ir/onboarding"
                msg = "Welcome to Matcha Lite. Let's set up your team."
            elif is_matcha_lite:
                # Client SPA chains the Stripe call directly; this hint is
                # for any caller that doesn't (e.g. broker portal preview).
                next_route = "/checkout/lite"
                msg = "Account created. Complete payment to activate Matcha Lite."
            elif is_ir_only:
                next_route = "/ir/onboarding"
                msg = "Welcome to Matcha IR. Let's set up your team."
            elif is_resources_free:
                next_route = "/app/resources"
                msg = "Account created. Resources unlocked."
            elif invitation or referring_broker_id:
                next_route = None
                msg = "Welcome! Your business account is approved and ready to use."
            else:
                next_route = None
                msg = "Your business registration is pending approval. You will be notified once it's reviewed."

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": settings.jwt_access_token_expire_minutes * 60,
                "user": {
                    "id": str(user["id"]),
                    "email": user["email"],
                    "role": user["role"],
                    "is_active": user["is_active"],
                    "created_at": user["created_at"].isoformat() if user["created_at"] else None,
                    "last_login": None
                },
                "company_status": company_status,
                "signup_source": signup_source,
                "next": next_route,
                "message": msg,
                "lite_broker_pays": lite_broker_pays,
                "lite_invite_activated": lite_invite_activated,
            }



@router.get("/business-invite/{token}")
async def validate_business_invite(token: str):
    """Validate a business invite token (public, no auth required)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, status, expires_at, note
            FROM business_invitations
            WHERE token = $1
            """,
            token,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Invite not found or invalid")

        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Invite is no longer valid (status: {row['status']})")

        if row["expires_at"] < datetime.utcnow():
            raise HTTPException(status_code=400, detail="Invite has expired")

        return {
            "valid": True,
            "expires_at": row["expires_at"].isoformat(),
            "note": row["note"],
        }



@router.get("/client-invite-info")
async def get_client_invite_info(ref: str):
    """Public, non-consuming: resolve a broker client-seat invite so the signup page
    can prefill the company name + seat count. Returns {valid:false} for unknown,
    revoked, redeemed, or expired tokens (and for generic, non-pinned referral links)."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT t.intended_company_name, t.seat_count, t.tier, t.is_active,
                   t.redeemed_company_id, t.expires_at, b.name AS broker_name
            FROM broker_lite_referral_tokens t
            JOIN brokers b ON b.id = t.broker_id
            WHERE t.token = $1 AND t.intended_company_name IS NOT NULL
            """,
            ref.strip(),
        )
    if not row:
        return {"valid": False}
    valid = bool(
        row["is_active"]
        and row["redeemed_company_id"] is None
        and (row["expires_at"] is None or row["expires_at"] > datetime.utcnow())
    )
    return {
        "valid": valid,
        "company_name": row["intended_company_name"],
        "seat_count": row["seat_count"],
        "tier": row["tier"] or "matcha_lite",
        "broker_name": row["broker_name"],
    }

