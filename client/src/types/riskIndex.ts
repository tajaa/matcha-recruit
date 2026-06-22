// Composite risk index — client portal + broker rollup.

export interface RiskComponent {
  key: string
  label: string
  weight: number
  score: number
  detail: string
}

export interface RiskIndex {
  company_id: string
  company_name?: string
  index: number | null
  band: string | null
  components: RiskComponent[]
  top_fixes: string[]
}

export interface RiskIndexPortfolioRow {
  company_id: string
  company_name: string
  industry: string | null
  index: number
  band: string
  components: RiskComponent[]
}

export interface RiskIndexPortfolio {
  summary: {
    client_count: number
    strong: number
    adequate: number
    developing: number
    exposed: number
    avg_index: number
  }
  companies: RiskIndexPortfolioRow[]
}

export const RISK_BAND_TONE: Record<string, string> = {
  strong: 'text-emerald-400',
  adequate: 'text-zinc-200',
  developing: 'text-amber-400',
  exposed: 'text-red-400',
}

// Submission-readiness — data→price completeness loop (folded into the portal).
export interface ReadinessItem {
  key: string
  label: string
  weight: number
  done: boolean
  fix: string
}

export interface SubmissionReadiness {
  score: number
  band: string
  items: ReadinessItem[]
  top_fixes: string[]
  summary: { done: number; total: number }
}

export const READINESS_BAND_TONE: Record<string, string> = {
  ready: 'text-emerald-400',
  developing: 'text-amber-400',
  thin: 'text-red-400',
}
