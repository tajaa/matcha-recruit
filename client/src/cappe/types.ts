// Cappe (website builder) — shared API response types.
export type CappeShopperSubscription = {
  id: string
  status: string
  interval: 'week' | 'month'
  items: { title: string; quantity: number }[]
  total_cents: number
  currency: string
  cancel_at_period_end: boolean
  current_period_end: string | null
  created_at?: string
  /** Owner's list only. */
  customer_email?: string | null
  customer_name?: string | null
  order_count?: number
  last_order_at?: string | null
}
// Cappe is a separate product from matcha; these types are independent of the
// matcha MeResponse / dashboard types.

export type CappeAccountType = 'business' | 'personal' | 'creator'

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
  intended_plan?: string | null
  intended_interval?: string | null
}

// Email confirmation: a session, plus the plan picked on the pricing page at
// signup (returned once) so the flow can continue into checkout.
export type CappeVerifyResponse = CappeTokenResponse & {
  intended_plan?: string | null
  intended_interval?: string | null
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
  app_url_scheme?: string | null
  app_bundle_id?: string | null
  id: string
  account_id: string
  name: string
  slug: string
  subdomain: string | null
  custom_domain: string | null
  source_type: 'template' | 'byo' | 'blank' | string
  template_id: string | null
  /** Registry key of the template the site was cloned from (null for blank sites). */
  template_slug?: string | null
  status: CappeSiteStatus
  theme_config: Record<string, unknown>
  meta_config: Record<string, unknown>
  timezone: string
  is_multi_location: boolean
  tax_rate_bps?: number | null
  tax_label?: string | null
  receipt_prefix?: string | null
  shipping_flat_cents?: number | null
  shipping_free_threshold_cents?: number | null
  shipping_label?: string | null
  /** Where the store is based: its shipping settings and tax rate are this country's. */
  home_country?: string
  /** What the store charges in; every product follows it. */
  currency?: string
  listed?: boolean
  directory_category?: string | null
  directory_tags?: string[]
  directory_blurb?: string | null
  directory_confirmed_at?: string | null
  published_at: string | null
  created_at: string
  updated_at: string
  page_count?: number | null
}

// --- Discover directory ------------------------------------------------------
// (CappeAccountType is already declared at the top of this file — reused here.)

/** One public directory card. Mirrors the backend's response allowlist exactly
 *  (models/public.py:CappeDirectoryEntry) — there is deliberately no contact
 *  email or account id in this shape. */
export type CappeDirectoryEntry = {
  slug: string
  name: string
  url: string
  category: string | null
  category_label: string | null
  tags: string[]
  blurb: string | null
  logo_url: string | null
  account_type: CappeAccountType
  city: string | null
  region: string | null
  distance_km: number | null
  rating: number | null
  review_count: number
  published_at: string | null
}

// --- Public pricing (gummfit.com landing) ------------------------------------
// Mirrors server `CappePublicPricing`: only purchasable prices, legacy tiers
// excluded, and the intro only when its Stripe Price exists.

export type CappePublicPrice = {
  interval: 'month' | 'year' | string
  unit_amount_cents: number
  currency: string
  purchasable: boolean
}

export type CappePublicPlan = {
  code: string
  name: string
  description: string | null
  sort_order: number
  platform_fee_bps: number
  allowed_fulfillment: string[]
  site_limit: number | null
  mailbox_quota_included: number
  prices: CappePublicPrice[]
  intro_price_cents: number | null
  intro_days: number | null
}

// --- Billing (authenticated) --------------------------------------------------

export type CappeBillingInterval = 'month' | 'year'

export type CappeBillingPlan = CappePublicPlan & { status: string; can_sell: boolean }

export type CappeCatalog = {
  plans: CappeBillingPlan[]
  /** Whether THIS account can still claim the intro price. */
  intro_available: boolean
}

export type CappeSubscription = {
  plan_code: string
  plan_name: string | null
  interval: string
  status: string
  /** 'stripe' for a paid subscription; anything else is granted by staff. */
  source: string
  current_period_end: string | null
  trial_end: string | null
  cancel_at_period_end: boolean
  comped_until: string | null
}

