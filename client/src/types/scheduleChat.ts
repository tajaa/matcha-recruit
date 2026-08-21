export type ScheduleChatKind = 'proposal' | 'clarify' | 'unactionable'

export interface ScheduleChatViolation {
  severity: string
  message: string
  statute?: string | null
}

export interface ScheduleChatShift {
  label: string
  role: string | null
  starts_at: string
  ends_at: string
  required_staff: number
  assignees: { employee_id: string; name: string; violations: ScheduleChatViolation[] }[]
  open_slots: number
  excluded: { name: string; reason: string }[]
  intrinsic_violations: ScheduleChatViolation[]
}

export interface ScheduleChatOp {
  kind: string
  starts_at?: string
  ends_at?: string
  new_starts_at?: string
  new_ends_at?: string
  shift_role?: string | null
  from_employee_name?: string | null
  to_employee_name?: string | null
  reason?: string
  ok?: boolean
}

export interface ScheduleChatTemplateBlock {
  name: string
  role: string | null
  start_time: string
  end_time: string
  required_staff: number
  days_of_week: number[]
}

export interface ScheduleChatWeekTemplate {
  name: string
  location_name?: string | null
  blocks: ScheduleChatTemplateBlock[]
}

export interface ScheduleChatApplyPreviewBlock {
  name: string
  start_time: string
  end_time: string
  days: number
  shifts: number
}

export interface ScheduleChatProposal {
  kind?: 'edit' | 'template' | 'apply_template'
  ack?: string
  clarify_question?: string | null
  clarify_options?: string[]
  shifts?: ScheduleChatShift[]
  ops?: ScheduleChatOp[]
  week_template?: ScheduleChatWeekTemplate
  week_template_name?: string
  start_date?: string
  end_date?: string
  total_shifts?: number
  blocks_preview?: ScheduleChatApplyPreviewBlock[]
}

export interface ScheduleChatTurnResponse {
  proposal_id: string | null
  kind: ScheduleChatKind
  message: string
  proposal: ScheduleChatProposal | null
  pill_text?: string
}

export interface ScheduleChatApplyResponse {
  ok: boolean
  text: string
  shift_ids: string[]
  week_template_id?: string | null
}

export type ScheduleVoiceCommand = 'confirm' | 'cancel' | 'other'

export interface ScheduleVoiceTranscript {
  available: boolean
  transcript: string | null
  command: ScheduleVoiceCommand
  model: string | null
}
