// TypeScript shapes mirroring server/app/tellus/models/tellus.py.

export type AccountType = 'consumer' | 'brand'

export type BrandPlanStatus = 'pending' | 'active' | 'past_due' | 'canceled'

// 'published' is derived server-side (held + past its 48h hold) — it never
// appears in the DB, only in API responses.
export type ReviewState = 'held' | 'published' | 'withdrawn'
export type DmSenderRole = 'brand' | 'consumer'

export interface TellusAccount {
  id: string
  email: string
  display_name: string | null
  account_type: AccountType
  status: string
  city: string | null
  state: string | null
  leaderboard_opt_in: boolean
  brand_id: string | null
  // Brand billing state — null for consumer accounts.
  plan_status: BrandPlanStatus | null
  location_count: number | null
  // Public review-page slug (brand accounts only) — /tellus/b/{brand_slug}.
  brand_slug: string | null
  // True when this account's email is in TELLUS_ADMIN_EMAILS — internal
  // changelog access at /tellus/admin/updates.
  is_admin: boolean
}

// Internal admin changelog row — mirrors server/app/tellus/routes/admin.py's
// response shape (same fields as matcha's AdminUpdate).
export interface TellusAdminUpdate {
  id: string
  date: string // ISO yyyy-mm-dd
  category: string
  title: string
  summary: string
  whatsNew: string[]
  howToUse: string[]
  setup: string[] | null
  notes: string[] | null
  tag: 'new' | 'action-needed' | null
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  expires_in: number
  account: TellusAccount
}

export interface SignupResponse {
  verification_required: boolean
  email: string
  access_token?: string
  refresh_token?: string
  expires_in?: number
  account?: TellusAccount
}

export interface Brand {
  id: string
  owner_account_id: string | null
  name: string
  logo_url: string | null
  reward_mode: 'auto' | 'manual'
  created_at: string
  messaging_enabled?: boolean
}

export interface BrandPrompt {
  id: string
  prompt: string
  position: number
}

export interface Store {
  id: string
  brand_id: string
  name: string
  address: string | null
  city: string | null
  state: string | null
  zipcode: string | null
  lat: number | null
  lng: number | null
  created_at: string
}

export interface FeedbackLink {
  id: string
  brand_id: string
  store_id: string | null
  token: string
  label: string | null
  is_active: boolean
  use_count: number
  max_uses: number | null
  expires_at: string | null
  revoked_at: string | null
  created_at: string
  store_name: string | null
}

export interface IntakePrompt {
  id: string
  prompt: string
}

export interface ReportAnswer {
  id: string
  prompt_text: string
  answer: string
  position: number
}

export interface IntakeConfig {
  brand_name: string
  brand_logo_url: string | null
  store_name: string | null
  categories: string[]
  prompts: IntakePrompt[]
  claimed: boolean
}

export interface SubmittedMedia {
  storage_path: string
  media_type: 'photo' | 'video'
  mime_type?: string | null
  file_size?: number | null
  original_filename?: string | null
}

export interface MediaPresignResponse {
  upload_url: string
  storage_path: string
  expires_in: number
}

export interface FeedbackSubmitResponse {
  report_id: string
  report_number: string | null
  points_awarded: number
  earned: boolean
  reward_pending: boolean
  public_review: boolean
  publish_at: string | null
}

export interface ReportMedia {
  id: string
  media_type: 'photo' | 'video'
  mime_type: string | null
  original_filename: string | null
  url: string | null
}

export interface Report {
  id: string
  brand_id: string
  store_id: string | null
  store_name: string | null
  report_number: string | null
  category: string
  sentiment: string
  title: string | null
  description: string | null
  occurred_at: string | null
  reporter_contact: string | null
  usefulness_score: number
  status: string
  ai_summary: string | null
  moderation_status: string
  reward_status: 'pending' | 'approved' | 'rejected' | null
  points_awarded: number
  created_at: string
  media: ReportMedia[]
  rating: number | null
  review_state: ReviewState | null
  publish_at: string | null
  hearted_at: string | null
  brand_public_reply: string | null
  brand_public_reply_at: string | null
  is_identified: boolean
  has_dm_thread: boolean
  answers: ReportAnswer[]
  like_count: number
}

