import { useEffect, useState } from 'react'
import { api } from '../client'

// Product codes priced through this table: the two Lite variants that share
// the /lite/signup page + checkout (standard, with an employee roster;
// Essentials, no roster/no OSHA logs), standalone Matcha Compliance, the
// Lite add-ons (block_size=1 ⇒ per-employee/month), and Tell-Us brand billing
// (block_size=1 ⇒ per-store/month — "headcount" fields mean store count here),
// and the personal Espresso plans (flat monthly, one unit) — each priced
// independently.
export type MatchaLiteProductCode =
  | 'matcha_lite'
  | 'matcha_lite_essentials'
  | 'matcha_compliance'
  | 'addon_voice_intake'
  | 'addon_hris_sync'
  | 'addon_handbook_watch'
  | 'tellus_brand'
  | 'espresso_lite'
  | 'espresso_pro'

// Flat monthly plans: no block size or headcount. Mirrors the server's
// matcha_lite_pricing.FLAT_PRODUCT_CODES (the admin PUT pins them to one unit).
export const FLAT_PLAN_CODES: readonly MatchaLiteProductCode[] = ['espresso_lite', 'espresso_pro']

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
  // Keyed by code, so a changed productCode reads null until its own price
  // arrives instead of briefly showing the previous product's.
  const [loaded, setLoaded] = useState<{ code: MatchaLiteProductCode; pricing: MatchaLitePricingConfig } | null>(null)
  useEffect(() => {
    let cancelled = false
    fetchMatchaLitePricing(productCode)
      .then((pricing) => { if (!cancelled) setLoaded({ code: productCode, pricing }) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [productCode])
  return loaded?.code === productCode ? loaded.pricing : null
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