export type CappePublicAddon = {
  code: string
  name: string
  description: string | null
  unit_label: string
  prices: CappePublicPrice[]
}

export type CappePublicPricing = {
  plans: CappePublicPlan[]
  addons: CappePublicAddon[]
}

export type CappeDirectoryPage = {
  entries: CappeDirectoryEntry[]
  /** Clamped server-side to the anti-enumeration depth cap — "results you can
   *  reach", not "sites we have". */
  total: number
  next_offset: number | null
}

export type CappeDirectoryCategory = { slug: string; label: string; count: number }

export type CappeDirectoryCategories = {
  categories: CappeDirectoryCategory[]
  total: number
}

/** The owner-side view of their own listing. */
export type CappeDirectoryListing = {
  listed: boolean
  category: string | null
  category_label: string | null
  tags: string[]
  blurb: string | null
  confirmed_at: string | null
  /** False when the listing is incomplete or blocked — the UI explains why
   *  rather than leaving the tenant wondering where they are. */
  visible: boolean
  blocked: boolean
  categories: { slug: string; label: string }[]
}

export type CappeDirectoryQuery = {
  q?: string
  category?: string
  type?: CappeAccountType | 'all'
  lat?: number
  lng?: number
  radius_km?: number
  sort?: 'relevance' | 'newest' | 'distance'
  offset?: number
  limit?: number
}

export type CappeDomainSearchResult = {
  domain: string
  available: boolean
  price_cents: number | null
}

export type CappeDomainStatus =
  | 'pending'
  | 'registering'
  | 'active'
  | 'failed'
  | 'expired'
  | 'transfer_requested'

/** CloudFront-side lifecycle, independent of `status`: a domain can be
 *  registered and paid for while its certificate is still validating. */
export type CappeDomainEdgeStatus = 'none' | 'provisioning' | 'pending_dns' | 'live' | 'failed'

export type CappeDomainConfig = {
  enabled: boolean
  /** Host the tenant's apex ALIAS/ANAME (or www CNAME) must point at. */
  routing_endpoint: string | null
}

export type CappeDomain = {
  id: string
  site_id: string
  domain: string
  kind: 'register' | 'connect'
  status: CappeDomainStatus
  edge_status: CappeDomainEdgeStatus
  edge_error: string | null
  cf_routing_endpoint: string | null
  price_cents: number | null
  auto_renew: boolean
  expires_at: string | null
  failure_reason: string | null
  verification_token: string | null
  transfer_requested_at: string | null
  /** Set when the last automatic renewal could not collect; `renewal_error`
   *  is the reason shown beside the "Renew now" button. */
  renewal_failed_at?: string | null
  renewal_error?: string | null
  created_at: string
}