export interface FeedbackStats {
  total: number
  new: number
  positive: number
  neutral: number
  negative: number
  by_category: Record<string, number>
}

export interface PointsBalance {
  account_id: string
  points_balance: number
  lifetime_points: number
  level: number
  current_streak: number
  longest_streak: number
  last_activity_date: string | null
  points_to_next_level: number
  level_floor: number
  level_ceiling: number
}

export interface LedgerEntry {
  id: string
  delta: number
  balance_after: number
  reason: string
  reference_type: string | null
  reference_id: string | null
  description: string | null
  created_at: string
}

export interface Listing {
  id: string
  brand_id: string | null
  brand_name: string | null
  city: string | null
  state: string | null
  title: string
  description: string | null
  image_url: string | null
  points_cost: number
  quantity_total: number | null
  quantity_claimed: number
  quantity_remaining: number | null
  redemption_type: 'code' | 'qr' | 'manual'
  terms: string | null
  active_from: string | null
  active_to: string | null
  is_active: boolean
  created_at: string
  expiry_days: number
  visibility: ListingVisibility
  like_count: number
  liked_by_me: boolean
}

export interface Redemption {
  id: string
  account_id: string
  listing_id: string
  listing_title: string | null
  brand_name: string | null
  listing_city: string | null
  listing_state: string | null
  points_spent: number
  status: string
  code: string | null
  issued_at: string | null
  redeemed_at: string | null
  expires_at: string | null
  created_at: string
}

export interface BadgeItem {
  key: string
  name: string
  description: string | null
  icon: string | null
  earned: boolean
  awarded_at: string | null
}

export interface LeaderboardEntry {
  rank: number
  account_id: string
  display_name: string
  lifetime_points: number
  level: number
  is_you: boolean
}

export interface BrandPricing {
  price_per_location_cents: number
  min_locations: number
  max_locations: number
}

export interface BrandBillingStatus {
  plan_status: BrandPlanStatus
  location_count: number
  store_count: number
  price_per_location_cents: number
  monthly_total_cents: number
  price_available: boolean
}

export interface CheckoutResponse {
  checkout_url: string
  stripe_session_id: string
}

export interface MyReview {
  id: string
  brand_name: string
  brand_slug: string
  store_name: string | null
  rating: number | null
  title: string | null
  description: string | null
  review_state: ReviewState
  publish_at: string
  created_at: string
  points_awarded: number
  hearted: boolean
  brand_public_reply: string | null
  brand_public_reply_at: string | null
  dm_thread_id: string | null
  media: ReportMedia[]
  answers: ReportAnswer[]
  like_count: number
  liked_by_me: boolean
}

export interface MyReviewUpdate {
  title?: string | null
  description?: string | null
  rating?: number | null
}

export interface PublicReview {
  id: string
  rating: number
  title: string | null
  description: string | null
  reviewer_name: string
  store_name: string | null
  created_at: string
  publish_at: string
  hearted: boolean
  brand_reply: string | null
  brand_reply_at: string | null
  media: ReportMedia[]
  answers: ReportAnswer[]
  like_count: number
  liked_by_me: boolean
}

export interface PublicBrandPage {
  brand_name: string
  slug: string
  logo_url: string | null
  review_count: number
  avg_rating: number | null
  reviews: PublicReview[]
  total: number
  claimed: boolean
  intake_token: string | null
  address: string | null
  city: string | null
  state: string | null
  older_count: number
  has_board: boolean
  messaging_enabled: boolean
  stores: MessagingStore[]
}

export interface ClaimResponse {
  ok: boolean
  claim_id: string
  status: string
  slug: string
}

export interface MyClaim {
  id: string
  brand_id: string
  brand_slug: string
  brand_name: string
  status: 'pending' | 'approved' | 'rejected' | 'cancelled'
  created_at: string
  decision_note: string | null
}

