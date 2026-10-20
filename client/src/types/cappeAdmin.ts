// Matcha admin's Cappe tools (/admin/cappe): the plan picker and signup-grant
// links, served by /api/cappe/matcha-admin/*.

export type CappePlanOption = { code: string; name: string; status: string }

export type CappeSignupGrantAccount = {
  id: string
  email: string
  plan: string
  signed_up_at: string
  email_verified_at: string | null
  // When the plan was given; `refused` says why it wasn't.
  redeemed_at: string | null
  refused: string | null
}

export type CappeSignupGrant = {
  id: string
  plan_code: string
  plan_name: string
  days: number
  max_redemptions: number
  redeemed_count: number
  email: string | null
  note: string | null
  expires_at: string | null
  revoked_at: string | null
  created_by_email: string | null
  created_at: string
  signup_url: string
  // Everyone who signed up through it; `accounts` is the latest few.
  signup_count: number
  accounts: CappeSignupGrantAccount[]
}
