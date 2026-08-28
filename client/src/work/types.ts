export type InventoryNetworkSummary = {
  location_count: number
  matched_item_groups: number
  transfer_count: number
  shortages_fully_covered: number
  remaining_reorder_count: number
  attention_count: number
  inventory_value_moved: number | null
}

export type InventoryNetworkTransfer = {
  item_name: string
  unit: string | null
  quantity: number
  from_item_id: string
  from_location_id: string
  from_location_name: string
  from_current_quantity: number
  from_target_quantity: number
  from_post_transfer_quantity: number
  to_item_id: string
  to_location_id: string
  to_location_name: string
  to_current_quantity: number
  to_target_quantity: number
  to_post_transfer_quantity: number
  receiver_remaining_shortage: number
  runout_date: string | null
  order_by_date: string | null
  days_of_cover_added: number | null
  inventory_value: number | null
  coverage: 'full' | 'partial'
  confidence: 'low' | 'medium' | 'high'
  rationale: string
}

export type InventoryNetworkShortage = {
  item_id: string
  item_name: string
  unit: string | null
  location_id: string
  location_name: string
  shortage_quantity: number
  suggested_order_quantity: number
  runout_date: string | null
  order_by_date: string | null
  confidence: 'low' | 'medium' | 'high'
}

export type InventoryNetworkAttention = {
  item_id: string
  item_name: string
  location_id: string
  location_name: string
  status: 'count_required' | 'insufficient_history'
}

export type InventoryNetworkPlan = {
  forecast_start: string
  summary: InventoryNetworkSummary
  transfers: InventoryNetworkTransfer[]
  remaining_shortages: InventoryNetworkShortage[]
  attention: InventoryNetworkAttention[]
}

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
  pr_url?: string | null
  pr_number?: number | null
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
  element_id?: string | null
  /** Checklist titles created alongside the task (e.g. AI-drafted steps). */
  subtasks?: string[]
}

/** Response of `POST /projects/{id}/tasks/ai-draft` — a structured ticket draft
 *  from a natural-language prompt. No DB write; the caller reviews/edits, then
 *  creates via the normal `createProjectTask` call. Mirrors the desktop
 *  `MWTaskDraft`. */
