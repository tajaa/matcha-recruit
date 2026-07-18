export type BrokerContract = {
  id: string | null
  currency: string | null
  base_platform_fee: number | null
  pepm_rate: number | null
  minimum_monthly_commit: number | null
}

export type Broker = {
  id: string
  name: string
  slug: string
  status: string
  support_routing: string
  billing_mode: string
  invoice_owner: string
  branding_mode: string
  active_member_count: number
  active_company_count: number
  allocated_seats?: number
  seats_used?: number
  plan?: string
  active_contract: BrokerContract | null
  created_at: string
}

export type BrokerListResponse = {
  brokers: Broker[]
}

export type CreateForm = {
  broker_name: string
  owner_email: string
  owner_name: string
  owner_password: string
  slug: string
  support_routing: string
  billing_mode: string
  invoice_owner: string
  allocated_seats: string
}

export const EMPTY_FORM: CreateForm = {
  broker_name: '',
  owner_email: '',
  owner_name: '',
  owner_password: '',
  slug: '',
  support_routing: 'shared',
  billing_mode: 'direct',
  invoice_owner: 'matcha',
  allocated_seats: '',
}

export type EditForm = {
  status: string
  support_routing: string
  allocated_seats: string
  plan: string
}

export type CreateResult = {
  broker: { name: string; slug: string }
  owner: { email: string; password?: string; generated_password: boolean; email_sent: boolean }
}

export type CompanyOption = { id: string; name: string; status: string; industry: string | null }
