export type LandingSizzleVideo = { id: string; title: string; caption?: string; url: string | null }
export type LandingCustomerLogo = { name: string; url: string }
export type LandingTestimonial = { quote: string; author: string; title: string }
export type SchedulingCommercial = {
  enabled: boolean
  /** true: viewers can start it with sound and get a Sound off/on button; false: always silent. */
  sound_enabled: boolean
  desktop_video_url: string | null
  mobile_video_url: string | null
  desktop_poster_url: string | null
  mobile_poster_url: string | null
  captions_url: string | null
}
export type CommercialSlot = 'desktop_video' | 'mobile_video' | 'desktop_poster' | 'mobile_poster' | 'captions'
export type CommercialUploadProgress = {
  phase: 'preparing' | 'uploading' | 'verifying'
  percent: number | null
}
export type LandingMedia = {
  hero_video_url: string | null
  hero_poster_url: string | null
  sizzle_videos: LandingSizzleVideo[]
  customer_logos: LandingCustomerLogo[]
  testimonials: LandingTestimonial[]
  scheduling_commercial?: SchedulingCommercial
}
export const EMPTY_COMMERCIAL: SchedulingCommercial = {
  enabled: false, sound_enabled: true, desktop_video_url: null, mobile_video_url: null,
  desktop_poster_url: null, mobile_poster_url: null, captions_url: null,
}
