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

// One photo or graphic in Gummfit Studio's curated bank (server
// services/magazine/studio/bank.py): photos carry their files, credit and
// licence; graphics their sha, group and whether sites recolour them.
export type CappeStudioBankItem = {
  id: string
  kind: 'photo' | 'graphic'
  name: string
  tags: string[]
  collection: string | null
  status: 'live' | 'hidden'
  sort_order: number
  url: string | null
  variants: { webp?: { url: string; width: number }[] } | null
  width: number | null
  height: number | null
  creator: string | null
  credit_line: string | null
  license: 'gummfit' | 'cc0' | 'pdm' | 'by' | 'by-sa' | null
  source_url: string | null
  sha: string | null
  mono: boolean | null
  fit: 'contain' | 'stretch' | 'tile' | null
  graphic_group: string | null
  created_by_email: string | null
  created_at: string
}
