import { api } from '../client'
import type {
  AnnounceChannel,
  EmployeeOption,
  KindCatalogEntry,
  Passcode,
  Symlink,
  SymlinkCreatePayload,
  SymlinkDetail,
  SymlinkStatus,
  SymlinkSubmission,
} from '../../types/symlink'

export function listKinds() {
  return api.get<{ kinds: KindCatalogEntry[] }>('/symlink/kinds')
}

export function listSymlinks(status?: SymlinkStatus) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<{ links: Symlink[] }>(`/symlink/links${qs}`)
}

export function createSymlink(payload: SymlinkCreatePayload) {
  return api.post<Symlink>('/symlink/links', payload)
}

export function getSymlink(id: string) {
  return api.get<SymlinkDetail>(`/symlink/links/${id}`)
}

export function resendSymlink(id: string) {
  return api.post<Symlink>(`/symlink/links/${id}/resend`)
}

export function revokeSymlink(id: string) {
  return api.post<Symlink>(`/symlink/links/${id}/revoke`)
}

export function attachmentDownloadUrl(linkId: string, attachmentId: string) {
  return api.get<{ url: string; file_name: string }>(`/symlink/links/${linkId}/attachments/${attachmentId}/download`)
}

export function listSubmissions(status: 'pending' | 'applied' | 'rejected' = 'pending') {
  return api.get<{ submissions: SymlinkSubmission[] }>(`/symlink/submissions?status=${status}`)
}

export function applySubmission(id: string) {
  return api.post<SymlinkSubmission>(`/symlink/submissions/${id}/apply`)
}

export function rejectSubmission(id: string, note?: string) {
  return api.post<SymlinkSubmission>(`/symlink/submissions/${id}/reject`, { note: note || null })
}

export function getPasscode() {
  return api.get<Passcode>('/symlink/passcode')
}

export function rotatePasscode() {
  return api.post<Passcode>('/symlink/passcode/rotate')
}

export function updatePasscodeSettings(body: {
  rotation_weekday?: number
  announce_channel_id?: string | null
  clear_announce_channel?: boolean
}) {
  return api.put<Passcode>('/symlink/passcode/settings', body)
}

export function listAnnounceChannels() {
  return api.get<{ channels: AnnounceChannel[] }>('/symlink/channels')
}

export function searchEmployees(q: string) {
  return api.get<{ employees: EmployeeOption[] }>(`/symlink/employees?q=${encodeURIComponent(q)}`)
}
