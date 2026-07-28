import { api, API_BASE } from '../client'

export type LandingSizzleVideo = { id: string; title: string; caption?: string; url: string | null }
export type LandingCustomerLogo = { name: string; url: string }
export type LandingTestimonial = { quote: string; author: string; title: string }
export type LandingMedia = {
  hero_video_url: string | null
  hero_poster_url: string | null
  sizzle_videos: LandingSizzleVideo[]
  customer_logos: LandingCustomerLogo[]
  testimonials: LandingTestimonial[]
}

export const landingMedia = {
  // Public unauthenticated endpoint — deliberate raw fetch (no auth header, no refresh)
  getPublic: async (): Promise<LandingMedia> => {
    const res = await fetch(`${API_BASE}/landing-media`)
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  },
  getAdmin: () => api.get<LandingMedia>('/admin/landing-media'),
  save: (data: LandingMedia) => api.put<{ ok: boolean; value: LandingMedia }>('/admin/landing-media', data),
  upload: (file: File, kind: 'video' | 'image') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('kind', kind)
    return api.upload<{ url: string; filename: string; content_type: string; size: number }>(
      '/admin/landing-media/upload',
      fd,
    )
  },
}
