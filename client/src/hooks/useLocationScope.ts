import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'

export type CompanyLocation = {
  id: string
  name: string | null
  address?: string | null
  city: string
  state: string
  zipcode?: string | null
  is_active: boolean
}

export function locationLabel(l: CompanyLocation): string {
  const address = [l.address, l.city, l.state, l.zipcode].filter(Boolean).join(', ')
  const base = l.name && address ? `${l.name} — ${address}` : (l.name || address)
  return l.is_active ? base : `${base} (inactive)`
}

/** URL-persisted (`?location=`) single-location scope, shared by every
 *  location-scoped page. `autoSelectSingle` picks the only location when a
 *  company has exactly one, so single-site tenants never see a picker. */
export function useLocationScope(opts: { autoSelectSingle?: boolean } = {}) {
  const { autoSelectSingle = true } = opts
  const [searchParams, setSearchParams] = useSearchParams()
  const locationId = searchParams.get('location') ?? ''
  const [locations, setLocations] = useState<CompanyLocation[]>([])
  const [loading, setLoading] = useState(true)

  const setLocationId = useCallback((next: string) => {
    setSearchParams((current) => {
      const params = new URLSearchParams(current)
      if (next) params.set('location', next)
      else params.delete('location')
      return params
    }, { replace: true })
  }, [setSearchParams])

  useEffect(() => {
    let cancelled = false
    api.get<{ locations: CompanyLocation[] }>('/locations')
      .then((r) => { if (!cancelled) setLocations(r.locations) })
      .catch(() => { if (!cancelled) setLocations([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    if (autoSelectSingle && !locationId && locations.length === 1) setLocationId(locations[0].id)
  }, [autoSelectSingle, locationId, locations, setLocationId])

  return { locationId, setLocationId, locations, loading }
}
