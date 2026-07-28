import { api } from '../client'

export function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<{ avatar_url: string }>('/auth/avatar', fd)
}
