"""compliance router package (L9 split of the monolith)."""
from app.core.routes.compliance._shared import router, lite_router, shared_router  # noqa: F401

# Import each route submodule for its decorator side-effects (registers routes
# onto the shared router objects above).
from app.core.routes.compliance import locations  # noqa: F401,E402
from app.core.routes.compliance import alerts  # noqa: F401,E402
from app.core.routes.compliance import remediations  # noqa: F401,E402
from app.core.routes.compliance import summary  # noqa: F401,E402
from app.core.routes.compliance import requirements  # noqa: F401,E402
from app.core.routes.compliance import payer_policies  # noqa: F401,E402
from app.core.routes.compliance import credentials  # noqa: F401,E402

__all__ = ["router", "lite_router", "shared_router"]
