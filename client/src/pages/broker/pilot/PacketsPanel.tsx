import { useState } from 'react'
import { Download, FileText, Loader2 } from 'lucide-react'
import { downloadPilotPacket, type PilotPacket, type PilotSession } from '../../../api/broker/brokerPilot'
import { HelpHint } from '../../../components/broker/HelpHint'
import { LABEL, fmtSize, fmtWhen } from './shared'

/** Work product: the memo PDFs generated for this session, newest first. */
export function PacketsPanel({ session }: { session: PilotSession }) {
  const [busy, setBusy] = useState<string | null>(null)
  const packets = session.packets ?? []
  if (packets.length === 0) return null

  const download = async (packet: PilotPacket) => {
    setBusy(packet.id)
    try { await downloadPilotPacket(session.id, packet) } finally { setBusy(null) }
  }

  return (
    <div className="flex flex-col border-b border-white/[0.06]">
      <div className="flex items-baseline justify-between px-4 pb-2 pt-4">
        <span className="inline-flex items-center gap-1.5">
          <span className={LABEL}>Work product</span>
          <HelpHint text="Analysis memos exported from this session — client-ready PDFs with the narrative, numbered grounded observations, an evidence index, and appendices reproducing every cited record. Click to re-download." />
        </span>
        <span className="font-mono text-[11px] tabular-nums text-zinc-500">{packets.length}</span>
      </div>
      <div className="pb-1">
        {packets.map((p) => (
          <button
            key={p.id}
            onClick={() => void download(p)}
            className="flex w-full items-center gap-2.5 border-t border-white/[0.04] px-4 py-2 text-left transition-colors first:border-t-0 hover:bg-white/[0.02]"
          >
            <FileText className="h-3.5 w-3.5 shrink-0 text-emerald-400/80" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-xs text-zinc-300">{p.filename}</div>
              <div className="font-mono text-[10px] tabular-nums text-zinc-600">
                {fmtWhen(p.generated_at)}{fmtSize(p.file_size) ? ` · ${fmtSize(p.file_size)}` : ''}
              </div>
            </div>
            {busy === p.id
              ? <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-zinc-500" />
              : <Download className="h-3.5 w-3.5 shrink-0 text-zinc-600" />}
          </button>
        ))}
      </div>
    </div>
  )
}
