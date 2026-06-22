import { api } from './client'
import type { Fleet, DriverPayload } from '../types/driverRisk'

export function fetchFleet() {
  return api.get<Fleet>('/driver-risk/fleet')
}

export function createDriver(payload: DriverPayload & { driver_name: string }) {
  return api.post<Fleet>('/driver-risk/drivers', payload)
}

export function updateDriver(id: string, payload: DriverPayload) {
  return api.put<Fleet>(`/driver-risk/drivers/${id}`, payload)
}

export function deleteDriver(id: string) {
  return api.delete<Fleet>(`/driver-risk/drivers/${id}`)
}

export function downloadFleetPdf() {
  return api.download('/driver-risk/fleet.pdf', 'driver-risk.pdf')
}
