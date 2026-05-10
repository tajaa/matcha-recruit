import { api } from './client'

export type ResourceKind =
  | 'template'
  | 'job_description'
  | 'glossary'
  | 'state_guide'
  | 'calculator'

export type ResourcePin = {
  kind: ResourceKind
  id: string
  created_at: string | null
}

export type ResourcePinList = { pins: ResourcePin[] }

export function listResourcePins() {
  return api.get<ResourcePinList>('/resources/pins')
}

export function addResourcePin(kind: ResourceKind, id: string) {
  return api.post<void>('/resources/pins', { kind, id })
}

export function removeResourcePin(kind: ResourceKind, id: string) {
  return api.delete<void>(`/resources/pins/${kind}/${encodeURIComponent(id)}`)
}
