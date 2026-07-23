"""Admin router package (J5 split of the 13k-line admin.py)."""
from fastapi import APIRouter

from app.core.routes.admin.jurisdictions import router as _jurisdictions
from app.core.routes.admin.companies import router as _companies
from app.core.routes.admin.deal_flow import router as _deal_flow
from app.core.routes.admin.brokers import router as _brokers
from app.core.routes.admin.invites import router as _invites
from app.core.routes.admin.platform_settings import router as _platform_settings
from app.core.routes.admin.posters import router as _posters
from app.core.routes.admin.users import router as _users
from app.core.routes.admin.research import router as _research
from app.core.routes.admin.products import router as _products
from app.core.routes.admin.schedule_rules import router as _schedule_rules

# Re-export the internal names other modules + tests import directly (the full
# external surface, verified by grepping app/ + tests/ for `admin import <name>`).
from app.core.routes.admin._shared import (  # noqa: F401
    KNOWN_PLATFORM_ITEMS,
    _link_status_for,
    _transition_state_for,
    _resolve_jurisdiction_chain,
)
from app.core.models.admin import ProposedCategory  # noqa: F401

router = APIRouter()
for _r in (_jurisdictions, _companies, _deal_flow, _brokers, _invites, _platform_settings, _posters, _users, _research, _products, _schedule_rules):
    router.include_router(_r)

__all__ = [
    "router",
    "KNOWN_PLATFORM_ITEMS",
    "ProposedCategory",
    "_link_status_for",
    "_transition_state_for",
    "_resolve_jurisdiction_chain",
]
