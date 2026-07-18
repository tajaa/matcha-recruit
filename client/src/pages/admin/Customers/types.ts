export type Subscription = {
  pack_id: string
  status: string
  amount_cents: number
  stripe_subscription_id: string
  stripe_customer_id: string
  current_period_end: string | null
  canceled_at: string | null
}

export type Registration = {
  id: string
  company_name: string
  industry: string | null
  company_size: string | null
  owner_user_id: string | null
  owner_email: string
  owner_name: string
  status: string
  created_at: string
  signup_source: string | null
  is_personal: boolean
  is_suspended: boolean
  deleted_at: string | null
  subscription: Subscription | null
}

export type Individual = {
  user_id: string
  email: string
  name: string | null
  company_id: string
  created_at: string | null
  free_tokens_used: number
  free_token_limit: number
  free_tokens_remaining: number
  subscription_token_limit: number
  subscription_tokens_remaining: number
  has_active_subscription: boolean
  beta_features?: Record<string, boolean>
  is_suspended?: boolean
  subscription?: Subscription | null
}

export type Tab = 'all' | 'free' | 'lite' | 'x' | 'platform' | 'personal'
