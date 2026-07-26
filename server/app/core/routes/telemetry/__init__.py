"""telemetry grouping folder — client/server error logging, traffic, usage."""
from app.core.routes.telemetry.client_errors import router as client_errors_router
from app.core.routes.telemetry.server_errors import router as server_errors_router
from app.core.routes.telemetry.traffic import router as traffic_router
from app.core.routes.telemetry.usage import router as usage_router

__all__ = [
    "client_errors_router",
    "server_errors_router",
    "traffic_router",
    "usage_router",
]