export interface AdminClaim extends MyClaim {
  account_id: string
  account_email: string
  account_display_name: string | null
  claimant_ip: string | null
  note: string | null
}

export interface PlaceSearchResult {
  slug: string; name: string; logo_url: string | null
  city: string | null; state: string | null
  claimed: boolean; intake_token: string | null; review_count: number
  google_place_id: string | null
  messaging_enabled: boolean
}
export interface PlaceCreateResponse {
  slug: string; name: string; claimed: boolean; intake_token: string | null; existing: boolean
}
export interface PlaceAutocompleteResult {
  place_id: string; name: string; secondary_text: string | null
}

export interface DmThread {
  id: string
  report_id: string | null
  counterparty_name: string
  report_title: string | null
  report_number: string | null
  review_state: ReviewState | null
  publish_at: string | null
  blocked: boolean
  unread_count: number
  last_message_at: string
  created_at: string
  kind?: 'feedback' | 'general'
  topic?: string | null
  status?: 'waiting_brand' | 'waiting_consumer' | 'closed'
  store_id?: string | null
  store_name?: string | null
  store_city?: string | null
  assigned_member_id?: string | null
  assigned_member_name?: string | null
  viewer_role?: 'consumer' | 'brand'
  first_brand_response_at?: string | null
  closed_at?: string | null
}

export interface DmMessage {
  id: string
  thread_id: string
  sender_role: DmSenderRole
  body: string
  created_at: string
  is_mine: boolean
}

export interface MessagingStore {
  id: string
  name: string
  address: string | null
  city: string | null
  state: string | null
}

export interface CommsStartResponse { thread: DmThread; message: DmMessage }

export interface InboxBrand {
  brand_id: string
  name: string
  slug: string
  plan_status: BrandPlanStatus | null
  role: 'owner' | 'member'
  can_manage_inbox: boolean
}

// ---------------------------------------------------------------------------
// Internal admin management (require_tellus_admin surfaces) — mirrors
// server/app/tellus/models/admin.py.
// ---------------------------------------------------------------------------

export interface AdminAccountSummary {
  id: string
  email: string
  display_name: string | null
  account_type: AccountType
  status: string
  email_verified: boolean
  city: string | null
  state: string | null
  created_at: string
  points_balance: number
  report_count: number
  brand_id: string | null
  brand_name: string | null
}

export interface AdminAccountList {
  items: AdminAccountSummary[]
  total: number
  limit: number
  offset: number
}

export interface AdminLedgerEntry {
  id: string
  delta: number
  balance_after: number
  reason: string
  event_key: string | null
  reference_type: string | null
  reference_id: string | null
  description: string | null
  created_at: string
}

export interface AdminAuditEntry {
  id: string
  actor_email: string
  action: string
  target_type: string
  target_id: string | null
  detail: Record<string, unknown> | null
  created_at: string
}

export interface AdminAuditList {
  items: AdminAuditEntry[]
  total: number
  limit: number
  offset: number
}

export interface AdminAccountDetail {
  account: AdminAccountSummary
  lifetime_points: number
  level: number
  current_streak: number
  ledger: AdminLedgerEntry[]
  recent_reports: Array<{
    id: string; brand_name: string | null; title: string | null
    rating: number | null; review_state: ReviewState | null
    moderation_status: string; created_at: string
  }>
  redemptions: Array<{
    id: string; listing_title: string; points_spent: number; status: string; created_at: string
  }>
  dm_threads: Array<{
    id: string; brand_name: string; blocked: boolean; last_message_at: string | null
  }>
  audit: AdminAuditEntry[]
}

export interface AdminPasswordResetResponse {
  reset_url: string
  expires_in_minutes: number
}

export interface AdminPointsAdjustResult {
  adjusted: boolean
  applied_delta: number
  balance: number
  lifetime: number
  level: number
}

export interface AdminBrandSummary {
  id: string
  name: string
  slug: string
  plan_status: BrandPlanStatus
  source: 'signup' | 'consumer_added'
  owner_account_id: string | null
  owner_email: string | null
  location_count: number
  store_count: number
  has_stripe_subscription: boolean
  created_at: string
}

