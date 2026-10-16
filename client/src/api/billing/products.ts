import { API_BASE } from '../client'
import type { ProductDefinition } from '../../types/dashboard'

/** A published product-builder product by slug, from the public (no-auth)
 *  GET /products/:slug — the signup page and the scheduling landing price
 *  both read it. Null when the product isn't published. */
export async function fetchPublicProduct(slug: string): Promise<ProductDefinition | null> {
  const r = await fetch(`${API_BASE}/products/${encodeURIComponent(slug)}`)
  return r.ok ? ((await r.json()) as ProductDefinition) : null
}
