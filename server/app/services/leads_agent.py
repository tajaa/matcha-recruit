"""
Leads Agent Service

Main orchestrator for the executive lead generation workflow:
1. Run job search with filters
2. Analyze results with Gemini
3. Save qualified leads
4. Find contacts
5. Rank contacts
6. Generate email drafts
7. Send emails via MailerSend
"""

import json
from datetime import datetime
from typing import Optional, List
from uuid import UUID

from ..config import get_settings
from ..database import get_connection
from ..models.leads_agent import (
    Lead, LeadStatus, LeadPriority,
    Contact, ContactCreate, OutreachStatus,
    LeadEmail, EmailStatus,
    SearchRequest, SearchResult, SearchResultItem,
    GeminiAnalysis,
    HunterContact,
)
from .contact_finder import get_contact_finder
from .gemini_leads import get_gemini_leads_service


class LeadsAgentService:
    """
    Orchestrates the full leads generation workflow.
    
    Workflow:
    1. Search for executive positions
    2. Filter with Gemini AI
    3. Save qualified leads
    4. Find decision-maker contacts
    5. Rank contacts with Gemini
    6. Generate email drafts
    7. Send via MailerSend
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.contact_finder = get_contact_finder()
        self.gemini = get_gemini_leads_service()
    
    # ===========================================
    # Search & Analysis
    # ===========================================
    
    async def run_search(
        self,
        criteria: SearchRequest,
        save_results: bool = True,
    ) -> SearchResult:
        """
        Run a job search and process results.
        
        Steps:
        1. Search Google Jobs via SearchAPI
        2. Analyze each result with Gemini
        3. Save qualified leads to database
        
        Args:
            criteria: Search configuration
            save_results: If True, save qualified leads to database
        
        Returns:
            SearchResult with counts and items
        """
        from ..routes.job_search import search_jobs
        from ..models.job_search import JobSearchRequest
        
        # Build search query from criteria
        query_parts = []
        
        # Add role types to query
        role_keywords = {
            "ceo": "CEO OR Chief Executive Officer",
            "cfo": "CFO OR Chief Financial Officer",
            "cto": "CTO OR Chief Technology Officer",
            "cmo": "CMO OR Chief Marketing Officer",
            "coo": "COO OR Chief Operating Officer",
            "cro": "CRO OR Chief Revenue Officer",
            "vp": "VP OR Vice President",
            "director": "Director",
            "senior": "Senior Manager OR Head of",
            "cho": "CHRO OR Chief People Officer OR Chief Human Resources Officer",
            "hr": "VP of HR OR Director of Human Resources OR Head of HR",
            "people": "VP of People OR Head of People OR People Operations",
        }
        
        if criteria.role_types:
            role_query = " OR ".join(
                role_keywords.get(r.lower(), r) for r in criteria.role_types
            )
            query_parts.append(f"({role_query})")
        else:
            # Default to executive roles
            query_parts.append("(CEO OR CTO OR CFO OR VP OR Director)")
        
        # Add industries if specified
        # NOTE: We skip adding industries to the search query to avoid over-filtering.
        # Gemini will filter for industry match during analysis.
        # if criteria.industries:
        #     query_parts.append(f"({' OR '.join(criteria.industries)})")
        
        query = " ".join(query_parts)
        
        # Build location string
        location = criteria.locations[0] if criteria.locations else None
        
        # Execute search
        request = JobSearchRequest(
            query=query,
            location=location,
        )
        
        # Log the search for debugging
        print(f"[LeadsAgent] Executing search: query='{query}', location='{location}'")
        
        try:
            search_response = await search_jobs(request)
            jobs = search_response.jobs
            print(f"[LeadsAgent] Search found {len(jobs)} jobs")
        except Exception as e:
            return SearchResult(
                jobs_found=0,
                jobs_qualified=0,
                leads_created=0,
                leads_deduplicated=0,
                items=[SearchResultItem(
                    title="Search Error",
                    company_name=str(e),
                )],
            )
        
        # Process each job with Gemini
        items = []
        qualified_count = 0
        created_count = 0
        deduped_count = 0
        
        for job in jobs:
            # Create search result item
            item = SearchResultItem(
                job_id=job.job_id,
                title=job.title,
                company_name=job.company_name,
                location=job.location,
                salary_text=job.detected_extensions.salary if job.detected_extensions else None,
                source_url=job.apply_links[0].link if job.apply_links else None,
                description=job.description,
            )
            
            # SKIP Gemini Analysis for speed/reliability
            # We assume if it was found by search, it's worth saving for manual review.
            analysis = GeminiAnalysis(
                relevance_score=5,
                is_qualified=True,
                reasoning="Pending AI Analysis (Skipped during search)",
                extracted_seniority=None,
                extracted_salary_min=None,
                extracted_salary_max=None,
                extracted_domain=None,
            )
            item.gemini_analysis = analysis
            items.append(item)
            
            if analysis.is_qualified:
                qualified_count += 1
                print(f"  - Qualified: {item.title} at {item.company_name} (Score: {analysis.relevance_score})")
                
                # Save to database if requested
                if save_results:
                    created, deduped = await self._save_lead_from_search(item, analysis)
                    if created:
                        created_count += 1
                        print(f"    - SAVED")
                    if deduped:
                        deduped_count += 1
                        print(f"    - SKIPPED (Duplicate)")
            else:
                print(f"  - NOT Qualified: {item.title} at {item.company_name} (Score: {analysis.relevance_score})")
        
        return SearchResult(
            jobs_found=len(jobs),
            jobs_qualified=qualified_count,
            leads_created=created_count,
            leads_deduplicated=deduped_count,
            items=items,
        )
    
    async def _save_lead_from_search(
        self,
        item: SearchResultItem,
        analysis: GeminiAnalysis,
    ) -> tuple[bool, bool]:
        """
        Save a qualified lead to the database.
        
        Returns (was_created, was_deduplicated).
        """
        async with get_connection() as conn:
            # Check for duplicate
            existing = await conn.fetchrow(
                """
                SELECT id FROM executive_leads 
                WHERE company_name = $1 AND title = $2 AND (location = $3 OR (location IS NULL AND $3 IS NULL))
                """,
                item.company_name,
                item.title,
                item.location,
            )
            
            if existing:
                return False, True
            
            # Insert new lead
            try:
                await conn.execute(
                    """
                    INSERT INTO executive_leads (
                        source_type, source_job_id, source_url,
                        title, company_name, company_domain, location,
                        salary_min, salary_max, salary_text, seniority_level,
                        job_description, relevance_score, gemini_analysis,
                        status, priority
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16
                    )
                    """,
                    "google_jobs",
                    item.job_id,
                    item.source_url,
                    item.title,
                    item.company_name,
                    analysis.extracted_domain,
                    item.location,
                    analysis.extracted_salary_min,
                    analysis.extracted_salary_max,
                    item.salary_text,
                    analysis.extracted_seniority,
                    item.description,
                    analysis.relevance_score,
                    json.dumps(analysis.model_dump()),
                    LeadStatus.NEW.value,
                    LeadPriority.MEDIUM.value,
                )
                return True, False
            except Exception as e:
                print(f"    - SAVE ERROR: {str(e)}")
                return False, False
    
    # ===========================================
    # Lead Management
    # ===========================================
    
    async def get_leads(
        self,
        status: Optional[LeadStatus] = None,
        priority: Optional[LeadPriority] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Lead]:
        """Get leads with optional filtering."""
        async with get_connection() as conn:
            conditions = []
            params = []
            param_idx = 1
            
            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1
            
            if priority:
                conditions.append(f"priority = ${param_idx}")
                params.append(priority.value)
                param_idx += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            rows = await conn.fetch(
                f"""
                SELECT el.*, 
                       (SELECT COUNT(*) FROM lead_contacts lc WHERE lc.lead_id = el.id) as contacts_count
                FROM executive_leads el
                WHERE {where_clause}
                ORDER BY 
                    CASE priority 
                        WHEN 'high' THEN 1 
                        WHEN 'medium' THEN 2 
                        WHEN 'low' THEN 3 
                        ELSE 4 
                    END,
                    created_at DESC
                LIMIT ${param_idx} OFFSET ${param_idx + 1}
                """,
                *params, limit, offset
            )
            
            print(f"[LeadsAgent] Fetched {len(rows)} leads for pipeline (limit={limit}, offset={offset})")
            return [self._row_to_lead(row) for row in rows]
    
    async def get_lead(self, lead_id: UUID) -> Optional[Lead]:
        """Get a single lead by ID."""
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM executive_leads WHERE id = $1",
                lead_id
            )
            if not row:
                return None
            return self._row_to_lead(row)
    
    async def update_lead(
        self,
        lead_id: UUID,
        status: Optional[LeadStatus] = None,
        priority: Optional[LeadPriority] = None,
        notes: Optional[str] = None,
        company_domain: Optional[str] = None,
    ) -> Optional[Lead]:
        """Update a lead's status, priority, or notes."""
        async with get_connection() as conn:
            updates = ["updated_at = NOW()"]
            params = []
            param_idx = 1
            
            if status:
                updates.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1
            
            if priority:
                updates.append(f"priority = ${param_idx}")
                params.append(priority.value)
                param_idx += 1
            
            if notes is not None:
                updates.append(f"notes = ${param_idx}")
                params.append(notes)
                param_idx += 1
            
            if company_domain:
                updates.append(f"company_domain = ${param_idx}")
                params.append(company_domain)
                param_idx += 1
            
            params.append(lead_id)
            
            row = await conn.fetchrow(
                f"""
                UPDATE executive_leads
                SET {", ".join(updates)}
                WHERE id = ${param_idx}
                RETURNING *
                """,
                *params
            )
            
            if not row:
                return None
            return self._row_to_lead(row)
    
    async def delete_lead(self, lead_id: UUID) -> bool:
        """Delete a lead and all associated data."""
        async with get_connection() as conn:
            result = await conn.execute(
                "DELETE FROM executive_leads WHERE id = $1",
                lead_id
            )
            return result == "DELETE 1"
    
    async def get_pipeline(self) -> dict[str, List[Lead]]:
        """Get leads grouped by status for pipeline view."""
        leads = await self.get_leads(limit=500)
        
        pipeline = {status.value: [] for status in LeadStatus}
        for lead in leads:
            pipeline[lead.status.value].append(lead)
        
        return pipeline
    
    # ===========================================
    # Contact Management
    # ===========================================
    
    async def find_contacts_for_lead(self, lead_id: UUID) -> List[Contact]:
        """
        Find contacts for a lead using Hunter.io/Apollo.
        Saves found contacts to the database.
        """
        lead = await self.get_lead(lead_id)
        if not lead:
            return []
        
        # Find contacts
        result = await self.contact_finder.find_contacts(
            company_name=lead.company_name,
            company_domain=lead.company_domain,
            position_title=lead.title,
            seniority=lead.seniority_level,
        )
        
        if result.error or not result.contacts:
            return []
        
        # Save contacts to database
        saved_contacts = []
        async with get_connection() as conn:
            for hunter_contact in result.contacts:
                # Check if contact already exists
                existing = await conn.fetchrow(
                    "SELECT id FROM lead_contacts WHERE lead_id = $1 AND email = $2",
                    lead_id, hunter_contact.email
                )
                if existing:
                    # Fetch and return existing
                    row = await conn.fetchrow(
                        "SELECT * FROM lead_contacts WHERE id = $1",
                        existing["id"]
                    )
                    saved_contacts.append(self._row_to_contact(row))
                    continue
                
                # Insert new contact
                row = await conn.fetchrow(
                    """
                    INSERT INTO lead_contacts (
                        lead_id, name, first_name, last_name, title, email,
                        email_confidence, linkedin_url, source
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING *
                    """,
                    lead_id,
                    f"{hunter_contact.first_name or ''} {hunter_contact.last_name or ''}".strip() or hunter_contact.email,
                    hunter_contact.first_name,
                    hunter_contact.last_name,
                    hunter_contact.position,
                    hunter_contact.email,
                    hunter_contact.confidence,
                    hunter_contact.linkedin,
                    result.source,
                )
                saved_contacts.append(self._row_to_contact(row))
        
        return saved_contacts
    
    async def rank_contacts_for_lead(self, lead_id: UUID) -> Optional[Contact]:
        """
        Use Gemini to rank contacts and pick the best one.
        Sets is_primary=True on the selected contact.
        """
        lead = await self.get_lead(lead_id)
        if not lead:
            return None
        
        contacts = await self.get_contacts_for_lead(lead_id)
        if not contacts:
            return None
        
        # Ask Gemini to rank
        best_contact, reason = await self.gemini.rank_contacts(lead, contacts)
        
        if best_contact:
            # Update the selected contact as primary
            async with get_connection() as conn:
                # Clear any existing primary
                await conn.execute(
                    "UPDATE lead_contacts SET is_primary = false WHERE lead_id = $1",
                    lead_id
                )
                # Set new primary
                await conn.execute(
                    "UPDATE lead_contacts SET is_primary = true, gemini_ranking_reason = $1 WHERE id = $2",
                    reason, best_contact.id
                )
            
            best_contact.is_primary = True
            best_contact.gemini_ranking_reason = reason
        
        return best_contact
    
    async def get_contacts_for_lead(self, lead_id: UUID) -> List[Contact]:
        """Get all contacts for a lead."""
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM lead_contacts
                WHERE lead_id = $1
                ORDER BY is_primary DESC, email_confidence DESC
                """,
                lead_id
            )
            return [self._row_to_contact(row) for row in rows]
    
    async def add_contact(self, lead_id: UUID, data: ContactCreate) -> Optional[Contact]:
        """Add a contact manually."""
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO lead_contacts (
                    lead_id, name, first_name, last_name, title, email,
                    phone, linkedin_url, is_primary, source
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'manual')
                RETURNING *
                """,
                lead_id,
                data.name,
                data.first_name,
                data.last_name,
                data.title,
                data.email,
                data.phone,
                data.linkedin_url,
                data.is_primary,
            )
            return self._row_to_contact(row)
    
    # ===========================================
    # Email Management
    # ===========================================
    
    async def generate_email_draft(
        self,
        lead_id: UUID,
        contact_id: UUID,
    ) -> Optional[LeadEmail]:
        """Generate an email draft using Gemini."""
        lead = await self.get_lead(lead_id)
        if not lead:
            return None
        
        # Get contact
        async with get_connection() as conn:
            contact_row = await conn.fetchrow(
                "SELECT * FROM lead_contacts WHERE id = $1 AND lead_id = $2",
                contact_id, lead_id
            )
            if not contact_row:
                return None
            contact = self._row_to_contact(contact_row)
        
        # Generate email with Gemini
        subject, body = await self.gemini.generate_outreach_email(lead, contact)
        
        # Save draft
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO lead_emails (lead_id, contact_id, subject, body, status)
                VALUES ($1, $2, $3, $4, 'draft')
                RETURNING *
                """,
                lead_id, contact_id, subject, body
            )
            
            # Update lead status to draft_ready
            await conn.execute(
                "UPDATE executive_leads SET status = 'draft_ready', updated_at = NOW() WHERE id = $1",
                lead_id
            )
            
            return self._row_to_email(row)
    
    async def get_emails(
        self,
        status: Optional[EmailStatus] = None,
        lead_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> List[LeadEmail]:
        """Get email drafts with optional filtering."""
        async with get_connection() as conn:
            conditions = []
            params = []
            param_idx = 1
            
            if status:
                conditions.append(f"status = ${param_idx}")
                params.append(status.value)
                param_idx += 1
            
            if lead_id:
                conditions.append(f"lead_id = ${param_idx}")
                params.append(lead_id)
                param_idx += 1
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            
            rows = await conn.fetch(
                f"""
                SELECT * FROM lead_emails
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ${param_idx}
                """,
                *params, limit
            )
            
            return [self._row_to_email(row) for row in rows]
    
    async def update_email(
        self,
        email_id: UUID,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> Optional[LeadEmail]:
        """Update an email draft."""
        async with get_connection() as conn:
            updates = []
            params = []
            param_idx = 1
            
            if subject:
                updates.append(f"subject = ${param_idx}")
                params.append(subject)
                param_idx += 1
            
            if body:
                updates.append(f"body = ${param_idx}")
                params.append(body)
                param_idx += 1
            
            if not updates:
                return None
            
            params.append(email_id)
            
            row = await conn.fetchrow(
                f"""
                UPDATE lead_emails
                SET {", ".join(updates)}
                WHERE id = ${param_idx}
                RETURNING *
                """,
                *params
            )
            
            if not row:
                return None
            return self._row_to_email(row)
    
    async def approve_email(self, email_id: UUID, user_id: UUID) -> Optional[LeadEmail]:
        """Approve an email for sending."""
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                UPDATE lead_emails
                SET status = 'approved', approved_at = NOW(), approved_by = $1
                WHERE id = $2
                RETURNING *
                """,
                user_id, email_id
            )
            
            if row:
                # Update lead status
                await conn.execute(
                    "UPDATE executive_leads SET status = 'approved', updated_at = NOW() WHERE id = $1",
                    row["lead_id"]
                )
            
            if not row:
                return None
            return self._row_to_email(row)
    
    async def send_email(self, email_id: UUID) -> Optional[LeadEmail]:
        """Send an approved email via MailerSend."""
        from .email import send_custom_email
        
        async with get_connection() as conn:
            # Get email
            email_row = await conn.fetchrow(
                "SELECT * FROM lead_emails WHERE id = $1 AND status = 'approved'",
                email_id
            )
            if not email_row:
                return None
            
            # Get contact
            contact_row = await conn.fetchrow(
                "SELECT * FROM lead_contacts WHERE id = $1",
                email_row["contact_id"]
            )
            if not contact_row or not contact_row["email"]:
                return None
            
            # Send via MailerSend
            try:
                message_id = await send_custom_email(
                    to_email=contact_row["email"],
                    to_name=contact_row["name"],
                    subject=email_row["subject"],
                    body=email_row["body"],
                )
                
                # Update email status
                row = await conn.fetchrow(
                    """
                    UPDATE lead_emails
                    SET status = 'sent', sent_at = NOW(), mailersend_message_id = $1
                    WHERE id = $2
                    RETURNING *
                    """,
                    message_id, email_id
                )
                
                # Update lead and contact status
                await conn.execute(
                    "UPDATE executive_leads SET status = 'contacted', updated_at = NOW(), last_activity_at = NOW() WHERE id = $1",
                    email_row["lead_id"]
                )
                await conn.execute(
                    "UPDATE lead_contacts SET outreach_status = 'sent', contacted_at = NOW() WHERE id = $1",
                    email_row["contact_id"]
                )
                
                return self._row_to_email(row)
            except Exception as e:
                # Log error but don't fail
                print(f"[LeadsAgent] Email send failed: {e}")
                return None
    
    # ===========================================
    # Helper Methods
    # ===========================================
    
    def _row_to_lead(self, row) -> Lead:
        """Convert database row to Lead model."""
        return Lead(
            id=row["id"],
            source_type=row["source_type"],
            source_job_id=row["source_job_id"],
            source_url=row["source_url"],
            title=row["title"],
            company_name=row["company_name"],
            company_domain=row["company_domain"],
            location=row["location"],
            salary_min=row["salary_min"],
            salary_max=row["salary_max"],
            salary_text=row["salary_text"],
            seniority_level=row["seniority_level"],
            job_description=row["job_description"],
            relevance_score=row["relevance_score"],
            gemini_analysis=json.loads(row["gemini_analysis"]) if row["gemini_analysis"] else None,
            status=LeadStatus(row["status"]) if row["status"] else LeadStatus.NEW,
            priority=LeadPriority(row["priority"]) if row["priority"] else LeadPriority.MEDIUM,
            notes=row["notes"],
            contacts_count=row.get("contacts_count", 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_activity_at=row["last_activity_at"],
        )
    
    def _row_to_contact(self, row) -> Contact:
        """Convert database row to Contact model."""
        return Contact(
            id=row["id"],
            lead_id=row["lead_id"],
            name=row["name"],
            first_name=row["first_name"],
            last_name=row["last_name"],
            title=row["title"],
            email=row["email"],
            email_confidence=row["email_confidence"],
            phone=row["phone"],
            linkedin_url=row["linkedin_url"],
            is_primary=row["is_primary"] or False,
            source=row["source"],
            gemini_ranking_reason=row["gemini_ranking_reason"],
            outreach_status=OutreachStatus(row["outreach_status"]) if row["outreach_status"] else OutreachStatus.PENDING,
            contacted_at=row["contacted_at"],
            opened_at=row["opened_at"],
            replied_at=row["replied_at"],
            created_at=row["created_at"],
        )
    
    def _row_to_email(self, row) -> LeadEmail:
        """Convert database row to LeadEmail model."""
        return LeadEmail(
            id=row["id"],
            lead_id=row["lead_id"],
            contact_id=row["contact_id"],
            subject=row["subject"],
            body=row["body"],
            status=EmailStatus(row["status"]) if row["status"] else EmailStatus.DRAFT,
            mailersend_message_id=row["mailersend_message_id"],
            sent_at=row["sent_at"],
            delivered_at=row["delivered_at"],
            opened_at=row["opened_at"],
            clicked_at=row["clicked_at"],
            replied_at=row["replied_at"],
            created_at=row["created_at"],
            approved_at=row["approved_at"],
            approved_by=row["approved_by"],
        )


# Singleton instance
_leads_agent: Optional[LeadsAgentService] = None


def get_leads_agent() -> LeadsAgentService:
    """Get the leads agent service instance."""
    global _leads_agent
    if _leads_agent is None:
        _leads_agent = LeadsAgentService()
    return _leads_agent