export interface AdminBrandList {
  items: AdminBrandSummary[]
  total: number
  limit: number
  offset: number
}

export interface AdminBrandDetail {
  brand: AdminBrandSummary
  activated_at: string | null
  claimed_at: string | null
  stripe_customer_id: string | null
  stripe_subscription_id: string | null
  stores: Array<{ id: string; name: string; city: string | null; state: string | null }>
  links: Array<{ id: string; is_active: boolean; revoked_at: string | null; created_at: string }>
  prompts: Array<{ id: string; prompt: string; position: number }>
  report_stats: { total?: number; last_30d?: number; avg_rating?: number | null }
  audit: AdminAuditEntry[]
}

export interface AdminPlanActionResult {
  plan_status: BrandPlanStatus
  stripe_warning: string | null
}

export interface AdminReportItem extends Report {
  brand_name: string | null
}

// GET /admin/dm-threads/{id}/messages — admin's read-only view, distinct from
// DmMessage (no `is_mine`; there's no "me" from the admin's perspective).
export interface AdminDmMessage {
  id: string
  thread_id: string
  sender_role: DmSenderRole
  body: string
  created_at: string
  read_at: string | null
}

export interface AdminDmThreadSummary {
  id: string
  report_id: string
  brand_name: string
  consumer_email: string
  blocked: boolean
  message_count: number
  last_message_at: string | null
  created_at: string
}

export interface AdminEarningRule {
  event_key: string
  points: number
  daily_cap: number | null
  cooldown_seconds: number | null
  is_active: boolean
}

export interface AdminBadge {
  key: string
  name: string
  description: string | null
  icon: string | null
  criteria: { type?: string; threshold?: number }
  sort_order: number
  award_count: number
}

export interface AdminListing {
  id: string
  title: string
  brand_id: string | null
  brand_name: string | null
  points_cost: number
  quantity_total: number | null
  quantity_claimed: number
  redemption_type: 'code' | 'qr' | 'manual'
  is_active: boolean
  created_at: string
}

export interface TellusNotification {
  id: string
  kind: string
  title: string
  body: string | null
  reference_type: string | null
  reference_id: string | null
  is_read: boolean
  created_at: string
}

// ---------------------------------------------------------------------------
// Regulars board — mirrors the board_* additions in
// server/app/tellus/models/tellus.py.
// ---------------------------------------------------------------------------

export type BoardPostKind = 'update' | 'deal' | 'event' | 'question'
export type BoardReplyStatus = 'held' | 'approved' | 'rejected' | 'removed'
export type BoardMembershipStatus = 'pending' | 'approved' | 'declined' | 'removed' | 'left' | 'cancelled'
export type ListingVisibility = 'public' | 'board'
export type LikeTarget = 'board_post' | 'board_reply' | 'report' | 'listing'

export interface LikeState {
  like_count: number
  liked_by_me: boolean
}

export interface BoardReply {
  id: string
  post_id: string
  author_name: string
  is_mine: boolean
  status: BoardReplyStatus
  body: string
  created_at: string
  like_count: number
  liked_by_me: boolean
}

export interface BoardPost {
  id: string
  kind: BoardPostKind
  title: string
  body: string | null
  listing: Listing | null
  event_starts_at: string | null
  event_ends_at: string | null
  is_pinned: boolean
  moderation_status: string
  approved_reply_count: number
  held_reply_count: number | null
  created_at: string
  like_count: number
  liked_by_me: boolean
}

export interface BoardPage {
  board_id: string
  brand_id: string
  brand_name: string
  brand_slug: string
  logo_url: string | null
  title: string | null
  description: string | null
  is_active: boolean
  plan_paused: boolean
  viewer_role: 'member' | 'moderator' | 'owner'
  posts: BoardPost[]
  total: number
}

export interface BoardMembership {
  id: string
  brand_id: string
  brand_name: string
  brand_slug: string
  logo_url: string | null
  status: BoardMembershipStatus
  requested_at: string
  decided_at: string | null
}

