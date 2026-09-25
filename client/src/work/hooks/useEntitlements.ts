import { useCallback, useEffect, useSyncExternalStore } from 'react'
import { useMe } from '../../hooks/useMe'
import { getEntitlements, type WorkEntitlements, type WorkPlan } from '../api/matchaWork/entitlements'

const ranks: Record<WorkPlan, number> = { free: 0, lite: 1, pro: 2, business: 2 }
const cache = new Map<string, WorkEntitlements>()
const inFlight = new Map<string, Promise<WorkEntitlements | null>>()
const listeners = new Map<string, Set<() => void>>()

function isEntitlements(value: WorkEntitlements): boolean {
  return value != null
    && Object.hasOwn(ranks, value.plan)
    && value.features != null
    && typeof value.features === 'object'
    && value.quotas != null
    && typeof value.quotas.token_limit === 'number'
    && typeof value.quotas.window_hours === 'number'
}

function notify(userId: string) {
  listeners.get(userId)?.forEach((listener) => listener())
}

function fetchEntitlements(userId: string): Promise<WorkEntitlements | null> {
  const pending = inFlight.get(userId)
  if (pending) return pending

  const request = getEntitlements()
    .then((value) => {
      if (!isEntitlements(value)) throw new Error('Invalid entitlement response')
      cache.set(userId, value)
      notify(userId)
      return value
    })
    .catch(() => cache.get(userId) ?? null)
    .finally(() => inFlight.delete(userId))
  inFlight.set(userId, request)
  return request
}

export function useEntitlements() {
  const { me } = useMe()
  const userId = me?.user?.id ?? null
  const subscribe = useCallback((listener: () => void) => {
    if (!userId) return () => {}
    let subscribers = listeners.get(userId)
    if (!subscribers) {
      subscribers = new Set()
      listeners.set(userId, subscribers)
    }
    subscribers.add(listener)
    return () => {
      subscribers.delete(listener)
      if (subscribers.size === 0) listeners.delete(userId)
    }
  }, [userId])
  const getSnapshot = useCallback(
    () => userId ? cache.get(userId) ?? null : null,
    [userId],
  )
  const entitlements = useSyncExternalStore(subscribe, getSnapshot, () => null)
  const refetch = useCallback(
    () => userId ? fetchEntitlements(userId) : Promise.resolve(null),
    [userId],
  )

  useEffect(() => {
    if (!userId) return
    void fetchEntitlements(userId)
    const onFocus = () => { void fetchEntitlements(userId) }
    window.addEventListener('focus', onFocus)
    // Stripe can return before its webhook has invalidated the server's
    // 60-second plan cache. Check again after that window without requiring
    // the user to leave and refocus the tab.
    const checkoutRetry = new URLSearchParams(window.location.search).has('upgraded')
      ? window.setTimeout(onFocus, 65_000)
      : null
    return () => {
      window.removeEventListener('focus', onFocus)
      if (checkoutRetry !== null) window.clearTimeout(checkoutRetry)
    }
  }, [userId])

  return {
    plan: entitlements?.plan ?? null,
    can: (feature: string) => entitlements == null || entitlements.features[feature] === true,
    atLeast: (minimum: WorkPlan) => entitlements == null || ranks[entitlements.plan] >= ranks[minimum],
    quotas: entitlements?.quotas ?? null,
    refetch,
  }
}
