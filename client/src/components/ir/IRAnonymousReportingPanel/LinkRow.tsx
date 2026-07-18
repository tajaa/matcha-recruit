import { Copy, QrCode, RefreshCw, X, History, Download } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { Button } from '../../ui'
import type { LinkHistoryEntry, LocationLink } from './types'
import { STATUS_STYLE } from './constants'

interface LinkRowProps {
  l: LocationLink
  qrOpen: string | null
  setQrOpen: (updater: (q: string | null) => string | null) => void
  histOpen: string | null
  histData: Record<string, LinkHistoryEntry[]>
  toggleHistory: (id: string) => void
  generateForLocation: (locationId: string, withLimits?: boolean) => void
  revokeLink: (id: string) => void
  downloadPoster: (path: string, filename: string) => void
}

export function LinkRow({
  l,
  qrOpen,
  setQrOpen,
  histOpen,
  histData,
  toggleHistory,
  generateForLocation,
  revokeLink,
  downloadPoster,
}: LinkRowProps) {
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