export interface BoardJoinRequest {
  id: string
  account_display_name: string
  note: string | null
  requested_at: string
  review_count: number
  hearted: boolean
  redemption_count: number
}

export interface BoardMemberEntry {
  id: string
  account_display_name: string
  joined_at: string
}

export interface BrandTeamMember {
  id: string
  account_display_name: string
  email: string
  role: 'owner' | 'moderator'
  created_at: string
  can_manage_inbox: boolean
}

// GET /me/moderated-brands — bootstrap list for consumer moderators (and any
// brand-typed account moderating a board other than its own).
export interface ModeratedBrand {
  brand_id: string
  name: string
  slug: string
  role: 'owner' | 'moderator'
}

export interface BoardManageSummary {
  board_id: string
  title: string | null
  description: string | null
  is_active: boolean
  pending_requests: number
  held_replies: number
  member_count: number
  viewer_role: 'owner' | 'moderator'
}

// GET /board/manage/replies — brand moderation queue row (own shape, distinct
// from BoardReply: carries post_title, never is_mine).
export interface BoardManageReplyRow {
  id: string
  post_id: string
  post_title: string
  author_name: string
  body: string
  status: BoardReplyStatus
  created_at: string
}

// GET /admin/board-posts — admin oversight row, mirrors
// TellusAdminBoardPostRow.
export interface AdminBoardPostRow {
  id: string
  board_id: string
  brand_id: string
  brand_name: string
  kind: BoardPostKind
  title: string
  moderation_status: string
  author_display_name: string | null
  created_at: string
}

// GET /admin/board-replies — mirrors TellusAdminBoardReplyRow.
export interface AdminBoardReplyRow {
  id: string
  post_id: string
  post_title: string
  brand_id: string
  brand_name: string
  author_display_name: string
  body: string
  status: BoardReplyStatus
  created_at: string
}

// ── Promo campaigns / QR reward cards ───────────────────────────────────────

export type PromoCampaignStatus = 'active' | 'paused' | 'cancelled'
export type EffectiveCardStatus = 'issued' | 'redeemed' | 'cancelled' | 'expired'
export type ClaimUnavailableReason =
  'ok' | 'cap_reached' | 'cancelled' | 'brand_inactive' | 'paused' | 'not_started' | 'ended'

export interface PromoCampaignStats {
  claimed: number
  redeemed: number
  outstanding: number
  expired: number
  cancelled: number
}

export interface PromoCampaign {
  id: string
  title: string
  description: string | null
  reward_text: string
  claim_token: string
  claim_url: string
  max_claims: number
  claim_count: number
  status: PromoCampaignStatus
  card_expiry_days: number
  starts_at: string | null
  ends_at: string | null
  flyer_image_url: string | null
  has_design: boolean
  cancelled_at: string | null
  created_at: string
  stats: PromoCampaignStats | null
}

export interface PromoCard {
  id: string
  card_token: string
  card_url: string
  status: EffectiveCardStatus
  campaign_title: string
  reward_text: string
  brand_name: string
  brand_logo_url: string | null
  issued_at: string
  expires_at: string
  redeemed_at: string | null
  redeemed_store_name: string | null
}

export interface PromoClaimResult extends PromoCard {
  created: boolean
}

export interface ClaimPreview {
  brand_name: string
  brand_logo_url: string | null
  title: string
  reward_text: string
  description: string | null
  flyer_image_url: string | null
  available: boolean
  reason: ClaimUnavailableReason
  already_claimed: boolean
  card_token: string | null
}

export interface ScannerDevice {
  id: string
  store_id: string
  store_name: string
  label: string | null
  token: string
  scanner_url: string
  is_active: boolean
  created_at: string
}

export interface PromoRedeemResult {
  campaign_title: string
  reward_text: string
  redeemed_at: string
  store_name: string | null
}

export interface PromoScanBootstrap {
  store_name: string
  brand_name: string
  brand_logo_url: string | null
}

// Designer document model — QR layers store no URL; the campaign's
// claim_token is resolved into an absolute claim URL at render/export time.
export type ArtboardPreset = 'flyer_letter' | 'reward_card' | 'social_square' | 'story'

