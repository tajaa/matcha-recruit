from datetime import date, datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


HandbookStatus = Literal["draft", "active", "archived"]
HandbookMode = Literal["single_state", "multi_state"]
HandbookSourceType = Literal["template", "upload"]
HandbookSectionType = Literal["core", "state", "custom", "uploaded"]
HandbookChangeStatus = Literal["pending", "accepted", "rejected"]


class HandbookScopeInput(BaseModel):
    state: str = Field(..., min_length=2, max_length=2)
    city: Optional[str] = None
    zipcode: Optional[str] = None
    location_id: Optional[UUID] = None


class HandbookSectionInput(BaseModel):
    section_key: str = Field(..., min_length=2, max_length=120)
    title: str = Field(..., min_length=2, max_length=255)
    content: str = ""
    section_order: int = 0
    section_type: HandbookSectionType = "custom"
    jurisdiction_scope: Optional[dict] = None


class CompanyHandbookProfileInput(BaseModel):
    legal_name: str = Field(..., min_length=1, max_length=255)
    dba: Optional[str] = Field(default=None, max_length=255)
    ceo_or_president: str = Field(..., min_length=1, max_length=255)
    headcount: Optional[int] = None
    remote_workers: bool = False
    minors: bool = False
    tipped_employees: bool = False
    union_employees: bool = False
    federal_contracts: bool = False
    group_health_insurance: bool = False
    background_checks: bool = False
    hourly_employees: bool = True
    salaried_employees: bool = False
    commissioned_employees: bool = False
    tip_pooling: bool = False


class HandbookCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=500)
    mode: HandbookMode = "single_state"
    source_type: HandbookSourceType = "template"
    industry: Optional[str] = Field(default=None, max_length=120)
    scopes: list[HandbookScopeInput]
    profile: CompanyHandbookProfileInput
    custom_sections: list[HandbookSectionInput] = Field(default_factory=list)
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    create_from_template: bool = True

    @model_validator(mode="after")
    def validate_shape(self):
        if self.mode == "single_state" and len(self.scopes) != 1:
            raise ValueError("Single-state handbooks must have exactly one scope")
        if self.mode == "multi_state" and len(self.scopes) < 2:
            raise ValueError("Multi-state handbooks must include at least two scopes")
        if self.source_type == "upload" and not self.file_url:
            raise ValueError("Uploaded handbooks require file_url")
        return self


class HandbookUpdateRequest(BaseModel):
    title: Optional[str] = None
    mode: Optional[HandbookMode] = None
    scopes: Optional[list[HandbookScopeInput]] = None
    profile: Optional[CompanyHandbookProfileInput] = None
    sections: Optional[list[HandbookSectionInput]] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_mode_scopes(self):
        if self.mode == "single_state" and self.scopes is not None and len(self.scopes) != 1:
            raise ValueError("Single-state handbooks must have exactly one scope")
        if self.mode == "multi_state" and self.scopes is not None and len(self.scopes) < 2:
            raise ValueError("Multi-state handbooks must include at least two scopes")
        return self


class HandbookScopeResponse(BaseModel):
    id: UUID
    state: str
    city: Optional[str] = None
    zipcode: Optional[str] = None
    location_id: Optional[UUID] = None


class HandbookSectionResponse(BaseModel):
    id: UUID
    section_key: str
    title: str
    content: str
    section_order: int
    section_type: HandbookSectionType
    jurisdiction_scope: dict = Field(default_factory=dict)


class CompanyHandbookProfileResponse(CompanyHandbookProfileInput):
    company_id: UUID
    updated_by: Optional[UUID] = None
    updated_at: datetime


class HandbookListItemResponse(BaseModel):
    id: UUID
    title: str
    status: HandbookStatus
    mode: HandbookMode
    source_type: HandbookSourceType
    active_version: int
    scope_states: list[str]
    pending_changes_count: int = 0
    updated_at: datetime
    published_at: Optional[datetime] = None
    created_at: datetime


class HandbookDetailResponse(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    status: HandbookStatus
    mode: HandbookMode
    source_type: HandbookSourceType
    active_version: int
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    scopes: list[HandbookScopeResponse]
    profile: CompanyHandbookProfileResponse
    sections: list[HandbookSectionResponse]
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    created_by: Optional[UUID] = None


class HandbookChangeRequestResponse(BaseModel):
    id: UUID
    handbook_id: UUID
    handbook_version_id: UUID
    alert_id: Optional[UUID] = None
    section_key: Optional[str] = None
    old_content: Optional[str] = None
    proposed_content: str
    rationale: Optional[str] = None
    source_url: Optional[str] = None
    effective_date: Optional[date] = None
    status: HandbookChangeStatus
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime


class HandbookPublishResponse(BaseModel):
    id: UUID
    status: HandbookStatus
    active_version: int
    published_at: Optional[datetime] = None


class HandbookDistributionResponse(BaseModel):
    handbook_id: UUID
    handbook_version: int
    assigned_count: int
    skipped_existing_count: int
    distributed_at: datetime


class HandbookAcknowledgementSummary(BaseModel):
    handbook_id: UUID
    handbook_version: int
    assigned_count: int
    signed_count: int
    pending_count: int
    expired_count: int


class HandbookGuidedQuestion(BaseModel):
    id: str = Field(..., min_length=2, max_length=80)
    question: str = Field(..., min_length=4, max_length=500)
    placeholder: Optional[str] = Field(default=None, max_length=255)
    required: bool = True


class HandbookGuidedSectionSuggestion(BaseModel):
    section_key: str = Field(..., min_length=2, max_length=120)
    title: str = Field(..., min_length=2, max_length=255)
    content: str = ""
    section_order: int = 300
    section_type: HandbookSectionType = "custom"
    jurisdiction_scope: dict = Field(default_factory=dict)


class HandbookGuidedDraftRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=500)
    mode: HandbookMode = "single_state"
    scopes: list[HandbookScopeInput] = Field(default_factory=list)
    profile: CompanyHandbookProfileInput
    industry: Optional[str] = Field(default=None, max_length=120)
    answers: dict[str, str] = Field(default_factory=dict)
    existing_custom_sections: list[HandbookGuidedSectionSuggestion] = Field(default_factory=list)


class HandbookGuidedDraftResponse(BaseModel):
    industry: str
    summary: str
    clarification_needed: bool = False
    questions: list[HandbookGuidedQuestion] = Field(default_factory=list)
    profile_updates: dict[str, Any] = Field(default_factory=dict)
    suggested_sections: list[HandbookGuidedSectionSuggestion] = Field(default_factory=list)
