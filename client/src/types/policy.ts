export type PolicyCategory =
  | 'clinical'
  | 'hr'
  | 'compliance'
  | 'operational'
  | 'safety'
  | 'infection_control'
  | 'hipaa'
  | 'other'

export type PolicyStatus = 'draft' | 'active' | 'archived'

export interface PolicyResponse {
  id: string
  company_id: string
  company_name?: string
  title: string
  description?: string
  content: string
  file_url?: string
  version: string
  status: PolicyStatus
  category?: PolicyCategory | null
  source_type?: string | null
  effective_date?: string | null
  review_date?: string | null
  original_filename?: string | null
  mime_type?: string | null
  page_count?: number | null
  signature_count?: number | null
  pending_signatures?: number | null
  signed_count?: number | null
  created_at: string
  updated_at: string
  created_by?: string | null
}
