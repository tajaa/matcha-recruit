import { api, API_BASE } from '../client'

import type { CommercialSlot, CommercialUploadProgress, LandingMedia, SchedulingCommercial } from '../../types/landingMedia'
export type { LandingMedia, LandingSizzleVideo, LandingCustomerLogo, LandingTestimonial } from '../../types/landingMedia'

export const landingMedia = {
  // Public unauthenticated endpoint — deliberate raw fetch (no auth header, no refresh)
  getPublic: async (signal?: AbortSignal): Promise<LandingMedia> => {
    const res = await fetch(`${API_BASE}/landing-media`, { signal })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json()
  },
  getAdmin: () => api.get<LandingMedia>('/admin/landing-media'),
  save: (data: LandingMedia) => api.put<{ ok: boolean; value: LandingMedia }>('/admin/landing-media', { hero_video_url: data.hero_video_url, hero_poster_url: data.hero_poster_url, sizzle_videos: data.sizzle_videos, customer_logos: data.customer_logos, testimonials: data.testimonials }),
  saveCommercial: (data: SchedulingCommercial) => api.put<{ ok: boolean; value: SchedulingCommercial }>('/admin/landing-media/scheduling-commercial', data),
  uploadCommercial: async (file: File, slot: CommercialSlot, onProgress: (progress: CommercialUploadProgress) => void) => {
    onProgress({ phase: 'preparing', percent: null })
    const contentType = slot === 'captions' ? 'text/vtt' : file.type
    const request = { filename: file.name, content_type: contentType, size: file.size, slot }
    const prepared = await api.post<{ upload_url: string; fields: Record<string, string>; asset_url: string }>('/admin/landing-media/scheduling-commercial/upload', request)
    const form = new FormData()
    for (const [key, value] of Object.entries(prepared.fields)) form.append(key, value)
    form.append('file', file)
    onProgress({ phase: 'uploading', percent: null })
    // This signed POST goes directly to S3; never attach the app's auth headers.
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', prepared.upload_url)
      xhr.timeout = 15 * 60 * 1000
      xhr.upload.onprogress = (event) => {
        onProgress({ phase: 'uploading', percent: event.lengthComputable && event.total > 0 ? Math.min(100, Math.round(event.loaded / event.total * 100)) : null })
      }
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error('S3 rejected the upload. Check the bucket upload configuration and try again.'))
      xhr.onerror = () => reject(new Error('Upload could not reach S3. Check your connection and the bucket CORS configuration.'))
      xhr.ontimeout = () => reject(new Error('Upload timed out. Try again with a smaller file.'))
      xhr.onabort = () => reject(new Error('Upload interrupted. Your previous saved video has not been changed.'))
      xhr.send(form)
    })
    onProgress({ phase: 'verifying', percent: null })
    const verified = await api.post<{ url: string }>('/admin/landing-media/scheduling-commercial/complete', { ...request, asset_url: prepared.asset_url })
    return verified.url
  },
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
