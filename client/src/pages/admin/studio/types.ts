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

// Geography-hierarchy tree for the Library shelf (GET /admin/jurisdictions/tree).
export type TreeNode = {
  id: string
  city: string | null
  state: string
  county: string | null
  level: string
  parent_id: string | null
  display_name: string | null
  requirement_count: number
  legislation_count: number
  location_count: number
  last_verified_at: string | null
}

export type TreeStateGroup = {
  code: string
  state_node: TreeNode | null
  children: TreeNode[]
}

export type TreeResponse = {
  federal: TreeNode[]
  states: TreeStateGroup[]
  totals: ListResponse['totals']
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

// ── Codified tab (the asset, and the funnel that feeds it) ───────────────────

// GET /admin/studio/codified-funnel. `scoped` is null until a state is picked:
// it comes from a per-chain walk (chain_uncodified), and it counts LABOR-domain
// obligations only — say so wherever it renders.
export type CodifiedFunnel = {
  state: string | null
  category: string | null
  scoped: { keyed: number; unkeyed: number } | null
  pending: number
  researched: number
  codified: number
  keyless: number
}

// One cell of GET /admin/studio/codified-breakdown: an authority × category.
// `level` is NOT an authority identity — 'national' means a foreign country in
// this catalog, while US federal law is 'federal'. Key on jurisdiction_id.
export type BreakdownRow = {
  jurisdiction_id: string
  level: string
  country_code: string | null
  state: string | null
  jurisdiction_name: string | null
  category: string
  group: string
  category_name: string
  total: number
  codified: number
}

// The shapes buildCodifiedSchema() folds those cells into.
export type CategoryStat = { category: string; name: string; total: number; codified: number }
export type GroupStat = { group: string; total: number; codified: number; categories: CategoryStat[] }
export type AuthorityNode = {
  id: string
  level: string
  state: string | null
  label: string
  total: number
  codified: number
  groups: GroupStat[]
}
export type SchemaSection = {
  code: string
  label: string
  total: number
  codified: number
  nodes: AuthorityNode[]
}

// What the schema panel hands the table when a cell is clicked.
export type CodifiedSelection = {
  jurisdictionId: string
  state: string | null
  label: string
  category?: string
  categoryName?: string
  group?: string
}

// One row of GET /admin/jurisdictions/quality-audit.
export type AuditRow = {
  id: string
  jurisdiction_id: string
  category: string | null
  title: string | null
  description: string | null
  source_url: string | null
  source_url_status: string | null
  current_value: string | null
  jurisdiction_name: string | null
  state: string | null
  city: string | null
  statute_citation: string | null
  citation_verified: boolean
  citation_verified_at: string | null
  regulation_key: string | null
  last_verified_at: string | null
}

export type AuditResponse = {
  summary: { total: number; verified_citation: number; unverified_citation: number }
  requirements: AuditRow[]
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

// ── Coverage: cross-jurisdiction industry grid (GET /admin/vertical-coverage) ─

export type VerticalIndustry = { tag: string; cells: number; covered: number }

export type VerticalCoverageCell = { status: string; written: number }

export type VerticalCoverageRow = {
  jurisdiction_id: string
  display_name: string | null
  city: string | null
  state: string | null
  level: string
  cells: Record<string, VerticalCoverageCell>
  summary: Record<string, number>
}

export type VerticalCoverageResponse = {
  industry_tag: string | null
  industries: VerticalIndustry[]
  categories: { slug: string; name: string }[]
  jurisdictions: VerticalCoverageRow[]
}

// ── Studio-wide view routing ─────────────────────────────────────────────────

export type StudioView = 'home' | 'pipeline' | 'coverage' | 'authority' | 'library' | 'codified' | 'pilot'

export type GotoParams = { state?: string; city?: string; industry?: string }
