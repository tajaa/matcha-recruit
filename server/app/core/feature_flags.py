import json
from typing import Any

DEFAULT_COMPANY_FEATURES: dict[str, bool] = {
    "handbooks": True,
    "accommodations": True,
    "matcha_work": False,
    "risk_assessment": True,
    "training": False,
    "i9": False,
    "cobra": False,
    "separation_agreements": False,
    "credential_templates": False,
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
}

# Tier-defining features that should always be on for a given signup_source,
# regardless of what's stored in `companies.enabled_features`. Lets new
# bundle members inherit features without a per-row backfill migration.
# Paid gates (incidents/employees/discipline) intentionally NOT here —
# those flip via Stripe webhook on checkout completion.
TIER_REQUIRED_FEATURES: dict[str, dict[str, bool]] = {
    # matcha_lite (paid) — employees/discipline gated on Stripe; only the
    # always-on bundle items overlay here.
    "matcha_lite": {"handbooks": True, "training": True, "employees": True},
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
