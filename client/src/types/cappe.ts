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
  timezone: string
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

// A content block in a page. Shape varies by `type`; the editor reads/writes
// fields generically against a per-type schema.
export type CappeBlock = { type: string; [key: string]: unknown }

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

// --- Shop -------------------------------------------------------------------

export type CappeProduct = {
  id: string
  site_id: string
  name: string
  description: string | null
  price_cents: number
  currency: string
  image_url: string | null
  sku: string | null
  inventory: number | null
  status: 'active' | 'draft' | 'archived'
  sort_order: number
  created_at: string
  updated_at: string
}

export type CappeProductInput = {
  name: string
  description?: string | null
  price_cents: number
  currency?: string
  image_url?: string | null
  sku?: string | null
  inventory?: number | null
  status?: 'active' | 'draft' | 'archived'
  sort_order?: number
}

export type CappeOrderItem = {
  id: string
  product_id: string | null
  title: string
  unit_price_cents: number
  quantity: number
}

export type CappeOrder = {
  id: string
  site_id: string
  customer_email: string | null
  customer_name: string | null
  status: 'pending' | 'paid' | 'fulfilled' | 'cancelled' | 'refunded'
  subtotal_cents: number
  currency: string
  payment_ref: string | null
  note: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  items: CappeOrderItem[]
}

// --- Newsletter -------------------------------------------------------------

export type CappeSubscriber = {
  id: string
  site_id: string
  email: string
  name: string | null
  status: 'subscribed' | 'unsubscribed' | 'bounced' | 'pending'
  source: string
  created_at: string
  unsubscribed_at: string | null
}

export type CappeCampaign = {
  id: string
  site_id: string
  subject: string
  body_html: string | null
  from_name: string | null
  status: 'draft' | 'scheduled' | 'sending' | 'sent' | 'cancelled'
  scheduled_at: string | null
  sent_at: string | null
  recipient_count: number
  created_at: string
  updated_at: string
}

// --- Forms ------------------------------------------------------------------

export type CappeFormField = {
  key: string
  label: string
  type: string
  required: boolean
  options?: string[] | null
}

export type CappeForm = {
  id: string
  site_id: string
  name: string
  slug: string
  fields: CappeFormField[]
  status: 'active' | 'draft' | 'archived'
  created_at: string
  updated_at: string
}

export type CappeFormSubmission = {
  id: string
  form_id: string
  data: Record<string, unknown>
  submitter_email: string | null
  is_read: boolean
  created_at: string
}

// --- Bookings ---------------------------------------------------------------

export type CappeBookingType = {
  id: string
  site_id: string
  name: string
  description: string | null
  duration_minutes: number
  price_cents: number | null
  status: 'active' | 'draft' | 'archived'
  created_at: string
  updated_at: string
}

export type CappeAvailabilitySlot = {
  weekday: number
  start_time: string
  end_time: string
  booking_type_id: string | null
}

export type CappeBooking = {
  id: string
  site_id: string
  booking_type_id: string | null
  customer_name: string | null
  customer_email: string | null
  starts_at: string
  ends_at: string
  status: 'pending' | 'confirmed' | 'cancelled' | 'completed'
  note: string | null
  created_at: string
}

// --- Blog -------------------------------------------------------------------

export type CappePost = {
  id: string
  site_id: string
  title: string
  slug: string
  excerpt: string | null
  body: string | null
  cover_image_url: string | null
  status: 'draft' | 'published' | 'archived'
  published_at: string | null
  created_at: string
  updated_at: string
}
