import { useState, useEffect } from 'react'
import { api } from '../../../api/client'
import type {
  AnonymousStatus,
  Branding,
  LinkHistoryEntry,
  LocationLink,
  LocationRow,
} from './types'
import { DEFAULT_BRAND } from './constants'

export function useAnonymousReporting() {
  const [status, setStatus] = useState<AnonymousStatus | null>(null)
  const [loading, setLoading] = useState(false)

  // Per-location magic links (attributed intake at /intake/:token)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [links, setLinks] = useState<LocationLink[]>([])
  const [pickLoc, setPickLoc] = useState('')
  const [genMaxUses, setGenMaxUses] = useState('')
  const [genExpiry, setGenExpiry] = useState('')
  const [genLoading, setGenLoading] = useState(false)
  const [qrOpen, setQrOpen] = useState<string | null>(null)
  const [histOpen, setHistOpen] = useState<string | null>(null)
  const [histData, setHistData] = useState<Record<string, LinkHistoryEntry[]>>({})
  const [linkSearch, setLinkSearch] = useState('')
  const [inactiveOpen, setInactiveOpen] = useState(false)

  // QR poster branding — client-customizable primary/secondary; Matcha stays fixed.
  const [branding, setBranding] = useState<Branding>(DEFAULT_BRAND)
  const [brandDefault, setBrandDefault] = useState<Branding>(DEFAULT_BRAND)
  const [brandingLoading, setBrandingLoading] = useState(true)
  const [brandingSaving, setBrandingSaving] = useState(false)
  const [brandingDirty, setBrandingDirty] = useState(false)
  const [brandingSaved, setBrandingSaved] = useState(false)

  // Always-on panel (not collapsible — admins must not miss it). Load on mount.
  useEffect(() => {
    api.get<AnonymousStatus>('/ir/incidents/anonymous-reporting/status')
      .then(setStatus)
      .catch(() => setStatus({ enabled: false }))
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations((rows || []).filter((r) => r.is_active)))
      .catch(() => setLocations([]))
    api.get<LocationLink[]>('/ir/incidents/anonymous-reporting/location-links')
      .then((rows) => setLinks(rows || []))
      .catch(() => setLinks([]))
    api.get<{ branding: Branding; default: Branding }>('/ir/incidents/anonymous-reporting/branding')
      .then((r) => { setBranding(r.branding); setBrandDefault(r.default) })
      .catch(() => { /* pre-migration or transient — keep defaults */ })
      .finally(() => setBrandingLoading(false))
  }, [])

  async function generateLink() {
    setLoading(true)
    try {
      const res = await api.post<{ link: string }>('/ir/incidents/anonymous-reporting/generate')
      setStatus({ enabled: true, link: res.link, used: false, last_used_at: null })
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  async function disable() {
    setLoading(true)
    try {
      await api.delete('/ir/incidents/anonymous-reporting/disable')
      setStatus({ enabled: false })
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  // Used for both the "Generate" button (with the limit inputs) and the
  // per-row Regenerate (rotate in place; carry no new limits — keep it simple).
  async function generateForLocation(locationId: string, withLimits = false) {
    if (!locationId) return
    setGenLoading(true)
    try {
      const body: { location_id: string; max_uses?: number; expires_at?: string } = { location_id: locationId }
      if (withLimits) {
        const m = parseInt(genMaxUses, 10)
        if (!Number.isNaN(m) && m > 0) body.max_uses = m
        if (genExpiry) body.expires_at = new Date(genExpiry).toISOString()
      }
      const link = await api.post<LocationLink>(
        '/ir/incidents/anonymous-reporting/location-links',
        body,
      )
      setLinks((prev) => {
        const others = prev.filter((l) => l.location_id !== link.location_id)
        return [...others, link].sort((a, b) => a.location_label.localeCompare(b.location_label))
      })
      // A fresh token retires the old one — drop any cached history so the
      // disclosure re-fetches.
      setHistData((prev) => { const next = { ...prev }; delete next[link.id]; return next })
      setPickLoc('')
      setGenMaxUses('')
      setGenExpiry('')
    } catch { /* ignore */ }
    finally { setGenLoading(false) }
  }

  // Soft revoke — the row stays (now inactive) so it can be regenerated and
  // keeps its history; patch it in place from the returned link.
  async function revokeLink(id: string) {
    try {
      const updated = await api.delete<LocationLink>(`/ir/incidents/anonymous-reporting/location-links/${id}`)
      setLinks((prev) => prev.map((l) => (l.id === id ? updated : l)))
      setQrOpen((q) => (q === id ? null : q))
      setHistData((prev) => { const next = { ...prev }; delete next[id]; return next })
    } catch { /* ignore */ }
  }

  async function toggleHistory(id: string) {
    if (histOpen === id) { setHistOpen(null); return }
    setHistOpen(id)
    if (!histData[id]) {
      try {
        const rows = await api.get<LinkHistoryEntry[]>(`/ir/incidents/anonymous-reporting/location-links/${id}/history`)
        setHistData((prev) => ({ ...prev, [id]: rows || [] }))
      } catch { setHistData((prev) => ({ ...prev, [id]: [] })) }
    }
  }

  // Download a branded QR poster PDF. Swallows errors (consistent with the rest of
  // this panel) so a transient failure doesn't surface an unhandled rejection.
  async function downloadPoster(path: string, filename: string) {
    try {
      await api.download(path, filename.replace(/[^\w.-]+/g, '-'))
    } catch { /* ignore */ }
  }

  const updateBrand = (k: keyof Branding, v: string) => {
    setBranding((b) => ({ ...b, [k]: v })); setBrandingDirty(true); setBrandingSaved(false)
  }
  const resetBranding = () => { setBranding(brandDefault); setBrandingDirty(true); setBrandingSaved(false) }
  async function saveBranding() {
    setBrandingSaving(true)
    try {
      const r = await api.put<{ branding: Branding }>('/ir/incidents/anonymous-reporting/branding', branding)
      setBranding(r.branding); setBrandingDirty(false); setBrandingSaved(true)
      setTimeout(() => setBrandingSaved(false), 2000)
    } catch { /* ignore */ } finally { setBrandingSaving(false) }
  }

  const linkedIds = new Set(links.map((l) => l.location_id))
  const pickable = locations.filter((l) => !linkedIds.has(l.id))

  const linkQuery = linkSearch.trim().toLowerCase()
  const filteredLinks = linkQuery
    ? links.filter((l) => l.location_label.toLowerCase().includes(linkQuery))
    : links
  const activeLinks = filteredLinks.filter((l) => l.status === 'active')
  const inactiveLinks = filteredLinks.filter((l) => l.status !== 'active')

  // Searching should surface inactive matches even though the section defaults
  // to collapsed — auto-open while there's a query, collapse again once cleared.
  useEffect(() => {
    if (linkQuery && inactiveLinks.length > 0) setInactiveOpen(true)
    else if (!linkQuery) setInactiveOpen(false)
  }, [linkQuery, inactiveLinks.length])

  return {
    status, loading, generateLink, disable,
    locations, links, pickLoc, setPickLoc,
    genMaxUses, setGenMaxUses, genExpiry, setGenExpiry, genLoading, generateForLocation,
    qrOpen, setQrOpen, histOpen, histData, toggleHistory, revokeLink, downloadPoster,
    linkSearch, setLinkSearch, inactiveOpen, setInactiveOpen,
    branding, brandingLoading, brandingSaving, brandingDirty, brandingSaved,
    updateBrand, resetBranding, saveBranding,
    pickable, linkQuery, activeLinks, inactiveLinks,
  }
}