export interface MWTaskDraft {
  title: string
  description: string | null
  priority: TaskPriority
  category: string
  board_column: BoardColumn
  assigned_to: string | null
  assigned_name: string | null
  element_id: string | null
  element_name: string | null
  subtasks: string[]
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
  pr_url: string | null
  pr_number: number | null
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

/** One row of `GET /projects/{id}/tasks/{taskId}/history` — the task audit
 *  trail. `metadata` is free-form JSONB whose keys vary by `event_type`
 *  (`subtask_rejected` carries subtask_id/title/reason/severity, `activity`
 *  carries body, …), so it stays loosely typed and callers narrow per key. */
export interface MWTaskHistoryEntry {
  id: string
  task_id: string
  event_type: string
  from_value: string | null
  to_value: string | null
  metadata: Record<string, unknown> | null
  created_at: string
  actor_user_id: string | null
  actor_name: string | null
  actor_avatar_url: string | null
  attachment_ids?: string[]
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
  // 'collab' projects carry a real discussion *channel* as their chat (see
  // ensureDiscussionChannel) — the mw_threads list is AI chat, a separate tab.
  project_type: 'general' | 'presentation' | 'recruiting' | 'collab'
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

// Grounding-mode keys — mirrors the backend registry
// (server/app/matcha/services/matcha_work_modes.py THREAD_MODES).
export type MWModeKey =
  | 'node'
  | 'compliance'
  | 'payer'
  | 'benefits'
  | 'legal'
  | 'risk'
  | 'training'
  | 'hr_pilot'
  | 'huume'

export interface MWThread {
  id: string
  title: string
  status: string
  task_type: MWTaskType | null
  is_pinned: boolean
  node_mode: boolean
  compliance_mode: boolean
  payer_mode: boolean
  benefits_mode: boolean
  legal_mode: boolean
  risk_mode: boolean
  training_mode: boolean
  hr_pilot_mode: boolean
  huume_mode: boolean
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

export interface ThresholdStatus {
  name: string
  threshold: number
  basis: string
  employee_count: number
  applies: boolean
  directional: boolean
}

export interface PayerAffectedStaff {
  location: string
  staff_count: number
  payers: string[]
}

/** One HR Pilot corpus record the answer cited. Server-side audit guarantees
 *  every entry here resolved against the corpus the prompt was built from. */
export interface HrPilotCitation {
  cid: string
  ref: string
  summary: string
  when?: string
  source?: string
  source_label?: string
  source_url?: string | null
  category?: string
  jurisdiction?: string
}

export interface MWThreadAttachment {
  url: string
  filename: string
  content_type?: string | null
  size?: number | null
  kind?: 'file' | 'image'
}

export interface MWMessageMetadata {
  /** Non-image files attached to this (user) message via POST /threads/{id}/files. */
  attachments?: MWThreadAttachment[]
  compliance_reasoning?: ComplianceReasoningLocation[]
  ai_reasoning_steps?: AIReasoningStep[]
  referenced_categories?: string[]
  referenced_locations?: string[]
  payer_sources?: PayerPolicySource[]
  affected_employees?: AffectedEmployeeGroup[]
  compliance_gaps?: ComplianceGap[]
  threshold_status?: ThresholdStatus[]
  payer_affected_staff?: PayerAffectedStaff[]
  /** HR Pilot cited answers — sources that resolved, and the ids that didn't. */
  citations?: HrPilotCitation[]
  dropped_citations?: string[]
  /** Huume agent-run tool-call timeline for this turn, if huume_mode was on. */
  huume_steps?: HuumeStep[]
  huume_run_id?: string
  /** Backend-authored Huume lifecycle notices (offer accept/decline routes,
   * REST plan-execute). Unknown future values must render as a plain bubble. */
  huume_event?: 'offer_accepted' | 'offer_declined' | 'plan_executed'
  offer_id?: string
}

// ──────────────────────────────────────────────────────────────────────
// Huume — agentic onboarding harness (matcha-work thread mode "huume")
// ──────────────────────────────────────────────────────────────────────

export interface HuumeStep {
  seq: number
  tool: string
  kind: 'read' | 'staged' | 'write' | 'finish'
  label: string
  status: 'ok' | 'rejected' | 'error' | 'skipped'
  detail?: string
  /** Tool-call input/output, capped server-side at ~4KB each (agent.py's
   * _cap_payload — an oversized value arrives as {_truncated, preview}).
   * Absent on messages persisted before the harness started recording them. */
  args?: unknown
  result?: unknown
}

export interface HuumeOffer {
  offer_id: string
  status: string
  event?: 'accepted' | 'declined'
  signed_name?: string | null
}

/** One row from `GET /threads/{id}/huume/offers` — every offer letter ever
 * drafted from this thread (`offer_letters.source_thread_id`), not just the
 * latest one `current_state.huume_offer` tracks. */
export interface HuumeThreadOffer {
  offer_id: string
  candidate_name: string
  status: string
}

/** One row from `GET /threads/{id}/huume/assets` — every durable artifact
 * Huume has created (offer letters, discipline records, incidents, schedule
 * changes, inventory rows, ...), registered at the moment each staged
 * action's executor succeeds. `status` is hydrated live server-side, not
 * stored — the underlying record moves through its own lifecycle. */
export interface HuumeAsset {
  asset_id: string
  asset_type: string
  ref_table: string
  ref_id: string
  label: string
  source: 'huume_action' | 'draft'
  created_at: string
  status: string | null
  thread_id: string | null
  thread_title: string
}

export interface HuumePlanStep {
  key: string
  label: string
  status: 'proposed' | 'approved' | 'skipped' | 'executing' | 'done' | 'failed'
  requires?: string | null
  reason?: string | null
  record_id?: string | null
  error?: string | null
}

export interface HuumePlan {
  status: 'proposed' | 'approved' | 'executing' | 'done' | 'cancelled'
  offer_id: string
  employee: { first_name?: string; last_name?: string; email?: string; position_title?: string }
  employee_id: string | null
  steps: HuumePlanStep[]
}

/** `current_state.huume_plans` — keyed by offer_id so a thread can be
 * onboarding several candidates at once. Replaces the old singular
 * `huume_plan` key (pre-release feature, no back-compat needed). */
export type HuumePlans = Record<string, HuumePlan>

export interface HuumeActionSendOffer {
  type: 'send_offer'
  offer_id: string
  status: 'proposed' | 'sent' | 'failed' | 'cancelled'
  candidate_name?: string
  recipient_email?: string
}

export interface HuumeActionDiscipline {
  type: 'discipline_draft'
  status: 'proposed' | 'filed' | 'failed' | 'cancelled'
  confirm_id: string
  employee_name?: string
  infraction_type?: string
  severity?: string
  occurrence_dates?: string[]
  description?: string
  expected_improvement?: string
}

export interface HuumeActionIrReport {
  type: 'ir_report'
  status: 'proposed' | 'filed' | 'failed' | 'cancelled'
  confirm_id: string
  description?: string
  occurred_at?: string | null
  incident_type?: string
  severity?: string
  location?: string | null
}

export interface HuumeActionErCase {
  type: 'er_case'
  status: 'proposed' | 'opened' | 'failed' | 'cancelled'
  confirm_id: string
  description?: string
  title?: string | null
  category?: string
}

export interface HuumeActionTrainingAssign {
  type: 'training_assign'
  status: 'proposed' | 'assigned' | 'failed' | 'cancelled'
  requirement_id: string
  employee_ids?: string[]
  due_date?: string | null
}

export interface HuumeActionPtoDecision {
  type: 'pto_decision'
  status: 'proposed' | 'decided' | 'failed' | 'cancelled'
  request_id: string
  decision?: 'approve' | 'deny'
  note?: string | null
}

export interface HuumeActionAmendHandbook {
  type: 'amend_handbook'
  status: 'proposed' | 'amended' | 'failed' | 'cancelled'
  target_handbook_id: string
  draft_ids?: string[]
  handbook_title?: string | null
}

/** Incident-triggered discipline draft — distinct from HuumeActionDiscipline
 * ('discipline_draft'): a record staged here goes to HR APPROVAL, it is never
 * issued directly. employee_id/incident_id are ids, never names (the backend
 * takes ids only); employee_name is enrichment-only, added at stage time for
 * display, never sent back on confirm. */
export interface HuumeActionDisciplineFromIncident {
  type: 'discipline_from_incident'
  status: 'proposed' | 'filed' | 'failed' | 'cancelled'
  confirm_id: string
  employee_id: string
  employee_name?: string
  incident_id?: string | null
  infraction_type: string
  severity?: string
  discipline_type?: string
  occurrence_dates?: string[]
  description?: string
  expected_improvement?: string
  template_id?: string | null
  template_name?: string | null
  rendered_preview?: string | null
  missing_fields?: string[]
}

export interface HuumeActionDisciplineDecision {
  type: 'discipline_decision'
  status: 'proposed' | 'decided' | 'failed' | 'cancelled'
  record_id: string
  decision?: 'approve' | 'deny'
  reason?: string | null
}

/** Promote a logged EMS event into a real IR incident — mirrors the
 * Events-tab button's own promote flow, staged here so it goes through the
 * same confirm-first two-turn gate as every other Huume write. */
export interface HuumeActionEmsPromote {
  type: 'ems_promote'
  status: 'proposed' | 'promoted' | 'failed' | 'cancelled'
  event_id: string
  title?: string | null
  incident_type?: string
  severity?: string
  occurred_at?: string | null
  location?: string | null
}

/** Stock in/out/stockout/adjust — see actions.py's _validate_inventory_movement.
 * Exactly one of item_id/new_item_name is set; quantity is null for stockout
 * (always zeroes the count regardless of what was asked). */
export interface HuumeActionInventoryMovement {
  type: 'inventory_movement'
  status: 'proposed' | 'recorded' | 'failed' | 'cancelled'
  confirm_id: string
  kind: 'in' | 'out' | 'stockout' | 'adjust'
  item_id?: string | null
  new_item_name?: string | null
  quantity?: number | null
  location_id?: string | null
  note?: string | null
}

export interface HuumeActionInventoryOrderDecision {
  type: 'inventory_order_decision'
  status: 'proposed' | 'decided' | 'failed' | 'cancelled'
  order_id: string
  decision: 'approve' | 'receive' | 'cancel'
  quantity?: number | null
}

export interface HuumeActionInventoryItemCreate {
  type: 'inventory_item_create'
  status: 'proposed' | 'created' | 'failed' | 'cancelled'
  confirm_id: string
  name: string
  unit?: string | null
  initial_quantity?: number | null
  low_stock_threshold?: number | null
  location_id?: string | null
}

export interface HuumeActionInventoryItemArchive {
  type: 'inventory_item_archive'
  status: 'proposed' | 'archived' | 'failed' | 'cancelled'
  item_id: string
}

export interface HuumeActionInventoryReceiptLine {
  item_id?: string | null
  new_item_name?: string | null
  order_id?: string | null
  quantity?: number | null
}

/** `dup_warning` rides the staged dict from stage time through to done/failed
 * (agent.py spreads the original `staged` dict, not the executor's action) —
 * it's never sent back to the executor (see actions.py's
 * _validate_inventory_receipt), just shown here. */
export interface HuumeActionInventoryReceipt {
  type: 'inventory_receipt'
  status: 'proposed' | 'committed' | 'failed' | 'cancelled'
  confirm_id: string
  lines: HuumeActionInventoryReceiptLine[]
  vendor?: string | null
  invoice_number?: string | null
  location_id?: string | null
  dup_warning?: string | null
}

/** Thread Huume's `propose_schedule_change` — see services/huume/schedule_skill.py.
 * `proposal_id`/`pill_text` are merged in by `schedule_skill.propose` on the stage
 * turn (the source of truth `execute` reads); the rest are the raw model args,
 * kept for the model's own reference across the confirm turn. */
export interface HuumeActionScheduleChange {
  type: 'schedule_change'
  status: 'proposed' | 'applied' | 'failed' | 'cancelled'
  confirm_id: string
  proposal_id?: string
  pill_text?: string
  kind?: string
  location_name?: string | null
  target_employee_name?: string | null
  target_date?: string | null
  target_role_hint?: string | null
  to_employee_name?: string | null
  second_employee_name?: string | null
  second_date?: string | null
  second_role_hint?: string | null
  new_date?: string | null
  new_start_time?: string | null
  new_end_time?: string | null
  shift_by_minutes?: number | null
  label?: string | null
  date?: string | null
  start_time?: string | null
  end_time?: string | null
  count?: number | null
  employee_names?: string[] | null
}

export interface HuumeActionScheduleWeekDraft {
  type: 'schedule_week_draft'
  status: 'proposed' | 'applied' | 'failed' | 'cancelled'
  confirm_id: string
  generation_run_id: string
  location_id: string
  week_start: string
  source_mode: 'existing' | 'template'
  week_template_id?: string | null
  summary?: string | null
  metrics?: {
    shift_count?: number
    required_positions?: number
    fixed_positions?: number
    overstaffed_positions?: number
    proposed_positions?: number
    filled_positions?: number
    open_positions?: number
  }
  unfilled?: Array<{
    shift_key?: string
    starts_at?: string
    role?: string | null
    reason?: string
  }>
  schedule_preview?: Array<{
    shift_key: string
    starts_at: string
    ends_at: string
    role?: string | null
    required_staff: number
    assignment_names: string[]
    existing_assignment_count?: number
  }>
  preview_truncated?: boolean
  origin?: 'manual' | 'automatic'
  auto_generated?: boolean
}

export interface HuumeActionScheduleNote {
  type: 'schedule_note'
  status: 'proposed' | 'created' | 'failed' | 'cancelled'
  confirm_id: string
  location_id: string
  shift_id: string
  employee_id: string
  note?: string | null
}

export interface HuumeActionMealBreakWaiver {
  type: 'meal_break_waiver'
  status: 'proposed' | 'created' | 'failed' | 'cancelled'
  confirm_id: string
  location_id: string
  employee_id: string
  on_file: boolean
  effective_from?: string | null
  note?: string | null
}

export interface HuumeActionWorkPermit {
  type: 'work_permit'
  status: 'proposed' | 'created' | 'failed' | 'cancelled'
  confirm_id: string
  location_id: string
  employee_id: string
  issued_at?: string | null
  expires_at?: string | null
}

export interface HuumeActionEligibilityDecision {
  type: 'eligibility_case_decision'
  status: 'proposed' | 'created' | 'failed' | 'cancelled'
  confirm_id: string
  location_id: string
  case_id: string
  employee_id?: string
  decision: 'remove' | 'keep'
  acknowledgement_note?: string | null
}

/** `current_state.huume_action` — the single staged confirm-first action
 * (one slot: staging a new one replaces whatever was pending).
 * Confirm/cancel are chat-only tools; the UI's buttons send the literal
 * words through the normal message path (a separate user turn, so the
 * backend's structural two-turn rule is untouched — see services/huume/actions.py). */
export type HuumeAction =
  | HuumeActionSendOffer
  | HuumeActionDiscipline
  | HuumeActionIrReport
  | HuumeActionErCase
  | HuumeActionTrainingAssign
  | HuumeActionPtoDecision
  | HuumeActionAmendHandbook
  | HuumeActionDisciplineFromIncident
  | HuumeActionDisciplineDecision
  | HuumeActionEmsPromote
  | HuumeActionInventoryMovement
  | HuumeActionInventoryOrderDecision
  | HuumeActionInventoryItemCreate
  | HuumeActionInventoryItemArchive
  | HuumeActionInventoryReceipt
  | HuumeActionScheduleChange
  | HuumeActionScheduleWeekDraft
  | HuumeActionScheduleNote
  | HuumeActionMealBreakWaiver
  | HuumeActionWorkPermit
  | HuumeActionEligibilityDecision

/** Subset of the backend `OfferLetter` model — only what the Huume panel's
 * offer viewer needs for the terms strip. Extra backend fields are ignored. */
export interface OfferLetterDetail {
  id: string
  candidate_name: string
  candidate_email: string | null
  position_title: string
  company_name: string
  manager_name: string | null
  status: 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired'
  salary: string | null
  bonus: string | null
  employment_type: string | null
  location: string | null
  start_date: string | null
  sent_at: string | null
  signed_name: string | null
  signed_at: string | null
  declined_at: string | null
}

export interface HuumeLegal { matter_id: string; title?: string | null }

/** `opened_at` is a per-stage nonce (a run/step id), not a timestamp to
 * display — it exists purely so the panel can tell "Huume just re-opened
 * this same record" apart from "nothing changed", which record_type+
 * record_id alone can't (re-showing the same record is a no-op key). */
export interface HuumeRecordRef { record_type: string; record_id: string; label?: string | null; opened_at?: string | null }

export type HuumeRecordChipTone = 'red' | 'orange' | 'amber' | 'emerald' | 'zinc'

/** Server-normalized view of whatever `show_record` staged — one shape for
 * any record type (incident, er_case, employee, credential, …), rendered by
 * a single generic `RecordViewer`. Adding a record type is a backend-only
 * change as long as it fits this shape. */
export interface HuumeRecordView {
  record_type: string
  record_id: string
  title: string
  subtitle?: string | null
  chips: { label: string; tone: HuumeRecordChipTone }[]
  meta: { label: string; value: string }[]
  sections: { label: string; body?: string | null; items?: string[] | null }[]
  link: string
}

export interface HuumeHandbook {
  session_id: string
  pending_drafts: { draft_id: string; kind?: string; title?: string }[]
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
  benefits_mode: boolean
  legal_mode: boolean
  risk_mode: boolean
  training_mode: boolean
  hr_pilot_mode: boolean
  huume_mode: boolean
  created_at: string
  assistant_reply: string | null
  pdf_url: string | null
}

// SSE event types from the stream endpoint
export type MWStreamEvent =
  | { type: 'usage'; data: MWTokenUsage & { stage: 'estimate' | 'final' } }
  | { type: 'status'; message: string }
  | { type: 'step'; data: HuumeStep }
  | { type: 'complete'; data: MWSendResponse }
  | { type: 'error'; message: string }
  | { type: 'keepalive' }
