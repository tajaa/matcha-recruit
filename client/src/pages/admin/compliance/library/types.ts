// Local types for the Jurisdiction Data admin page

export type Tab = 'explorer' | 'policies' | 'quality' | 'evals' | 'key-index' | 'integrity' | 'penalties' | 'preemption' | 'bookmarks' | 'api-sources' | 'schedule-rules'

export type SourceCount = {
  research_source: string
  total: number
  category_count: number
  jurisdiction_count: number
  earliest: string | null
  latest: string | null
}

export type ApiReqRow = {
  id: string
  category: string
  title: string
  description: string | null
  current_value: string | null
  source_name: string | null
  source_url: string | null
  effective_date: string | null
  created_at: string | null
  updated_at: string | null
  jurisdiction_level: string
  jurisdiction_name: string | null
  last_verified_at: string | null
  city: string
  state: string
}

export type ApiSourcesData = {
  source_counts: SourceCount[]
  recent_api: ApiReqRow[]
  api_by_category: { category: string; count: number }[]
}
