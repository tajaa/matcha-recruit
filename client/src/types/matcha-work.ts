export type MWTaskType =
  | 'chat'
  | 'offer_letter'
  | 'review'
  | 'workbook'
  | 'onboarding'
  | 'presentation'
  | 'handbook'
  | 'policy'
  | 'resume_batch'
  | 'inventory'
  | 'project'
  | 'language_tutor'

export interface ResumeCandidate {
  id: string
  filename: string
  resume_url: string | null
  name: string | null
  email: string | null
  phone: string | null
  location: string | null
  current_title: string | null
  experience_years: number | null
  skills: string[] | null
  education: string | null
  certifications: string[] | null
  summary: string | null
  strengths: string[] | null
  flags: string[] | null
  status: string
  interview_id?: string | null
  interview_status?: string | null
  interview_score?: number | null
  interview_summary?: string | null
  match_score?: number | null
  match_summary?: string | null
  rejection_reason?: string | null
}

export interface RecruitingPosting {
  title?: string
  description?: string
  requirements?: string
  compensation?: string
  location?: string
  employment_type?: string
}

export interface RecruitingData {
  posting?: RecruitingPosting
  candidates?: ResumeCandidate[]
  shortlist_ids?: string[]
  dismissed_ids?: string[]
}

export interface ProjectCollaborator {
  user_id: string
  name: string
  email: string
  avatar_url: string | null
  role: 'owner' | 'collaborator'
  created_at: string
}

// ── Project kanban tasks (collaborative 5-column board) ──

/** Board lane. Order on the board: todo → in_progress → review →
 *  changes_requested → done (matches the desktop `kanbanColumns`). The backend
 *  also tolerates legacy sales-pipeline stages, but the web board only uses
 *  these five. */
export type BoardColumn =
  | 'todo'
  | 'in_progress'
  | 'review'
  | 'changes_requested'
  | 'done'

export type TaskPriority = 'critical' | 'high' | 'medium' | 'low'

/** A file attached to a kanban task — embedded in the list query so cards can
 *  render thumbnails without an N+1 follow-up (shape from
 *  project_file_service.list_files_for_tasks). storage_url is presigned. */
export interface MWTaskAttachment {
  id: string
  project_id: string
  task_id: string
  uploaded_by: string | null
  filename: string
  storage_url: string
  content_type: string | null
  file_size: number
  folder_id: string | null
  created_at: string
  uploader_name: string | null
  uploader_avatar_url: string | null
}

/** One kanban card (`mw_tasks` row with project_id set). Mirrors the desktop
 *  `MWProjectTask`. The aggregate fields (`subtask_total`, `subtask_done`,
 *  `review_cycle_count`, `last_moved_at`, `assigned_name`, `assigned_email`,
 *  `attachments`, `update_count`, `recent_event_ids`, `element_name`) are
 *  present only on the list query — create/update/reject RETURNING clauses
 *  omit them, so treat them as optional. */
export interface MWProjectTask {
  id: string
  project_id: string | null
  company_id?: string | null
  created_by?: string | null
  title: string
  description: string | null
  board_column: BoardColumn
  priority: TaskPriority
  status: 'pending' | 'completed' | 'cancelled'
  assigned_to: string | null
  assigned_name?: string | null
  assigned_email?: string | null
  /** List-query-only (like the aggregates below): assignee's profile photo. */
  assigned_avatar_url?: string | null
  /** List-query-only: ticket creator identity for the card-face badge. */
  created_by_name?: string | null
  created_by_avatar_url?: string | null
  due_date: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  progress_note: string | null
  category: string | null
  element_id: string | null
  element_name?: string | null
  review_note?: string | null
  // List-query-only aggregates (undefined on create/update/reject responses).
  last_moved_at?: string | null
  review_cycle_count?: number | null
  subtask_total?: number | null
  subtask_done?: number | null
  update_count?: number | null
  recent_event_ids?: string[] | null
  attachments?: MWTaskAttachment[]
}

/** Body accepted by `POST /projects/{id}/tasks`. Only `title` is required. */
export interface MWProjectTaskCreate {
  title: string
  board_column?: BoardColumn
  priority?: TaskPriority
  description?: string | null
  assigned_to?: string | null
  due_date?: string | null
  category?: string | null
}

/** Partial patch for `PATCH /projects/{id}/tasks/{taskId}`. Send ONLY the keys
 *  that changed — a present key with a null value (e.g. `board_column: null`)
 *  is rejected 400 by the column validator (drag-to-move sends just
 *  `{ board_column }`). */
export type MWProjectTaskPatch = Partial<{
  title: string
  description: string | null
  board_column: BoardColumn
  priority: TaskPriority
  status: 'pending' | 'completed' | 'cancelled'
  assigned_to: string | null
  due_date: string | null
  progress_note: string | null
}>

/** A checklist item under a kanban task (`mw_subtasks`). */
export interface MWSubtask {
  id: string
  task_id: string | null
  project_id: string | null
  title: string
  is_done: boolean
  position: number
  round_index: number | null
  assigned_to: string | null
  created_by: string | null
  completed_at: string | null
  created_at: string | null
  updated_at: string | null
}

// ── Research Tasks ──

export interface ResearchField {
  name: string
  label: string
  type: 'text' | 'boolean' | 'number'
}

export interface ResearchInput {
  id: string
  url: string
  status: 'pending' | 'running' | 'completed' | 'error'
  queued_at?: string
  completed_at?: string
  error?: string
}

export interface ResearchResult {
  input_id: string
  findings: Record<string, unknown>
  summary?: string
  screenshot_url?: string
}

