// Shared types across the Compliance Studio tabs. Split out so the worklist
// (Command Center) and the individual tabs can reference the same shapes
// without importing from each other's tab files.

// ── Library (jurisdictions repository) ──────────────────────────────────────

export type Jurisdiction = {
  id: string
  city: string
  state: string
  county: string | null
  parent_id: string | null
  parent_city: string | null
  parent_state: string | null
  children_count: number
  requirement_count: number
  legislation_count: number
  location_count: number
  auto_check_count: number
  inherits_from_parent: boolean
  last_verified_at: string | null
  created_at: string | null
}

export type ListResponse = {
  jurisdictions: Jurisdiction[]
  totals: { total_jurisdictions: number; total_requirements: number; total_legislation: number; total_codified?: number }
}

export type ResearchItem = {
  jurisdiction_id: string
  city: string
  state: string
  county: string | null
  repo_count: number
  location_count: number
  company_count: number
  status: string
  created_at: string | null
}

// ── Pipeline (demand funnel: coverage requests → review → approve → codify) ─

export type PendingCategoryDetail = {
  key: string | null
  name: string
  description: string | null
}

export type CategoryPendingItem = {
  type: 'category'
  id: string
  city: string
  state: string
  county: string | null
  status: string
  company_name: string
  employee_count: number
  note: string | null
  categories: PendingCategoryDetail[]
  created_at: string | null
}

export type VerticalPendingItem = {
  type: 'vertical'
  company_id: string
  company_name: string
  label: string
  areas: number
  categories: PendingCategoryDetail[]
  jurisdictions: string[]
  created_at: string | null
}

export type PendingItem = CategoryPendingItem | VerticalPendingItem

export type ReviewRow = {
  id: string
  category: string
  category_name: string
  title: string
  description: string | null
  current_value: string | null
  source_url: string | null
  source_name: string | null
  regulation_key: string | null
  // True → approving reconciles this into a verified statute citation; false →
  // it goes live but still needs classifying/codifying to complete.
  will_codify: boolean
}

// Per-row codification outcome returned by /research-review/approve.
export type ApproveResult = {
  id: string
  title: string
  description: string | null
  current_value: string | null
  source_url: string | null
  source_name: string | null
  regulation_key: string | null
  codified: boolean
  statute_citation: string | null
  citation_url: string | null
  citation_item_id: string | null
  state: string | null
  city: string | null
}

export type ReviewGroup = {
  jurisdiction_id: string
  label: string
  city: string
  state: string
  request_ids: string[]
  company_ids: string[]
  rows: ReviewRow[]
}

// A live-but-uncodified requirement surfaced by the Command Center worklist.
export type UncodifiedItem = {
  id: string
  title: string
  regulation_key: string | null
  description: string | null
  current_value: string | null
  source_url: string | null
  source_name: string | null
  state: string | null
  city: string | null
}

// ── Command Center worklist ──────────────────────────────────────────────────

export type WorklistAction =
  | { kind: 'review_staged'; priority: number; count: number; groups: ReviewGroup[] }
  | { kind: 'codify_uncodified'; priority: number; count: number; auto_reconcilable: number; items: UncodifiedItem[] }
  | { kind: 'research_coverage'; priority: number; count: number; items: PendingItem[] }
  | { kind: 'confirm_authority'; priority: number; count: number; by_index: { slug: string; name: string; unclassified_count: number }[] }
  | { kind: 'ack_drift'; priority: number; count: number }
  | { kind: 'research_baseline'; priority: number; count: number; items: ResearchItem[] }

export type Worklist = {
  // keyless: active, uncodified rows with no regulation_key — they can't codify
  // (the modal 422s), so they cap the Authoritative % below 100 with no worklist
  // action to clear them. Surfaced on the meter tooltip, not as an action.
  meters: { codified: number; requirements: number; keyless: number; open_items: number }
  actions: WorklistAction[]
}

// ── Studio-wide view routing ─────────────────────────────────────────────────

export type StudioView = 'home' | 'pipeline' | 'coverage' | 'authority' | 'library'

export type GotoParams = { state?: string; city?: string; industry?: string }
