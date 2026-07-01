import { useEffect, useState } from 'react'
import { api } from './client'

export interface MatchaLitePricingConfig {
  price_per_block_cents: number
  block_size: number
  effective_price_per_block_cents: number
  sale_active: boolean
  min_headcount: number
  max_headcount: number
}

export function fetchMatchaLitePricing() {
  return api.get<MatchaLitePricingConfig>('/resources/matcha-lite/pricing')
}

export function computeLitePriceDollars(headcount: number, pricing: MatchaLitePricingConfig): number {
  return Math.ceil(headcount / pricing.block_size) * (pricing.effective_price_per_block_cents / 100)
}

// Live Matcha Lite price, fetched once. Callers should fall back to a sane
// default (e.g. 300) for max_headcount while `pricing` is still null.
export function useMatchaLitePricing(): MatchaLitePricingConfig | null {
  const [pricing, setPricing] = useState<MatchaLitePricingConfig | null>(null)
  useEffect(() => {
    fetchMatchaLitePricing().then(setPricing).catch(() => {})
  }, [])
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

export function fetchMatchaLitePricingAdmin() {
  return api.get<MatchaLitePricingAdminConfig>('/admin/matcha-lite-pricing')
}

export function saveMatchaLitePricingAdmin(update: MatchaLitePricingUpdate) {
  return api.put<MatchaLitePricingAdminConfig>('/admin/matcha-lite-pricing', update)
}
