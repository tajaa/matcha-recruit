"""Pydantic models for the Leads Agent system."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, EmailStr


class LeadStatus(str, Enum):
    """Status of a lead in the pipeline."""
    NEW = "new"
    STAGING = "staging"
    DRAFT_READY = "draft_ready"
    APPROVED = "approved"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CLOSED = "closed"


class LeadPriority(str, Enum):
    """Priority level of a lead."""
    SKIP = "skip"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SeniorityLevel(str, Enum):
    """Seniority level for executive roles."""
    C_SUITE = "c_suite"
    VP = "vp"
    DIRECTOR = "director"
    SENIOR = "senior"


class ContactSource(str, Enum):
    """Source of a contact."""
    HUNTER = "hunter"
    APOLLO = "apollo"
    CLEARBIT = "clearbit"
    LINKEDIN = "linkedin"
    MANUAL = "manual"


class OutreachStatus(str, Enum):
    """Status of outreach to a contact."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"


class EmailStatus(str, Enum):
    """Status of an email draft."""
    DRAFT = "draft"
    APPROVED = "approved"
    SENT = "sent"
    DELIVERED = "delivered"
    OPENED = "opened"
    REPLIED = "replied"
    BOUNCED = "bounced"


# ===========================================
# Search Configuration Models
# ===========================================

class SearchConfigCreate(BaseModel):
    """Request to create a search configuration."""
    name: str
    role_types: List[str] = []  # ['ceo', 'cfo', 'vp', 'director']
    locations: List[str] = []   # ['San Francisco', 'New York']
    industries: List[str] = []  # ['Technology', 'Finance']
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None


class SearchConfig(SearchConfigCreate):
    """Search configuration with metadata."""
    id: UUID
    is_active: bool = True
    last_run_at: Optional[datetime] = None
    created_by: Optional[UUID] = None
    created_at: datetime


class SearchRequest(BaseModel):
    """Request to run a lead search."""
    role_types: List[str] = []
    locations: List[str] = []
    industries: List[str] = []
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    save_config: bool = False
    config_name: Optional[str] = None


# ===========================================
# Lead Models
# ===========================================

class LeadCreate(BaseModel):
    """Request to create a lead manually."""
    title: str
    company_name: str
    company_domain: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_text: Optional[str] = None
    seniority_level: Optional[SeniorityLevel] = None
    source_url: Optional[str] = None
    job_description: Optional[str] = None
    notes: Optional[str] = None


class LeadUpdate(BaseModel):
    """Request to update a lead."""
    status: Optional[LeadStatus] = None
    priority: Optional[LeadPriority] = None
    notes: Optional[str] = None
    company_domain: Optional[str] = None


class Lead(BaseModel):
    """Executive lead (a position being tracked)."""
    id: UUID
    source_type: str
    source_job_id: Optional[str] = None
    source_url: Optional[str] = None
    
    title: str
    company_name: str
    company_domain: Optional[str] = None
    location: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    salary_text: Optional[str] = None
    seniority_level: Optional[str] = None
    job_description: Optional[str] = None
    
    relevance_score: Optional[int] = None
    gemini_analysis: Optional[dict] = None
    
    status: LeadStatus = LeadStatus.NEW
    priority: LeadPriority = LeadPriority.MEDIUM
    notes: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    last_activity_at: Optional[datetime] = None


class LeadWithContacts(Lead):
    """Lead with its associated contacts."""
    contacts: List["Contact"] = []
    emails: List["LeadEmail"] = []


# ===========================================
# Contact Models
# ===========================================

class ContactCreate(BaseModel):
    """Request to add a contact manually."""
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    is_primary: bool = False


class ContactUpdate(BaseModel):
    """Request to update a contact."""
    name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    is_primary: Optional[bool] = None
    outreach_status: Optional[OutreachStatus] = None


class Contact(BaseModel):
    """Decision-maker contact for a lead."""
    id: UUID
    lead_id: UUID
    
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    title: Optional[str] = None
    email: Optional[str] = None
    email_confidence: Optional[int] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    
    is_primary: bool = False
    source: Optional[str] = None
    gemini_ranking_reason: Optional[str] = None
    
    outreach_status: OutreachStatus = OutreachStatus.PENDING
    contacted_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    
    created_at: datetime


# ===========================================
# Email Models
# ===========================================

class EmailDraftCreate(BaseModel):
    """Request to generate an email draft."""
    contact_id: UUID


class EmailUpdate(BaseModel):
    """Request to update an email draft."""
    subject: Optional[str] = None
    body: Optional[str] = None


class LeadEmail(BaseModel):
    """Email draft or sent email for a lead."""
    id: UUID
    lead_id: UUID
    contact_id: UUID
    
    subject: str
    body: str
    
    status: EmailStatus = EmailStatus.DRAFT
    
    mailersend_message_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    
    created_at: datetime
    approved_at: Optional[datetime] = None
    approved_by: Optional[UUID] = None


# ===========================================
# Search Result Models
# ===========================================

class GeminiAnalysis(BaseModel):
    """Result of Gemini position analysis."""
    relevance_score: int  # 1-10
    is_qualified: bool
    reasoning: str
    extracted_seniority: Optional[str] = None
    extracted_salary_min: Optional[int] = None
    extracted_salary_max: Optional[int] = None
    extracted_domain: Optional[str] = None


class SearchResultItem(BaseModel):
    """A single job from search results."""
    job_id: Optional[str] = None
    title: str
    company_name: str
    location: Optional[str] = None
    salary_text: Optional[str] = None
    source_url: Optional[str] = None
    description: Optional[str] = None
    
    # Set after Gemini analysis
    gemini_analysis: Optional[GeminiAnalysis] = None


class SearchResult(BaseModel):
    """Result of running a lead search."""
    jobs_found: int
    jobs_qualified: int
    leads_created: int
    leads_deduplicated: int
    items: List[SearchResultItem] = []


# ===========================================
# Contact Finder Models
# ===========================================

class HunterContact(BaseModel):
    """Contact from Hunter.io."""
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    position: Optional[str] = None
    seniority: Optional[str] = None
    department: Optional[str] = None
    linkedin: Optional[str] = None
    confidence: int = 0  # 0-100


class ContactFinderResult(BaseModel):
    """Result of contact finding."""
    domain: str
    contacts_found: int
    contacts: List[HunterContact] = []
    source: str
    error: Optional[str] = None


# ===========================================
# Pipeline Models
# ===========================================

class PipelineStage(BaseModel):
    """A stage in the pipeline with its leads."""
    status: LeadStatus
    count: int
    leads: List[Lead] = []


class PipelineStats(BaseModel):
    """Statistics for the leads pipeline."""
    total_leads: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    emails_pending: int
    emails_sent: int
    response_rate: float


# Update forward references
LeadWithContacts.model_rebuild()
