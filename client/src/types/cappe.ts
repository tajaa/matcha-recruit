// Cappe (website builder) — shared API response types.
// Cappe is a separate product from matcha; these types are independent of the
// matcha MeResponse / dashboard types.

export type CappeAccount = {
  id: string
  email: string
  name: string | null
  plan: 'free' | 'hosting' | 'pro' | 'business' | string
  status: 'active' | 'suspended' | 'deleted' | string
}

export type CappeTokenResponse = {
  access_token: string
  refresh_token: string
  expires_in: number
  account: CappeAccount
}

export type CappeSiteStatus = 'draft' | 'published' | 'archived'

export type CappeSite = {
  id: string
  account_id: string
  name: string
  slug: string
  subdomain: string | null
  custom_domain: string | null
  source_type: 'template' | 'byo' | 'blank' | string
  template_id: string | null
  status: CappeSiteStatus
  theme_config: Record<string, unknown>
  meta_config: Record<string, unknown>
  published_at: string | null
  created_at: string
  updated_at: string
  page_count?: number | null
}

export type CappePage = {
  id: string
  site_id: string
  title: string
  slug: string
  content: Record<string, unknown>
  sort_order: number
  status: CappeSiteStatus
  created_at: string
  updated_at: string
}

export type CappeTemplateSummary = {
  id: string
  name: string
  slug: string
  category: string
  description: string | null
  preview_image_url: string | null
  is_premium: boolean
  price_cents: number
}

export type CappeTemplateDetail = CappeTemplateSummary & {
  structure: Record<string, unknown>
}
