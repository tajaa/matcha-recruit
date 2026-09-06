"""auth router package (split of the pre-2026-07-25 auth.py monolith)."""
from app.core.routes.auth._shared import router  # noqa: F401

# Import each route submodule for its decorator side-effects (registers routes
# onto the shared router object above).
from app.core.routes.auth import login  # noqa: F401,E402
from app.core.routes.auth import google  # noqa: F401,E402
from app.core.routes.auth import register_business  # noqa: F401,E402
from app.core.routes.auth import verify_email  # noqa: F401,E402
from app.core.routes.auth import register_users  # noqa: F401,E402
from app.core.routes.auth import broker  # noqa: F401,E402
from app.core.routes.auth import test_accounts  # noqa: F401,E402
from app.core.routes.auth import profile  # noqa: F401,E402
from app.core.routes.auth import credentials  # noqa: F401,E402
from app.core.routes.auth import beta  # noqa: F401,E402

# Re-exported for tests that import these by module path (see
# tests/auth/test_auth_registration.py, tests/auth/test_auth_broker_branding.py).
from app.core.routes.auth._shared import _upsert_business_headcount_profile  # noqa: F401,E402
from app.core.routes.auth.broker import get_broker_branding_runtime  # noqa: F401,E402

__all__ = ["router"]
