"""Admin shared helpers + constants (J5 split)."""
import asyncio
import difflib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Depends, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services.credential_crypto import decrypt_credential_fields
from app.core.services.scope_registry.codify import codified_sql
from app.core.feature_flags import merge_company_features
from app.core.services.email import get_email_service
from app.core.models.compliance import AutoCheckSettings, LocationCreate
from app.core.models.compliance_evals import EvalRunRequest, FindingResolveRequest
from app.core.compliance_registry import (
    TRIGGER_PROFILES,
    LABOR_CATEGORIES, HEALTHCARE_CATEGORIES, ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES, SUPPLEMENTARY_CATEGORIES,
)
from app.core.services.compliance_service import (
    _resolve_industry,
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
    run_compliance_check_background,
    run_compliance_check_stream,
    research_jurisdiction_repo_only,
    get_locations,
    get_location_requirements,
    create_location,
    admin_add_requirement_to_location,
)
from app.core.services.redis_cache import (
    get_redis_cache, cache_get, cache_set, cache_delete, cache_delete_pattern,
    admin_jurisdictions_list_key, admin_jurisdiction_detail_key,
    admin_jurisdiction_data_overview_key, admin_jurisdiction_policy_overview_key,
    admin_bookmarked_requirements_key,
)
from app.core.services.rate_limiter import get_rate_limiter
from app.core.services.auth import hash_password
from app.core.services.platform_settings import (
    get_visible_features, prime_visible_features_cache,
    get_matcha_work_model_mode, prime_matcha_work_model_mode_cache,
    get_jurisdiction_research_model_mode, prime_jurisdiction_research_model_mode_cache,
    get_er_similarity_weights, prime_er_similarity_weights_cache,
    get_tenant_codified_only, prime_tenant_codified_only_cache,
    DEFAULT_ER_SIMILARITY_WEIGHTS, EXPECTED_WEIGHT_KEYS,
)
from app.matcha.services import billing_service as mw_billing_service
from app.config import get_settings
from app.core.services.stripe_service import StripeService, StripeServiceError
from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
from app.core.services.deal_pricing import DealInputs
from app.core.services.deal_full import FullDealInputs
from app.core.services.deal_broker import BrokerInputs
from app.core.services.deal_book import BookInputs


from app.core.services.scope_registry.jurisdiction_chain import (  # noqa: E402
    resolve_jurisdiction_chain as _resolve_jurisdiction_chain,
)

from app.core.models.admin import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

__all__ = [
    "_row_to_registration",
    "_tier_filter_clause",
    "_slugify_broker_name",
    "_validate_broker_enums",
    "_transition_state_for",
    "_link_status_for",
    "_normalize_city_input",
    "_is_non_city_jurisdiction",
    "_city_display",
    "_canonicalize_city_fallback",
    "_canonicalize_city_from_reference",
    "_canonicalize_city",
    "_is_supported_city",
    "_get_required_categories",
    "_row_metadata",
    "_eval_iso",
    "_eval_json",
    "_jurisdiction_label",
    "_to_sse",
    "_format_city_label",
    "_phase_percent",
    "_source_confidence",
    "_requirement_confidence",
    "_legislation_confidence",
    "_run_jurisdiction_check_events",
    "_get_or_create_metro_jurisdiction",
    "_fmt_dt",
    "_profile_row_to_dict",
    "_load_industry_profile_row",
    "_publish_research_to_requesters",
    "_heartbeat_while_admin",
    "_project_chain_to_location_categories",
    "_snapshot_requirements_bg",
    "_publish_vertical_to_company",
    "_deal_template_row",
    "_cappe_site_row",
    "KNOWN_PLATFORM_ITEMS",
    "STRICT_CONFIDENCE_THRESHOLD",
    "MAX_CONFIDENCE_REFETCH_ATTEMPTS",
    "TOP_15_METROS",
    "FALLBACK_ALLOWED_CITIES_BY_STATE",
    "FALLBACK_CITY_ALIASES",
    "KNOWN_FEATURES",
    "_BUSINESS_REGISTRATION_SELECT",
    "VALID_BROKER_STATUSES",
    "VALID_BROKER_SUPPORT_ROUTING",
    "VALID_BROKER_BILLING_MODES",
    "VALID_INVOICE_OWNERS",
    "VALID_BROKER_CONTRACT_STATUSES",
    "VALID_BROKER_LINK_STATUSES",
    "VALID_POST_TERMINATION_MODES",
    "VALID_BROKER_BRANDING_MODES",
    "VALID_TRANSITION_STATUSES",
    "VALID_DATA_HANDOFF_STATUSES",
    "VALID_LINK_TRANSITION_STATES",
    "_data_overview_cache",
    "_data_overview_cached_at",
    "_DATA_OVERVIEW_CACHE_TTL",
    "_REQUIRED_CATEGORIES_FALLBACK",
    "_required_categories_cache",
    "_required_categories_cached_at",
    "_REQUIRED_CATEGORIES_CACHE_TTL",
    "_CATEGORY_DOMAIN",
    "_DOMAIN_LABELS",
    "_CATEGORY_LABELS",
    "DOMAIN_CATEGORIES",
    "VALID_ORDER_STATUSES",
    "_NOTIFICATION_LINK_MAP",
    "_NOTIFICATION_SUBQUERIES",
    "HEARTBEAT_INTERVAL_ADMIN",
    "_TIER_FEATURE_PRESETS",
    "_DEAL_TEMPLATE_KEYS",
    "_CAPPE_PAID_STATUSES",
]


KNOWN_PLATFORM_ITEMS = {
    "admin_overview", "client_management", "company_features", "industry_handbooks", "admin_import",
    "projects", "interviewer", "candidate_metrics", "interview_prep", "test_bot",
    "onboarding", "employees", "policies", "handbooks", "time_off",
    "accommodations", "er_copilot", "incidents", "risk_assessment",
    "compliance", "jurisdictions", "blog", "hr_news", "matcha_work",
    "offer_letters", "discipline",
}


STRICT_CONFIDENCE_THRESHOLD = 0.95


MAX_CONFIDENCE_REFETCH_ATTEMPTS = 2


# Hardcoded metro preset by design: this keeps execution simple and deterministic.
TOP_15_METROS: list[dict[str, str]] = [
    {"city": "new york", "state": "NY", "label": "New York City"},
    {"city": "los angeles", "state": "CA", "label": "Los Angeles"},
    {"city": "chicago", "state": "IL", "label": "Chicago"},
    {"city": "houston", "state": "TX", "label": "Houston"},
    {"city": "phoenix", "state": "AZ", "label": "Phoenix"},
    {"city": "philadelphia", "state": "PA", "label": "Philadelphia"},
    {"city": "san antonio", "state": "TX", "label": "San Antonio"},
    {"city": "san diego", "state": "CA", "label": "San Diego"},
    {"city": "dallas", "state": "TX", "label": "Dallas"},
    {"city": "jacksonville", "state": "FL", "label": "Jacksonville"},
    {"city": "austin", "state": "TX", "label": "Austin"},
    {"city": "fort worth", "state": "TX", "label": "Fort Worth"},
    {"city": "san jose", "state": "CA", "label": "San Jose"},
    {"city": "columbus", "state": "OH", "label": "Columbus"},
    {"city": "charlotte", "state": "NC", "label": "Charlotte"},
]


# Fallback allowlist for environments where jurisdiction_reference is unavailable.
# Keep this intentionally constrained and canonical.
FALLBACK_ALLOWED_CITIES_BY_STATE: dict[str, set[str]] = {
    "NY": {"new york"},
    "CA": {"los angeles", "san diego", "san jose"},
    "IL": {"chicago"},
    "TX": {"houston", "san antonio", "dallas", "austin", "fort worth"},
    "AZ": {"phoenix"},
    "PA": {"philadelphia"},
    "FL": {"jacksonville"},
    "OH": {"columbus"},
    "NC": {"charlotte"},
    "UT": {"salt lake city"},
}


FALLBACK_CITY_ALIASES: dict[tuple[str, str], str] = {
    ("NY", "new york city"): "new york",
    ("NY", "nyc"): "new york",
    ("UT", "salt lake"): "salt lake city",
}


# Known feature keys that can be toggled
KNOWN_FEATURES = {
    "policies", "handbooks", "compliance",
    "employees", "offer_letters",
    "er_copilot", "incidents", "time_off", "accommodations", "interview_prep",
    "matcha_work", "risk_assessment",
    "training", "i9", "cobra", "separation_agreements", "credential_templates",
    "hris_import", "hris_gusto", "hris_finch", "hris_deductions",
    "paid_channel_creator", "discipline", "inventory",
    "werk_lite", "werk_lite_calls_all_members",
    "workforce_compliance", "risk_profile", "resident_care", "controls_evidence",
    "limit_adequacy", "driver_risk", "ir_voice_intake", "legal_defense",
    "handbook_pilot", "analysis_pilot", "hr_pilot", "employee_schedule",
}


