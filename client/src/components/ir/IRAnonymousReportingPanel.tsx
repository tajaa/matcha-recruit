import { useState, useEffect } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, QrCode, RefreshCw, X, History, Download } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Input, Select } from '../ui'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

type LinkStatus = 'active' | 'revoked' | 'expired'

type LocationLink = {
  id: string
  location_id: string
  location_name: string | null
  location_label: string
  token: string
  link: string
  is_active: boolean
  status: LinkStatus
  use_count: number
  max_uses: number | null
  used: boolean
  last_used_at: string | null
  expires_at: string | null
  revoked_at: string | null
  created_at: string | null
}

type LinkHistoryEntry = {
  token: string
  status: 'active' | 'rotated' | 'revoked'
  use_count: number
  went_live_at: string | null
  retired_at: string | null
}

const STATUS_STYLE: Record<LinkStatus, string> = {
  active: 'text-emerald-400/80',
  revoked: 'text-red-400/80',
  expired: 'text-zinc-500',
}

function locationLabel(loc: LocationRow): string {
  const name = (loc.name || '').trim()
  const place = [loc.city, loc.state].filter(Boolean).join(', ')
  if (name && place) return `${name} — ${place}`
  return name || place || loc.id.slice(0, 8)
}

export function IRAnonymousReportingPanel() {
  const [status, setStatus] = useState<{ enabled: boolean; link?: string } | null>(null)
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

  // Always-on panel (not collapsible — admins must not miss it). Load on mount.
  useEffect(() => {
    api.get<{ enabled: boolean; link?: string }>('/ir/incidents/anonymous-reporting/status')
      .then(setStatus)
      .catch(() => setStatus({ enabled: false }))
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations((rows || []).filter((r) => r.is_active)))
      .catch(() => setLocations([]))
    api.get<LocationLink[]>('/ir/incidents/anonymous-reporting/location-links')
      .then((rows) => setLinks(rows || []))
      .catch(() => setLinks([]))
  }, [])

  async function generateLink() {
    setLoading(true)
    try {
      const res = await api.post<{ link: string }>('/ir/incidents/anonymous-reporting/generate')
      setStatus({ enabled: true, link: res.link })
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

  const linkedIds = new Set(links.map((l) => l.location_id))
  const pickable = locations.filter((l) => !linkedIds.has(l.id))

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl">
      <div className="px-5 py-3 border-b border-white/5">
        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Anonymous Reporting</span>
      </div>
      <div className="p-5 space-y-5">
          {/* Company-wide anonymous link */}
          <div className="space-y-3">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Company-wide link</p>
            {!status ? (
              <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">Loading…</p>
            ) : (
              <>
                {status.link && (
                  <div className="flex items-center gap-2">
                    <input
                      readOnly
                      value={status.link}
                      className="flex-1 bg-zinc-950 border border-white/10 rounded-lg text-[11px] text-zinc-300 px-3 py-2 font-mono"
                    />
                    <Button size="sm" variant="ghost" onClick={() => navigator.clipboard.writeText(status.link!)}>Copy</Button>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <Button size="sm" disabled={loading} onClick={generateLink}>
                    {status.link ? 'Regenerate Link' : 'Generate Link'}
                  </Button>
                  {status.enabled && (
                    <Button size="sm" variant="ghost" disabled={loading} onClick={disable}>Disable</Button>
                  )}
                  {status.link && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => downloadPoster('/ir/incidents/anonymous-reporting/poster.pdf', 'incident-qr-poster.pdf')}
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download QR poster
                    </Button>
                  )}
                </div>
                <p className="text-[11px] text-zinc-500">Anonymous — no name collected, single-use.</p>
              </>
            )}
          </div>

          <div className="border-t border-white/5" />

          {/* Per-location magic links */}
          <div className="space-y-3">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">Location-specific links</p>
            <p className="text-[11px] text-zinc-500">
              A unique URL / QR per site. Opens the full intake form with the location locked — the reporter just
              adds details and their name. Reusable until revoked or expired; regenerate to rotate the token if it leaks.
            </p>

            {locations.length === 0 ? (
              <p className="text-[11px] text-zinc-500">Add a location in Settings → Locations to create a link.</p>
            ) : (
              <div className="space-y-2">
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <Select
                      label="Location"
                      options={[
                        { value: '', label: pickable.length ? 'Select a location…' : 'All locations have links' },
                        ...pickable.map((l) => ({ value: l.id, label: locationLabel(l) })),
                      ]}
                      value={pickLoc}
                      onChange={(e) => setPickLoc(e.target.value)}
                    />
                  </div>
                  <Button size="sm" disabled={genLoading || !pickLoc} onClick={() => generateForLocation(pickLoc, true)}>
                    Generate
                  </Button>
                </div>
                {/* Optional limits — blank = unlimited uses / never expires. */}
                <div className="flex items-end gap-2">
                  <div className="w-32">
                    <Input
                      label="Max uses"
                      type="number"
                      min={1}
                      placeholder="Unlimited"
                      value={genMaxUses}
                      onChange={(e) => setGenMaxUses(e.target.value)}
                    />
                  </div>
                  <div className="flex-1">
                    <Input
                      label="Expires"
                      type="date"
                      value={genExpiry}
                      onChange={(e) => setGenExpiry(e.target.value)}
                    />
                  </div>
                </div>
              </div>
            )}

            {links.length > 0 && (
              <div className="space-y-2">
                {links.map((l) => (
                  <div key={l.id} className={`bg-zinc-950/60 border rounded-lg p-3 space-y-2 ${l.status === 'active' ? 'border-white/10' : 'border-red-500/20'}`}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-zinc-200">{l.location_label}</span>
                      <span className={`text-[10px] uppercase tracking-widest font-mono ${STATUS_STYLE[l.status]}`}>{l.status}</span>
                    </div>
                    <p className="text-[11px] text-zinc-500">
                      {l.use_count}{l.max_uses != null ? `/${l.max_uses}` : ''} {l.use_count === 1 && l.max_uses == null ? 'use' : 'uses'}
                      {' · '}
                      {l.expires_at ? `expires ${new Date(l.expires_at).toLocaleDateString()}` : 'never expires'}
                    </p>
                    <div className="flex items-center gap-2">
                      <input
                        readOnly
                        value={l.link}
                        className="flex-1 bg-zinc-950 border border-white/10 rounded-lg text-[11px] text-zinc-300 px-3 py-2 font-mono"
                      />
                      <button
                        type="button"
                        title="Copy link"
                        onClick={() => navigator.clipboard.writeText(l.link)}
                        className="p-2 text-zinc-400 hover:text-zinc-100"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        title="Show QR code"
                        onClick={() => setQrOpen((q) => (q === l.id ? null : l.id))}
                        className={`p-2 hover:text-zinc-100 ${qrOpen === l.id ? 'text-emerald-400' : 'text-zinc-400'}`}
                      >
                        <QrCode className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        title="Show rotation history"
                        onClick={() => toggleHistory(l.id)}
                        className={`p-2 hover:text-zinc-100 ${histOpen === l.id ? 'text-emerald-400' : 'text-zinc-400'}`}
                      >
                        <History className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        title={l.status === 'active' ? 'Regenerate (rotate token)' : 'Regenerate (revive link)'}
                        onClick={() => generateForLocation(l.location_id)}
                        className="p-2 text-zinc-400 hover:text-zinc-100"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        title="Revoke"
                        disabled={!l.is_active}
                        onClick={() => revokeLink(l.id)}
                        className="p-2 text-zinc-400 hover:text-red-400 disabled:opacity-30 disabled:hover:text-zinc-400"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {qrOpen === l.id && (
                      <div className="flex flex-col items-center gap-2 pt-1">
                        <div className="bg-white p-3 rounded-lg inline-block">
                          <QRCodeSVG value={l.link} size={140} />
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => downloadPoster(
                            `/ir/incidents/anonymous-reporting/location-links/${l.id}/poster.pdf`,
                            `incident-qr-${l.location_label}.pdf`,
                          )}
                        >
                          <Download className="w-3.5 h-3.5" />
                          Download PDF
                        </Button>
                      </div>
                    )}
                    {histOpen === l.id && (
                      <div className="pt-1 space-y-1">
                        {(histData[l.id] || []).length === 0 ? (
                          <p className="text-[11px] text-zinc-600">No rotation history yet.</p>
                        ) : (
                          (histData[l.id] || []).map((h, i) => (
                            <div key={`${h.token}-${i}`} className="flex items-center justify-between gap-2 text-[11px] text-zinc-500">
                              <span className="font-mono text-zinc-400">…{h.token.slice(-6)}</span>
                              <span className={STATUS_STYLE[h.status === 'active' ? 'active' : h.status === 'revoked' ? 'revoked' : 'expired']}>
                                {h.status}
                              </span>
                              <span>{h.use_count} {h.use_count === 1 ? 'use' : 'uses'}</span>
                              <span>{h.retired_at ? new Date(h.retired_at).toLocaleDateString() : 'live'}</span>
                            </div>
                          ))
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
    </div>
  )
}
