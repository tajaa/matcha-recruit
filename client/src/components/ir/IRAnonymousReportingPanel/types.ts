export type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

export type LinkStatus = 'active' | 'revoked' | 'expired'

export type LocationLink = {
  id: string
  location_id: string
  location_name: string | null
  location_label: string
  token: string
  link: string
  is_active: boolean
  status: LinkStatus
  use_count: number
  max_uses: number | null
  used: boolean
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
  created_at: string | null
}

export type LinkHistoryEntry = {
  token: string
  status: 'active' | 'rotated' | 'revoked'
  use_count: number
  went_live_at: string | null
  retired_at: string | null
}

export type Branding = { primary: string; secondary: string }

export type AnonymousStatus = {
  enabled: boolean
  link?: string
  used?: boolean
  last_used_at?: string | null
}
