// Deal types
export type CompensationType = 'fixed' | 'per_deliverable' | 'revenue_share' | 'product_only' | 'negotiable';
export type DealStatus = 'draft' | 'open' | 'closed' | 'filled' | 'cancelled';
export type DealVisibility = 'public' | 'invite_only' | 'private';
export type ApplicationStatus = 'pending' | 'under_review' | 'shortlisted' | 'accepted' | 'rejected' | 'withdrawn';
export type ContractStatus = 'pending' | 'active' | 'completed' | 'cancelled' | 'disputed';
export type PaymentStatus = 'pending' | 'invoiced' | 'paid' | 'overdue' | 'cancelled';

// Deliverable
export interface Deliverable {
  type: string;
  platform?: string;
  quantity?: number;
  description?: string;
}

// Brand Deal
export interface BrandDeal {
  id: string;
  agency_id: string;
  agency_name?: string;
  title: string;
  brand_name: string;
  description: string;
  requirements: Record<string, unknown>;
  deliverables: Deliverable[];
  compensation_type: CompensationType;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: string;
  compensation_details: string | null;
  niches: string[];
  min_followers: number | null;
  max_followers: number | null;
  preferred_platforms: string[];
  audience_requirements: Record<string, unknown>;
  timeline_start: string | null;
  timeline_end: string | null;
  application_deadline: string | null;
  status: DealStatus;
  visibility: DealVisibility;
  applications_count: number;
  created_at: string;
  updated_at: string;
}

export interface BrandDealCreate {
  title: string;
  brand_name: string;
  description: string;
  requirements?: Record<string, unknown>;
  deliverables?: Deliverable[];
  compensation_type: CompensationType;
  compensation_min?: number;
  compensation_max?: number;
  compensation_currency?: string;
  compensation_details?: string;
  niches?: string[];
  min_followers?: number;
  max_followers?: number;
  preferred_platforms?: string[];
  audience_requirements?: Record<string, unknown>;
  timeline_start?: string;
  timeline_end?: string;
  application_deadline?: string;
  visibility?: DealVisibility;
}

export interface BrandDealUpdate {
  title?: string;
  brand_name?: string;
  description?: string;
  requirements?: Record<string, unknown>;
  deliverables?: Deliverable[];
  compensation_type?: CompensationType;
  compensation_min?: number;
  compensation_max?: number;
  compensation_currency?: string;
  compensation_details?: string;
  niches?: string[];
  min_followers?: number;
  max_followers?: number;
  preferred_platforms?: string[];
  audience_requirements?: Record<string, unknown>;
  timeline_start?: string;
  timeline_end?: string;
  application_deadline?: string;
  status?: DealStatus;
  visibility?: DealVisibility;
}

export interface BrandDealPublic {
  id: string;
  agency_name: string;
  agency_verified: boolean;
  title: string;
  brand_name: string;
  description: string;
  deliverables: Deliverable[];
  compensation_type: CompensationType;
  compensation_min: number | null;
  compensation_max: number | null;
  compensation_currency: string;
  niches: string[];
  min_followers: number | null;
  max_followers: number | null;
  preferred_platforms: string[];
  timeline_start: string | null;
  timeline_end: string | null;
  application_deadline: string | null;
  created_at: string;
}

// Deal Application
export interface DealApplication {
  id: string;
  deal_id: string;
  deal_title?: string;
  creator_id: string;
  creator_name?: string;
  pitch: string;
  proposed_rate: number | null;
  proposed_currency: string;
  proposed_deliverables: Deliverable[];
  portfolio_links: string[];
  availability_notes: string | null;
  status: ApplicationStatus;
  agency_notes: string | null;
  match_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface DealApplicationCreate {
  pitch: string;
  proposed_rate?: number;
  proposed_currency?: string;
  proposed_deliverables?: Deliverable[];
  portfolio_links?: string[];
  availability_notes?: string;
}

export interface DealApplicationUpdate {
  pitch?: string;
  proposed_rate?: number;
  proposed_deliverables?: Deliverable[];
  portfolio_links?: string[];
  availability_notes?: string;
}

export interface ApplicationStatusUpdate {
  status: ApplicationStatus;
  agency_notes?: string;
}

// Contract
export interface DealContract {
  id: string;
  deal_id: string;
  deal_title?: string;
  application_id: string;
  creator_id: string;
  creator_name?: string;
  agency_id: string;
  agency_name?: string;
  agreed_rate: number;
  agreed_currency: string;
  agreed_deliverables: Deliverable[];
  terms: string | null;
  contract_document_url: string | null;
  start_date: string | null;
  end_date: string | null;
  status: ContractStatus;
  total_paid: number;
  created_at: string;
  updated_at: string;
}

export interface ContractCreate {
  agreed_rate: number;
  agreed_currency?: string;
  agreed_deliverables: Deliverable[];
  terms?: string;
  start_date?: string;
  end_date?: string;
}

export interface ContractStatusUpdate {
  status: ContractStatus;
}

// Payment
export interface ContractPayment {
  id: string;
  contract_id: string;
  amount: number;
  currency: string;
  milestone_name: string | null;
  due_date: string | null;
  paid_date: string | null;
  status: PaymentStatus;
  payment_method: string | null;
  transaction_reference: string | null;
  notes: string | null;
  created_at: string;
}

export interface PaymentCreate {
  amount: number;
  currency?: string;
  milestone_name?: string;
  due_date?: string;
}

export interface PaymentUpdate {
  status?: PaymentStatus;
  paid_date?: string;
  payment_method?: string;
  transaction_reference?: string;
  notes?: string;
}

// Match
export interface CreatorDealMatch {
  id: string;
  deal_id: string;
  creator_id: string;
  creator_name?: string;
  overall_score: number;
  niche_score: number | null;
  audience_score: number | null;
  engagement_score: number | null;
  budget_fit_score: number | null;
  match_reasoning: string | null;
  breakdown: Record<string, unknown>;
  created_at: string;
}
