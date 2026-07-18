// Local types for the Jurisdiction Detail panel.

import type { PreemptionRule, IndustryProfile } from '../jurisdiction/types'

export type JurisdictionReq = {
  id: string
  requirement_key: string
  category: string
  jurisdiction_level: string
  jurisdiction_name: string
  applicable_industries?: string[]
  title: string
  description: string | null
  current_value: string | null
  source_url: string | null
  source_url_status?: 'unchecked' | 'ok' | 'dead' | null
  source_name: string | null
  effective_date: string | null
  is_bookmarked: boolean
  sort_order: number | null
  previous_value: string | null
  last_verified_at: string | null
}

export type LinkedLocation = {
  id: string
  name: string | null
  city: string
  company_name: string
}

export type ChildJurisdiction = {
  id: string
  city: string
  state: string
}

export type JurisdictionDetail = {
  id: string
  city: string
  state: string
  county: string | null
  parent_id: string | null
  children: ChildJurisdiction[]
  requirements: JurisdictionReq[]
  legislation: { id: string; category: string; title: string; current_status: string; expected_effective_date: string | null; source_url: string | null }[]
  locations: LinkedLocation[]
}

export type ViewMode = 'requirements' | 'hierarchy' | 'legislation'

export type EditForm = {
  title: string
  description: string
  current_value: string
  effective_date: string
  source_url: string
  source_name: string
}

export type Props = {
  id: string
  city: string
  state: string
  categoriesMissing?: string[]
  preemptionRules?: PreemptionRule[]
  selectedProfile?: IndustryProfile | null
  onCheckComplete?: () => void
  onNavigate?: (id: string) => void
  // URL-driven focus: 'general' (or empty) → General employment law section;
  // an industry tag (e.g. 'manufacturing', 'healthcare') → that industry section.
  initialIndustry?: string | null
  // URL-driven focus on ONE requirement id — scroll to + highlight it (the
  // post-codify "here's the exact policy" deep-link). Takes precedence over section.
  initialReq?: string | null
  // Optional cross-link to the Coverage map for this coordinate.
  onViewCoverage?: () => void
}

// Shared bundle of row-render dependencies passed down to the row/category renderers.
export type RowContext = {
  editingId: string | null
  editForm: EditForm
  setEditForm: (form: EditForm) => void
  saving: boolean
  saveEdit: () => void
  setEditingId: (id: string | null) => void
  reordering: boolean
  reorderReq: (reqId: string, direction: -1 | 1) => void
  toggleBookmark: (reqId: string) => void
  startEditing: (req: JurisdictionReq) => void
  profileFocused: Set<string> | null
  profileEvidence: Record<string, { confidence: number; reason: string }> | null
  initialReq?: string | null
}
