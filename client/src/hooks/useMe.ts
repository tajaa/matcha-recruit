import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { MeResponse } from '../types/dashboard'

let _cache: MeResponse | null = null
let _promise: Promise<MeResponse> | null = null

function _fetch(): Promise<MeResponse> {
  if (_cache) return Promise.resolve(_cache)
  if (_promise) return _promise
  _promise = api.get<MeResponse>('/auth/me').then((data) => {
    _cache = data
    _promise = null
    return data
  }).catch((err) => {
    _promise = null
    throw err
  })
  return _promise
}

export function invalidateMeCache() {
  _cache = null
  _promise = null
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

  return { me, loading, hasFeature, isHealthcare, refresh }
}
