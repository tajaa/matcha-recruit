import { api } from '../../client'
import type {
  JurisdictionOption,
  BusinessLocation,
  LocationCreate,
  LocationUpdate,
  FacilityAttributes,
} from '../../../types/compliance'

// ── Jurisdictions ──

export function fetchJurisdictions() {
  return api.get<JurisdictionOption[]>('/compliance/jurisdictions')
}

// ── Locations ──

export function fetchLocations() {
  return api.get<BusinessLocation[]>('/compliance/locations')
}

export function fetchLocation(locationId: string) {
  return api.get<BusinessLocation>(`/compliance/locations/${locationId}`)
}

export function createLocation(data: LocationCreate) {
  return api.post<BusinessLocation>('/compliance/locations', data)
}

export function updateLocation(locationId: string, data: LocationUpdate) {
  return api.put<BusinessLocation>(`/compliance/locations/${locationId}`, data)
}

export function deleteLocation(id: string) {
  return api.delete(`/compliance/locations/${id}`)
}

// ── Facility Attributes ──

export function fetchFacilityAttributes(locationId: string) {
  return api.get<{ facility_attributes: FacilityAttributes }>(
    `/compliance/locations/${locationId}/facility-attributes`
  )
}

export function updateFacilityAttributes(locationId: string, data: Partial<FacilityAttributes>) {
  return api.patch<{ facility_attributes: FacilityAttributes }>(
    `/compliance/locations/${locationId}/facility-attributes`,
    data
  )
}
