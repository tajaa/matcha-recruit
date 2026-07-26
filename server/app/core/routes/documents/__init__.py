"""documents grouping folder — handbooks, policies, credentialing, signature links."""
from app.core.routes.documents.handbooks import router as handbooks_router, public_router as handbooks_public_router
from app.core.routes.documents.policies import router as policies_router
from app.core.routes.documents.handbook_gap_analyzer import router as handbook_gap_analyzer_router
from app.core.routes.documents.admin_handbook_references import router as admin_handbook_references_router
from app.core.routes.documents.public_signatures import router as public_signatures_router
from app.core.routes.documents.public_employee_documents import router as public_employee_documents_router
from app.core.routes.documents.credential_templates import router as credential_templates_router

__all__ = [
    "handbooks_router",
    "handbooks_public_router",
    "policies_router",
    "handbook_gap_analyzer_router",
    "admin_handbook_references_router",
    "public_signatures_router",
    "public_employee_documents_router",
    "credential_templates_router",
]
