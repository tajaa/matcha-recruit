export type LeadStatus = 'new' | 'qualified' | 'staging' | 'prioritized' | 'draft_ready' | 'approved' | 'contacted' | 'replied' | 'closed' | 'archived';

export type LeadPriority = 'skip' | 'low' | 'medium' | 'high';

export type SeniorityLevel = 'c_suite' | 'vp' | 'director' | 'senior';

export type OutreachStatus = 'pending' | 'sent' | 'delivered' | 'opened' | 'replied' | 'bounced';

export type EmailStatus = 'draft' | 'approved' | 'sent' | 'delivered' | 'opened' | 'replied' | 'bounced';

export interface Lead {
    id: string;
    source_type: string;
    source_job_id?: string;
    source_url?: string;
    title: string;
    company_name: string;
    company_domain?: string;
    location?: string;
    salary_min?: number;
    salary_max?: number;
    salary_text?: string;
    seniority_level?: string;
    job_description?: string;
    relevance_score?: number;
    gemini_analysis?: {
        relevance_score: number;
        is_qualified: boolean;
        reasoning: string;
        extracted_seniority?: string;
        extracted_salary_min?: number;
        extracted_salary_max?: number;
        extracted_domain?: string;
    };
    status: LeadStatus;
    priority: LeadPriority;
    notes?: string;
    created_at: string;
    updated_at: string;
    last_activity_at?: string;
}

export interface Contact {
    id: string;
    lead_id: string;
    name: string;
    first_name?: string;
    last_name?: string;
    title?: string;
    email?: string;
    email_confidence?: number;
    phone?: string;
    linkedin_url?: string;
    is_primary: boolean;
    source?: string;
    gemini_ranking_reason?: string;
    outreach_status: OutreachStatus;
    contacted_at?: string;
    opened_at?: string;
    replied_at?: string;
    created_at: string;
}

export interface LeadEmail {
    id: string;
    lead_id: string;
    contact_id: string;
    subject: string;
    body: string;
    status: EmailStatus;
    mailersend_message_id?: string;
    sent_at?: string;
    delivered_at?: string;
    opened_at?: string;
    clicked_at?: string;
    replied_at?: string;
    created_at: string;
    approved_at?: string;
}

export interface LeadWithContacts extends Lead {
    contacts: Contact[];
    emails: LeadEmail[];
}

export interface LeadUpdate {
    status?: LeadStatus;
    priority?: LeadPriority;
    notes?: string;
    company_domain?: string;
}

export interface ContactCreate {
    name: string;
    first_name?: string;
    last_name?: string;
    title?: string;
    email?: string;
    phone?: string;
    linkedin_url?: string;
    is_primary?: boolean;
}

export interface EmailUpdate {
    subject?: string;
    body?: string;
}

export interface SearchRequest {
    role_types: string[];
    locations: string[];
    industries: string[];
    salary_min?: number;
    salary_max?: number;
    save_config?: boolean;
    config_name?: string;
}

export interface SearchResultItem {
    job_id?: string;
    title: string;
    company_name: string;
    location?: string;
    salary_text?: string;
    source_url?: string;
    description?: string;
    gemini_analysis?: {
        relevance_score: number;
        is_qualified: boolean;
        reasoning: string;
        extracted_seniority?: string;
        extracted_salary_min?: number;
        extracted_salary_max?: number;
        extracted_domain?: string;
    };
}

export interface SearchResult {
    jobs_found: number;
    jobs_qualified: number;
    leads_created: number;
    leads_deduplicated: number;
    items: SearchResultItem[];
}
