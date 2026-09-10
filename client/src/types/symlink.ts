// Sym-link — bounded, guided task links. Mirrors server/app/matcha/models/symlink.py
// and services/symlink/kinds.py (the spec shape).

export type SymlinkKind = 'credential_upload' | 'manager_review' | 'info_update' | 'custom'
export type SymlinkStatus =
  | 'pending'
  | 'in_progress'
  | 'submitted'
  | 'applied'
  | 'rejected'
  | 'revoked'
  | 'expired'
export type SubmissionStatus = 'pending' | 'applied' | 'rejected'
export type SpecFieldType = 'text' | 'long_text' | 'date_text' | 'number' | 'choice'

export type SpecField = {
  key: string
  label: string
  type: SpecFieldType
  required: boolean
  hint?: string | null
  max_len?: number
  choices?: string[] | null
}

export type SpecAttachment = {
  slot: string
  label: string
  required: boolean
  accept?: string[]
}

export type SymlinkSpec = {
  kind: SymlinkKind
  goal: string
  opening_message: string
  fields: SpecField[]
  attachments: SpecAttachment[]
  document_type?: string
  submit_label?: string
}

export type KindCatalogEntry = {
  kind: SymlinkKind
  label: string
  description: string
  spec: SymlinkSpec
  credential_document_types: string[] | null
}

export type SpecFieldOverride = {
  key: string
  label: string
  type?: SpecFieldType
  required?: boolean
  hint?: string | null
  choices?: string[] | null
}

export type SpecAttachmentOverride = {
  slot: string
  label: string
  required?: boolean
  /** Extensions (".pdf", ".docx"…). Omitted ⇒ every supported type for a sender-defined slot. */
  accept?: string[] | null
}

export type SpecOverrides = {
  goal?: string | null
  fields?: SpecFieldOverride[] | null
  attachments?: SpecAttachmentOverride[] | null
  document_type?: string | null
}

export type SymlinkCreatePayload = {
  kind: SymlinkKind
  title: string
  instructions?: string | null
  recipient_name: string
  recipient_email: string
  employee_id?: string | null
  expires_in_days?: number
  spec_overrides?: SpecOverrides
  send_email?: boolean
}

export type SymlinkAttachment = {
  id: string
  slot: string
  file_name: string
  content_type?: string | null
  size_bytes: number
  uploaded_at?: string | null
}

export type SymlinkSubmission = {
  id: string
  symlink_id: string
  status: SubmissionStatus
  fields: Record<string, unknown>
  attachment_ids: string[]
  submitted_at?: string | null
  reviewed_by?: string | null
  reviewed_at?: string | null
  review_note?: string | null
  applied_ref?: Record<string, unknown> | null
  link?: Symlink
}

export type Symlink = {
  id: string
  kind: SymlinkKind
  title: string
  instructions?: string | null
  spec: SymlinkSpec
  recipient_name: string
  recipient_email: string
  employee_id?: string | null
  status: SymlinkStatus
  link: string
  expires_at?: string | null
  created_at?: string | null
  sent_at?: string | null
  last_sent_at?: string | null
  first_unlocked_at?: string | null
  completed_at?: string | null
  turn_count: number
  email_sent?: boolean | null
}

export type ChatMessage = { role: 'assistant' | 'user'; content: string }

export type SymlinkDetail = Symlink & {
  transcript: ChatMessage[]
  known_fields: Record<string, unknown>
  attachments: SymlinkAttachment[]
  submission: SymlinkSubmission | null
}

export type Passcode = {
  code: string
  rotated_at?: string | null
  next_rotation_at?: string | null
  rotation_weekday: number
  announce_channel_id?: string | null
  announced?: boolean
}

export type AnnounceChannel = { id: string; name: string; scope: string }
export type EmployeeOption = { id: string; name: string; email: string }

// ── public (recipient) side ───────────────────────────────────────────────

export type PublicSpec = {
  kind: SymlinkKind
  goal: string
  opening_message: string
  fields: SpecField[]
  attachments: SpecAttachment[]
  submit_label: string
}

export type MissingItem = { kind: 'field' | 'attachment'; key: string; label: string }

export type PublicSymlinkInfo = {
  valid: boolean
  company_name: string | null
  title: string
  kind: SymlinkKind
  instructions?: string | null
  recipient_name: string
  status: SymlinkStatus
  expires_at?: string | null
  closed_message?: string
  unlocked?: boolean
  unlock_token?: string
  spec?: PublicSpec
  transcript?: ChatMessage[]
  known_fields?: Record<string, unknown>
  attachments?: SymlinkAttachment[]
  complete?: boolean
  missing?: MissingItem[]
  turn_count?: number
}

export type PublicTurnResponse = {
  assistant_message: string
  fields: Record<string, unknown>
  complete: boolean
  turn_count: number
  error: boolean
  limit_reached?: boolean
}
