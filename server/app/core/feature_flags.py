import json
from typing import Any
from uuid import UUID

DEFAULT_COMPANY_FEATURES: dict[str, bool] = {
    "handbooks": True,
    "accommodations": True,
    "matcha_work": False,
    # Werk Lite — the standalone business work-chat surface (/werk-lite): channel
    # chat + LiveKit calls + collaborative boards only. Presentation/entry gate
    # (sidebar entry + page access); the Boards kanban backend stays gated by
    # `matcha_work`, so a Werk-Lite company needs BOTH flags on. Default off.
    "werk_lite": False,
    # Werk Lite call-start policy. False = only admins/business-admins (role in
    # admin/client) may START a call; True = any channel member may start.
    # Joining an active call is always open to members. Only consulted for
    # werk_lite companies (other surfaces keep the owner + Pro gate).
    "werk_lite_calls_all_members": False,
    "risk_assessment": True,
    "training": False,
    "i9": False,
    "cobra": False,
    "separation_agreements": False,
    "credential_templates": False,
    # Customer policy library (create/upload/AI-draft policies, draft→active→
    # archived lifecycle, effective/review dates, IR/ER-mined gap suggestions).
    # Gates the policies_router + /app/policies. Default off so
    # require_feature("policies") is well-defined for every company (same rule
    # as compliance/incidents) — it was previously absent from defaults, which
    # left it 403-by-omission everywhere. Granted to the standalone Matcha
    # Compliance product via the matcha_compliance TIER_REQUIRED overlay.
    "policies": False,
    # Handbook AUDIT (gap analyzer) as an in-app feature. Distinct from
    # `handbooks` (the generator, which Lite keeps). Default off; granted to
    # Matcha-X via TIER_REQUIRED overlay and to Pro/bespoke at signup time.
    # The public lead-gen analyzer is unaffected — it gates teaser/full via
    # handbook_gap_analyzer._resolve_caller_tier, which reads this flag.
    "handbook_audit": False,
    # Full Compliance feature. Two ways a company gets it: (1) the self-serve,
    # Stripe-billed "Matcha Compliance" product flips it on via the
    # checkout.session.completed webhook (signup_source='matcha_compliance');
    # (2) Pro/bespoke stores compliance=True at signup for the power tools
    # (live re-research, AI ask, action plans, wage-violations, payer policies).
    # Default off so require_feature("compliance") is well-defined for every
    # company; existing Pro rows keep their stored compliance=True. NOT in any
    # TIER_REQUIRED overlay — it's a paid gate flipped by payment, never
    # force-asserted at read time (same rule as `incidents`).
    "compliance": False,
    # Read-only "taste" of Compliance for Matcha-X. Distinct from the full
    # `compliance` feature (Pro-only, stored at bespoke signup) which unlocks the
    # power tools (live re-research, AI ask, action plans, wage-violations, payer
    # policies). `compliance_lite` exposes ONLY the read-only viewers (per-location
    # requirements, jurisdiction stack, summary, upcoming legislation) that the
    # X onboarding build already populated. Default off; granted to Matcha-X via
    # the TIER_REQUIRED overlay. The shared read-only endpoints admit either flag.
    "compliance_lite": False,
    # HRIS import. `hris_gusto` = connect directly to Gusto (OAuth); `hris_finch` =
    # connect via Finch unified API (Rippling, BambooHR, ADP, …). Independent per
    # company. `hris_import` is the legacy umbrella — treated as "both" by the gates
    # for back-compat with companies provisioned before the split.
    "hris_import": False,
    "hris_gusto": False,
    "hris_finch": False,
    # Deductions/benefits WRITE-back through Finch. Per-client: when on, the Finch
    # connect flow requests the `benefits` product so the company's token can write
    # benefits/deductions (provider must support it — QuickBooks/Gusto/ADP yes,
    # Square no). Gates the /provisioning/hris/benefits endpoints.
    "hris_deductions": False,
    "paid_channel_creator": False,
    "channel_job_postings": False,
    "discipline": True,
    # Employee-benefits broker tooling. When on, exposes the benefits roster
    # ingestion (Finch + CSV), eligibility-exception detection (new-hire
    # enrollment gaps + terminated-but-still-deducted "premium leaks"), and the
    # renewal-risk radar. Gates the company-facing /benefits/* router; the
    # broker-portal rollups live under /broker/benefits/* (broker-role gated).
    "benefits_admin": False,
    # Labor Relations — union / collective-bargaining-agreement admin (CBA
    # document store + clause library, grievance workflow with contractual
    # step-deadlines, just-cause/Weingarten on discipline, bargaining units +
    # seniority, arbitration/ULP). Gates the /labor/* router + the /app/labor
    # surface. Default off; BUNDLED INTO PRO — stored True at bespoke signup
    # (auth.py) + the admin 'bespoke' tier preset (admin.py), exactly like
    # handbook_audit / credential_templates. Deliberately NOT in any
    # TIER_REQUIRED overlay, so it never leaks to personal Werk (which shares
    # signup_source='bespoke' with is_personal=true).
    "labor_relations": False,
    # Workforce Compliance — business-first employment-practices risk trackers:
    # pay-transparency (per-state posting compliance), AI hiring-tool bias-audit
    # register (cadence/overdue), and biometric/BIPA consent inventory. Each is a
    # legal obligation the business tracks for itself; together they flip the
    # corresponding broker EPL factors from attested → derived. Gates the
    # /workforce-compliance router + the /app/workforce-compliance surface.
    # Default off; admin-toggle per company. NOT in any tier overlay.
    "workforce_compliance": False,
    # Client-facing risk portal (composite WC+EPL+compliance index). Gates
    # /risk-profile + /app/risk-profile. Default off; admin-toggle. Not bundled.
    "risk_profile": False,
    # Healthcare/senior-living resident-care risk asset (safety programs, MVR
    # reviews, insurer-facing PDF). Gates /resident-care + /app/resident-care.
    # Default off; admin-toggle (vertical). Not bundled.
    "resident_care": False,
    # Universal controls-evidence register + "Proof of Controls" underwriter
    # packet (WTW p.85). Auto-fills from existing HR/safety/compliance data;
    # gates /controls-evidence + /app/controls-evidence. Default off;
    # admin-toggle. Not bundled.
    "controls_evidence": False,
    # Limit-adequacy + contract review (gap-analysis #6/#28 — "benchmarking +
    # contractual-limit review"). Company records carried limits + uploads
    # contracts (Gemini extracts required limits); the engine diffs them →
    # grounded shortfalls + a directional size/venue baseline. Gates
    # /limit-adequacy + /app/limit-adequacy + the broker limits surfaces.
    # Default off; admin-toggle. Not bundled.
    "limit_adequacy": False,
    # Driver-risk / MVR (gap-analysis #15) — standalone fleet driver-risk surface
    # for any employer with drivers (commercial-auto entry). Scores each driver
    # (clean/marginal/high-risk) from employer-recorded MVR data; reuses the
    # mvr_reviews table shared with resident_care. Gates /driver-risk +
    # /app/driver-risk. Default off; admin-toggle. Not bundled.
    "driver_risk": False,
    # Commercial property (P-side). Tenant Statement of Values (per-building COPE +
    # values), insurance-to-value + COPE grade, property limits via the limit-adequacy
    # engine (line='property') and property loss runs via loss-development, a property
    # component in the composite risk index, geocoded catastrophe exposure
    # (flood/quake/wildfire/wind), and broker property-portfolio + submission section.
    # Gates /property + /app/property + the broker property surfaces. Default off;
    # admin-toggle. Not bundled.
    "property": False,
    # Total Cost of Risk + aggregate retention/SIR optimizer. Assembles premiums +
    # retained losses + fees + mitigation spend into TCOR, and uses the Monte-Carlo
    # aggregate loss distribution to price candidate aggregate retentions (expected
    # retained loss + volatility + a labeled premium-credit heuristic). Gates /tcor +
    # /app/tcor. Default off; admin-toggle. Not bundled.
    "tcor": False,
    # Certificate-of-insurance tracking. Inbound COI capture (Gemini extract of
    # carrier/limits/expiry), auto-verify carried-vs-required limits via the
    # limit-adequacy engine, and expiry alerting (Celery sweep). Gates /coi +
    # /app/coi. Default off; admin-toggle. Not bundled.
    "coi_tracking": False,
    # D&O / Management-liability readiness. EPL-style weighted readiness score
    # (board governance, financial health, ERISA/fiduciary, bankruptcy/M&A) from
    # derived + attested factors, plus a submission section. Gates
    # /management-liability + /app/management-liability. Default off; admin-toggle.
    "do_readiness": False,
    # ACORD form generation (branded equivalents of 125/126/130/140) from data
    # already held (SOV, WC class exposures, loss runs, company profile). Gates
    # /acord. Default off; admin-toggle. Not bundled.
    "acord_forms": False,
    # Optional voice dictation on the IR create form (all IR products). The reporter
    # records a spoken account; one Gemini multimodal call transcribes + extracts the
    # form fields for the user to review before submitting (never auto-creates). Gates
    # only POST /ir/incidents/voice/parse + the "Dictate" button (stacks on the
    # incidents gate). Default off; admin-toggle; NOT in any tier overlay.
    "ir_voice_intake": False,
    # Scheduled handbook-freshness monitoring ("handbook watch"). Gates ONLY the
    # per-company sweep in the handbook_freshness Celery worker (+ its alert
    # emails) — the manual POST /handbooks/{id}/freshness-check stays free with
    # `handbooks`. Sold as a Lite-family add-on (own Stripe sub via the
    # matcha_lite_addon checkout); a paid gate like `incidents`, so NOT in any
    # tier overlay — merged value == stored value, letting the worker filter in
    # SQL on enabled_features. Default off; admin-toggle.
    "handbook_watch": False,
    # Legal Defense builder (full Matcha / Pro). An admin opens a legal matter
    # (subpoena / class action / EEOC / audit), converses with a GROUNDED AI that
    # pulls the company's own records across every enabled subsystem (IR/OSHA, ER,
    # compliance, discipline, training, handbooks, accommodations + audit logs),
    # and exports an attorney-facing evidence packet (defense-memo PDF that cites
    # only real records + a ZIP bundle of the underlying source documents). Read-
    # only over evidence; every generation/download is audit-logged. Gates the
    # /legal-pilot router + the /app/legal-pilot page. Default off; admin-
    # toggle; NOT bundled (paid full-platform asset).
    "legal_defense": False,
    # Handbook Pilot builder (Pro + Matcha-X). A business admin opens a
    # generation session and converses with a GROUNDED AI that pulls the
    # company's handbook profile + jurisdiction/compliance requirements +
    # existing handbooks/policies, iteratively drafting handbook sections and
    # standalone policies. AI-authored candidates land as reviewable drafts
    # (citation-validated — the shared legal_defense.validate_citations gate
    # drops any uncited jurisdiction reference) that the admin then PROMOTES
    # into the real handbooks / policies tables as drafts to edit/publish
    # normally. Gates the /handbook-pilot router + the /app/handbook-pilot
    # page. Default off; in the matcha_x TIER_REQUIRED overlay + stored True
    # at Pro/bespoke signup (like handbook_audit / credential_templates).
    "handbook_pilot": False,
    # Analysis Pilot (full Matcha / Pro). A company-facing, GENERAL-PURPOSE
    # bring-your-own-data analysis engine in a chat UI: the business uploads any
    # dataset (CSV / XLSX / financial-document PDF — 10-Ks, P&Ls, balance sheets,
    # loss runs, inventory, scores), a DETERMINISTIC Python engine
    # (services/analysis_packs) computes metrics via a pluggable analyzer-pack
    # registry — general descriptive stats (trends/extremes/totals/rankings),
    # volatility & risk (VaR/drawdown/correlation, the flagship pack), financial
    # ratios, insurance loss, inventory — and a GROUNDED AI answers questions over
    # the COMPUTED numbers only (citation-gated by the shared
    # legal_defense.validate_citations). Documents are Gemini-extracted then
    # user-confirmed before their metrics enter the corpus; highlighted records
    # can be discussed in chat, and AI-proposed extraction corrections apply only
    # via the confirmed PATCH → recompute path. Saves cross-dataset comparisons;
    # exports an analyst report PDF with inline SVG charts. Gates the
    # /analysis-pilot router + the /app/analysis-pilot page. Default off;
    # admin-toggle; NOT bundled (paid analysis asset, like legal_defense).
    "analysis_pilot": False,
    # OSHA 300/301/300A logs within IR. Default True (existing behavior for
    # every `incidents` company, unchanged) — forced False for the no-roster
    # matcha_lite_essentials config, where there's no employee roster to log
    # injured persons against. Gates the ir_incidents osha.py sub-router.
    "osha_logs": True,
}