_BUSINESS_REGISTRATION_SELECT = """
    SELECT
        comp.id,
        comp.name as company_name,
        comp.industry,
        comp.healthcare_specialties,
        comp.size as company_size,
        comp.signup_source,
        comp.is_personal,
        comp.deleted_at,
        u.id as owner_user_id,
        u.email as owner_email,
        u.is_suspended as is_suspended,
        c.name as owner_name,
        c.phone as owner_phone,
        c.job_title as owner_job_title,
        comp.status,
        comp.rejection_reason,
        comp.approved_at,
        approver.email as approved_by_email,
        comp.created_at,
        sub.pack_id as sub_pack_id,
        sub.status as sub_status,
        sub.amount_cents as sub_amount_cents,
        sub.stripe_subscription_id as sub_stripe_sub_id,
        sub.stripe_customer_id as sub_stripe_customer_id,
        sub.current_period_end as sub_current_period_end,
        sub.canceled_at as sub_canceled_at
    FROM companies comp
    JOIN clients c ON c.company_id = comp.id
    JOIN users u ON c.user_id = u.id
    LEFT JOIN users approver ON comp.approved_by = approver.id
    LEFT JOIN LATERAL (
        SELECT pack_id, status, amount_cents, stripe_subscription_id,
               stripe_customer_id, current_period_end, canceled_at
        FROM mw_subscriptions
        WHERE company_id = comp.id
        ORDER BY (status = 'active') DESC, created_at DESC
        LIMIT 1
    ) sub ON TRUE
"""


VALID_BROKER_STATUSES = {"pending", "active", "suspended", "terminated"}


VALID_BROKER_SUPPORT_ROUTING = {"broker_first", "matcha_first", "shared"}


VALID_BROKER_BILLING_MODES = {"direct", "reseller", "hybrid"}


VALID_INVOICE_OWNERS = {"matcha", "broker"}


VALID_BROKER_CONTRACT_STATUSES = {"draft", "active", "suspended", "terminated"}


VALID_BROKER_LINK_STATUSES = {"pending", "active", "suspending", "grace", "terminated", "transferred"}


VALID_POST_TERMINATION_MODES = {"convert_to_direct", "transfer_to_broker", "sunset", "matcha_managed"}


VALID_BROKER_BRANDING_MODES = {"direct", "co_branded", "white_label"}


VALID_TRANSITION_STATUSES = {"planned", "in_progress", "completed", "cancelled"}


VALID_DATA_HANDOFF_STATUSES = {"not_required", "pending", "in_progress", "completed"}


VALID_LINK_TRANSITION_STATES = {"none", "planned", "in_progress", "matcha_managed", "completed"}


_data_overview_cache: dict | None = None


_data_overview_cached_at: float = 0.0


_DATA_OVERVIEW_CACHE_TTL = 3600  # 1 hour


# Historical hardcoded list — kept ONLY as the fallback `_get_required_categories()`
# returns when the DB query fails (e.g. connection issue). This list is why the 8
# orphaned manufacturing categories (Phase C1) went unnoticed for as long as they did:
# it never grew when new domains were seeded. Do not add new categories here — seed
# them in `compliance_categories` via migration instead; `_get_required_categories()`
# picks them up automatically.
_REQUIRED_CATEGORIES_FALLBACK = [
    # Labor
    "minimum_wage", "overtime", "sick_leave", "meal_breaks",
    "pay_frequency", "final_pay", "minor_work_permit", "scheduling_reporting",
    "leave", "workplace_safety", "workers_comp", "anti_discrimination",
    # Supplementary
    "business_license", "tax_rate", "posting_requirements",
    # Healthcare
    "hipaa_privacy", "billing_integrity", "clinical_safety", "healthcare_workforce",
    "corporate_integrity", "research_consent", "state_licensing", "emergency_preparedness",
    # Oncology
    "radiation_safety", "chemotherapy_handling", "tumor_registry",
    "oncology_clinical_trials", "oncology_patient_rights",
    # Medical Compliance
    "health_it", "quality_reporting", "cybersecurity", "environmental_safety",
    "pharmacy_drugs", "payer_relations", "reproductive_behavioral", "pediatric_vulnerable",
    "telehealth", "medical_devices", "transplant_organ", "antitrust",
    "tax_exempt", "language_access", "records_retention", "marketing_comms",
    "emerging_regulatory",
]


_required_categories_cache: list[str] | None = None


_required_categories_cached_at: float = 0.0


_REQUIRED_CATEGORIES_CACHE_TTL = 3600  # 1 hour — mirrors _DATA_OVERVIEW_CACHE_TTL


# ── Category → domain mapping (mirrors CATEGORY_GROUPS in complianceCategories.ts) ──
_CATEGORY_DOMAIN: dict[str, str] = {}


_DOMAIN_LABELS: dict[str, str] = {
    "labor": "Labor",
    "supplementary": "Supplementary",
    "healthcare": "Healthcare",
    "oncology": "Oncology",
    "medical_compliance": "Medical Compliance",
    "manufacturing": "Manufacturing",
}


_CATEGORY_LABELS: dict[str, str] = {
    "minimum_wage": "Minimum Wage", "overtime": "Overtime", "sick_leave": "Sick Leave",
    "meal_breaks": "Meal & Rest Breaks", "pay_frequency": "Pay Frequency", "final_pay": "Final Pay",
    "minor_work_permit": "Minor Work Permits", "scheduling_reporting": "Scheduling & Reporting Time",
    "leave": "Leave", "workplace_safety": "Workplace Safety", "workers_comp": "Workers' Comp",
    "anti_discrimination": "Anti-Discrimination", "business_license": "Business License",
    "tax_rate": "Tax Rate", "posting_requirements": "Posting Requirements",
    "hipaa_privacy": "HIPAA Privacy & Security", "billing_integrity": "Billing & Financial Integrity",
    "clinical_safety": "Clinical & Patient Safety", "healthcare_workforce": "Healthcare Workforce",
    "corporate_integrity": "Corporate Integrity & Ethics", "research_consent": "Research & Informed Consent",
    "state_licensing": "State Licensing & Scope", "emergency_preparedness": "Emergency Preparedness",
    "radiation_safety": "Radiation Safety", "chemotherapy_handling": "Chemotherapy & Hazardous Drugs",
    "tumor_registry": "Tumor Registry Reporting", "oncology_clinical_trials": "Oncology Clinical Trials",
    "oncology_patient_rights": "Oncology Patient Rights", "health_it": "Health IT & Interoperability",
    "quality_reporting": "Quality Reporting", "cybersecurity": "Cybersecurity",
    "environmental_safety": "Environmental Safety", "pharmacy_drugs": "Pharmacy & Controlled Substances",
    "payer_relations": "Payer Relations", "reproductive_behavioral": "Reproductive & Behavioral Health",
    "pediatric_vulnerable": "Pediatric & Vulnerable Populations", "telehealth": "Telehealth & Digital Health",
    "medical_devices": "Medical Device Safety", "transplant_organ": "Transplant & Organ Procurement",
    "antitrust": "Healthcare Antitrust", "tax_exempt": "Tax-Exempt Compliance",
    "language_access": "Language Access & Civil Rights", "records_retention": "Records Retention",
    "marketing_comms": "Marketing & Communications", "emerging_regulatory": "Emerging Regulatory",
    "process_safety": "Process Safety Management", "environmental_compliance": "Environmental & Emissions",
    "chemical_safety": "Chemical & Hazardous Materials", "machine_safety": "Machine & Equipment Safety",
    "industrial_hygiene": "Industrial Hygiene & Exposure", "trade_compliance": "Import/Export & Trade",
    "product_safety": "Product Safety & Standards", "labor_relations": "Labor Relations",
    "quality_systems": "Quality Management Systems", "supply_chain": "Supply Chain & Procurement",
}


DOMAIN_CATEGORIES = {
    "healthcare": sorted(HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES | MEDICAL_COMPLIANCE_CATEGORIES),
    "hr": sorted(LABOR_CATEGORIES | SUPPLEMENTARY_CATEGORIES),
}


VALID_ORDER_STATUSES = {"requested", "quoted", "processing", "shipped", "delivered", "cancelled"}


_NOTIFICATION_LINK_MAP: dict[str, str] = {
    "incident": "/app/ir/incidents/{id}",
    "employee": "/app/matcha/employees/{id}",
    "offer_letter": "/app/matcha/offer-letters",
    "er_case": "/app/matcha/er-copilot/{id}",
    "handbook": "/app/matcha/handbook/{id}",
    "compliance_alert": "/app/matcha/compliance",
    "registration": "/app/admin/business-registrations",
}


_NOTIFICATION_SUBQUERIES: list[str] = [
    # New incidents
    """SELECT id::text, 'incident' AS type,
            title, incident_number AS subtitle,
            severity, status, company_id::text, created_at
       FROM ir_incidents WHERE created_at > NOW() - INTERVAL '30 days'""",
    # New employees
    """SELECT e.id::text, 'employee' AS type,
            e.first_name || ' ' || e.last_name AS title,
            e.job_title AS subtitle,
            NULL AS severity, 'onboarded' AS status, e.org_id::text AS company_id, e.created_at
       FROM employees e WHERE e.created_at > NOW() - INTERVAL '30 days'""",
    # Offer letters
    """SELECT id::text, 'offer_letter' AS type,
            candidate_name || ' - ' || position_title AS title,
            status AS subtitle,
            NULL AS severity, status, company_id::text, created_at
       FROM offer_letters WHERE created_at > NOW() - INTERVAL '30 days'""",
    # ER cases
    """SELECT id::text, 'er_case' AS type,
            title, case_number AS subtitle,
            NULL AS severity, status, company_id::text, created_at
       FROM er_cases WHERE created_at > NOW() - INTERVAL '30 days'""",
    # Handbooks
    """SELECT id::text, 'handbook' AS type,
            title, status AS subtitle,
            NULL AS severity, status, company_id::text, created_at
       FROM handbooks WHERE created_at > NOW() - INTERVAL '30 days'""",
    # Compliance alerts
    """SELECT id::text, 'compliance_alert' AS type,
            title, message AS subtitle,
            severity, status, company_id::text, created_at
       FROM compliance_alerts WHERE created_at > NOW() - INTERVAL '30 days'""",
    # New company registrations
    """SELECT id::text, 'registration' AS type,
            name AS title, status AS subtitle,
            NULL AS severity, status, NULL AS company_id, created_at
       FROM companies WHERE created_at > NOW() - INTERVAL '30 days'""",
]


