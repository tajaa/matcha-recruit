import { api } from '../../client'
import type {
  AvailablePoster,
  PosterOrder,
} from '../../../types/compliance'

// ── Posters ──

export function fetchAvailablePosters() {
  return api.get<AvailablePoster[]>('/compliance/posters/available')
}

export function fetchPosterOrders() {
  return api.get<{ orders: PosterOrder[] }>('/compliance/posters/orders')
}

export function createPosterOrder(data: { location_id: string; template_ids: string[] }) {
  return api.post<PosterOrder>('/compliance/posters/orders', data)
}
