"""Feature availability is independent of the source task's entitlements."""
from app.config import get_settings

RENDER_QUEUE = "espresso_recaps_render"
TEMPLATE = "espresso-recap.v1"
SOURCE_BYTES = 128 * 1024 * 1024
OUTPUT_BYTES = 64 * 1024 * 1024
SCRATCH_BYTES = 256 * 1024 * 1024


def enabled() -> bool:
    try:
        return bool(get_settings().espresso_recaps_enabled)
    except RuntimeError:
        return False


def available(user_id) -> bool:
    settings = get_settings()
    allowed = {v.strip() for v in settings.espresso_recaps_allowed_users.split(",") if v.strip()}
    return enabled() and str(user_id) in allowed and bool(settings.s3_private_bucket)