HEARTBEAT_INTERVAL_ADMIN = 10.0


_TIER_FEATURE_PRESETS: dict[str, dict] = {
    # Free / Resources tier: no paid features.
    "resources_free": {k: False for k in DEFAULT_COMPANY_FEATURES},
    # Matcha Lite: incidents only (matches what stripe_webhook flips on
    # checkout.session.completed for matcha_lite — see stripe_webhook.py
    # line ~214). Don't add `employees` here or the post-tier-change shape
    # diverges from a real Lite signup.
    "matcha_lite": {**{k: False for k in DEFAULT_COMPANY_FEATURES}, "incidents": True},
    # Matcha-X (mid tier): incidents only here, same as Lite — employees/
    # discipline come from TIER_REQUIRED_FEATURES["matcha_x"] at read time
    # via merge_company_features, so don't add them to the preset.
    "matcha_x": {**{k: False for k in DEFAULT_COMPANY_FEATURES}, "incidents": True},
    # Bespoke / Platform: full feature set per DEFAULT_COMPANY_FEATURES, plus
    # the Pro-bundled gates (labor_relations union/CBA admin; handbook_pilot
    # conversational handbook/policy generation), which default off so they
    # must be force-set here for admin-created/-tier-changed Pro cos.
    "bespoke": {**dict(DEFAULT_COMPANY_FEATURES), "labor_relations": True,
                "handbook_pilot": True},
    # IR self-serve (Cap): incidents + employees + discipline.
    "ir_only_self_serve": {
        **{k: False for k in DEFAULT_COMPANY_FEATURES},
        "incidents": True, "employees": True, "discipline": True,
    },
    # Matcha Compliance (standalone): compliance itself plus the 4-pillar
    # bundle, forced True directly (no webhook involved in an admin-driven
    # tier change, unlike the Stripe-flipped self-serve path). Like Lite/X,
    # `matcha_compliance` is in _stripe_gated below, so admins can't PATCH a
    # company *into* it without payment (use a signup link — self-serve or a
    # comped invite token); this preset covers a same-tier reset-to-clean-
    # defaults and makes the tier a recognized PATCH target when downgrading
    # a compliance company to something else.
    "matcha_compliance": {
        **{k: False for k in DEFAULT_COMPANY_FEATURES},
        "compliance": True, "handbook_audit": True, "policies": True,
        "credential_templates": True, "employees": True,
    },
}


# ── Deal Flow — saved editor templates (DB-backed; admin-global, one row per tab) ──
# The deal builder is otherwise stateless. These two endpoints let a master-admin
# persist an editor tab's template — its prose blocks plus that tab's structured
# config (book volume tiers, broker margin tiers, one-pager per-tier pricing). The
# payload is opaque JSONB whose shape the frontend tab owns; on load each tab layers
# the saved payload over the hardcoded `*-defaults` (GET returns null when unsaved,
# so the tab falls back to defaults and behaves exactly as before).
_DEAL_TEMPLATE_KEYS = {"book", "full", "broker", "one_pager", "lite"}


_CAPPE_PAID_STATUSES = ("paid", "fulfilled")


def _row_to_registration(row) -> BusinessRegistrationResponse:
    sub: Optional[SubscriptionSummary] = None
    if row["sub_pack_id"]:
        sub = SubscriptionSummary(
            pack_id=row["sub_pack_id"],
            status=row["sub_status"],
            amount_cents=row["sub_amount_cents"],
            stripe_subscription_id=row["sub_stripe_sub_id"],
            stripe_customer_id=row["sub_stripe_customer_id"],
            current_period_end=row["sub_current_period_end"],
            canceled_at=row["sub_canceled_at"],
        )
    return BusinessRegistrationResponse(
        id=row["id"],
        company_name=row["company_name"],
        industry=row["industry"],
        healthcare_specialties=list(row["healthcare_specialties"] or []) or None,
        company_size=row["company_size"],
        owner_user_id=row["owner_user_id"],
        owner_email=row["owner_email"],
        owner_name=row["owner_name"],
        owner_phone=row["owner_phone"],
        owner_job_title=row["owner_job_title"],
        status=row["status"] or "approved",
        rejection_reason=row["rejection_reason"],
        approved_at=row["approved_at"],
        approved_by_email=row["approved_by_email"],
        created_at=row["created_at"],
        signup_source=row["signup_source"],
        is_personal=bool(row["is_personal"]),
        is_suspended=bool(row["is_suspended"]),
        deleted_at=row["deleted_at"],
        subscription=sub,
    )


def _tier_filter_clause(tier: Optional[str]) -> tuple[str, list]:
    """Translate a tier chip ('free'|'lite'|'x'|'compliance'|'platform'|'personal') to SQL.

    Personal is by `is_personal=true` (lives on companies). The others
    are by `signup_source` value; platform covers bespoke + legacy NULL rows
    AND excludes personal workspaces.
    """
    if tier == "free":
        return " AND comp.signup_source = 'resources_free'", []
    if tier == "lite":
        return " AND comp.signup_source = 'matcha_lite'", []
    if tier == "x":
        return " AND comp.signup_source = 'matcha_x'", []
    if tier == "compliance":
        return " AND comp.signup_source = 'matcha_compliance'", []
    if tier == "platform":
        return " AND (comp.signup_source IN ('bespoke') OR comp.signup_source IS NULL) AND comp.is_personal IS NOT TRUE", []
    if tier == "personal":
        return " AND comp.is_personal = TRUE", []
    return "", []


def _slugify_broker_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug[:120] or "broker"


def _validate_broker_enums(*, status_value: Optional[str] = None, support_routing: Optional[str] = None,
                           billing_mode: Optional[str] = None, invoice_owner: Optional[str] = None,
                           contract_status: Optional[str] = None, link_status: Optional[str] = None,
                           post_termination_mode: Optional[str] = None, branding_mode: Optional[str] = None,
                           transition_status: Optional[str] = None,
                           data_handoff_status: Optional[str] = None,
                           link_transition_state: Optional[str] = None):
    if status_value is not None and status_value not in VALID_BROKER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid broker status '{status_value}'")
    if support_routing is not None and support_routing not in VALID_BROKER_SUPPORT_ROUTING:
        raise HTTPException(status_code=400, detail=f"Invalid support_routing '{support_routing}'")
    if billing_mode is not None and billing_mode not in VALID_BROKER_BILLING_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid billing_mode '{billing_mode}'")
    if invoice_owner is not None and invoice_owner not in VALID_INVOICE_OWNERS:
        raise HTTPException(status_code=400, detail=f"Invalid invoice_owner '{invoice_owner}'")
    if contract_status is not None and contract_status not in VALID_BROKER_CONTRACT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid contract status '{contract_status}'")
    if link_status is not None and link_status not in VALID_BROKER_LINK_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid link status '{link_status}'")
    if post_termination_mode is not None and post_termination_mode not in VALID_POST_TERMINATION_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid post_termination_mode '{post_termination_mode}'")
    if branding_mode is not None and branding_mode not in VALID_BROKER_BRANDING_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid branding_mode '{branding_mode}'")
    if transition_status is not None and transition_status not in VALID_TRANSITION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid transition status '{transition_status}'")
    if data_handoff_status is not None and data_handoff_status not in VALID_DATA_HANDOFF_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid data_handoff_status '{data_handoff_status}'")
    if link_transition_state is not None and link_transition_state not in VALID_LINK_TRANSITION_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid link transition state '{link_transition_state}'")


def _transition_state_for(mode: str, transition_status: str) -> str:
    if transition_status == "cancelled":
        return "none"
    if mode == "matcha_managed":
        return "matcha_managed"
    if transition_status == "planned":
        return "planned"
    if transition_status == "in_progress":
        return "in_progress"
    if transition_status == "completed":
        return "completed"
    return "none"


def _link_status_for(mode: str, transition_status: str, current_status: str) -> str:
    if transition_status == "planned":
        if mode in {"convert_to_direct", "matcha_managed"}:
            return "grace"
        if mode in {"transfer_to_broker", "sunset"}:
            return "suspending"
    if transition_status == "in_progress":
        if mode in {"convert_to_direct", "matcha_managed"}:
            return "grace"
        if mode in {"transfer_to_broker", "sunset"}:
            return "suspending"
    if transition_status == "completed":
        if mode == "transfer_to_broker":
            return "transferred"
        if mode in {"convert_to_direct", "sunset"}:
            return "terminated"
        if mode == "matcha_managed":
            return "grace"
    if transition_status == "cancelled":
        return "active" if current_status in {"grace", "suspending"} else current_status
    return current_status


def _normalize_city_input(city: str) -> str:
    normalized = city.lower().strip()
    normalized = normalized.replace(".", "")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _is_non_city_jurisdiction(city: Optional[str]) -> bool:
    token = (city or "").strip().lower()
    return token == "" or token.startswith("_county_")


