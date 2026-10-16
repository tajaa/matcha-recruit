import { useEffect, useState } from 'react'
import { API_BASE } from '../../../api/client'
import type { ProductDefinition } from '../../../types/dashboard'
import { SCHEDULING_PRODUCT_SLUG } from './signup'

/** The self-serve scheduling price — the same product row "Start now" checks
 *  out against, edited at /admin/pricing. */
export type SchedulingPrice = { name: string; perLocation: number }

/** Null until it loads, and stays null if the product isn't published or
 *  isn't priced per location: callers then keep the proposed plan prices. */
export function useSchedulingPrice(): SchedulingPrice | null {
  const [price, setPrice] = useState<SchedulingPrice | null>(null)
  useEffect(() => {
    let cancelled = false
    // Public endpoint, no auth — same fetch as the signup page (ProductSignup).
    fetch(`${API_BASE}/products/${encodeURIComponent(SCHEDULING_PRODUCT_SLUG)}`)
      .then((r) => (r.ok ? (r.json() as Promise<ProductDefinition>) : null))
      .then((product) => {
        if (cancelled || !product || product.pricing_model !== 'per_location' || !product.price_cents) return
        setPrice({ name: product.name, perLocation: product.price_cents / 100 })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  return price
}
