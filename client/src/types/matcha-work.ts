export type MWThreadStatus = 'active' | 'finalized' | 'archived';
export type MWMessageRole = 'user' | 'assistant' | 'system';
export type MWTaskType = 'offer_letter' | 'review' | 'workbook' | 'onboarding';

export interface MWThread {
  id: string;
  title: string;
  task_type: MWTaskType;
  status: MWThreadStatus;
  version: number;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface MWElement {
  id: string;
  thread_id: string;
  element_type: MWTaskType;
  title: string;
  status: MWThreadStatus;
  version: number;
  linked_offer_letter_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface MWMessage {
  id: string;
  thread_id: string;
  role: MWMessageRole;
  content: string;
  version_created: number | null;
  created_at: string;
}

export interface MWDocumentState {
  candidate_name?: string | null;
  position_title?: string | null;
  company_name?: string | null;
  salary?: string | null;
  bonus?: string | null;
  stock_options?: string | null;
  start_date?: string | null;
  employment_type?: string | null;
  location?: string | null;
  benefits?: string | null;
  manager_name?: string | null;
  manager_title?: string | null;
  expiration_date?: string | null;
  benefits_medical?: boolean | null;
  benefits_medical_coverage?: number | null;
  benefits_medical_waiting_days?: number | null;
  benefits_dental?: boolean | null;
  benefits_vision?: boolean | null;
  benefits_401k?: boolean | null;
  benefits_401k_match?: string | null;
  benefits_wellness?: string | null;
  benefits_pto_vacation?: boolean | null;
  benefits_pto_sick?: boolean | null;
  benefits_holidays?: boolean | null;
  benefits_other?: string | null;
  contingency_background_check?: boolean | null;
  contingency_credit_check?: boolean | null;
  contingency_drug_screening?: boolean | null;
  company_logo_url?: string | null;
  salary_range_min?: number | null;
  salary_range_max?: number | null;
  candidate_email?: string | null;
  review_title?: string | null;
  review_subject?: string | null;
  context?: string | null;
  accomplishments?: string | null;
  strengths?: string | null;
  growth_areas?: string | null;
  next_steps?: string | null;
  summary?: string | null;
  overall_rating?: number | null;
  anonymized?: boolean | null;
  recipient_emails?: string[] | null;
  review_request_statuses?: MWReviewRequestStatus[] | null;
  review_expected_responses?: number | null;
  review_received_responses?: number | null;
  review_pending_responses?: number | null;
  review_last_sent_at?: string | null;
  workbook_title?: string | null;
  industry?: string | null;
  objective?: string | null;
  sections?: { title: string; content: string }[] | null;
}

export interface MWThreadDetail {
  id: string;
  title: string;
  task_type: MWTaskType;
  status: MWThreadStatus;
  current_state: MWDocumentState;
  version: number;
  is_pinned: boolean;
  linked_offer_letter_id: string | null;
  created_at: string;
  updated_at: string;
  messages: MWMessage[];
}

export interface MWCreateThreadResponse {
  id: string;
  title: string;
  task_type: MWTaskType;
  status: MWThreadStatus;
  current_state: MWDocumentState;
  version: number;
  is_pinned: boolean;
  created_at: string;
  assistant_reply: string | null;
  pdf_url: string | null;
}

export interface MWTokenUsage {
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  estimated: boolean;
  model: string | null;
}

export interface MWSendMessageResponse {
  user_message: MWMessage;
  assistant_message: MWMessage;
  current_state: MWDocumentState;
  version: number;
  pdf_url: string | null;
  token_usage?: MWTokenUsage | null;
}

export interface MWUsageStreamEvent {
  type: 'usage';
  data: MWTokenUsage & { stage: 'estimate' | 'final' };
}

export interface MWCompleteStreamEvent {
  type: 'complete';
  data: MWSendMessageResponse;
}

export interface MWErrorStreamEvent {
  type: 'error';
  message: string;
}

export type MWMessageStreamEvent =
  | MWUsageStreamEvent
  | MWCompleteStreamEvent
  | MWErrorStreamEvent;

export interface MWUsageTotals {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  operation_count: number;
  estimated_operations: number;
}

export interface MWUsageByModel extends MWUsageTotals {
  model: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
}

export interface MWUsageSummaryResponse {
  period_days: number;
  generated_at: string;
  totals: MWUsageTotals;
  by_model: MWUsageByModel[];
}

export interface MWDocumentVersion {
  id: string;
  thread_id: string;
  version: number;
  state_json: MWDocumentState;
  diff_summary: string | null;
  created_at: string;
}

export interface MWFinalizeResponse {
  thread_id: string;
  status: string;
  version: number;
  pdf_url: string | null;
  linked_offer_letter_id: string | null;
}

export interface MWSaveDraftResponse {
  thread_id: string;
  linked_offer_letter_id: string;
  offer_status: string;
  saved_at: string;
}

export interface MWReviewRequestStatus {
  email: string;
  status: 'pending' | 'sent' | 'failed' | 'submitted';
  sent_at: string | null;
  submitted_at: string | null;
  last_error: string | null;
}

export interface MWSendReviewRequestsResponse {
  thread_id: string;
  expected_responses: number;
  received_responses: number;
  pending_responses: number;
  sent_count: number;
  failed_count: number;
  recipients: MWReviewRequestStatus[];
}

export interface MWSendHandbookSignaturesResponse {
  handbook_id: string;
  handbook_version: number;
  assigned_count: number;
  skipped_existing_count: number;
  distributed_at: string;
}

export interface MWPublicReviewRequest {
  token: string;
  review_title: string;
  recipient_email: string;
  status: 'pending' | 'sent' | 'failed' | 'submitted';
  submitted_at: string | null;
}

export interface MWPublicReviewSubmitResponse {
  status: 'submitted';
  submitted_at: string;
}