export type CappeDnsRecord = {
  id: string
  type: string
  name: string
  content: string
  ttl: string | null
  prio: string | null
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

// Freeform grid-snap canvas block (a `canvas` block type). Elements sit on a CSS
// grid at explicit per-breakpoint coordinates. Stored opaquely inside the block;
// the editor narrows a CappeBlock to these shapes when type === 'canvas'.
export type CappeCanvasPos = { x: number; y: number; w: number; h: number }
export type CappeCanvasElementStyle = {
  font?: string
  size?: number
  weight?: number
  spacing?: string
  lineHeight?: number
  color?: string
  align?: 'left' | 'center' | 'right' | 'justify'
  fit?: 'cover' | 'contain' | 'fill' | 'none'
  radius?: number
  variant?: 'solid' | 'outline' // button
  bg?: string // button background
}
export type CappeCanvasElement = {
  id: string
  kind: 'heading' | 'text' | 'image' | 'button'
  text?: string
  src?: string
  alt?: string
  href?: string // button link
  d: CappeCanvasPos // desktop placement (grid units)
  m?: CappeCanvasPos // mobile placement (auto-derived when absent)
  style?: CappeCanvasElementStyle
}
export type CappeCanvasGrid = { cols: number; rowH: number; rows?: number }
export type CappeCanvasBlock = {
  type: 'canvas'
  grid: CappeCanvasGrid
  mobile: CappeCanvasGrid
  elements: CappeCanvasElement[]
  _design?: Record<string, unknown>
}

/** One template-gallery card (models/sites.py:CappeTemplateSummary). Every
 *  template is available on every plan, so there is no premium flag or price;
 *  `category` is a Discover taxonomy slug and `pages` drives the preview tabs. */
export type CappeTemplateSummary = {
  slug: string
  name: string
  category: string
  category_label: string
  tags: string[]
  description: string
  mode: 'light' | 'dark' | string
  heading_font: string
  swatch: { bg: string; surface: string; brand: string; text: string }
  pages: { slug: string; title: string }[]
}

// --- Shop -------------------------------------------------------------------

// How an offering is delivered. physical=shipped good (inventory); digital=file
// download; service=seller delivers a result; booking=scheduled session.
export type CappeFulfillment = 'physical' | 'digital' | 'service' | 'booking'

export type CappeProductOption = {
  id: string
  name: string
  price_delta_cents: number
  sort_order: number
  inventory?: number | null
}
export type CappeProductOptionGroup = {
  id: string
  name: string
  select_type: 'single' | 'multi'
  required: boolean
  sort_order: number
  options: CappeProductOption[]
}
// Input shapes for the product editor (whole-set replace).
// `id` keeps an existing option's row (and so its id) through a save. Stock is
// tri-state on an existing option: omitted = leave alone, number = set,
// null = stop tracking; `expected_inventory` is what the form was showing.
export type CappeProductOptionInput = {
  id?: string
  name: string
  price_delta_cents: number
  sort_order?: number
  inventory?: number | null
  expected_inventory?: number | null
}

export type CappeInventoryAdjustment = {
  id: string
  product_id: string
  option_id: string | null
  delta: number
  balance_after: number | null
  reason: string
  note: string | null
  created_at: string
}
export type CappeProductOptionGroupInput = {
  id?: string
  name: string
  select_type: 'single' | 'multi'
  required: boolean
  sort_order?: number
  options: CappeProductOptionInput[]
}

export type CappeProduct = {
  subscription_intervals?: ('week' | 'month')[]
  subscription_discount_bps?: number
  id: string
  site_id: string
  name: string
  description: string | null
  price_cents: number
  currency: string
  image_url: string | null
  sku: string | null
  inventory: number | null
  low_stock_threshold: number | null
  status: 'active' | 'draft' | 'archived'
  sort_order: number
  fulfillment: CappeFulfillment
  digital_file_url: string | null
  booking_type_id: string | null
  requires_approval: boolean
  intake_fields: CappeFormField[]
  category: string | null
  option_groups: CappeProductOptionGroup[]
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
  category?: string | null
  option_groups?: CappeProductOptionGroupInput[]
}

export type CappeOrderItem = {
  id: string
  product_id: string | null
  title: string
  unit_price_cents: number
  quantity: number
  fulfillment: CappeFulfillment
  intake_answers: Record<string, unknown>
  selected_options: { group?: string; name?: string; price_delta_cents?: number }[]
  deliverable_url: string | null
  booking_id: string | null
  /** Units already back on the shelf after a refund. */
  restocked_quantity?: number
  /** This line's share of a promo code's discount. */
  promo_discount_cents?: number
}

/** One refund in an order's ledger. */
export type CappeOrderRefund = {
  id: string
  amount_cents: number
  restock: boolean
  lines: { item_id: string; quantity: number }[]
  reason: string | null
  status: 'pending' | 'succeeded' | 'failed'
  /** dashboard | manual (paid outside Stripe) | stripe (made in Stripe) | dispute | legacy */
  source: string
  stripe_refund_id: string | null
  failure: string | null
  created_at: string
}

export type CappeRefundBody = {
  restock?: boolean
  amount_cents?: number
  lines?: { item_id: string; quantity: number }[]
  reason?: string
}

export type CappeShippingAddress = {
  name?: string | null
  address?: {
    line1?: string | null
    line2?: string | null
    city?: string | null
    state?: string | null
    postal_code?: string | null
    country?: string | null
  } | null
}

export type CappeOrder = {
  subscription_id?: string | null
  id: string
  site_id: string
  customer_email: string | null
  customer_name: string | null
  status: 'pending' | 'paid' | 'fulfilled' | 'cancelled' | 'refunded' | 'declined'
  subtotal_cents: number
  tax_cents: number
  shipping_cents: number
  shipping_address?: CappeShippingAddress | null
  /** Where a physical order was priced to ship. */
  ship_country?: string | null
  /** The refund ledger (detail view only). */
  refunds?: CappeOrderRefund[]
  /** The promo code the buyer used and what it took off (subtotal is after it). */
  promo_code?: string | null
  discount_cents?: number
  carrier?: string | null
  tracking_number?: string | null
  total_cents: number | null
  receipt_number: string | null
  currency: string
  payment_ref: string | null
  note: string | null
  requires_approval: boolean
  approved_at: string | null
  decline_reason: string | null
  /** Set by a refund. A PARTIAL refund made in Stripe records its amount in
   *  `refunded_cents` while the status stays paid. */
  refunded_at?: string | null
  refunded_cents?: number
  /** Stripe's status for a chargeback opened against this order, if any. */
  dispute_status?: string | null
  disputed_at?: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string
  items: CappeOrderItem[]
  /** List view only (the list carries no `items`). */
  item_count?: number
  items_summary?: string | null
  /** Accepted and waiting for the buyer to pay from the emailed link, until then. */
  pay_by?: string | null
  shipped_notified_at?: string | null
  platform_fee_cents?: number | null
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

// One day's hours (Mon=0..Sun=6). open/close "HH:MM"; closed = no hours that day.
export type CappeLocationHours = { day: number; open?: string | null; close?: string | null; closed?: boolean }

export type CappeLocation = {
  id: string
  site_id: string
  name: string
  address: string | null
  lat: number | null
  lng: number | null
  timezone: string | null
  hours: CappeLocationHours[]
  contact_phone: string | null
  contact_email: string | null
  is_default: boolean
  active: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type CappeLocationInput = {
  name: string
  address?: string | null
  lat?: number | null
  lng?: number | null
  timezone?: string | null
  hours?: CappeLocationHours[]
  contact_phone?: string | null
  contact_email?: string | null
  is_default?: boolean
  active?: boolean
  sort_order?: number
}

export type CappeStaff = {
  id: string
  site_id: string
  name: string
  bio: string | null
  image_url: string | null
  active: boolean
  sort_order: number
  location_id?: string | null
  created_at: string
  updated_at: string
}

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
  category: string | null
  buffer_minutes: number
  staff_ids: string[]
  location_id?: string | null
  created_at: string
  updated_at: string
}

export type CappeAvailabilitySlot = {
  weekday: number
  start_time: string
  end_time: string
  booking_type_id: string | null
  staff_id?: string | null
  location_id?: string | null
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
  location_id?: string | null
  created_at: string
}

export type CappeRateRuleInput = {
  label: string
  booking_type_id: string | null
  weekday: number | null
  start_time: string
  end_time: string
  multiplier: number
  location_id?: string | null
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
  location_id?: string | null
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
  location_id?: string | null
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
  staff_id?: string | null
  staff_name?: string | null
  customer_name: string | null
  customer_email: string | null
  starts_at: string
  ends_at: string
  location_id?: string | null
  location_name?: string | null
  status: 'pending' | 'confirmed' | 'declined' | 'cancelled' | 'completed'
  note: string | null
  requires_approval: boolean
  quoted_price_cents: number | null
  approved_at: string | null
  decline_reason: string | null
  rider_acknowledged: boolean
  rider_snapshot: Array<{ label: string; detail?: string | null; is_required: boolean }>
  created_at: string
  /** The shop order this booking was bought through, if any. Cancelling the
   *  booking does not refund a PAID order. */
  order_id?: string | null
  order_status?: string | null
  /** The timezone the booking's times mean (its location's, else the site's). */
  timezone?: string | null
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

// Customer-facing booking view (token-gated self-serve page).
export type CappePublicBooking = {
  status: string
  type_name: string
  site_name: string
  slug: string
  booking_type_id: string | null
  starts_at: string
  ends_at: string
  quoted_price_cents: number | null
  timezone: string
  can_modify: boolean
  staff_id?: string | null
  staff_name?: string | null
  location_id?: string | null
  location_name?: string | null
}

export type CappeSlot = {
  start: string
  end: string
  date: string
  day_label: string
  time_label: string
  price_cents: number | null
}

export type CappeSlotsResponse = {
  timezone: string
  discount_percent: number
  slots: CappeSlot[]
}

export type CappeReview = {
  id: string
  site_id: string
  author_name: string
  rating: number | null
  body: string
  status: 'pending' | 'approved' | 'hidden'
  created_at: string
  /** What it's about; null = the store in general. */
  product_id?: string | null
  product_name?: string | null
  /** Written from a paid order's page. */
  verified?: boolean
  /** The store's public answer. */
  owner_reply?: string | null
  owner_replied_at?: string | null
}

/** Who may post reviews: anyone, only buyers (from their order page), or nobody. */
export type CappeReviewSubmissions = 'anyone' | 'buyers' | 'off'

export type CappeClient = {
  email: string
  name: string | null
  phone?: string | null
  orders_count: number
  bookings_count: number
  is_subscriber: boolean
  has_thread: boolean
  is_imported?: boolean
  total_spent_cents: number
  last_activity: string | null
  location_id?: string | null
  location_name?: string | null
}

export type CappeClientImportError = { row: number; email: string | null; reason: string }

export type CappeClientImportResult = {
  total: number
  created: number
  updated: number
  skipped: number
  newsletter_added: number
  branches_matched: number
  errors: CappeClientImportError[]
}

export type CappeStaffImportError = { row: number; name: string | null; reason: string }

export type CappeStaffImportResult = {
  total: number
  created: number
  updated: number
  skipped: number
  branches_matched: number
  errors: CappeStaffImportError[]
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

// A saved reusable look: kind='theme' → a theme_config style subset;
// kind='section' → a block _design bag.
export type CappeStylePreset = {
  id: string
  name: string
  kind: 'theme' | 'section'
  data: Record<string, unknown>
  created_at: string
}

// --- Merlin setup concierge (dashboard) --------------------------------------

export type CappeSetupActionStatus = 'proposed' | 'executed' | 'dismissed' | 'blocked'

export type CappeSetupAction = {
  id: string
  type: string
  summary: string
  payload: Record<string, unknown>
  status: CappeSetupActionStatus
  result?: Record<string, unknown> | null
  message?: string | null
  created_at: string
  executed_at?: string | null
}

export type CappeSetupLink = { target: string; label: string }

export type CappeSetupConversationSummary = {
  id: string
  title: string
  created_at: string
  updated_at: string
}

// --- Creator marketplace ------------------------------------------------------

export const CREATOR_NICHES = [
  'fitness', 'beauty', 'fashion', 'food', 'travel', 'tech', 'gaming',
  'music', 'art', 'parenting', 'finance', 'health', 'sports', 'comedy',
  'education', 'lifestyle', 'outdoors', 'pets', 'diy', 'other',
] as const

export const SOCIAL_PLATFORMS = ['instagram', 'tiktok', 'youtube', 'x', 'twitch', 'facebook', 'linkedin', 'other'] as const
export const DELIVERABLE_TYPES = ['post', 'reel', 'story', 'video', 'short', 'stream', 'ugc', 'blog', 'other'] as const

export const PAYMENT_SCHEDULES = [
  { value: 'upfront', label: 'Upfront', blurb: '100% when the offer is accepted' },
  { value: 'split_50_50', label: '50 / 50', blurb: 'Half on acceptance, half when all deliverables are approved' },
  { value: 'per_deliverable', label: 'Per deliverable', blurb: 'Each deliverable pays out on approval' },
] as const

export const fmtCents = (c: number | null | undefined, currency = 'usd') =>
  ((c ?? 0) / 100).toLocaleString('en-US', { style: 'currency', currency: currency.toUpperCase() })

export type CreatorSocial = {
  id: string
  platform: string
  handle: string
  url: string
  follower_count: number | null
  engagement_rate: number | null
  audit_status: 'unverified' | 'verified' | 'flagged' | string
  verified_follower_count: number | null
  audited_at: string | null
  sort_order: number
}

export type CreatorSocialInput = {
  platform: string
  handle: string
  url: string
  follower_count?: number | null
  engagement_rate?: number | null
  sort_order?: number
}

export type CreatorPortfolioItem = {
  id: string
  title: string
  description: string | null
  media_url: string | null
  media_type: 'image' | 'video' | null
  external_url: string | null
  brand_name: string | null
  metrics: Record<string, unknown>
  sort_order: number
  created_at: string
}

export type CreatorPortfolioInput = {
  title: string
  description?: string | null
  media_url?: string | null
  media_type?: 'image' | 'video' | null
  external_url?: string | null
  brand_name?: string | null
  metrics?: Record<string, unknown>
  sort_order?: number
}

export type CreatorRate = {
  id: string
  deliverable_type: string
  platform: string
  price_cents: number
  negotiable: boolean
  notes: string | null
  sort_order: number
}

export type CreatorRateInput = {
  deliverable_type: string
  platform: string
  price_cents: number
  negotiable?: boolean
  notes?: string | null
  sort_order?: number
}

export type CreatorProfileMe = {
  id: string
  handle: string
  display_name: string
  avatar_url: string | null
  cover_url: string | null
  bio: string | null
  location: string | null
  niches: string[]
  languages: string[]
  open_to_offers: boolean
  status: 'draft' | 'pending_review' | 'published' | 'rejected' | 'suspended' | string
  review_note: string | null
  submitted_at: string | null
  published_at: string | null
  reach_verified: boolean
  reach_audited_at: string | null
  socials: CreatorSocial[]
  portfolio: CreatorPortfolioItem[]
  rates: CreatorRate[]
}

export type PublicCreatorCard = {
  handle: string
  display_name: string
  avatar_url: string | null
  cover_url: string | null
  bio: string | null
  location: string | null
  niches: string[]
  reach_verified: boolean
  max_followers: number
  max_engagement_rate: number | null
  min_rate_cents: number | null
  platforms: string[]
}

export type PublicCreatorProfile = {
  id: string
  handle: string
  display_name: string
  avatar_url: string | null
  cover_url: string | null
  bio: string | null
  location: string | null
  niches: string[]
  languages: string[]
  open_to_offers: boolean
  reach_verified: boolean
  reach_audited_at: string | null
  socials: CreatorSocial[]
  portfolio: CreatorPortfolioItem[]
  rates: CreatorRate[]
}

export type PublicCreatorPage = {
  creators: PublicCreatorCard[]
  total: number
}

// --- Collabs (brand<->creator offers) -----------------------------------------

export type PaymentSchedule = 'upfront' | 'split_50_50' | 'per_deliverable'
export type OfferStatus =
  | 'sent' | 'negotiating' | 'accepted' | 'active' | 'completed'
  | 'declined' | 'withdrawn' | 'cancelled'

export type TermsDeliverable = {
  type: string
  platform: string
  quantity: number
  spec: string | null
  due_date: string | null
}

export type TermsUsageRights = {
  scope: 'organic' | 'paid'
  duration_months: number | null
  whitelisting: boolean
}

export type TermsExclusivity = {
  category: string
  duration_months: number
}

export type CollabTerms = {
  compensation_cents: number
  payment_schedule: PaymentSchedule
  deliverables: TermsDeliverable[]
  usage_rights: TermsUsageRights
  exclusivity: TermsExclusivity | null
  revision_rounds: number
  approval_required: boolean
  ftc_disclosure: boolean
  start_date: string | null
  end_date: string | null
  notes: string | null
}

export type Campaign = {
  id: string
  title: string
  description: string | null
  budget_min_cents: number | null
  budget_max_cents: number | null
  deliverable_notes: string | null
  status: 'active' | 'archived' | string
  offer_count: number
  created_at: string
}

export type OfferRevision = {
  id: string
  revision_no: number
  proposed_by: 'brand' | 'creator'
  terms: CollabTerms
  message: string | null
  created_at: string
}

export type OfferMessage = {
  id: string
  sender: 'brand' | 'creator'
  body: string
  revision_id: string | null
  created_at: string
}

export type Deliverable = {
  id: string
  idx: number
  type: string
  platform: string
  spec: string | null
  due_date: string | null
  status: 'pending' | 'submitted' | 'revision_requested' | 'approved' | string
  submission_url: string | null
  submission_note: string | null
  proof_media_url: string | null
  submitted_at: string | null
  revision_count: number
  review_note: string | null
  approved_at: string | null
}

export type CollabPayment = {
  id: string
  idx: number
  label: string
  amount_cents: number
  currency: string
  trigger: 'on_accept' | 'on_all_approved' | 'on_deliverable'
  deliverable_id: string | null
  status: 'scheduled' | 'due' | 'processing' | 'paid' | 'failed' | 'refunded' | 'cancelled' | string
  fee_cents: number | null
  due_at: string | null
  paid_at: string | null
}

export type OfferListItem = {
  id: string
  title: string
  status: OfferStatus | string
  payment_schedule: PaymentSchedule | null
  total_cents: number | null
  currency: string
  campaign_id: string | null
  brand_name: string | null
  creator_handle: string
  creator_display_name: string
  creator_avatar_url: string | null
  last_action_at: string
  created_at: string
}

export type DealCheckSeverity = 'good' | 'caution' | 'warning'

export type DealCheckItem = {
  key: string
  severity: DealCheckSeverity
  title: string
  detail: string
}

export type BrandStats = {
  completed_collabs: number
  brand_cancelled: number
  in_progress: number
  avg_hours_to_pay: number | null
}

export type OfferDetail = OfferListItem & {
  side: 'brand' | 'creator'
  accepted_revision_id: string | null
  declined_reason: string | null
  cancelled_by: 'brand' | 'creator' | null
  cancel_reason: string | null
  revisions: OfferRevision[]
  messages: OfferMessage[]
  deliverables: Deliverable[]
  payments: CollabPayment[]
  creator_payouts_ready: boolean
  deal_check: DealCheckItem[] | null
  brand_stats: BrandStats | null
  auto_approve_days: number
}

export type OfferPage = {
  offers: OfferListItem[]
  total: number
}

export type EarningsRow = {
  offer_id: string
  offer_title: string
  brand_name: string | null
  label: string
  amount_cents: number
  fee_cents: number | null
  status: string
  paid_at: string | null
}

// --- Shipping zones ------------------------------------------------------------

/** A destination beyond the store's home country, with its own rates. */
export type CappeShippingZoneInput = {
  name: string
  countries: string[]
  /** Covers every country no other zone names. At most one per store. */
  rest_of_world: boolean
  flat_cents: number
  free_threshold_cents: number | null
  /** Charge the store's tax rate on goods shipped here. */
  charge_tax: boolean
}

export type CappeShippingZone = CappeShippingZoneInput & { id: string; sort_order: number }

export type CappeShippingZones = {
  /** Whether the plan includes zones; saved zones are paused when it doesn't. */
  enabled: boolean
  home_country: string
  currency: string
  /** Every country a zone can name. */
  countries: string[]
  zones: CappeShippingZone[]
}

// --- Finances ------------------------------------------------------------------

export type CappeFinancials = {
  currency: string
  start: string
  end: string
  group: 'day' | 'week' | 'month'
  orders: number
  gross_cents: number
  goods_cents: number
  tax_cents: number
  shipping_cents: number
  platform_fee_cents: number
  refunds_cents: number
  refund_count: number
  net_cents: number
  average_order_cents: number
  series: { period: string; orders: number; gross_cents: number; refunds_cents: number }[]
  top_products: { product_id: string | null; title: string; units: number; revenue_cents: number }[]
  other_currency_orders: number
  export_enabled: boolean
}

export type CappeBalance = {
  connected: boolean
  available: { amount_cents: number; currency: string }[]
  pending: { amount_cents: number; currency: string }[]
  payouts: { id: string; amount_cents: number; currency: string; status: string; arrival_date: number | null }[]
}

// --- Promo codes -----------------------------------------------------------------

export type CappePromoCodeInput = {
  code: string
  kind: 'percent' | 'fixed'
  percent_off: number | null
  amount_off_cents: number | null
  min_subtotal_cents: number | null
  starts_on: string | null
  ends_on: string | null
  max_redemptions: number | null
  once_per_customer: boolean
  active: boolean
}

export type CappePromoCode = CappePromoCodeInput & { id: string; redemption_count: number; created_at: string }

export type CappePromoCodes = { enabled: boolean; currency: string; codes: CappePromoCode[] }