# Tier-defining features that should always be on for a given signup_source,
# regardless of what's stored in `companies.enabled_features`. Lets new
# bundle members inherit features without a per-row backfill migration.
# Paid gates (incidents/employees/discipline) intentionally NOT here —
# those flip via Stripe webhook on checkout completion.
TIER_REQUIRED_FEATURES: dict[str, dict[str, bool]] = {
    # matcha_lite (paid, entry tier) — IR + employees + handbook GENERATION
    # only. training + discipline are forced OFF here (they moved up to
    # Matcha-X); the False values override any stored True (incl. existing
    # Lite rows + the broker-pays signup path) at read time. handbook_audit
    # + credential_templates stay off via DEFAULT (not granted to Lite).
    "matcha_lite": {
        "handbooks": True,
        "employees": True,
        "training": False,
        "discipline": False,
    },
    # matcha_lite_essentials — a signup-time choice on the SAME /lite/signup
    # page/checkout as matcha_lite (not a separate product surface), for
    # companies that want incident reporting without managing an employee
    # roster. No `employees` (no CSV/HRIS import, no roster picker on the
    # incident form — client already gates that on hasFeature('employees')),
    # no `osha_logs` (OSHA 300 logs need a roster to log injured persons
    # against; sold separately later). `incidents` itself is still the
    # Stripe-gated flag, flipped by the same checkout.session.completed
    # webhook as standard Lite. Priced as its own row in matcha_lite_pricing
    # (product_code='matcha_lite_essentials'), cheaper than standard Lite.
    "matcha_lite_essentials": {
        "handbooks": True,
        "employees": False,
        "training": False,
        "discipline": False,
        "osha_logs": False,
    },
    # matcha_x (paid mid tier) — clone of matcha_lite at Lite parity. Unlike
    # Lite, `discipline` is in the always-on overlay so the paid bundle is
    # identical on every payment path (Lite leaves discipline path-dependent:
    # only set on broker-pays/invite signup). `incidents` stays the single
    # Stripe-gated flag, flipped by the checkout.session.completed webhook.
    "matcha_x": {
        "handbooks": True,
        "training": True,
        "employees": True,
        "discipline": True,
        # X-and-up exclusives — forced on for every Matcha-X company
        # (existing + new) at read time, no per-row backfill.
        "handbook_audit": True,
        "credential_templates": True,
        # Conversational handbook/policy generation — bundled into Matcha-X
        # alongside the handbook audit it complements (audit finds gaps;
        # pilot drafts the fixes). Also stored True at Pro/bespoke signup.
        "handbook_pilot": True,
        # Read-only compliance taste — lets X view the baseline the onboarding
        # build wrote (requirements + jurisdiction stack + summary + upcoming
        # legislation). Full `compliance` (power tools) stays Pro-only.
        "compliance_lite": True,
    },
    # matcha_compliance (paid, standalone self-serve product) — the full
    # Compliance system sold on its own, bundling four pillars assembled from
    # existing Matcha-X pieces: jurisdictional compliance + handbook audit +
    # policy management + credentialing (per-employee, needs the roster).
    # `compliance` itself is DELIBERATELY NOT here — it stays the Stripe-webhook
    # paid gate (stripe_webhook.py flips it on checkout.session.completed;
    # isMatchaCompliancePending checks !compliance). Putting compliance in the
    # overlay would make every company non-pending = a free product. The four
    # pillar flags below are always-on for the tier (zero-backfill inheritance,
    # same pattern as matcha_x) — a pending/unpaid company still sees the
    # Subscribe CTA because sidebar dispatch checks !compliance first.
    "matcha_compliance": {
        "handbook_audit": True,
        "policies": True,
        "credential_templates": True,
        "employees": True,
    },
    # ir_only_self_serve (legacy free private beta) — full IR + HR bundle is
    # always on, no payment gate.
    "ir_only_self_serve": {
        "handbooks": True,
        "training": True,
        "employees": True,
        "discipline": True,
        "incidents": True,
    },
}


