import { useEffect, useState } from 'react'
import { fetchPublicProduct } from '../../../api/billing/products'
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
    // The same product row the signup page (ProductSignup) checks out against.
    fetchPublicProduct(SCHEDULING_PRODUCT_SLUG)
      .then((product) => {
        if (cancelled || !product || product.pricing_model !== 'per_location' || !product.price_cents) return
        setPrice({ name: product.name, perLocation: product.price_cents / 100 })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])
  return price
}
