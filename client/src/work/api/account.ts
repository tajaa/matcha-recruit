import { api } from '../../api/client'

export function updateWorkProfile(body: { name: string; phone?: string }) {
  return api.put<{ status: string }>('/auth/profile', body)
}

export function uploadWorkAvatar(file: File) {
  const form = new FormData()
  form.append('file', file)
  return api.upload<{ avatar_url: string }>('/auth/avatar', form)
}
