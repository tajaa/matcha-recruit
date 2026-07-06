import { useEffect, useState } from 'react'
import { api } from './client'

// Product codes priced through this table: the two Lite variants that share
// the /lite/signup page + checkout (standard, with an employee roster;
// Essentials, no roster/no OSHA logs), standalone Matcha Compliance, and the
// Lite add-ons (block_size=1 ⇒ per-employee/month) — each priced independently.
export type MatchaLiteProductCode =
  | 'matcha_lite'
  | 'matcha_lite_essentials'
  | 'matcha_compliance'
  | 'addon_voice_intake'
  | 'addon_hris_sync'
  | 'addon_handbook_watch'

export interface MatchaLitePricingConfig {
  price_per_block_cents: number
  block_size: number
  effective_price_per_block_cents: number
  sale_active: boolean
  min_headcount: number
  max_headcount: number
}

export function fetchMatchaLitePricing(productCode: MatchaLiteProductCode = 'matcha_lite') {
  return api.get<MatchaLitePricingConfig>(`/resources/matcha-lite/pricing?product_code=${encodeURIComponent(productCode)}`)
}

export function computeLitePriceDollars(headcount: number, pricing: MatchaLitePricingConfig): number {
  return Math.ceil(headcount / pricing.block_size) * (pricing.effective_price_per_block_cents / 100)
}

// Live Matcha Lite price, fetched once per productCode. Callers should fall
// back to a sane default (e.g. 300) for max_headcount while `pricing` is null.
export function useMatchaLitePricing(productCode: MatchaLiteProductCode = 'matcha_lite'): MatchaLitePricingConfig | null {
  const [pricing, setPricing] = useState<MatchaLitePricingConfig | null>(null)
  useEffect(() => {
    setPricing(null)
    fetchMatchaLitePricing(productCode).then(setPricing).catch(() => {})
  }, [productCode])
  return pricing
}

// Admin — Matcha Lite pricing config (base + sale price). Distinct shape from
// MatchaLitePricingConfig above: no computed effective_price_per_block_cents,
// but exposes the raw sale price + change metadata for editing.
export interface MatchaLitePricingAdminConfig {
  price_per_block_cents: number
  block_size: number
  sale_price_per_block_cents: number | null
  sale_active: boolean
  min_headcount: number
  max_headcount: number
  updated_at: string | null
  updated_by: string | null
}

export interface MatchaLitePricingUpdate {
  price_per_block_cents: number
  block_size: number
  sale_price_per_block_cents: number | null
  sale_active: boolean
  min_headcount: number
  max_headcount: number
}

export function fetchMatchaLitePricingAdmin(productCode: MatchaLiteProductCode = 'matcha_lite') {
  return api.get<MatchaLitePricingAdminConfig>(`/admin/matcha-lite-pricing?product_code=${encodeURIComponent(productCode)}`)
}

export function saveMatchaLitePricingAdmin(
  update: MatchaLitePricingUpdate,
  productCode: MatchaLiteProductCode = 'matcha_lite',
) {
  return api.put<MatchaLitePricingAdminConfig>(`/admin/matcha-lite-pricing?product_code=${encodeURIComponent(productCode)}`, update)
}
