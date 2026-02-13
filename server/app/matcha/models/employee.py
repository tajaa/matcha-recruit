from datetime import datetime, date
from typing import Optional, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr
from decimal import Decimal


EmploymentType = Literal["full_time", "part_time", "contractor"]
PTORequestType = Literal["vacation", "sick", "personal", "other"]
PTORequestStatus = Literal["pending", "approved", "denied", "cancelled"]
DocumentStatus = Literal["draft", "pending_signature", "signed", "expired", "archived"]

LeaveType = Literal[
    "fmla", "state_pfml", "parental", "bereavement",
    "jury_duty", "medical", "military", "unpaid_loa",
]
LeaveStatus = Literal[
    "requested", "approved", "denied",
    "active", "completed", "cancelled",
]


# ================================
# Employee Models
# ================================

class EmployeeBase(BaseModel):
    email: EmailStr
    first_name: str
    last_name: str
    work_state: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    start_date: Optional[date] = None
    phone: Optional[str] = None
    address: Optional[str] = None


class EmployeeCreate(EmployeeBase):
    org_id: UUID
    manager_id: Optional[UUID] = None


class EmployeeUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    work_state: Optional[str] = None
    employment_type: Optional[EmploymentType] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    manager_id: Optional[UUID] = None
    emergency_contact: Optional[dict] = None


class EmployeeResponse(EmployeeBase):
    id: UUID
    org_id: UUID
    user_id: Optional[UUID]
    manager_id: Optional[UUID]
    termination_date: Optional[date]
    emergency_contact: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmployeeListResponse(BaseModel):
    employees: list[EmployeeResponse]
    total: int


# ================================
# PTO Models
# ================================

class PTOBalanceResponse(BaseModel):
    id: UUID
    employee_id: UUID
    year: int
    balance_hours: Decimal
    accrued_hours: Decimal
    used_hours: Decimal
    carryover_hours: Decimal
    updated_at: datetime

    class Config:
        from_attributes = True


class PTORequestBase(BaseModel):
    start_date: date
    end_date: date
    hours: Decimal
    reason: Optional[str] = None
    request_type: PTORequestType = "vacation"


class PTORequestCreate(PTORequestBase):
    pass


class PTORequestResponse(PTORequestBase):
    id: UUID
    employee_id: UUID
    status: PTORequestStatus
    approved_by: Optional[UUID]
    approved_at: Optional[datetime]
    denial_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PTORequestListResponse(BaseModel):
    requests: list[PTORequestResponse]
    total: int


class PTOSummary(BaseModel):
    balance: PTOBalanceResponse
    pending_requests: list[PTORequestResponse]
    approved_requests: list[PTORequestResponse]


# ================================
# Employee Document Models
# ================================

class EmployeeDocumentBase(BaseModel):
    doc_type: str
    title: str
    description: Optional[str] = None
    expires_at: Optional[date] = None


class EmployeeDocumentCreate(EmployeeDocumentBase):
    employee_id: UUID
    storage_path: Optional[str] = None


class EmployeeDocumentResponse(EmployeeDocumentBase):
    id: UUID
    org_id: UUID
    employee_id: UUID
    storage_path: Optional[str]
    status: DocumentStatus
    signed_at: Optional[datetime]
    assigned_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EmployeeDocumentListResponse(BaseModel):
    documents: list[EmployeeDocumentResponse]
    total: int


class SignDocumentRequest(BaseModel):
    signature_data: str  # Base64 encoded signature or typed name


# ================================
# Portal Dashboard Models
# ================================

class PendingTask(BaseModel):
    id: UUID
    task_type: str  # "document_signature", "pto_approval", etc.
    title: str
    description: Optional[str]
    due_date: Optional[date]
    created_at: datetime


class PortalDashboard(BaseModel):
    employee: EmployeeResponse
    pto_balance: Optional[PTOBalanceResponse]
    pending_tasks_count: int
    pending_documents_count: int
    pending_pto_requests_count: int


class PortalTasks(BaseModel):
    tasks: list[PendingTask]
    total: int


# ================================
# Profile Update Models
# ================================

class ProfileUpdateRequest(BaseModel):
    phone: Optional[str] = None
    address: Optional[str] = None
    emergency_contact: Optional[dict] = None


# ================================
# Leave Request Models
# ================================

class LeaveRequestCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: Optional[date] = None
    expected_return_date: Optional[date] = None
    reason: Optional[str] = None
    intermittent: bool = False
    intermittent_schedule: Optional[str] = None


class LeaveRequestUpdate(BaseModel):
    status: Optional[LeaveStatus] = None
    end_date: Optional[date] = None
    expected_return_date: Optional[date] = None
    actual_return_date: Optional[date] = None
    denial_reason: Optional[str] = None
    hours_approved: Optional[Decimal] = None
    notes: Optional[str] = None


class LeaveRequestResponse(BaseModel):
    id: UUID
    employee_id: UUID
    org_id: UUID
    leave_type: LeaveType
    reason: Optional[str]
    start_date: date
    end_date: Optional[date]
    expected_return_date: Optional[date]
    actual_return_date: Optional[date]
    status: LeaveStatus
    intermittent: bool
    intermittent_schedule: Optional[str]
    hours_approved: Optional[Decimal]
    hours_used: Optional[Decimal]
    denial_reason: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LeaveRequestListResponse(BaseModel):
    requests: list[LeaveRequestResponse]
    total: int
