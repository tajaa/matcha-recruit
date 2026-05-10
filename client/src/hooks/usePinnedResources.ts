import { useCallback, useEffect, useState } from 'react'

import {
  type ResourceKind,
  type ResourcePin,
  addResourcePin,
  listResourcePins,
  removeResourcePin,
} from '../api/resourcePins'

/**
 * Shared in-memory pin set across the whole app — multiple PinButtons +
 * the dashboard widget all read from one source. Module-scoped cache +
 * subscriber list so a toggle on one button updates every other consumer
 * without prop drilling. Mirrors the `useMe` pattern.
 *
 * Optimistic updates: toggle mutates the cache + broadcasts immediately,
 * then sends to the server; on error refetches to recover. Double-clicks
 * inside a single tick collapse to a single network call thanks to the
 * cache being mutated synchronously.
 */

let _cache: ResourcePin[] | null = null
let _loading = false
let _promise: Promise<void> | null = null
const _subscribers = new Set<(p: ResourcePin[] | null) => void>()

function _broadcast() {
  for (const sub of _subscribers) sub(_cache)
}

async function _load(): Promise<void> {
  if (_promise) return _promise
  _loading = true
  _promise = listResourcePins()
    .then(d => {
      _cache = d.pins
      _loading = false
      _promise = null
      _broadcast()
    })
    .catch(() => {
      _cache = []
      _loading = false
      _promise = null
      _broadcast()
    })
  return _promise
}

export function invalidatePinsCache() {
  _cache = null
  _broadcast()
}

export function usePinnedResources() {
  const [pins, setPins] = useState<ResourcePin[] | null>(_cache)

  useEffect(() => {
    _subscribers.add(setPins)
    if (_cache === null && !_loading) void _load()
    return () => {
      _subscribers.delete(setPins)
    }
  }, [])

  const isPinned = useCallback((kind: ResourceKind, id: string) => {
    return !!_cache?.some(p => p.kind === kind && p.id === id)
  }, [pins])

  const togglePin = useCallback(async (kind: ResourceKind, id: string) => {
    const currently = !!_cache?.some(p => p.kind === kind && p.id === id)
    // Optimistic local mutation.
    if (currently) {
      _cache = (_cache ?? []).filter(p => !(p.kind === kind && p.id === id))
    } else {
      _cache = [
        { kind, id, created_at: new Date().toISOString() },
        ...(_cache ?? []),
      ]
    }
    _broadcast()
    try {
      if (currently) await removeResourcePin(kind, id)
      else await addResourcePin(kind, id)
    } catch {
      // Refetch on error so client state matches server.
      await _load()
    }
  }, [])

  return {
    pins: pins ?? [],
    isPinned,
    togglePin,
    loading: pins === null,
  }
}
