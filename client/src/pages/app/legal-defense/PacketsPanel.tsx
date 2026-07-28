import { useState } from 'react'
import { ChevronDown, Download, FileArchive, FileText, Link2Off, Loader2, Share2 } from 'lucide-react'
import { useToast } from '../../../components/ui'
import { PacketsPanel as PilotPacketsPanel } from '../../../components/pilot/PacketsPanel'
import { downloadPacket, revokeShare, type Packet, type PacketShareStatus } from '../../../api/legal-defense/legalDefense'
import { fmtSize } from './shared'

function isLive(share: PacketShareStatus): boolean {
  return !share.revoked && !(share.expires_at && new Date(share.expires_at) < new Date())
}

function oneShareStatusText(share: PacketShareStatus): string {
  const who = share.recipient_email ? ` with ${share.recipient_email}` : ''
  if (share.download_count === 0) return `Shared${who} — not yet opened`
  const last = share.last_downloaded_at ? new Date(share.last_downloaded_at).toLocaleDateString() : null
  return `Shared${who} — opened ${share.download_count}×${last ? ` (last ${last})` : ''}`
}

/** Summary line above the live-links list — must never disagree with it. Built
 *  from `shares` (every link), not `share` (only the newest): re-share A, then
 *  B, then revoke B, and `share` is B's now-revoked row — rendering "Link
 *  revoked" directly above a live entry for A, which reads as a packet that is
 *  simultaneously not shared and shared. With >1 live link the summary reads
 *  the count rather than picking one link to represent all of them; falls back
 *  to the newest link's own status only when none are live. */
function shareStatusText(shares: PacketShareStatus[] | null | undefined): string | null {
  const all = shares ?? []
  if (all.length === 0) return null
  const live = all.filter(isLive)
  if (live.length === 1) return oneShareStatusText(live[0])
  if (live.length > 1) {
    const opened = live.filter((s) => s.download_count > 0).length
    return `Shared with ${live.length} link${live.length === 1 ? '' : 's'} — ${opened} opened`
  }
  // Nothing live: newest link explains why (revoked / expired).
  const newest = all[0]
  if (newest.revoked) return 'Link revoked'
  if (newest.expires_at && new Date(newest.expires_at) < new Date()) return 'Link expired'
  return oneShareStatusText(newest)
}

/** Work product: latest PDF/ZIP pinned, older versions collapsed. Rows keep
 *  a chain-of-custody line for anything already shared with counsel. */
export function PacketsPanel({ matterId, packets, toast, onShare, onRevoked }: {
  matterId: string
  packets: Packet[]
  toast: ReturnType<typeof useToast>['toast']
  onShare: (p: Packet) => void
  /** Refresh the matter after a revoke so the row reflects the new state. */
  onRevoked?: () => void
}) {
  const [showOlder, setShowOlder] = useState(false)

  // Newest-first from the backend; pin the latest of each kind.
  const latest: Packet[] = []
  const seen = new Set<string>()
  for (const p of packets) {
    if (!seen.has(p.kind)) { seen.add(p.kind); latest.push(p) }
  }
  const latestIds = new Set(latest.map((p) => p.id))
  const older = packets.filter((p) => !latestIds.has(p.id))

  return (
    <PilotPacketsPanel
      empty={packets.length === 0}
      className="shrink-0 border-t border-white/[0.06]"
      variant="inline"
      helpText="The PDF is a defense memo that cites only real records; the ZIP bundles the underlying source documents. Shared links are logged for chain of custody."
    >
      {latest.map((p) => (
        <PacketRow key={p.id} matterId={matterId} packet={p} toast={toast} onShare={() => onShare(p)} onRevoked={onRevoked} />
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
              <PacketRow matterId={matterId} packet={p} toast={toast} onShare={() => onShare(p)} onRevoked={onRevoked} />
            </div>
          ))}
        </>
      )}
    </PilotPacketsPanel>
  )
}

function PacketRow({ matterId, packet, toast, onShare, onRevoked }: {
  matterId: string; packet: Packet; onShare: () => void
  toast: ReturnType<typeof useToast>['toast']
  onRevoked?: () => void
}) {
  const [revoking, setRevoking] = useState<string | null>(null)
  const shareText = shareStatusText(packet.shares)
  const size = fmtSize(packet.file_size)
  // Every link that still works, not just the newest. A packet re-shared with a
  // second attorney leaves the first link live, and the row used to show only
  // the latest — so the older one could neither be seen nor pulled back.
  const liveShares = (packet.shares ?? []).filter(isLive)

  async function revoke(shareId: string) {
    setRevoking(shareId)
    try {
      await revokeShare(matterId, shareId)
      toast('Share link revoked — that link no longer opens the packet.', 'success')
      onRevoked?.()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Could not revoke the link', 'error')
    } finally {
      setRevoking(null)
    }
  }

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
      {liveShares.length > 0 && (
        <div className="mt-1.5 space-y-1">
          {liveShares.map((s) => (
            <div key={s.id} className="flex items-center gap-2 text-[10px] leading-snug text-zinc-500">
              <span className="truncate">
                Live link{s.recipient_email ? ` · ${s.recipient_email}` : ''}
                {s.expires_at ? ` · expires ${new Date(s.expires_at).toLocaleDateString()}` : ''}
                {` · ${s.download_count} download${s.download_count === 1 ? '' : 's'}`}
              </span>
              <button
                onClick={() => void revoke(s.id)}
                disabled={revoking === s.id}
                title="Revoke this link. Restoring access means sending a new one."
                className="ml-auto flex shrink-0 items-center gap-1 rounded border border-white/[0.08] px-1.5 py-0.5 text-[10px] text-zinc-400 transition-colors hover:border-red-500/40 hover:text-red-300 disabled:opacity-50"
              >
                {revoking === s.id
                  ? <Loader2 className="h-2.5 w-2.5 animate-spin" />
                  : <Link2Off className="h-2.5 w-2.5" />}
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
