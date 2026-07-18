import { Download } from 'lucide-react'
import { Button } from '../../ui'
import type { AnonymousStatus } from './types'

interface CompanyWideSectionProps {
  status: AnonymousStatus | null
  loading: boolean
  generateLink: () => void
  disable: () => void
  downloadPoster: (path: string, filename: string) => void
}

export function CompanyWideSection({ status, loading, generateLink, disable, downloadPoster }: CompanyWideSectionProps) {
  return (
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
  )
}
