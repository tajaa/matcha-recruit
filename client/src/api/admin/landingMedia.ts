import { api, API_BASE } from '../client'
import { reportJsError } from '../errorReporter'

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
      // The browser talks to S3 directly, so the backend never sees these failures. Report them
      // (they land in Admin → Client Errors) with what's needed to tell CORS from a bad policy.
      const fail = (message: string, outcome: 'rejected' | 'unreachable' | 'timeout') => {
        reportJsError(new Error(message), {
          source: 'landing-media-s3-upload',
          outcome,
          slot,
          size: file.size,
          content_type: contentType,
          http_status: xhr.status,
          upload_host: new URL(prepared.upload_url).host,
          page_origin: window.location.origin,
        })
        reject(new Error(message))
      }
      xhr.open('POST', prepared.upload_url)
      xhr.timeout = 15 * 60 * 1000
      xhr.upload.onprogress = (event) => {
        onProgress({ phase: 'uploading', percent: event.lengthComputable && event.total > 0 ? Math.min(100, Math.round(event.loaded / event.total * 100)) : null })
      }
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : fail('S3 rejected the upload. Check the bucket upload configuration and try again.', 'rejected')
      xhr.onerror = () => fail('Upload could not reach S3. Check your connection and the bucket CORS configuration.', 'unreachable')
      xhr.ontimeout = () => fail('Upload timed out. Try again with a smaller file.', 'timeout')
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