// Semantic colour tokens. Every colour-bearing field below accepts EITHER a
// '#rrggbb' literal OR one of these names, resolved against the document's own
// palette at render time (utils/designer.ts:resolveColor).
//
// The point of the indirection is that one palette swap restyles the whole
// flyer coherently, and a template authored in tokens is correct on every
// palette instead of needing a variant per look. Hex stays legal forever — the
// human colour pickers still write it, and no saved design breaks.
export type FlyerPaletteToken = 'ink' | 'paper' | 'brand' | 'brandSoft' | 'accent' | 'muted'
export type FlyerPalette = Record<FlyerPaletteToken, string>

// One entry of public/designer/palettes.json. That file is the single source of
// truth for the curated looks: this picker reads it, and the backend's parity
// test reads the same file, so a palette can't exist on one side only.
export interface PalettePreset {
  key: string
  label: string
  blurb: string
  colors: FlyerPalette
}

export interface FlyerDesign {
  version: 1
  artboard: { preset: ArtboardPreset; w: number; h: number }
  background: { kind: 'color'; color: string } | { kind: 'image'; src: string; fit: 'cover' }
  // Absent = DEFAULT_PALETTE. Optional so documents saved before tokens
  // existed keep loading unchanged.
  palette?: FlyerPalette
  layers: DesignLayer[]
}

interface DesignLayerBase {
  id: string
  x: number
  y: number
  rotation: number
  opacity: number
  locked?: boolean
}

export type DesignLayer =
  | (DesignLayerBase & {
      type: 'text'
      text: string
      fontFamily: string
      fontSize: number
      fontStyle: 'normal' | 'bold' | 'italic'
      fill: string
      align: 'left' | 'center' | 'right'
      width: number
      lineHeight: number
      letterSpacing: number
    })
  | (DesignLayerBase & { type: 'image'; src: string; width: number; height: number; slot?: 'logo' })
  | (DesignLayerBase & { type: 'sticker'; assetId: string; width: number; height: number })
  | (DesignLayerBase & {
      type: 'shape'
      shape: 'rect' | 'circle' | 'line'
      width: number
      height: number
      fill: string
      stroke?: string
      strokeWidth?: number
      cornerRadius?: number
    })
  | (DesignLayerBase & { type: 'qr'; size: number; fg: string; bg: string })

// --- design assistant ------------------------------------------------------
// The server validates AND applies, so a turn hands back the finished document
// rather than ops for the client to fold. `ops`/`results` are for the
// transcript; `design` is what the editor adopts (one undo step).
export interface FlyerOpResult {
  ok: boolean
  summary: string
}

export interface FlyerAssistResponse {
  message: string
  design: FlyerDesign
  ops: Record<string, unknown>[]
  results: FlyerOpResult[]
  rejected: { op: Record<string, unknown>; reason: string }[]
}

export interface FlyerIdea {
  key: string
  label: string
  blurb: string
  design: FlyerDesign
}

export interface FlyerAiSchema {
  palette_tokens: string[]
  palettes: PalettePreset[]
  layouts: { key: string; label: string; blurb: string; preset: ArtboardPreset }[]
  fonts: string[]
  layer_kinds: string[]
  addable_layer_kinds: string[]
  ops: string[]
  max_ops_per_turn: number
}

export interface FontManifestEntry {
  family: string
  // null = rely on the platform having the family installed (the shipped
  // manifest is system stacks). Dropping a woff2 into public/designer/fonts/
  // and filling this in upgrades a family to self-hosted with no code change —
  // useDesignerFonts registers a FontFace for every entry that has a file.
  file: string | null
  weight: number
  preview: string
}

export interface StickerManifestEntry {
  id: string
  file: string
  thumb: string
  w: number
  h: number
}

export interface TemplateManifestEntry {
  id: string
  name: string
  preset: ArtboardPreset
  file: string
  // null = the picker renders a live miniature of the template document
  // instead of a baked thumbnail, so a template edit can never go stale.
  thumb: string | null
}
