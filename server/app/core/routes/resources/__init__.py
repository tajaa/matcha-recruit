"""resources router package (L9 split of the monolith)."""
from app.core.routes.resources._shared import router  # noqa: F401

# Import each route submodule for its decorator side-effects (registers routes
# onto the shared router objects above).
from app.core.routes.resources import checkout  # noqa: F401,E402
from app.core.routes.resources import lite_addons  # noqa: F401,E402
from app.core.routes.resources import upgrade  # noqa: F401,E402
from app.core.routes.resources import leadgen  # noqa: F401,E402
from app.core.routes.resources import state_guides  # noqa: F401,E402
from app.core.routes.resources import pins  # noqa: F401,E402

__all__ = ["router"]
