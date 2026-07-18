export type AuthorityIndex = {
  slug: string
  name: string
  level: string
  jurisdiction_id: string | null
  source_type: string
  enumerable: boolean
  item_count: number
  unclassified_count: number
  last_ingested_at: string | null
}

export type AuthorityItem = {
  id: string
  citation: string
  heading: string | null
  disposition: string | null
  regulation_key: string | null
  status: string | null
  proposed_by: string | null
  applies_to_categories: string[] | null
  excludes_categories: string[] | null
  excluded_reason: string | null
  entity_condition: Record<string, unknown> | null
}

export type Vocabulary = {
  dispositions: string[]
  categories: Array<{ slug: string; label: string; parent: string | null }>
  keys_by_category: Record<string, string[]>
}

export type Stratum = {
  id: string
  level: string
  jurisdiction_label: string | null
  category_slug: string | null
  label: string | null
  status: string
  item_count: number
  key_count: number
  refreshed_at: string | null
}

export type ShadowRow = {
  id: string
  company_id: string | null
  company_name: string | null
  resolve_keys: string[]
  expand_keys: string[]
  only_in_resolve: string[]
  only_in_expand: string[]
  created_at: string
}
