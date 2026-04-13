import { useEffect, useState } from 'react'
import { landingMedia, type LandingMedia } from '../api/client'

const FALLBACK: LandingMedia = {
  hero_video_url: null,
  hero_poster_url: null,
  sizzle_videos: [],
  customer_logos: [],
  testimonials: [],
}

export function useLandingMedia() {
  const [data, setData] = useState<LandingMedia>(FALLBACK)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let cancelled = false
    landingMedia
      .getPublic()
      .then((res) => { if (!cancelled) setData({ ...FALLBACK, ...res }) })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err : new Error(String(err))) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return { data, loading, error }
}
