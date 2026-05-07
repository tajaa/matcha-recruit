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
    "hris_import": False,
    "paid_channel_creator": False,
    "channel_job_postings": False,
    "discipline": True,
}

# Tier-defining features that should always be on for a given signup_source,
# regardless of what's stored in `companies.enabled_features`. Lets new
# bundle members inherit features without a per-row backfill migration.
# Paid gates (incidents/employees/discipline) intentionally NOT here —
# those flip via Stripe webhook on checkout completion.
TIER_REQUIRED_FEATURES: dict[str, dict[str, bool]] = {
    "matcha_lite": {"handbooks": True, "training": True},
    # ir_only_self_serve is the legacy name for matcha_lite — same feature
    # surface (handbooks + training auto-enabled). Kept distinct only because
    # the signup_source value persists on existing rows.
    "ir_only_self_serve": {"handbooks": True, "training": True},
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
