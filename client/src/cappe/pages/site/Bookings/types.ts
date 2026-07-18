import type { CappePricingMode } from '../../../types'

export type TypeForm = {
  name: string
  description: string
  duration_minutes: string
  pricing_mode: CappePricingMode
  price: string
  requires_approval: boolean
  category: string
  buffer: string
  staffIds: string[]
}

export type StaffForm = { name: string; bio: string; image_url: string }

export type LocForm = { name: string; timezone: string; address: string; phone: string }
