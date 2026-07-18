import { api } from '../client'
import type { PropertySov, BuildingPayload, BulkUploadResult, SovParseResult } from '../../types/property'

export function fetchPropertySov() {
  return api.get<PropertySov>('/property/sov')
}

export function downloadBuildingTemplate() {
  return api.download('/property/buildings/template', 'property_sov_template.csv')
}

export function bulkUploadBuildings(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<BulkUploadResult>('/property/buildings/bulk-upload', fd)
}

export function parseSovFile(file: File) {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<SovParseResult>('/property/buildings/parse', fd)
}

export function bulkInsertBuildings(buildings: BuildingPayload[]) {
  return api.post<BulkUploadResult>('/property/buildings/bulk-insert', { buildings })
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
