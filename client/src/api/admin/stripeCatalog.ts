import { api } from '../client'
import type { StripeCatalog, StripeCatalogKey } from '../../types/stripeCatalog'

export const fetchStripeCatalog = () => api.get<StripeCatalog>('/admin/stripe-catalog')
export const syncStripeCatalog = (key: StripeCatalogKey) =>
  api.post<StripeCatalog>(`/admin/stripe-catalog/${key}/sync`, {})
export const connectStripeCatalogWebhook = () =>
  api.post<{ url: string; catalog_events_enabled: boolean }>('/admin/stripe-catalog/webhook', {})
export const saveStripeCatalogDetails = (key: StripeCatalogKey, details: { name: string; description: string }) =>
  api.put<StripeCatalog>(`/admin/stripe-catalog/${key}`, details)
