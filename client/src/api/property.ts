import { api } from './client'
import type { PropertySov, BuildingPayload } from '../types/property'

export function fetchPropertySov() {
  return api.get<PropertySov>('/property/sov')
}

export function createBuilding(body: BuildingPayload) {
  return api.post<PropertySov>('/property/buildings', body)
}

export function updateBuilding(id: string, body: BuildingPayload) {
  return api.put<PropertySov>(`/property/buildings/${id}`, body)
}

export function deleteBuilding(id: string) {
  return api.delete<PropertySov>(`/property/buildings/${id}`)
}
