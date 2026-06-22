import json
from typing import Any

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
        # Read-only compliance taste — lets X view the baseline the onboarding
        # build wrote (requirements + jurisdiction stack + summary + upcoming
        # legislation). Full `compliance` (power tools) stays Pro-only.
        "compliance_lite": True,
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
