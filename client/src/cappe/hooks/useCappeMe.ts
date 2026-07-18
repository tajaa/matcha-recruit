import { useCallback, useEffect, useState } from 'react'
import { cappeApi, getCappeToken } from '../api'
import type { CappeAccount } from '../types'

// Singleton cache (mirrors useMe.ts) — the Cappe account, fetched once.
let _cache: CappeAccount | null = null
let _promise: Promise<CappeAccount> | null = null

function _fetch(): Promise<CappeAccount> {
  if (_cache) return Promise.resolve(_cache)
  if (_promise) return _promise
  _promise = cappeApi
    .get<CappeAccount>('/auth/me')
    .then((data) => {
      _cache = data
      _promise = null
      return data
    })
    .catch((err) => {
      _promise = null
      throw err
    })
  return _promise
}

export function invalidateCappeMeCache() {
  _cache = null
  _promise = null
}

/** Auth state for the Cappe product. Returns null account when unauthenticated. */
export function useCappeMe() {
  const hasToken = !!getCappeToken()
  const [account, setAccount] = useState<CappeAccount | null>(_cache)
  const [loading, setLoading] = useState(hasToken && !_cache)

  const refresh = useCallback(() => {
    invalidateCappeMeCache()
    if (!getCappeToken()) {
      setAccount(null)
      setLoading(false)
      return
    }
    setLoading(true)
    _fetch()
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!getCappeToken()) {
      setAccount(null)
      setLoading(false)
      return
    }
    _fetch()
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setLoading(false))
  }, [])

  return { account, loading, refresh }
}
