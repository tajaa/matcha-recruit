// TypeScript shapes mirroring server/app/tellus/models/tellus.py.

export type AccountType = 'consumer' | 'brand'

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
  owner_account_id: string
  name: string
  logo_url: string | null
  reward_mode: 'auto' | 'manual'
  created_at: string
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

export interface IntakeConfig {
  brand_name: string
  brand_logo_url: string | null
  store_name: string | null
  categories: string[]
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
}

export interface Redemption {
  id: string
  account_id: string
  listing_id: string
  listing_title: string | null
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
