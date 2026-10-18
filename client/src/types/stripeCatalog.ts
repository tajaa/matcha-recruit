export type StripeCatalogKey = 'incidents' | 'scheduler'

export type StripeCatalogProduct = {
  key: StripeCatalogKey
  name: string
  display_name: string
  description: string
  active: boolean
  status: 'synced' | 'out_of_sync' | 'error' | 'not_synced' | 'not_configured' | 'not_ready'
  stripe_product_id: string | null
  prices: { key: string; label: string; stripe_price_id: string; amount_cents: number }[]
  error: string | null
  synced_at: string | null
  webhook_verified_at: string | null
}

export type StripeCatalog = {
  configured: boolean
  account_id: string | null
  livemode: boolean | null
  webhook: { catalog_events_enabled?: boolean; url?: string }
  products: StripeCatalogProduct[]
}
