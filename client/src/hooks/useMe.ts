import { useCallback, useEffect, useState } from 'react'
import { onAuthReset } from '../api/authReset'
import { api } from '../api/client'
import type { MeResponse } from '../types/dashboard'

let _cache: MeResponse | null = null
let _cacheAt = 0
let _promise: Promise<MeResponse> | null = null

// Past this age the cache is served stale-while-revalidate: callers get the
// cached value instantly, a background refetch picks up feature flips
// (Stripe webhook, admin toggle) without requiring a full page reload.
const CACHE_TTL_MS = 60_000

function _revalidate(): Promise<MeResponse> {
  if (_promise) return _promise
  _promise = api.get<MeResponse>('/auth/me').then((data) => {
    _cache = data
    _cacheAt = Date.now()
    _promise = null
    return data
  }).catch((err) => {
    _promise = null
    throw err
  })
  return _promise
}

function _fetch(): Promise<MeResponse> {
  if (_cache) {
    if (Date.now() - _cacheAt > CACHE_TTL_MS) void _revalidate().catch(() => {})
    return Promise.resolve(_cache)
  }
  return _revalidate()
}

export function invalidateMeCache() {
  _cache = null
  _cacheAt = 0
  _promise = null
}

onAuthReset(invalidateMeCache)

/** Read-only accessor for callers that want to decide whether to revalidate. */
export function getMeCacheAgeMs(): number {
  return _cacheAt === 0 ? Number.POSITIVE_INFINITY : Date.now() - _cacheAt
}

export function useMe() {
  const [me, setMe] = useState<MeResponse | null>(_cache)
  const [loading, setLoading] = useState(!_cache)

  const refresh = useCallback(() => {
    invalidateMeCache()
    setLoading(true)
    _fetch()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    _fetch()
      .then(setMe)
      .catch(() => setMe(null))
      .finally(() => setLoading(false))
  }, [])

  const hasFeature = useCallback(
    (f: string): boolean => !!me?.profile?.enabled_features?.[f],
    [me],
  )

  const isHealthcare =
    me?.profile?.industry?.toLowerCase() === 'healthcare'

  const isPersonal = !!me?.profile?.is_personal

  const bf = me?.user?.beta_features ?? {}
  const mwBetaLite = bf['matcha_work_beta_lite'] === true || bf['matcha_work_beta_full'] === true
  const mwBetaFull = bf['matcha_work_beta_full'] === true

  return { me, loading, hasFeature, isHealthcare, isPersonal, mwBetaLite, mwBetaFull, refresh }
}