def _city_display(city: str) -> str:
    return " ".join(part.capitalize() for part in city.split())


def _canonicalize_city_fallback(city: str, state: str) -> str:
    state_key = state.upper().strip()[:2]
    city_key = _normalize_city_input(city)
    city_key = FALLBACK_CITY_ALIASES.get((state_key, city_key), city_key)

    allowed = FALLBACK_ALLOWED_CITIES_BY_STATE.get(state_key, set())
    if city_key in allowed:
        return city_key

    suggestion = None
    if allowed:
        suggestion_match = difflib.get_close_matches(city_key, sorted(allowed), n=1, cutoff=0.72)
        suggestion = suggestion_match[0] if suggestion_match else None

    suggestion_msg = f" Did you mean '{_city_display(suggestion)}'?" if suggestion else ""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unsupported city '{city.strip()}' for state {state_key}."
            f"{suggestion_msg}"
        ),
    )


async def _canonicalize_city_from_reference(conn: asyncpg.Connection, city: str, state: str) -> str:
    state_key = state.upper().strip()[:2]
    city_key = _normalize_city_input(city)
    city_key = FALLBACK_CITY_ALIASES.get((state_key, city_key), city_key)

    match = await conn.fetchrow(
        """
        SELECT city
        FROM jurisdiction_reference
        WHERE state = $2
          AND (
            city = $1
            OR EXISTS (
              SELECT 1
              FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
              WHERE LOWER(alias) = $1
            )
          )
        LIMIT 1
        """,
        city_key,
        state_key,
    )
    if match:
        return match["city"]

    candidates = await conn.fetch(
        "SELECT city FROM jurisdiction_reference WHERE state = $1 ORDER BY city",
        state_key,
    )
    candidate_cities = [row["city"] for row in candidates]
    suggestion = None
    if candidate_cities:
        suggestion_match = difflib.get_close_matches(city_key, candidate_cities, n=1, cutoff=0.72)
        suggestion = suggestion_match[0] if suggestion_match else None

    suggestion_msg = f" Did you mean '{_city_display(suggestion)}'?" if suggestion else ""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            f"Unsupported city '{city.strip()}' for state {state_key}."
            f"{suggestion_msg}"
        ),
    )


async def _canonicalize_city(conn: asyncpg.Connection, city: str, state: str) -> str:
    try:
        return await _canonicalize_city_from_reference(conn, city, state)
    except asyncpg.UndefinedTableError:
        return _canonicalize_city_fallback(city, state)


async def _is_supported_city(conn: asyncpg.Connection, city: str, state: str) -> bool:
    state_key = state.upper().strip()[:2]
    city_key = _normalize_city_input(city)
    city_key = FALLBACK_CITY_ALIASES.get((state_key, city_key), city_key)

    try:
        exists = await conn.fetchval(
            """
            SELECT 1
            FROM jurisdiction_reference
            WHERE state = $2
              AND (
                city = $1
                OR EXISTS (
                  SELECT 1
                  FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
                  WHERE LOWER(alias) = $1
                )
              )
            LIMIT 1
            """,
            city_key,
            state_key,
        )
        return bool(exists)
    except asyncpg.UndefinedTableError:
        return city_key in FALLBACK_ALLOWED_CITIES_BY_STATE.get(state_key, set())


async def _get_required_categories(force_refresh: bool = False) -> list[str]:
    """Slugs of every seeded compliance category, DB-derived and cached.

    Categories only change via migration, so a simple process-lifetime cache is
    enough — pass `force_refresh=True` (wired to the `bust` query param on
    `/jurisdictions/data-overview`) to pick up a just-applied migration without a
    restart. A TTL fallback also refetches once the cache is older than
    `_REQUIRED_CATEGORIES_CACHE_TTL`, bounding staleness across uvicorn's
    multiple worker processes even when a `bust` request lands on a different
    worker than the one that just applied a migration. Falls back to the
    historical hardcoded list ONLY on a DB error, and always logs a warning
    when that happens so the fallback going stale (as `REQUIRED_CATEGORIES`
    silently did) is never silent again.
    """
    import time

    global _required_categories_cache, _required_categories_cached_at
    now = time.monotonic()
    if (
        not force_refresh
        and _required_categories_cache is not None
        and (now - _required_categories_cached_at) < _REQUIRED_CATEGORIES_CACHE_TTL
    ):
        return _required_categories_cache

    try:
        async with get_connection() as conn:
            rows = await conn.fetch("SELECT slug FROM compliance_categories ORDER BY sort_order, slug")
        slugs = [r["slug"] for r in rows]
        if not slugs:
            raise ValueError("compliance_categories table returned zero rows")
        _required_categories_cache = slugs
        _required_categories_cached_at = now
        return slugs
    except Exception:
        logger.warning(
            "Failed to load compliance_categories from DB; falling back to hardcoded category list",
            exc_info=True,
        )
        return list(_REQUIRED_CATEGORIES_FALLBACK)


