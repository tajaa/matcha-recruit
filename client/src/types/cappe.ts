// Cappe (website builder) — shared API response types.
// Cappe is a separate product from matcha; these types are independent of the
// matcha MeResponse / dashboard types.

export type CappeAccountType = 'business' | 'personal'

export type CappeAccount = {
  id: string
  email: string
  name: string | null
  plan: 'free' | 'hosting' | 'pro' | 'business' | string
  status: 'active' | 'suspended' | 'deleted' | string
  account_type: CappeAccountType | string
}

export type CappeTokenResponse = {
  access_token: string
  refresh_token: string
  expires_in: number
  account: CappeAccount
}

// Signup result. Real signups must confirm their email first
// (verification_required=true, no tokens); reserved test-domain signups
// auto-verify and carry tokens inline.
export type CappeSignupResponse = {
  verification_required: boolean
  email: string
  access_token?: string
  refresh_token?: string
  expires_in?: number
  account?: CappeAccount
}

export type CappeReadinessItem = {
  key: string
  label: string
  hint: string
  done: boolean
  required: boolean
  action: string | null
}

export type CappeReadiness = {
  ready: boolean
  items: CappeReadinessItem[]
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

// How an offering is delivered. physical=shipped good (inventory); digital=file
// download; service=seller delivers a result; booking=scheduled session.
export type CappeFulfillment = 'physical' | 'digital' | 'service' | 'booking'

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
  fulfillment: CappeFulfillment
  digital_file_url: string | null
  booking_type_id: string | null
  requires_approval: boolean
  intake_fields: CappeFormField[]
  created_at: string
  updated_at: string
  discount_percent?: number
  discounted_price_cents?: number | null
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
  fulfillment?: CappeFulfillment
  digital_file_url?: string | null
  booking_type_id?: string | null
  requires_approval?: boolean
  intake_fields?: CappeFormField[]
}

export type CappeOrderItem = {
  id: string
  product_id: string | null
  title: string
  unit_price_cents: number
  quantity: number
  fulfillment: CappeFulfillment
  intake_answers: Record<string, unknown>
  deliverable_url: string | null
  booking_id: string | null
}

export type CappeOrder = {
  id: string
  site_id: string
  customer_email: string | null
  customer_name: string | null
  status: 'pending' | 'paid' | 'fulfilled' | 'cancelled' | 'refunded' | 'declined'
  subtotal_cents: number
  currency: string
  payment_ref: string | null
  note: string | null
  requires_approval: boolean
  approved_at: string | null
  decline_reason: string | null
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

export type CappePricingMode = 'flat' | 'hourly'

export type CappeBookingType = {
  id: string
  site_id: string
  name: string
  description: string | null
  duration_minutes: number
  price_cents: number | null
  status: 'active' | 'draft' | 'archived'
  requires_approval: boolean
  pricing_mode: CappePricingMode
  created_at: string
  updated_at: string
}

export type CappeAvailabilitySlot = {
  weekday: number
  start_time: string
  end_time: string
  booking_type_id: string | null
}

// Time-window rate multiplier (e.g. after 8pm = 2x). weekday null = every day.
export type CappeRateRule = {
  id: string
  site_id: string
  booking_type_id: string | null
  label: string
  weekday: number | null
  start_time: string
  end_time: string
  multiplier: number
  created_at: string
}

export type CappeRateRuleInput = {
  label: string
  booking_type_id: string | null
  weekday: number | null
  start_time: string
  end_time: string
  multiplier: number
}

export type CappeRiderItem = {
  id: string
  site_id: string
  label: string
  detail: string | null
  is_required: boolean
  sort_order: number
  created_at: string
}

export type CappeDiscountScope = 'all' | 'booking_type' | 'product'

export type CappeDiscount = {
  id: string
  site_id: string
  label: string
  percent_off: number
  scope: CappeDiscountScope
  target_id: string | null
  active: boolean
  starts_on: string | null
  ends_on: string | null
  created_at: string
}

export type CappeDiscountInput = {
  label: string
  percent_off: number
  scope: CappeDiscountScope
  target_id: string | null
  active: boolean
  starts_on: string | null
  ends_on: string | null
}

export type CappeRiderItemInput = {
  label: string
  detail: string | null
  is_required: boolean
  sort_order: number
}

export type CappeBooking = {
  id: string
  site_id: string
  booking_type_id: string | null
  customer_name: string | null
  customer_email: string | null
  starts_at: string
  ends_at: string
  status: 'pending' | 'confirmed' | 'declined' | 'cancelled' | 'completed'
  note: string | null
  requires_approval: boolean
  quoted_price_cents: number | null
  approved_at: string | null
  decline_reason: string | null
  rider_acknowledged: boolean
  rider_snapshot: Array<{ label: string; detail?: string | null; is_required: boolean }>
  created_at: string
}

// One row in the creator's accept/decline queue (booking or order).
export type CappeRequestSummary = {
  kind: 'booking' | 'order'
  id: string
  customer_name: string | null
  customer_email: string | null
  title: string
  amount_cents: number | null
  currency: string
  starts_at: string | null
  note: string | null
  rider_acknowledged: boolean | null
  created_at: string
}

// --- Messages + clients -----------------------------------------------------

export type CappeMessage = {
  id: string
  thread_id: string
  sender: 'owner' | 'client'
  body: string
  created_at: string
}

export type CappeThread = {
  id: string
  site_id: string
  client_email: string
  client_name: string | null
  subject: string | null
  status: 'open' | 'closed'
  booking_id: string | null
  order_id: string | null
  owner_unread: number
  last_message_at: string
  created_at: string
  last_snippet?: string | null
}

export type CappeThreadDetail = CappeThread & {
  access_token: string
  messages: CappeMessage[]
}

export type CappePublicThread = {
  site_name: string
  subject: string | null
  messages: CappeMessage[]
}

export type CappeClient = {
  email: string
  name: string | null
  orders_count: number
  bookings_count: number
  is_subscriber: boolean
  has_thread: boolean
  total_spent_cents: number
  last_activity: string | null
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