def default_company_features_json() -> str:
    return json.dumps(DEFAULT_COMPANY_FEATURES)


def merge_company_features(
    raw_features: Any,
    signup_source: str | None = None,
) -> dict[str, bool]:
    if isinstance(raw_features, str):
        try:
            raw_features = json.loads(raw_features)
        except json.JSONDecodeError:
            raw_features = {}

    features = raw_features if isinstance(raw_features, dict) else {}
    merged = dict(DEFAULT_COMPANY_FEATURES)
    for key, value in features.items():
        merged[key] = bool(value)

    if signup_source and signup_source in TIER_REQUIRED_FEATURES:
        for key, value in TIER_REQUIRED_FEATURES[signup_source].items():
            merged[key] = value

    return merged


# Named gate tuples for the Compliance feature family — mounted via
# require_any_feature(*TUPLE) in routes/__init__.py. Named so the frontend
# gates (FeatureGate anyOf=[...]) can be kept in sync with the backend by eye
# instead of by re-deriving the tuple from the mount call.
COMPLIANCE_READ_FEATURES = ("compliance", "compliance_lite", "incidents")
COMPLIANCE_SHARED_FEATURES = ("compliance", "compliance_lite")


async def get_company_features(company_id: UUID) -> dict:
    """Fetch a company's row and return its merged feature flags.

    Opens its own connection. Shared helper for the enabled_features +
    signup_source fetch-then-merge pattern that was inlined at each call site
    (compliance.py's create_location_endpoint is the first caller migrated to
    it — channel_calls.py and legal_defense.py keep their own private copies
    for now; migrating those is separate, lower-priority cleanup).
    """
    from ..database import get_connection

    async with get_connection() as conn:
        company_row = await conn.fetchrow(
            "SELECT enabled_features, signup_source FROM companies WHERE id = $1",
            company_id,
        )
    return merge_company_features(
        company_row["enabled_features"] if company_row else None,
        company_row["signup_source"] if company_row else None,
    )