def _row_metadata(value) -> dict:
    """asyncpg returns jsonb columns as raw strings (no pool codec); coerce to dict."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _eval_iso(value) -> Optional[str]:
    """ISO-format a timestamp. The `fmt_date` helpers elsewhere in this module are
    nested inside their handlers, so the eval endpoints carry their own."""
    return value.isoformat() if value else None


def _eval_json(value):
    """asyncpg has no jsonb codec on this pool — jsonb columns arrive as raw text."""
    return json.loads(value) if isinstance(value, str) else value


def _jurisdiction_label(label: Optional[str], state: Optional[str]) -> Optional[str]:
    if label and state and label != state:
        return f"{label}, {state}"
    return label


def _to_sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _format_city_label(city: str) -> str:
    if not city:
        return city
    parts = city.replace("_", " ").split()
    return " ".join(part.capitalize() for part in parts)


def _phase_percent(phase: str) -> int:
    mapping = {
        "started": 5,
        "researching": 20,
        "retrying": 24,
        "confidence_retry": 30,
        "confidence_gate": 38,
        "processing": 48,
        "scanning": 62,
        "legislation": 70,
        "syncing": 82,
        "verifying": 90,
        "poster_updated": 94,
        "poster_alerts": 96,
        "completed": 100,
        "error": 100,
    }
    return mapping.get(phase, 35)


def _source_confidence(source_url: Optional[str], source_name: Optional[str]) -> float:
    from app.core.services.jurisdiction_context import extract_domain

    domain = extract_domain(source_url or "")
    if not domain:
        return 0.0

    score = 0.7
    if domain.endswith(".gov"):
        score = 0.98
    elif domain.endswith(".us"):
        score = 0.95
    elif domain.endswith(".org"):
        score = 0.8

    source_label = (source_name or "").lower()
    if "department of labor" in source_label or "labor commissioner" in source_label:
        score = max(score, 0.97)
    elif "city of" in source_label or "county of" in source_label or "state of" in source_label:
        score = max(score, 0.93)

    return min(score, 0.99)


def _requirement_confidence(req: dict[str, Any]) -> float:
    return _source_confidence(req.get("source_url"), req.get("source_name"))


def _legislation_confidence(item: dict[str, Any]) -> float:
    raw = item.get("confidence")
    try:
        parsed = float(raw) if raw is not None else 0.0
    except (TypeError, ValueError):
        parsed = 0.0
    return max(parsed, _source_confidence(item.get("source_url"), item.get("source_name")))


async def _run_jurisdiction_check_events(
    jurisdiction_id: UUID,
    inline_healthcare_research: bool = False,
) -> AsyncGenerator[dict[str, Any], None]:
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.services.compliance_service import (
        _upsert_jurisdiction_requirements,
        _upsert_jurisdiction_legislation,
        _normalize_category,
        _normalize_requirement_categories,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _filter_requirements_for_company,
        _sync_requirements_to_location,
        _create_alert,
        score_verification_confidence,
        _compute_requirement_key,
        _normalize_title_key,
        REQUIRED_LABOR_CATEGORIES,
        _missing_required_categories,
        _lookup_has_local_ordinance,
        _refresh_repository_missing_categories,
        _research_healthcare_requirements_for_jurisdiction,
        _research_oncology_requirements_for_jurisdiction,
        ONCOLOGY_CATEGORIES,
    )
    from app.core.models.compliance import VerificationResult

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT * FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    city, state, county = j["city"], j["state"], j["county"]
    location_label = f"{_format_city_label(city)}, {state}"

    yield {"type": "started", "location": location_label}
    yield {"type": "researching", "message": f"Researching requirements for {location_label}..."}

    service = get_gemini_compliance_service()
    async with get_connection() as conn:
        used_repository = False
        has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
        try:
            preemption_rows = await conn.fetch(
                "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                state.upper(),
            )
            preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
        except asyncpg.UndefinedTableError:
            preemption_rules = {}

        async def _prepare_requirements_for_sync(requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
            prepared = [dict(req) for req in requirements]
            if has_local_ordinance is False:
                prepared = _filter_city_level_requirements(prepared, state)
            _normalize_requirement_categories(prepared)
            prepared = await _filter_with_preemption(conn, prepared, state)
            return prepared

        city_key = _normalize_city_input(city)
        city_jurisdiction_rows = await conn.fetch(
            """
            SELECT
                j.id,
                j.city,
                j.state,
                j.requirement_count,
                j.legislation_count,
                j.last_verified_at,
                j.created_at,
                COUNT(bl.id) AS location_count
            FROM jurisdictions j
            LEFT JOIN business_locations bl ON bl.jurisdiction_id = j.id AND bl.is_active = true
            WHERE j.state = $1
              AND j.city <> ''
              AND j.city NOT LIKE '_county_%'
            GROUP BY j.id
            """,
            state,
        )
        same_city_rows = [
            row for row in city_jurisdiction_rows
            if _normalize_city_input(row["city"]) == city_key
        ]
        if not same_city_rows:
            j_dict = dict(j)
            same_city_rows = [{
                "id": j_dict["id"],
                "city": j_dict["city"],
                "state": j_dict["state"],
                "requirement_count": j_dict.get("requirement_count", 0),
                "legislation_count": j_dict.get("legislation_count", 0),
                "last_verified_at": j_dict.get("last_verified_at"),
                "created_at": j_dict.get("created_at"),
                "location_count": 0,
            }]

        def _canonical_priority(row):
            return (
                (row["requirement_count"] or 0) + (row["legislation_count"] or 0),
                row["location_count"] or 0,
                1 if row["last_verified_at"] is not None else 0,
                row["last_verified_at"] or datetime.min,
                1 if row["created_at"] is not None else 0,
                row["created_at"] or datetime.min,
            )

        canonical_row = max(same_city_rows, key=_canonical_priority)
        canonical_jurisdiction_id = canonical_row["id"]
        duplicate_jurisdiction_ids = [
            row["id"] for row in same_city_rows
            if row["id"] != canonical_jurisdiction_id
        ]
        city_group_ids = [canonical_jurisdiction_id, *duplicate_jurisdiction_ids]

        if duplicate_jurisdiction_ids:
            moved_locations = await conn.fetchval(
                """
                WITH moved AS (
                    UPDATE business_locations
                    SET jurisdiction_id = $1
                    WHERE jurisdiction_id = ANY($2::uuid[])
                    RETURNING id
                )
                SELECT COUNT(*) FROM moved
                """,
                canonical_jurisdiction_id,
                duplicate_jurisdiction_ids,
            )
            moved_children = await conn.fetchval(
                """
                WITH moved AS (
                    UPDATE jurisdictions
                    SET parent_id = $1
                    WHERE parent_id = ANY($2::uuid[])
                      AND id <> $1
                    RETURNING id
                )
                SELECT COUNT(*) FROM moved
                """,
                canonical_jurisdiction_id,
                duplicate_jurisdiction_ids,
            )
            moved_location_count = int(moved_locations or 0)
            moved_child_count = int(moved_children or 0)
            if moved_location_count or moved_child_count:
                yield {
                    "type": "syncing",
                    "message": (
                        "Aligned duplicate city jurisdictions to canonical source: "
                        f"{moved_location_count} location(s), {moved_child_count} child node(s) relinked."
                    ),
                }
            if canonical_jurisdiction_id != jurisdiction_id:
                yield {
                    "type": "syncing",
                    "message": (
                        f"Using canonical jurisdiction record for {_format_city_label(city)}, {state}."
                    ),
                }

        existing_jurisdiction_rows = await conn.fetch(
            "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = ANY($1::uuid[])",
            city_group_ids,
        )
        for row in existing_jurisdiction_rows:
            row_dict = dict(row)
            normalized_category = _normalize_category(row_dict.get("category")) or row_dict.get("category")
            row_dict["category"] = normalized_category
            normalized_key = _compute_requirement_key(row_dict)
            if (
                normalized_category != row["category"]
                or normalized_key != row["requirement_key"]
            ):
                try:
                    await conn.execute(
                        """
                        UPDATE jurisdiction_requirements
                        SET category = $2, requirement_key = $3, updated_at = NOW()
                        WHERE id = $1
                        """,
                        row["id"],
                        normalized_category,
                        normalized_key,
                    )
                except asyncpg.UniqueViolationError:
                    await conn.execute(
                        "DELETE FROM jurisdiction_requirements WHERE id = $1",
                        row["id"],
                    )

        existing_jurisdiction_rows = await conn.fetch(
            "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = ANY($1::uuid[])",
            city_group_ids,
        )
        existing_requirements = [_jurisdiction_row_to_dict(dict(row)) for row in existing_jurisdiction_rows]
        existing_requirements = await _prepare_requirements_for_sync(existing_requirements)
        present_categories = {
            _normalize_category(req.get("category")) or req.get("category")
            for req in existing_requirements
            if req.get("category")
        }
        research_categories = sorted(
            cat for cat in REQUIRED_LABOR_CATEGORIES
            if cat not in present_categories
        ) or None
        if research_categories:
            yield {
                "type": "researching",
                "message": (
                    f"Filling missing coverage for {location_label}: "
                    f"{', '.join(research_categories)}."
                ),
            }

        best_requirements: dict[str, tuple[float, dict[str, Any]]] = {}
        for pass_index in range(MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1):
            if pass_index > 0:
                # Only re-research categories that still have low-confidence items
                low_conf_cats = {
                    _normalize_category(req.get("category")) or req.get("category")
                    for confidence, req in best_requirements.values()
                    if confidence < STRICT_CONFIDENCE_THRESHOLD
                }
                if not low_conf_cats:
                    break
                retry_categories = sorted(low_conf_cats)
                yield {
                    "type": "confidence_retry",
                    "message": (
                        f"Low-confidence requirements found. Cross-checking {_format_city_label(city)} "
                        f"against {state} sources — {len(retry_categories)} categor{'y' if len(retry_categories) == 1 else 'ies'} "
                        f"(pass {pass_index + 1}/{MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1})..."
                    ),
                }
            else:
                retry_categories = research_categories

            research_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def _on_retry(attempt: int, error_text: str):
                reason = f" Reason: {error_text}" if error_text else ""
                research_queue.put_nowait(
                    {
                        "type": "retrying",
                        "message": (
                            f"Retrying research (attempt {attempt + 1})..."
                            f"{reason[:220]}"
                        ),
                    }
                )

            research_task = asyncio.create_task(
                service.research_location_compliance(
                    city=city,
                    state=state,
                    county=county,
                    categories=retry_categories,
                    preemption_rules=preemption_rules,
                    has_local_ordinance=has_local_ordinance,
                    on_retry=_on_retry,
                )
            )
            try:
                while not research_task.done():
                    while not research_queue.empty():
                        yield research_queue.get_nowait()
                    done, _ = await asyncio.wait({research_task}, timeout=8)
                    if done:
                        break
                    yield {"type": "heartbeat"}
            except asyncio.CancelledError:
                if not research_task.done():
                    research_task.cancel()
                raise

            while not research_queue.empty():
                yield research_queue.get_nowait()

            pass_requirements = research_task.result() or []
            if retry_categories and existing_requirements:
                target_set = set(retry_categories)
                preserved = [
                    req for req in existing_requirements
                    if (_normalize_category(req.get("category")) or req.get("category")) not in target_set
                ]
                pass_requirements = preserved + pass_requirements
            pass_requirements = await _prepare_requirements_for_sync(pass_requirements)

            for req in pass_requirements:
                req_key = _compute_requirement_key(req)
                confidence = _requirement_confidence(req)
                existing = best_requirements.get(req_key)
                if existing is None or confidence > existing[0]:
                    best_requirements[req_key] = (confidence, req)

            if best_requirements:
                low_count = sum(
                    1 for confidence, _ in best_requirements.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
                )
                yield {
                    "type": "confidence_gate",
                    "message": (
                        f"Requirement confidence gate: {low_count} item(s) below "
                        f"{int(STRICT_CONFIDENCE_THRESHOLD * 100)}% after pass {pass_index + 1}."
                    ),
                }
                if low_count == 0:
                    break

        requirements = [req for _, req in best_requirements.values()]
        requirements = await _prepare_requirements_for_sync(requirements)
        missing_categories = _missing_required_categories(requirements)
        if requirements and missing_categories:
            yield {
                "type": "repository_refresh",
                "jurisdiction_id": str(canonical_jurisdiction_id),
                "missing_categories": missing_categories,
                "message": (
                    "Coverage is still missing "
                    f"{', '.join(missing_categories)}. Running source-aware repository refresh for "
                    f"{location_label}."
                ),
            }

            refresh_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def _on_partial_refresh_retry(attempt: int, error_text: str):
                reason = f" Reason: {error_text}" if error_text else ""
                refresh_queue.put_nowait(
                    {
                        "type": "retrying",
                        "message": (
                            f"Retrying repository refresh (attempt {attempt + 1})..."
                            f"{reason[:220]}"
                        ),
                    }
                )

            partial_refresh_task = asyncio.create_task(
                _refresh_repository_missing_categories(
                    conn,
                    service,
                    jurisdiction_id=canonical_jurisdiction_id,
                    city=city,
                    state=state,
                    county=county,
                    has_local_ordinance=has_local_ordinance,
                    current_requirements=requirements,
                    missing_categories=missing_categories,
                    on_retry=_on_partial_refresh_retry,
                )
            )
            try:
                while not partial_refresh_task.done():
                    while not refresh_queue.empty():
                        yield refresh_queue.get_nowait()
                    done, _ = await asyncio.wait({partial_refresh_task}, timeout=8)
                    if done:
                        break
                    yield {"type": "heartbeat"}
            except asyncio.CancelledError:
                if not partial_refresh_task.done():
                    partial_refresh_task.cancel()
                raise

            while not refresh_queue.empty():
                yield refresh_queue.get_nowait()

            refreshed_partial = partial_refresh_task.result() or requirements
            requirements = await _prepare_requirements_for_sync(refreshed_partial)
            missing_after_partial = _missing_required_categories(requirements)
            if missing_after_partial:
                yield {
                    "type": "repository_only",
                    "jurisdiction_id": str(canonical_jurisdiction_id),
                    "missing_categories": missing_after_partial,
                    "message": (
                        "Repository is still missing "
                        f"{', '.join(missing_after_partial)} after refresh."
                    ),
                }
            else:
                yield {
                    "type": "repository_refreshed",
                    "jurisdiction_id": str(canonical_jurisdiction_id),
                    "message": f"Repository refresh completed for {location_label}.",
                }

        low_conf_requirement_count = sum(
            1 for confidence, _ in best_requirements.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
        )

        if not requirements:
            missing_categories = sorted(REQUIRED_LABOR_CATEGORIES)
            yield {
                "type": "repository_refresh",
                "jurisdiction_id": str(canonical_jurisdiction_id),
                "missing_categories": missing_categories,
                "message": (
                    "No requirements returned from direct research. Running source-aware repository refresh for "
                    f"{location_label} ({', '.join(missing_categories)})."
                ),
            }

            refresh_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

            def _on_refresh_retry(attempt: int, error_text: str):
                reason = f" Reason: {error_text}" if error_text else ""
                refresh_queue.put_nowait(
                    {
                        "type": "retrying",
                        "message": (
                            f"Retrying repository refresh (attempt {attempt + 1})..."
                            f"{reason[:220]}"
                        ),
                    }
                )

            refresh_task = asyncio.create_task(
                _refresh_repository_missing_categories(
                    conn,
                    service,
                    jurisdiction_id=canonical_jurisdiction_id,
                    city=city,
                    state=state,
                    county=county,
                    has_local_ordinance=has_local_ordinance,
                    current_requirements=existing_requirements,
                    missing_categories=missing_categories,
                    on_retry=_on_refresh_retry,
                )
            )
            try:
                while not refresh_task.done():
                    while not refresh_queue.empty():
                        yield refresh_queue.get_nowait()
                    done, _ = await asyncio.wait({refresh_task}, timeout=8)
                    if done:
                        break
                    yield {"type": "heartbeat"}
            except asyncio.CancelledError:
                if not refresh_task.done():
                    refresh_task.cancel()
                raise

            while not refresh_queue.empty():
                yield refresh_queue.get_nowait()

            refreshed_requirements = refresh_task.result() or []
            if refreshed_requirements:
                requirements = await _prepare_requirements_for_sync(refreshed_requirements)
                yield {
                    "type": "repository_refreshed",
                    "jurisdiction_id": str(canonical_jurisdiction_id),
                    "message": f"Repository refresh produced {len(requirements)} requirement(s).",
                }

        if not requirements:
            cached_rows = await conn.fetch(
                """
                SELECT * FROM jurisdiction_requirements
                WHERE jurisdiction_id = ANY($1::uuid[])
                ORDER BY category
                """,
                city_group_ids,
            )
            if cached_rows:
                requirements = [_jurisdiction_row_to_dict(dict(row)) for row in cached_rows]
                requirements = await _prepare_requirements_for_sync(requirements)
                used_repository = True
                logger.warning(
                    "Falling back to stale repository data (%d cached requirements)", len(requirements)
                )
                yield {"type": "fallback", "message": "Using cached data (live research unavailable)"}

        if not requirements:
            yield {
                "type": "completed",
                "location": location_label,
                "new": 0,
                "updated": 0,
                "alerts": 0,
                "low_confidence": 0,
                "low_confidence_requirements": 0,
                "low_confidence_legislation": 0,
                "low_confidence_changes": 0,
            }
            return

        yield {"type": "processing", "message": f"Processing {len(requirements)} requirements..."}

        if not used_repository:
            await _upsert_jurisdiction_requirements(conn, canonical_jurisdiction_id, requirements)

        new_count = len(requirements)
        for req in requirements:
            req_conf = _requirement_confidence(req)
            yield {
                "type": "result",
                "status": "new",
                "message": req.get("title", ""),
                "confidence": round(req_conf, 2),
            }

        yield {"type": "scanning", "message": "Scanning for upcoming legislation..."}
        best_legislation: dict[str, tuple[float, dict[str, Any]]] = {}
        try:
            for pass_index in range(MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1):
                if pass_index > 0:
                    yield {
                        "type": "confidence_retry",
                        "message": (
                            f"Low-confidence legislation found. Re-scanning authoritative sources "
                            f"(pass {pass_index + 1}/{MAX_CONFIDENCE_REFETCH_ATTEMPTS + 1})..."
                        ),
                    }

                leg_task = asyncio.create_task(
                    service.scan_upcoming_legislation(
                        city=city,
                        state=state,
                        county=county,
                        current_requirements=[dict(req) for req in requirements],
                    )
                )
                try:
                    while not leg_task.done():
                        done, _ = await asyncio.wait({leg_task}, timeout=8)
                        if done:
                            break
                        yield {"type": "heartbeat"}
                except asyncio.CancelledError:
                    if not leg_task.done():
                        leg_task.cancel()
                    raise

                pass_legislation = leg_task.result() or []
                for item in pass_legislation:
                    leg_key = item.get("legislation_key") or _normalize_title_key(item.get("title", ""))
                    if not leg_key:
                        continue
                    item["legislation_key"] = leg_key
                    confidence = _legislation_confidence(item)
                    existing = best_legislation.get(leg_key)
                    if existing is None or confidence > existing[0]:
                        best_legislation[leg_key] = (confidence, item)

                if best_legislation:
                    low_count = sum(
                        1 for confidence, _ in best_legislation.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
                    )
                    yield {
                        "type": "confidence_gate",
                        "message": (
                            f"Legislation confidence gate: {low_count} item(s) below "
                            f"{int(STRICT_CONFIDENCE_THRESHOLD * 100)}% after pass {pass_index + 1}."
                        ),
                    }
                    if low_count == 0:
                        break
        except Exception as exc:
            logger.error("Jurisdiction legislation scan error: %s", exc)

        legislation_items = [item for _, item in best_legislation.values()]
        low_conf_legislation_count = sum(
            1 for confidence, _ in best_legislation.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
        )

        if legislation_items:
            await _upsert_jurisdiction_legislation(conn, canonical_jurisdiction_id, legislation_items)
            yield {
                "type": "legislation",
                "message": (
                    f"Found {len(legislation_items)} upcoming legislative change(s); "
                    f"{low_conf_legislation_count} below confidence gate."
                ),
            }

        linked_locations = await conn.fetch(
            """
            SELECT id, company_id
            FROM business_locations
            WHERE jurisdiction_id = ANY($1::uuid[]) AND is_active = true
            """,
            city_group_ids,
        )

        total_alerts = 0
        total_updated = 0
        verified_changes: dict[tuple[str, Any, Any], tuple[float, VerificationResult]] = {}

        if linked_locations:
            yield {"type": "syncing", "message": f"Syncing to {len(linked_locations)} location(s)..."}
            for loc in linked_locations:
                try:
                    location_requirements = await _filter_requirements_for_company(
                        conn,
                        loc["company_id"],
                        requirements,
                    )
                    sync_result = await _sync_requirements_to_location(
                        conn,
                        loc["id"],
                        loc["company_id"],
                        location_requirements,
                        create_alerts=True,
                    )
                    total_alerts += sync_result["alerts"]
                    total_updated += sync_result["updated"]

                    for change_info in sync_result["changes_to_verify"]:
                        req = change_info["req"]
                        existing = change_info["existing"]
                        old_val = change_info["old_value"]
                        new_val = change_info["new_value"]
                        cat = req.get("category", "")

                        cache_key = (cat, old_val, new_val)
                        if cache_key not in verified_changes:
                            try:
                                verify_task = asyncio.create_task(
                                    service.verify_compliance_change_adaptive(
                                        category=cat,
                                        title=req.get("title", ""),
                                        jurisdiction_name=req.get("jurisdiction_name", ""),
                                        old_value=old_val,
                                        new_value=new_val,
                                    )
                                )
                                try:
                                    while not verify_task.done():
                                        done, _ = await asyncio.wait({verify_task}, timeout=8)
                                        if done:
                                            break
                                        yield {"type": "heartbeat"}
                                except asyncio.CancelledError:
                                    if not verify_task.done():
                                        verify_task.cancel()
                                    raise

                                verification = verify_task.result()
                                confidence = max(
                                    score_verification_confidence(verification.sources),
                                    verification.confidence,
                                )
                                for retry_index in range(MAX_CONFIDENCE_REFETCH_ATTEMPTS):
                                    if confidence >= STRICT_CONFIDENCE_THRESHOLD:
                                        break
                                    yield {
                                        "type": "verifying",
                                        "message": (
                                            f"Confidence {confidence:.2f} for '{req.get('title', 'change')}' "
                                            f"is below {STRICT_CONFIDENCE_THRESHOLD:.2f}; "
                                            f"re-verifying ({retry_index + 1}/{MAX_CONFIDENCE_REFETCH_ATTEMPTS})..."
                                        ),
                                    }
                                    retry_task = asyncio.create_task(
                                        service.verify_compliance_change_adaptive(
                                            category=cat,
                                            title=req.get("title", ""),
                                            jurisdiction_name=req.get("jurisdiction_name", ""),
                                            old_value=old_val,
                                            new_value=new_val,
                                        )
                                    )
                                    try:
                                        while not retry_task.done():
                                            done, _ = await asyncio.wait({retry_task}, timeout=8)
                                            if done:
                                                break
                                            yield {"type": "heartbeat"}
                                    except asyncio.CancelledError:
                                        if not retry_task.done():
                                            retry_task.cancel()
                                        raise

                                    retry_verification = retry_task.result()
                                    retry_confidence = max(
                                        score_verification_confidence(retry_verification.sources),
                                        retry_verification.confidence,
                                    )
                                    if retry_confidence > confidence:
                                        confidence = retry_confidence
                                        verification = retry_verification
                            except Exception as exc:
                                logger.error("Verification failed: %s", exc)
                                verification = VerificationResult(
                                    confirmed=False,
                                    confidence=0.0,
                                    sources=[],
                                    explanation="Verification unavailable",
                                )
                                confidence = 0.5

                            verified_changes[cache_key] = (confidence, verification)

                        confidence, verification = verified_changes[cache_key]
                        change_msg = f"Value changed from {old_val} to {new_val}."
                        if req.get("description"):
                            change_msg += f" {req['description']}"

                        if confidence >= STRICT_CONFIDENCE_THRESHOLD:
                            total_alerts += 1
                            await _create_alert(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                existing["id"],
                                f"Compliance Change: {req.get('title')}",
                                change_msg,
                                "warning",
                                req.get("category"),
                                source_url=req.get("source_url"),
                                source_name=req.get("source_name"),
                                alert_type="change",
                                confidence_score=round(confidence, 2),
                                verification_sources=verification.sources,
                                metadata={
                                    "source": "jurisdiction_sync",
                                    "verification_explanation": verification.explanation,
                                },
                            )
                        elif confidence >= 0.6:
                            total_alerts += 1
                            await _create_alert(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                existing["id"],
                                f"Pending Verification: {req.get('title')}",
                                change_msg,
                                "info",
                                req.get("category"),
                                source_url=req.get("source_url"),
                                source_name=req.get("source_name"),
                                alert_type="change",
                                confidence_score=round(confidence, 2),
                                verification_sources=verification.sources,
                                metadata={
                                    "source": "jurisdiction_sync",
                                    "verification_explanation": verification.explanation,
                                    "unverified": True,
                                },
                            )
                        elif confidence >= 0.3:
                            total_alerts += 1
                            await _create_alert(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                existing["id"],
                                f"Unverified: {req.get('title')}",
                                change_msg,
                                "info",
                                req.get("category"),
                                source_url=req.get("source_url"),
                                source_name=req.get("source_name"),
                                alert_type="change",
                                confidence_score=round(confidence, 2),
                                verification_sources=verification.sources,
                                metadata={
                                    "source": "jurisdiction_sync",
                                    "verification_explanation": verification.explanation,
                                    "unverified": True,
                                },
                            )
                        else:
                            logger.warning(
                                "Low confidence (%.2f) for change: %s, skipping alert",
                                confidence,
                                req.get("title"),
                            )

                    await conn.execute(
                        "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                        loc["id"],
                    )
                except Exception as exc:
                    logger.error("Failed to sync location %s: %s", loc["id"], exc)

        low_conf_change_count = sum(
            1 for confidence, _verification in verified_changes.values() if confidence < STRICT_CONFIDENCE_THRESHOLD
        )

        try:
            from app.core.services.poster_service import check_and_regenerate_poster, create_poster_update_alerts

            poster_result = await check_and_regenerate_poster(conn, canonical_jurisdiction_id)
            if poster_result and poster_result.get("status") == "generated":
                poster_version = poster_result.get("version", "?")
                yield {
                    "type": "poster_updated",
                    "message": f"Poster PDF regenerated (v{poster_version})",
                }
                alert_count = await create_poster_update_alerts(conn, canonical_jurisdiction_id)
                if alert_count:
                    total_alerts += alert_count
                    yield {
                        "type": "poster_alerts",
                        "message": f"Notified {alert_count} company(s) about poster update",
                    }
        except Exception as exc:
            logger.error("Poster regeneration check failed: %s", exc)

        total_low_confidence = low_conf_requirement_count + low_conf_legislation_count + low_conf_change_count
        if total_low_confidence > 0:
            yield {
                "type": "confidence_gate",
                "message": (
                    f"{total_low_confidence} item(s) remain below "
                    f"{int(STRICT_CONFIDENCE_THRESHOLD * 100)}% confidence after retries."
                ),
            }

        if inline_healthcare_research:
            try:
                yield {
                    "type": "repository_refresh",
                    "message": f"Researching healthcare-specific compliance for {location_label}...",
                }
                healthcare_result = await _research_healthcare_requirements_for_jurisdiction(
                    conn, canonical_jurisdiction_id
                )
                if healthcare_result.get("new", 0):
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        canonical_jurisdiction_id,
                    )
                    requirements = [
                        _jurisdiction_row_to_dict(dict(row)) for row in rows
                    ]
                    requirements = await _prepare_requirements_for_sync(requirements)
                    new_count = len(requirements)
                    if linked_locations:
                        yield {
                            "type": "syncing",
                            "message": (
                                f"Syncing healthcare-specific updates to "
                                f"{len(linked_locations)} location(s)..."
                            ),
                        }
                        for loc in linked_locations:
                            location_requirements = await _filter_requirements_for_company(
                                conn,
                                loc["company_id"],
                                requirements,
                            )
                            sync_result = await _sync_requirements_to_location(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                location_requirements,
                                create_alerts=True,
                            )
                            total_alerts += sync_result["alerts"]
                            total_updated += sync_result["updated"]
                yield {
                    "type": "repository_refresh",
                    "message": (
                        f"Healthcare research completed for {location_label}: "
                        f"{healthcare_result.get('new', 0)} requirement(s) added."
                    ),
                }
            except Exception as exc:
                logger.warning("Healthcare inline research failed: %s", exc)
                yield {
                    "type": "warning",
                    "message": f"Healthcare-specific research failed: {exc}",
                }

            # Oncology research (inline, after healthcare)
            try:
                yield {
                    "type": "repository_refresh",
                    "message": f"Researching oncology-specific compliance for {location_label}...",
                }
                oncology_result = await _research_oncology_requirements_for_jurisdiction(
                    conn, canonical_jurisdiction_id
                )
                if oncology_result.get("new", 0):
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        canonical_jurisdiction_id,
                    )
                    requirements = [
                        _jurisdiction_row_to_dict(dict(row)) for row in rows
                    ]
                    requirements = await _prepare_requirements_for_sync(requirements)
                    new_count = len(requirements)
                    if linked_locations:
                        yield {
                            "type": "syncing",
                            "message": (
                                f"Syncing oncology-specific updates to "
                                f"{len(linked_locations)} location(s)..."
                            ),
                        }
                        for loc in linked_locations:
                            location_requirements = await _filter_requirements_for_company(
                                conn,
                                loc["company_id"],
                                requirements,
                            )
                            sync_result = await _sync_requirements_to_location(
                                conn,
                                loc["id"],
                                loc["company_id"],
                                location_requirements,
                                create_alerts=True,
                            )
                            total_alerts += sync_result["alerts"]
                            total_updated += sync_result["updated"]
                yield {
                    "type": "repository_refresh",
                    "message": (
                        f"Oncology research completed for {location_label}: "
                        f"{oncology_result.get('new', 0)} requirement(s) added."
                    ),
                }
            except Exception as exc:
                logger.warning("Oncology inline research failed: %s", exc)
                yield {
                    "type": "warning",
                    "message": f"Oncology-specific research failed: {exc}",
                }
        else:
            # Keep top-metro batch fast by queuing healthcare-only work.
            try:
                from app.core.services.compliance_service import HEALTHCARE_CATEGORIES
                from app.workers.tasks.healthcare_research import run_healthcare_research
                hc_existing = await conn.fetch(
                    "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1 AND category = ANY($2::text[])",
                    canonical_jurisdiction_id,
                    sorted(HEALTHCARE_CATEGORIES),
                )
                hc_present = {r["category"] for r in hc_existing}
                hc_missing = HEALTHCARE_CATEGORIES - hc_present
                if hc_missing:
                    run_healthcare_research.delay(str(canonical_jurisdiction_id))
                    yield {
                        "type": "repository_refresh",
                        "message": f"Healthcare compliance research queued in background ({len(hc_missing)} categories).",
                    }
            except Exception as exc:
                logger.warning("Could not queue healthcare research: %s", exc)

            # Queue oncology research in background too
            try:
                from app.workers.tasks.oncology_research import run_oncology_research
                onc_existing = await conn.fetch(
                    "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1 AND category = ANY($2::text[])",
                    canonical_jurisdiction_id,
                    sorted(ONCOLOGY_CATEGORIES),
                )
                onc_present = {r["category"] for r in onc_existing}
                onc_missing = ONCOLOGY_CATEGORIES - onc_present
                if onc_missing:
                    run_oncology_research.delay(str(canonical_jurisdiction_id))
                    yield {
                        "type": "repository_refresh",
                        "message": f"Oncology compliance research queued in background ({len(onc_missing)} categories).",
                    }
            except Exception as exc:
                logger.warning("Could not queue oncology research: %s", exc)

        yield {
            "type": "completed",
            "location": location_label,
            "new": new_count,
            "updated": total_updated,
            "alerts": total_alerts,
            "low_confidence": total_low_confidence,
            "low_confidence_requirements": low_conf_requirement_count,
            "low_confidence_legislation": low_conf_legislation_count,
            "low_confidence_changes": low_conf_change_count,
        }


async def _get_or_create_metro_jurisdiction(city: str, state: str) -> UUID:
    city_key = city.lower().strip()
    state_key = state.upper().strip()[:2]
    async with get_connection() as conn:
        try:
            county = await conn.fetchval(
                "SELECT county FROM jurisdiction_reference WHERE city = $1 AND state = $2",
                city_key,
                state_key,
            )
        except Exception:
            county = None
        display_name = f"{city.strip()}, {state_key}"
        row = await conn.fetchrow(
            """
            INSERT INTO jurisdictions (city, state, county, display_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (COALESCE(city, ''), COALESCE(state, ''), country_code) DO UPDATE SET
                county = COALESCE(jurisdictions.county, EXCLUDED.county)
            RETURNING id
            """,
            city_key,
            state_key,
            county,
            display_name,
        )
        return row["id"]


def _fmt_dt(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _profile_row_to_dict(r) -> dict:
    evidence = r["category_evidence"]
    if isinstance(evidence, str):
        evidence = json.loads(evidence)
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "description": r["description"],
        "focused_categories": list(r["focused_categories"]),
        "rate_types": list(r["rate_types"]) if r["rate_types"] else [],
        "category_order": list(r["category_order"]),
        "category_evidence": evidence,
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


async def _load_industry_profile_row(conn, canonical: str):
    """Profile row for a canonical industry slug.

    Looks the profile up by its exact seeded name via `INDUSTRY_PROFILE_NAMES`
    rather than pattern-matching the caller's string. The old `name ILIKE $1`
    against the raw frontend value silently returned nothing for
    `construction_manufacturing` / `restaurant_hospitality` / `tech_professional`
    — SQL `_` is a single-char wildcard, so only `fast_food` ever matched, and it
    matched by accident with the `_` standing in for the space in "Fast Food".

    Not every canonical industry has a profile row (`biotech` has none); those
    still resolve their categories through `industry_tag`.
    """
    from app.core.services.compliance_evals.industry_keysets import INDUSTRY_PROFILE_NAMES

    profile_name = INDUSTRY_PROFILE_NAMES.get(canonical)
    if not profile_name:
        return None
    return await conn.fetchrow(
        "SELECT * FROM industry_compliance_profiles WHERE name = $1", profile_name
    )


async def _publish_research_to_requesters(jurisdiction_id: UUID) -> dict:
    """After we research a jurisdiction into the shared catalog, close the loop
    for every tenant who was waiting on it: mark their coverage request done,
    auto-populate their compliance tab from the (now-richer) catalog, and email
    their admins. Gemini-free — pure projection. Best-effort; never raises.
    """
    from app.core.services.compliance_service import (
        project_location_from_catalog,
        _get_company_admin_contacts,
    )

    tenants_updated = 0
    emails_sent = 0
    try:
        async with get_connection() as conn:
            jur = await conn.fetchrow(
                "SELECT city, state FROM jurisdictions WHERE id = $1", jurisdiction_id
            )
            if not jur or not jur["city"]:
                return {"tenants_updated": 0, "emails_sent": 0}

            reqs = await conn.fetch(
                """
                SELECT id, requested_by_company_id
                FROM jurisdiction_coverage_requests
                WHERE status IN ('pending', 'in_progress')
                  AND LOWER(city) = LOWER($1) AND UPPER(state) = UPPER($2)
                """,
                jur["city"], jur["state"],
            )
            if not reqs:
                return {"tenants_updated": 0, "emails_sent": 0}

            email_service = get_email_service()
            for req in reqs:
                company_id = req["requested_by_company_id"]
                # Project every active location this company has in the jurisdiction.
                locs = await conn.fetch(
                    """
                    SELECT id, name, city, state FROM business_locations
                    WHERE company_id = $1 AND is_active = true
                      AND LOWER(city) = LOWER($2) AND UPPER(state) = UPPER($3)
                    """,
                    company_id, jur["city"], jur["state"],
                )
                total_new = 0
                loc_name = None
                for loc in locs:
                    try:
                        result = await project_location_from_catalog(
                            conn, company_id, loc["id"],
                            create_alerts=True, check_type="research_publish",
                        )
                        total_new += result.get("new", 0)
                        loc_name = loc["name"] or f"{loc['city']}, {loc['state']}"
                    except Exception as exc:
                        logger.warning("publish: projection failed for %s: %s", loc["id"], exc)

                await conn.execute(
                    "UPDATE jurisdiction_coverage_requests "
                    "SET status = 'completed', processed_at = NOW() WHERE id = $1",
                    req["id"],
                )
                tenants_updated += 1

                # Email the company's admins that their pending items are live.
                try:
                    company_name, contacts = await _get_company_admin_contacts(company_id)
                    for c in contacts:
                        ok = await email_service.send_compliance_change_notification_email(
                            to_email=c["email"],
                            to_name=c.get("name"),
                            company_name=company_name,
                            location_name=loc_name or f"{jur['city']}, {jur['state']}",
                            changed_requirements_count=total_new,
                            jurisdictions=[f"{jur['city']}, {jur['state']}"],
                        )
                        if ok:
                            emails_sent += 1
                except Exception as exc:
                    logger.warning("publish: email failed for company %s: %s", company_id, exc)
    except Exception as exc:
        logger.warning("publish: research-to-requesters failed: %s", exc)

    return {"tenants_updated": tenants_updated, "emails_sent": emails_sent}


async def _heartbeat_while_admin(task):
    """Heartbeat dicts while a single coroutine task runs (SSE keepalive)."""
    while not task.done():
        done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_INTERVAL_ADMIN)
        if done:
            break
        yield {"type": "heartbeat"}


async def _project_chain_to_location_categories(conn, jurisdiction_id: UUID) -> List[dict]:
    """The active-catalog categories present across a jurisdiction's chain — used
    to compute 'all outstanding' when a category run passes categories=null.
    """
    rows = await conn.fetch(
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id FROM jurisdictions WHERE id = $1
            UNION ALL
            SELECT j.id, j.parent_id FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
        )
        SELECT DISTINCT r.category FROM jurisdiction_requirements r
        JOIN chain c ON c.id = r.jurisdiction_id
        WHERE r.status = 'active' AND r.category IS NOT NULL
        """,
        jurisdiction_id,
    )
    return [{"category": r["category"]} for r in rows]