export interface ResearchTask {
  id: string
  name: string
  instructions: string
  inputs: ResearchInput[]
  results: ResearchResult[]
}

export interface ResearchData {
  research_tasks?: ResearchTask[]
}

export interface MWProject {
  id: string
  title: string
  project_type: 'general' | 'presentation' | 'recruiting'
  sections: ProjectSection[]
  project_data: RecruitingData & ResearchData & Record<string, unknown>
  status: string
  is_pinned: boolean
  version: number
  chat_count: number
  chats?: MWThread[]
  collaborator_role?: 'owner' | 'collaborator'
  collaborators?: ProjectCollaborator[]
  hiring_client_id?: string | null
  hiring_client_name?: string | null
  created_at: string
  updated_at: string
}

export interface RecruitingClient {
  id: string
  name: string
  website?: string | null
  logo_url?: string | null
  notes?: string | null
  created_at: string
  updated_at: string
  archived_at?: string | null
  project_count?: number
}

export interface AgentEmail {
  id: string
  subject: string
  from: string
  date: string
  body: string
}

export interface DiagramData {
  svg_source: string
  storage_url: string
  created_from: string
}

export interface ProjectSection {
  id: string
  title: string | null
  content: string
  source_message_id: string | null
  diagram_data?: DiagramData[]
}

export interface InventoryItem {
  id: string
  filename: string
  product_name: string | null
  sku: string | null
  category: string | null
  quantity: number | null
  unit: string | null
  unit_cost: number | null
  total_cost: number | null
  vendor: string | null
  par_level: number | null
  status: string
}

export interface PresentationSlide {
  title: string
  bullets: string[] | null
  speaker_notes: string | null
}

export interface PresentationState {
  presentation_title: string | null
  subtitle: string | null
  theme: string | null
  slides: PresentationSlide[] | null
  cover_image_url: string | null
  generated_at: string | null
}

export interface MWThread {
  id: string
  title: string
  status: string
  task_type: MWTaskType | null
  is_pinned: boolean
  node_mode: boolean
  compliance_mode: boolean
  payer_mode: boolean
  collaborator_count: number
  version: number
  created_at: string
  updated_at: string
}

// Gemini's reasoning step
export interface AIReasoningStep {
  step: number
  question: string
  answer: string
  conclusion: string
  sources: string[]
}

// Pre-computed jurisdiction level
export interface ComplianceReasoningLevel {
  jurisdiction_level: string
  jurisdiction_name: string
  title: string
  current_value: string | null
  numeric_value: number | null
  source_url: string | null
  statute_citation: string | null
  trigger_condition: Record<string, unknown> | null
  is_governing: boolean
  effective_date: string | null
  last_verified_at: string | null
  previous_value: string | null
  last_changed_at: string | null
  expiration_date: string | null
  requires_written_policy: boolean
  penalty_summary: string | null
  enforcing_agency: string | null
}

export interface ComplianceReasoningCategory {
  category: string
  governing_level: string
  precedence_type: 'floor' | 'ceiling' | 'supersede' | 'additive' | null
  reasoning_text: string | null
  legal_citation: string | null
  all_levels: ComplianceReasoningLevel[]
}

export interface ComplianceReasoningLocation {
  location_id: string
  location_label: string
  facility_attributes: Record<string, unknown> | null
  activated_profiles: { label: string; categories: string[] }[]
  categories: ComplianceReasoningCategory[]
}

export interface PayerPolicySource {
  payer_name: string
  policy_title: string | null
  policy_number: string | null
  source_url: string | null
  similarity: number
}

export interface AffectedEmployeeGroup {
  location: string
  count: number
  match_type: 'exact' | 'state'
}

export interface ComplianceGap {
  category: string
  label: string
  status: 'missing' | 'partial'
}

export interface MWMessageMetadata {
  compliance_reasoning?: ComplianceReasoningLocation[]
  ai_reasoning_steps?: AIReasoningStep[]
  referenced_categories?: string[]
  referenced_locations?: string[]
  payer_sources?: PayerPolicySource[]
  affected_employees?: AffectedEmployeeGroup[]
  compliance_gaps?: ComplianceGap[]
}

export interface MWMessage {
  id: string
  thread_id: string
  role: 'user' | 'assistant'
  content: string
  version_created: number | null
  metadata: MWMessageMetadata | null
  created_at: string
}

export interface MWThreadDetail extends MWThread {
  current_state: Record<string, unknown>
  linked_offer_letter_id: string | null
  messages: MWMessage[]
}

export interface MWTokenUsage {
  prompt_tokens: number | null
  completion_tokens: number | null
  total_tokens: number | null
  estimated: boolean
  model: string | null
  cost_dollars: number | null
}

export interface MWSendResponse {
  user_message: MWMessage
  assistant_message: MWMessage
  current_state: Record<string, unknown>
  version: number
  task_type: MWTaskType | null
  pdf_url: string | null
  token_usage: MWTokenUsage | null
}

export interface MWCreateResponse {
  id: string
  title: string
  status: string
  current_state: Record<string, unknown>
  version: number
  task_type: MWTaskType | null
  is_pinned: boolean
  node_mode: boolean
  compliance_mode: boolean
  payer_mode: boolean
  created_at: string
  assistant_reply: string | null
  pdf_url: string | null
}

// SSE event types from the stream endpoint
export type MWStreamEvent =
  | { type: 'usage'; data: MWTokenUsage & { stage: 'estimate' | 'final' } }
  | { type: 'status'; message: string }
  | { type: 'complete'; data: MWSendResponse }
  | { type: 'error'; message: string }
  | { type: 'keepalive' }
