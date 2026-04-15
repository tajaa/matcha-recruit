import { api } from './client'

export interface ParsedResume {
  name?: string | null
  email?: string | null
  phone?: string | null
  location?: string | null
  current_title?: string | null
  experience_years?: number | null
  skills?: string[] | null
  education?: string | null
  certifications?: string[] | null
  summary?: string | null
  strengths?: string[] | null
  flags?: string[] | null
}

export interface ProfileResume {
  filename: string
  resume_url: string
  parsed_data: ParsedResume
  updated_at: string
}

export const getMyResume = () => api.get<ProfileResume | null>('/users/me/resume')

export const uploadMyResume = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.upload<ProfileResume>('/users/me/resume', fd)
}

export const deleteMyResume = () => api.delete<void>('/users/me/resume')

/** Recruiter-only: view an applicant's current profile resume.
 *  Authorized by the server when the caller has posted a channel job
 *  posting that the target user has applied to.
 */
export const getApplicantResume = (userId: string) =>
  api.get<ProfileResume | null>(`/users/${userId}/resume`)
