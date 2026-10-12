"""The company's Autopilot gate, independent of a selected demand source."""

from app.core.feature_flags import FEATURE_REQUIRES


def autopilot_availability(features: dict) -> dict:
    required = ("schedule_autopilot", *FEATURE_REQUIRES["schedule_autopilot"])
    missing = [feature for feature in required if not features.get(feature)]
    labels = {
        "schedule_autopilot": "Schedule Autopilot",
        "employee_schedule": "Employee scheduling",
        "huume": "Huume",
        "matcha_work": "Matcha Work",
    }
    message = (
        "Schedule Autopilot is available for this company."
        if not missing else
        "Schedule Autopilot requires these features to be enabled: "
        + ", ".join(labels[feature] for feature in missing) + "."
    )
    return {
        "enabled": bool(features.get("schedule_autopilot")),
        "available": not missing,
        "missing_features": missing,
        "message": message,
    }
