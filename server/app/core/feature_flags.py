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
}


def default_company_features_json() -> str:
    return json.dumps(DEFAULT_COMPANY_FEATURES)


def merge_company_features(raw_features: Any) -> dict[str, bool]:
    if isinstance(raw_features, str):
        try:
            raw_features = json.loads(raw_features)
        except json.JSONDecodeError:
            raw_features = {}

    features = raw_features if isinstance(raw_features, dict) else {}
    merged = dict(DEFAULT_COMPANY_FEATURES)
    for key, value in features.items():
        merged[key] = bool(value)
    return merged
