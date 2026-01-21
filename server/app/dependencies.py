"""
DEPRECATED: Dependencies have been reorganized into domains.

- Core dependencies: server/app/core/dependencies.py
- Matcha (HR/Recruiting) dependencies: server/app/matcha/dependencies.py
- Gummfit (Creator Agency) dependencies: server/app/gummfit/dependencies.py

These re-exports are provided for backward compatibility.
"""

# Core dependencies
from .core.dependencies import (
    get_current_user,
    require_roles,
    require_admin,
    require_candidate,
    get_optional_user,
    security,
)

# Matcha dependencies
from .matcha.dependencies import (
    require_client,
    require_employee,
    require_admin_or_client,
    require_admin_or_employee,
    get_client_company_id,
    get_employee_info,
    require_employee_record,
    require_interview_prep_access,
)

# Gummfit dependencies
from .gummfit.dependencies import (
    require_creator,
    require_agency,
    require_gumfit_admin,
    require_creator_or_agency,
    require_admin_or_creator,
    require_admin_or_agency,
    get_creator_info,
    require_creator_record,
    get_agency_info,
    require_agency_membership,
    require_agency_admin,
)

__all__ = [
    # Core
    "get_current_user",
    "require_roles",
    "require_admin",
    "require_candidate",
    "get_optional_user",
    "security",
    # Matcha
    "require_client",
    "require_employee",
    "require_admin_or_client",
    "require_admin_or_employee",
    "get_client_company_id",
    "get_employee_info",
    "require_employee_record",
    "require_interview_prep_access",
    # Gummfit
    "require_creator",
    "require_agency",
    "require_gumfit_admin",
    "require_creator_or_agency",
    "require_admin_or_creator",
    "require_admin_or_agency",
    "get_creator_info",
    "require_creator_record",
    "get_agency_info",
    "require_agency_membership",
    "require_agency_admin",
]
