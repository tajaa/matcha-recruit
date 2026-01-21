"""
DEPRECATED: Models have been reorganized into domains.

- Core models: server/app/core/models/
- Matcha (HR/Recruiting) models: server/app/matcha/models/
- Gummfit (Creator Agency) models: server/app/gummfit/models/

These re-exports are provided for backward compatibility.
"""

# Core models
from ..core.models.bulk_import import (
    BulkImportResult,
    BulkImportError,
    CompanyBulkRow,
    PositionBulkRow,
)
from ..core.models.policy import (
    Policy,
    PolicyCreate,
    PolicyUpdate,
    PolicyResponse,
    PolicyStatus,
    SignatureRequest,
    SignatureCreate,
    PolicySignature,
    PolicySignatureResponse,
    SignatureStatus,
    SignerType,
)

# Matcha models
from ..matcha.models.company import Company, CompanyCreate, CompanyResponse
from ..matcha.models.interview import Interview, InterviewCreate, InterviewResponse
from ..matcha.models.candidate import Candidate, CandidateResponse
from ..matcha.models.matching import MatchResult, MatchResultResponse
from ..matcha.models.position import (
    Position,
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionMatchResult,
    PositionMatchResultResponse,
    EmploymentType,
    ExperienceLevel,
    RemotePolicy,
    PositionStatus,
)
from ..matcha.models.job_search import (
    JobSearchRequest,
    JobSearchResponse,
    JobListing,
    JobApplyLink,
    JobDetectedExtensions,
    JobHighlightSection,
    SavedJob,
    SavedJobCreate,
)

__all__ = [
    # Core
    "BulkImportResult",
    "BulkImportError",
    "CompanyBulkRow",
    "PositionBulkRow",
    "Policy",
    "PolicyCreate",
    "PolicyUpdate",
    "PolicyResponse",
    "PolicyStatus",
    "SignatureRequest",
    "SignatureCreate",
    "PolicySignature",
    "PolicySignatureResponse",
    "SignatureStatus",
    "SignerType",
    # Matcha
    "Company",
    "CompanyCreate",
    "CompanyResponse",
    "Interview",
    "InterviewCreate",
    "InterviewResponse",
    "Candidate",
    "CandidateResponse",
    "MatchResult",
    "MatchResultResponse",
    "Position",
    "PositionCreate",
    "PositionUpdate",
    "PositionResponse",
    "PositionMatchResult",
    "PositionMatchResultResponse",
    "EmploymentType",
    "ExperienceLevel",
    "RemotePolicy",
    "PositionStatus",
    "JobSearchRequest",
    "JobSearchResponse",
    "JobListing",
    "JobApplyLink",
    "JobDetectedExtensions",
    "JobHighlightSection",
    "SavedJob",
    "SavedJobCreate",
]
