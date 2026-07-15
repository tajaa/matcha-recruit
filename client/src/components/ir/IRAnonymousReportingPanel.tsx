import { useState, useEffect, type CSSProperties } from 'react'
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

// --- QR poster branding -----------------------------------------------------

type Branding = { primary: string; secondary: string }
const DEFAULT_BRAND: Branding = { primary: '#4f9d72', secondary: '#f5a623' }

// Mirrors the server's WCAG auto-contrast pick (ir_report_poster._text_on) so the
// live preview shows the same title/footer color the PDF will use.
function relLum(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
function contrastRatio(a: string, b: string): number {
  const la = relLum(a), lb = relLum(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}
function textOn(primary: string): string {
  return contrastRatio(primary, '#0c1f16') >= contrastRatio(primary, '#ffffff') ? '#0c1f16' : '#ffffff'
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex items-center gap-3">
      <input
        type="color"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8 w-10 shrink-0 rounded border border-white/10 bg-transparent cursor-pointer p-0"
      />
      <span className="flex-1 text-[11px] text-zinc-400">{label}</span>
      <span className="text-[11px] font-mono text-zinc-500 uppercase">{value}</span>
    </label>
  )
}

// Live poster mock — same layout as ir_report_poster.build_report_poster_pdf:
// primary background, secondary corner brackets, white QR card, fixed Matcha wordmark.
function PosterPreview({ primary, secondary }: Branding) {
  const text = textOn(primary)
  const corner = (pos: CSSProperties): CSSProperties => ({
    position: 'absolute', height: 14, width: 14, ...pos,
  })
  return (
    <div
      className="relative rounded-lg overflow-hidden"
      style={{ background: primary, width: 150, height: 194, color: text, fontFamily: 'Georgia, serif' }}
    >
      <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 px-2 text-center">
        <div className="text-[9px] font-bold tracking-wide leading-tight">SUBMIT AN INCIDENT</div>
        <div className="relative" style={{ width: 78, height: 78 }}>
          <span style={corner({ top: 0, left: 0, borderTop: `2px solid ${secondary}`, borderLeft: `2px solid ${secondary}`, borderTopLeftRadius: 3 })} />
          <span style={corner({ top: 0, right: 0, borderTop: `2px solid ${secondary}`, borderRight: `2px solid ${secondary}`, borderTopRightRadius: 3 })} />
          <span style={corner({ bottom: 0, left: 0, borderBottom: `2px solid ${secondary}`, borderLeft: `2px solid ${secondary}`, borderBottomLeftRadius: 3 })} />
          <span style={corner({ bottom: 0, right: 0, borderBottom: `2px solid ${secondary}`, borderRight: `2px solid ${secondary}`, borderBottomRightRadius: 3 })} />
          <div className="absolute inset-[7px] bg-white rounded flex items-center justify-center">
            <QrCode className="w-8 h-8 text-zinc-900" />
          </div>
        </div>
        <div className="leading-tight">
          <div className="text-[10px] font-bold tracking-wider">SCAN ME</div>
          <div className="text-[7px] font-bold tracking-wide">HEY-MATCHA.COM</div>
          <div className="text-[5px] uppercase tracking-wider" style={{ opacity: 0.7 }}>Powered by Matcha</div>
        </div>
      </div>
    </div>
  )
}

export function IRAnonymousReportingPanel() {
  const [status, setStatus] = useState<{ enabled: boolean; link?: string; used?: boolean; last_used_at?: string | null } | null>(null)
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
    api.get<{ enabled: boolean; link?: string; used?: boolean; last_used_at?: string | null }>('/ir/incidents/anonymous-reporting/status')
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

  function renderLinkRow(l: LocationLink) {
    return (
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
    )
  }

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
                <p className="text-[11px] text-zinc-500">
                  Anonymous — no name collected. Reusable until regenerated.
                  {status.used && ` Last used ${status.last_used_at ? new Date(status.last_used_at).toLocaleDateString() : 'recently'}.`}
                </p>
              </>
            )}
          </div>

          <div className="border-t border-white/5" />

          {/* QR poster branding — customize colors; Matcha branding stays fixed */}
          <div className="space-y-3">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">QR poster branding</p>
            <p className="text-[11px] text-zinc-500">
              Recolor the printable QR poster to match your brand. Matcha branding stays on every poster.
            </p>
            {brandingLoading ? (
              <p className="text-xs text-zinc-500 uppercase tracking-widest font-mono animate-pulse">Loading…</p>
            ) : (
              <div className="flex flex-col sm:flex-row gap-4">
                <div className="flex-1 space-y-3">
                  <ColorField label="Primary (background)" value={branding.primary} onChange={(v) => updateBrand('primary', v)} />
                  <ColorField label="Secondary (accents)" value={branding.secondary} onChange={(v) => updateBrand('secondary', v)} />
                  <div className="flex items-center gap-2 pt-1">
                    <Button size="sm" disabled={brandingSaving || !brandingDirty} onClick={saveBranding}>
                      {brandingSaved ? 'Saved' : 'Save branding'}
                    </Button>
                    <Button size="sm" variant="ghost" disabled={brandingSaving} onClick={resetBranding}>
                      Reset to default
                    </Button>
                  </div>
                  <p className="text-[11px] text-zinc-600">
                    "HEY-MATCHA.COM" and "Powered by Matcha" always appear; title text auto-adjusts for contrast.
                  </p>
                </div>
                <div className="flex flex-col items-center gap-1">
                  <PosterPreview primary={branding.primary} secondary={branding.secondary} />
                  <span className="text-[10px] text-zinc-600 uppercase tracking-widest">Preview</span>
                </div>
              </div>
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
              <div className="space-y-3">
                <Input
                  placeholder="Search locations…"
                  value={linkSearch}
                  onChange={(e) => setLinkSearch(e.target.value)}
                />

                <div className="space-y-2">
                  <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                    Active ({activeLinks.length})
                  </p>
                  {activeLinks.length === 0 ? (
                    <p className="text-[11px] text-zinc-600">
                      {linkQuery ? 'No matches.' : 'No active links.'}
                    </p>
                  ) : (
                    <div className="space-y-2">{activeLinks.map(renderLinkRow)}</div>
                  )}
                </div>

                {inactiveLinks.length > 0 && (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() => setInactiveOpen((v) => !v)}
                      className="text-[10px] font-bold text-zinc-500 hover:text-zinc-300 uppercase tracking-widest"
                    >
                      {inactiveOpen ? 'Hide' : 'Show'} inactive ({inactiveLinks.length})
                    </button>
                    {inactiveOpen && (
                      <div className="space-y-2">{inactiveLinks.map(renderLinkRow)}</div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
    </div>
  )
}
