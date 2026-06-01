import { api } from './client'

// Saved Deal Flow editor template (admin-global, one row per tab key). The
// payload shape is owned by each editor tab; the backend stores it as opaque
// JSONB and returns null when the tab has never been saved.
export type SavedTemplate<T> = {
  key: string
  payload: T | null
  updated_at: string | null
  updated_by: string | null
}

export type DealTemplateKey = 'book' | 'full' | 'broker' | 'one_pager' | 'lite'

export function getTemplate<T>(key: DealTemplateKey) {
  return api.get<SavedTemplate<T>>(`/admin/deal-flow/templates/${key}`)
}

export function saveTemplate<T>(key: DealTemplateKey, payload: T) {
  return api.put<SavedTemplate<T>>(`/admin/deal-flow/templates/${key}`, { payload })
}