async def _snapshot_requirements_bg(targets: list, context: str) -> None:
    """Freeze source pages for `targets` = [(requirement_id, url), …] off the
    request path (BackgroundTasks). Opens its own connection + one shared client;
    each snapshot is best-effort and never raises. Kept out of the handler so a
    slow/dead citation host can't add minutes to an approve/codify response or
    pin a pooled DB connection during network I/O."""
    urls = [(rid, u) for rid, u in targets if u]
    if not urls:
        return
    try:
        import httpx as _httpx
        from app.core.services.source_snapshot import snapshot_source
        async with _httpx.AsyncClient(
            timeout=_httpx.Timeout(10.0, connect=5.0), follow_redirects=True,
            headers={"User-Agent": "MatchaComplianceBot/1.0 (+compliance evidence capture)"},
        ) as client, get_connection() as conn:
            for rid, url in urls:
                await snapshot_source(conn, rid, url, context, client=client)
    except Exception as exc:  # evidence capture must never surface as an error
        logger.warning("background source snapshot pass failed (%s): %s", context, exc)


async def _publish_vertical_to_company(company_id: UUID) -> None:
    """Reproject a company's tabs from the catalog + email its admins that new
    specialty requirements landed. Pooled-conn analog of the sweep's post-fill
    reproject + _notify (the worker helper is pool-free; here we have a pool).
    """
    from app.core.services import vertical_coverage
    from app.core.services.compliance_service import _get_company_admin_contacts

    async with get_connection() as conn:
        locs = await conn.fetch(
            "SELECT id FROM business_locations WHERE company_id=$1 AND is_active=true", company_id,
        )
        total = 0
        for row in locs:
            total += await vertical_coverage.reproject_location(conn, company_id, row["id"])
    if total <= 0:
        return
    try:
        company_name, contacts = await _get_company_admin_contacts(company_id)
        email_service = get_email_service()
        for c in contacts:
            await email_service.send_compliance_change_notification_email(
                to_email=c["email"], to_name=c.get("name"),
                company_name=company_name, location_name=company_name,
                changed_requirements_count=total,
            )
    except Exception as exc:
        logger.warning("_publish_vertical_to_company: email failed for %s: %s", company_id, exc)


def _deal_template_row(key: str, row) -> dict:
    """Shape a deal_flow_templates row (or absence) into the API response."""
    if not row:
        return {"key": key, "payload": None, "updated_at": None, "updated_by": None}
    payload = row["payload"]
    if isinstance(payload, str):  # asyncpg returns jsonb as text unless a codec is set
        payload = json.loads(payload)
    return {
        "key": key,
        "payload": payload,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "updated_by": row["updated_by"],
    }


def _cappe_site_row(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "subdomain": row["subdomain"],
        "custom_domain": row["custom_domain"],
        "status": row["status"],
        "page_count": row["page_count"],
        "order_count": row["order_count"],
        "revenue_cents": row["revenue_cents"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "published_at": row["published_at"].isoformat() if row["published_at"] else None,
    }
