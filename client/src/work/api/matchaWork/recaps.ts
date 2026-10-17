import { api } from '../../../api/client'
import type { RecapDetail, RecapList, RecapPlayback, RecapPreferences, RecapSummary } from '../../types'

const ROOT = '/matcha-work/recaps'
export const getRecapPreferences = () => api.get<RecapPreferences>(`${ROOT}/preferences`)
export const saveRecapPreferences = (value: Pick<RecapPreferences, 'enabled' | 'email_enabled'>) => api.put<RecapPreferences>(`${ROOT}/preferences`, value)
export const getRecap = (id: string) => api.get<RecapDetail>(`${ROOT}/${encodeURIComponent(id)}`)
export const getRecapPlayback = (id: string) => api.post<RecapPlayback>(`${ROOT}/${encodeURIComponent(id)}/playback`, {})
export const retryRecap = (id: string, requestId: string) => api.post<RecapSummary>(`${ROOT}/${encodeURIComponent(id)}/retry`, { request_id: requestId })
export const deleteRecap = (id: string) => api.delete(`${ROOT}/${encodeURIComponent(id)}`)
export function listRecaps(before?: string | null, sourceId?: string | null) {
  const query = new URLSearchParams()
  if (before) query.set('before', before)
  if (sourceId) query.set('source_id', sourceId)
  return api.get<RecapList>(`${ROOT}?${query}`)
}
