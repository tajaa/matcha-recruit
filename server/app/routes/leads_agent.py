"""
Leads Agent API Routes

Endpoints for the Leads Agent system:
- Search and filtering
- Leads management (CRUD, pipeline)
- Contact finding and ranking
- Email workflow (generate, approve, send)
"""

from typing import List, Optional, Dict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..dependencies import get_current_user, require_admin
from ..models.auth import CurrentUser
from ..models.leads_agent import (
    Lead, LeadCreate, LeadUpdate, LeadWithContacts,
    Contact, ContactCreate, ContactUpdate,
    LeadEmail, EmailDraftCreate, EmailUpdate,
    SearchRequest, SearchResult,
    LeadStatus, LeadPriority, EmailStatus,
    PipelineStats,
)
from ..services.leads_agent import get_leads_agent, LeadsAgentService


router = APIRouter(prefix="/leads-agent", tags=["leads-agent"])


# ===========================================
# Search Endpoints
# ===========================================

@router.post("/search", response_model=SearchResult)
async def run_search(
    request: SearchRequest,
    preview: bool = Query(False, description="If true, do not save results to DB"),
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """
    Run a job search and process results with Gemini.
    
    If preview=False (default), qualified leads are saved to the database.
    """
    return await service.run_search(request, save_results=not preview)


# ===========================================
# Leads Management
# ===========================================

@router.get("/leads", response_model=List[Lead])
async def get_leads(
    status: Optional[LeadStatus] = None,
    priority: Optional[LeadPriority] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """List executive leads with filtering."""
    return await service.get_leads(status, priority, limit, offset)


@router.get("/leads/{lead_id}", response_model=LeadWithContacts)
async def get_lead(
    lead_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Get a lead with its contacts and email drafts."""
    lead = await service.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Enrich with contacts and emails
    contacts = await service.get_contacts_for_lead(lead_id)
    emails = await service.get_emails(lead_id=lead_id)
    
    # Manually reconstruct LeadWithContacts
    lead_dict = lead.model_dump()
    lead_dict["contacts"] = contacts
    lead_dict["emails"] = emails
    
    return LeadWithContacts(**lead_dict)


@router.patch("/leads/{lead_id}", response_model=Lead)
async def update_lead(
    lead_id: UUID,
    update: LeadUpdate,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Update a lead's status, priority, or notes."""
    lead = await service.update_lead(
        lead_id,
        status=update.status,
        priority=update.priority,
        notes=update.notes,
        company_domain=update.company_domain,
    )
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.delete("/leads/{lead_id}")
async def delete_lead(
    lead_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Delete a lead."""
    deleted = await service.delete_lead(lead_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Lead not found")
    return {"status": "success", "message": "Lead deleted"}


@router.get("/pipeline", response_model=Dict[str, List[Lead]])
async def get_pipeline(
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Get leads grouped by status for pipeline view."""
    return await service.get_pipeline()


# ===========================================
# Contact Management
# ===========================================

@router.post("/leads/{lead_id}/find-contacts", response_model=List[Contact])
async def find_contacts(
    lead_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Find contacts for a lead using Hunter.io/Apollo."""
    contacts = await service.find_contacts_for_lead(lead_id)
    return contacts


@router.post("/leads/{lead_id}/rank-contacts", response_model=Contact)
async def rank_contacts(
    lead_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Rank contacts with Gemini and pick the primary one."""
    contact = await service.rank_contacts_for_lead(lead_id)
    if not contact:
        raise HTTPException(status_code=404, detail="No contacts found for this lead")
    return contact


@router.post("/leads/{lead_id}/contacts", response_model=Contact)
async def add_contact(
    lead_id: UUID,
    contact: ContactCreate,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Manually add a contact to a lead."""
    return await service.add_contact(lead_id, contact)


# ===========================================
# Email Workflow
# ===========================================

@router.post("/leads/{lead_id}/draft-email", response_model=LeadEmail)
async def draft_email(
    lead_id: UUID,
    request: EmailDraftCreate,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Generate an email draft for a contact."""
    email = await service.generate_email_draft(lead_id, request.contact_id)
    if not email:
        raise HTTPException(status_code=400, detail="Could not generate email draft")
    return email


@router.get("/emails", response_model=List[LeadEmail])
async def get_emails(
    status: Optional[EmailStatus] = None,
    lead_id: Optional[UUID] = None,
    limit: int = 50,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """List email drafts."""
    return await service.get_emails(status, lead_id, limit)


@router.patch("/emails/{email_id}", response_model=LeadEmail)
async def update_email(
    email_id: UUID,
    update: EmailUpdate,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Edit an email draft."""
    email = await service.update_email(email_id, update.subject, update.body)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.post("/emails/{email_id}/approve", response_model=LeadEmail)
async def approve_email(
    email_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Approve an email for sending."""
    email = await service.approve_email(email_id, current_user.id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.post("/emails/{email_id}/send", response_model=LeadEmail)
async def send_email(
    email_id: UUID,
    current_user: CurrentUser = Depends(require_admin),
    service: LeadsAgentService = Depends(get_leads_agent),
):
    """Send an approved email."""
    email = await service.send_email(email_id)
    if not email:
        raise HTTPException(status_code=400, detail="Could not send email (not approved or invalid contact)")
    return email
