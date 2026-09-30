import { api } from '../../api/client'
import type {
  DriveFile,
  DriveFolder,
  DriveFolderView,
  DriveGrant,
  DriveGrantPermission,
  DrivePerson,
  DriveSpace,
  DriveTree,
} from '../types'

// Matcha Drive — company + HR document store (business /work only).
// Backend: server/app/matcha/routes/matcha_work/drive.py. Every capability
// check is server-side; `caps` on a folder only drives what the UI offers.

const BASE = '/matcha-work/drive'

export const getDriveTree = () => api.get<DriveTree>(`${BASE}/tree`)

export const getDriveFolder = (folderId: string) =>
  api.get<DriveFolderView>(`${BASE}/folders/${folderId}`)

export const createDriveFolder = (parentId: string, name: string) =>
  api.post<DriveFolder>(`${BASE}/folders`, { parent_id: parentId, name })

export const updateDriveFolder = (folderId: string, patch: { name?: string; parent_id?: string }) =>
  api.patch<DriveFolder>(`${BASE}/folders/${folderId}`, patch)

export const deleteDriveFolder = (folderId: string) => api.delete<void>(`${BASE}/folders/${folderId}`)

export function uploadDriveFile(folderId: string, file: File) {
  const form = new FormData()
  form.append('folder_id', folderId)
  form.append('file', file)
  return api.upload<DriveFile>(`${BASE}/files`, form)
}

export const updateDriveFile = (fileId: string, patch: { filename?: string; folder_id?: string }) =>
  api.patch<DriveFile>(`${BASE}/files/${fileId}`, patch)

export const deleteDriveFile = (fileId: string) => api.delete<void>(`${BASE}/files/${fileId}`)

export const getDriveDownloadUrl = (fileId: string) =>
  api.get<{ url: string; filename: string; expires_in: number }>(`${BASE}/files/${fileId}/download`)

export function searchDrive(q: string, space?: DriveSpace) {
  const params = new URLSearchParams({ q })
  if (space) params.set('space', space)
  return api.get<{ results: DriveFile[] }>(`${BASE}/search?${params.toString()}`)
}

export const listDriveGrants = (folderId: string) =>
  api.get<{ grants: DriveGrant[] }>(`${BASE}/folders/${folderId}/grants`)

export const setDriveGrant = (folderId: string, userId: string, permission: DriveGrantPermission) =>
  api.put<{ user_id: string; permission: DriveGrantPermission }>(`${BASE}/folders/${folderId}/grants`, {
    user_id: userId,
    permission,
  })

export const removeDriveGrant = (folderId: string, userId: string) =>
  api.delete<void>(`${BASE}/folders/${folderId}/grants/${userId}`)

export function searchDrivePeople(q: string) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  return api.get<{ people: DrivePerson[] }>(`${BASE}/people?${params.toString()}`)
}
