import { useState, useEffect } from 'react'
import { QRCodeSVG } from 'qrcode.react'
import { Copy, QrCode, RefreshCw, X } from 'lucide-react'
import { api } from '../../api/client'
import { Button, Select } from '../ui'

type LocationRow = {
  id: string
  name: string | null
  city: string
  state: string
  is_active: boolean
}

type LocationLink = {
  id: string
  location_id: string
  location_name: string | null
  location_label: string
  token: string
  link: string
  used: boolean
  used_at: string | null
  created_at: string | null
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
  const [expanded, setExpanded] = useState(false)

  // Per-location magic links (attributed intake at /intake/:token)
  const [locations, setLocations] = useState<LocationRow[]>([])
  const [links, setLinks] = useState<LocationLink[]>([])
  const [pickLoc, setPickLoc] = useState('')
  const [genLoading, setGenLoading] = useState(false)
  const [qrOpen, setQrOpen] = useState<string | null>(null)

  useEffect(() => {
    if (expanded && !status) {
      api.get<{ enabled: boolean; link?: string }>('/ir/incidents/anonymous-reporting/status')
        .then(setStatus)
        .catch(() => setStatus({ enabled: false }))
    }
  }, [expanded, status])

  useEffect(() => {
    if (!expanded) return
    api.get<LocationRow[]>('/ir-onboarding/locations')
      .then((rows) => setLocations((rows || []).filter((r) => r.is_active)))
      .catch(() => setLocations([]))
    api.get<LocationLink[]>('/ir/incidents/anonymous-reporting/location-links')
      .then((rows) => setLinks(rows || []))
      .catch(() => setLinks([]))
  }, [expanded])

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

  async function generateForLocation(locationId: string) {
    if (!locationId) return
    setGenLoading(true)
    try {
      const link = await api.post<LocationLink>(
        '/ir/incidents/anonymous-reporting/location-links',
        { location_id: locationId },
      )
      setLinks((prev) => {
        const others = prev.filter((l) => l.location_id !== link.location_id)
        return [...others, link].sort((a, b) => a.location_label.localeCompare(b.location_label))
      })
      setPickLoc('')
    } catch { /* ignore */ }
    finally { setGenLoading(false) }
  }

  async function revokeLink(id: string) {
    try {
      await api.delete(`/ir/incidents/anonymous-reporting/location-links/${id}`)
      setLinks((prev) => prev.filter((l) => l.id !== id))
      setQrOpen((q) => (q === id ? null : q))
    } catch { /* ignore */ }
  }

  const linkedIds = new Set(links.map((l) => l.location_id))
  const pickable = locations.filter((l) => !linkedIds.has(l.id))

  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-3 bg-zinc-950/50 hover:bg-zinc-950/70 text-left transition-colors"
      >
        <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Anonymous Reporting</span>
        <span className="text-zinc-500 text-xs font-mono">{expanded ? '−' : '+'}</span>
      </button>
      {expanded && (
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
              adds details and their name. Single-use; regenerate to issue a fresh one.
            </p>

            {locations.length === 0 ? (
              <p className="text-[11px] text-zinc-500">Add a location in Settings → Locations to create a link.</p>
            ) : (
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
                <Button size="sm" disabled={genLoading || !pickLoc} onClick={() => generateForLocation(pickLoc)}>
                  Generate
                </Button>
              </div>
            )}

            {links.length > 0 && (
              <div className="space-y-2">
                {links.map((l) => (
                  <div key={l.id} className="bg-zinc-950/60 border border-white/10 rounded-lg p-3 space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs text-zinc-200">{l.location_label}</span>
                      {l.used && (
                        <span className="text-[10px] uppercase tracking-widest text-amber-400/80 font-mono">Used</span>
                      )}
                    </div>
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
                        title="Regenerate"
                        onClick={() => generateForLocation(l.location_id)}
                        className="p-2 text-zinc-400 hover:text-zinc-100"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        title="Revoke"
                        onClick={() => revokeLink(l.id)}
                        className="p-2 text-zinc-400 hover:text-red-400"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    {qrOpen === l.id && (
                      <div className="flex justify-center pt-1">
                        <div className="bg-white p-3 rounded-lg inline-block">
                          <QRCodeSVG value={l.link} size={140} />
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
