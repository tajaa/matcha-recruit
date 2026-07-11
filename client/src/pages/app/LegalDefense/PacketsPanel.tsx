import { useState } from 'react'
import { ChevronDown, Download, FileArchive, FileText, Share2 } from 'lucide-react'
import { useToast } from '../../../components/ui'
import { HelpHint } from '../../../components/ui/HelpHint'
import { downloadPacket, type Packet } from '../../../api/legalDefense'
import { fmtSize } from './shared'

function shareStatusText(share: Packet['share']): string | null {
  if (!share) return null
  if (share.revoked) return 'Link revoked'
  if (share.expires_at && new Date(share.expires_at) < new Date()) return 'Link expired'
  const who = share.recipient_email ? ` with ${share.recipient_email}` : ''
  if (share.download_count === 0) return `Shared${who} — not yet opened`
  const last = share.last_downloaded_at ? new Date(share.last_downloaded_at).toLocaleDateString() : null
  return `Shared${who} — opened ${share.download_count}×${last ? ` (last ${last})` : ''}`
}

/** Work product: latest PDF/ZIP pinned, older versions collapsed. Rows keep
 *  a chain-of-custody line for anything already shared with counsel. */
export function PacketsPanel({ matterId, packets, toast, onShare }: {
  matterId: string
  packets: Packet[]
  toast: ReturnType<typeof useToast>['toast']
  onShare: (p: Packet) => void
}) {
  const [showOlder, setShowOlder] = useState(false)
  if (packets.length === 0) return null

  // Newest-first from the backend; pin the latest of each kind.
  const latest: Packet[] = []
  const seen = new Set<string>()
  for (const p of packets) {
    if (!seen.has(p.kind)) { seen.add(p.kind); latest.push(p) }
  }
  const latestIds = new Set(latest.map((p) => p.id))
  const older = packets.filter((p) => !latestIds.has(p.id))

  return (
    <div className="shrink-0 border-t border-white/[0.06]">
      <div className="flex items-center gap-1.5 px-4 pb-1 pt-3 text-[10px] font-medium uppercase tracking-[0.15em] text-zinc-500">
        Work product
        <HelpHint text="The PDF is a defense memo that cites only real records; the ZIP bundles the underlying source documents. Shared links are logged for chain of custody." />
      </div>
      {latest.map((p) => (
        <PacketRow key={p.id} matterId={matterId} packet={p} toast={toast} onShare={() => onShare(p)} />
      ))}
      {older.length > 0 && (
        <>
          <button
            className="flex w-full items-center gap-1 px-4 py-2 text-[11px] text-zinc-600 transition-colors hover:text-zinc-300"
            onClick={() => setShowOlder((v) => !v)}
          >
            <ChevronDown className={`h-3 w-3 transition-transform ${showOlder ? 'rotate-180' : ''}`} />
            {showOlder ? 'Hide earlier versions' : `${older.length} earlier version${older.length === 1 ? '' : 's'}`}
          </button>
          {showOlder && older.map((p) => (
            <div key={p.id} className="opacity-60">
              <PacketRow matterId={matterId} packet={p} toast={toast} onShare={() => onShare(p)} />
            </div>
          ))}
        </>
      )}
    </div>
  )
}

function PacketRow({ matterId, packet, toast, onShare }: {
  matterId: string; packet: Packet; onShare: () => void
  toast: ReturnType<typeof useToast>['toast']
}) {
  const shareText = shareStatusText(packet.share)
  const size = fmtSize(packet.file_size)
  return (
    <div className="border-t border-white/[0.04] px-4 py-2.5">
      <div className="flex items-center gap-2">
        {packet.kind === 'zip'
          ? <FileArchive className="h-3.5 w-3.5 text-zinc-500" />
          : <FileText className="h-3.5 w-3.5 text-zinc-500" />}
        <span className="font-mono text-[11px] uppercase tracking-wide text-zinc-200">{packet.kind}</span>
        <span className="ml-auto font-mono text-[10px] tabular-nums text-zinc-500">
          {size ? `${size} · ` : ''}{new Date(packet.generated_at).toLocaleDateString()}
        </span>
      </div>
      <div className="mt-1.5 flex gap-1">
        <button
          onClick={() => void downloadPacket(matterId, packet).catch((e) =>
            toast(e instanceof Error ? e.message : 'Download failed', 'error'))}
          className="flex items-center gap-1.5 rounded border border-white/[0.08] px-2 py-1 text-[11px] text-zinc-300 transition-colors hover:border-emerald-500/40 hover:text-zinc-100"
        >
          <Download className="h-3 w-3" /> Download
        </button>
        <button
          onClick={onShare}
          className="flex items-center gap-1.5 rounded border border-white/[0.08] px-2 py-1 text-[11px] text-zinc-300 transition-colors hover:border-emerald-500/40 hover:text-zinc-100"
        >
          <Share2 className="h-3 w-3" /> Send to counsel
        </button>
      </div>
      {shareText && <div className="mt-1.5 text-[10px] leading-snug text-zinc-500">{shareText}</div>}
    </div>
  )
}
