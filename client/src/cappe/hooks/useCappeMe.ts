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

// Every mounted hook instance. Each holds its own copy of the account, so a
// refresh in one place (the billing page after a plan change) has to be pushed
// to the rest, or the sidebar and the editor keep showing the old plan.
const _listeners = new Set<(account: CappeAccount | null) => void>()

export function invalidateCappeMeCache() {
  _cache = null
  _promise = null
}

/** Auth state for the Cappe product. Returns null account when unauthenticated. */
export function useCappeMe() {
  const hasToken = !!getCappeToken()
  // Signed out reads as "no account" from the first render, so the mount effect
  // has nothing to reset.
  const [account, setAccount] = useState<CappeAccount | null>(hasToken ? _cache : null)
  const [loading, setLoading] = useState(hasToken && !_cache)

  const refresh = useCallback(() => {
    invalidateCappeMeCache()
    if (!getCappeToken()) {
      setAccount(null)
      setLoading(false)
      return
    }
    setLoading(true)
    return _fetch()
      .then((fresh) => { _listeners.forEach((notify) => notify(fresh)) })
      .catch(() => setAccount(null))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    _listeners.add(setAccount)
    return () => { _listeners.delete(setAccount) }
  }, [])

  useEffect(() => {
    if (!getCappeToken()) return
    _fetch()
      .then(setAccount)
      .catch(() => setAccount(null))
      .finally(() => setLoading(false))
  }, [])

  return { account, loading, refresh }
}
