export type MWThreadStatus = 'active' | 'finalized' | 'archived';
export type MWMessageRole = 'user' | 'assistant' | 'system';

export interface MWThread {
  id: string;
  title: string;
  task_type: string;
  status: MWThreadStatus;
  version: number;
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
}

export interface MWThreadDetail {
  id: string;
  title: string;
  task_type: string;
  status: MWThreadStatus;
  current_state: MWDocumentState;
  version: number;
  linked_offer_letter_id: string | null;
  created_at: string;
  updated_at: string;
  messages: MWMessage[];
}

export interface MWCreateThreadResponse {
  id: string;
  title: string;
  status: MWThreadStatus;
  current_state: MWDocumentState;
  version: number;
  created_at: string;
  assistant_reply: string | null;
  pdf_url: string | null;
}

export interface MWSendMessageResponse {
  user_message: MWMessage;
  assistant_message: MWMessage;
  current_state: MWDocumentState;
  version: number;
  pdf_url: string | null;
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
