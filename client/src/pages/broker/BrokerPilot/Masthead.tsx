import { useEffect, useState } from 'react'
import { Building2, Check, Download, FileText, Globe, Loader2, Pencil, X } from 'lucide-react'
import { Button } from '../../../components/ui'
import {
  updatePilotSession, generatePilotMemo, downloadPilotPacket,
  type ContextPreview, type PilotSession,
} from '../../../api/brokerPilot'
import { LABEL, SOURCE_META, deriveSystems, fmtWhen } from './shared'

interface MastheadProps {
  session: PilotSession
  context: ContextPreview | null
  onChanged: () => void
}

/** Session docket header: subject caption + the systems strip (which platform
 *  subsystems + documents ground this session, live counts) + memo export. */
export function Masthead({ session, context, onChanged }: MastheadProps) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(session.title)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasAssistant = (session.messages ?? []).some((m) => m.role === 'assistant')
  const latestPacket = (session.packets ?? [])[0]

  const saveTitle = async () => {
    const next = title.trim()
    if (!next || next === session.title) { setEditing(false); setTitle(session.title); return }
    await updatePilotSession(session.id, { title: next })
    setEditing(false)
    onChanged()
  }

  const exportMemo = async () => {
    setGenerating(true)
    setError(null)
    try {
      const packet = await generatePilotMemo(session.id)
      await downloadPilotPacket(session.id, packet)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Memo generation failed')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="shrink-0 border-b border-white/[0.06]">
      <div className="flex items-start justify-between gap-4 px-5 pt-4">
        <div className="min-w-0">
          <div className={LABEL}>Session</div>
          {editing ? (
            <div className="mt-0.5 flex items-center gap-2">
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') void saveTitle(); if (e.key === 'Escape') { setEditing(false); setTitle(session.title) } }}
                className="w-80 rounded-md border border-white/[0.08] bg-zinc-900/60 px-2 py-1 text-lg font-semibold text-zinc-100 outline-none focus:border-emerald-500/50"
                autoFocus
              />
              <button onClick={() => void saveTitle()} className="text-emerald-400 hover:text-emerald-300"><Check className="h-4 w-4" /></button>
              <button onClick={() => { setEditing(false); setTitle(session.title) }} className="text-zinc-500 hover:text-zinc-300"><X className="h-4 w-4" /></button>
            </div>
          ) : (
            <div className="mt-0.5 flex items-center gap-2 min-w-0">
              <h2 className="truncate text-lg font-semibold tracking-tight text-zinc-100">{session.title}</h2>
              <button onClick={() => setEditing(true)} className="shrink-0 text-zinc-600 hover:text-zinc-300" title="Rename">
                <Pencil className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] uppercase tracking-wide text-zinc-500">
            <span className="inline-flex items-center gap-1.5 normal-case text-zinc-300">
              {session.subject_kind === 'company'
                ? <Building2 className="h-3 w-3 text-emerald-400/80" />
                : <Globe className="h-3 w-3 text-emerald-400/80" />}
              {session.subject_name ?? 'Client'}
            </span>
            <span>{session.subject_kind === 'company' ? 'platform' : 'external'}</span>
            <span className={session.status === 'closed' ? 'text-zinc-600' : 'text-emerald-400/90'}>{session.status}</span>
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            {latestPacket && (
              <Button size="sm" variant="secondary" onClick={() => void downloadPilotPacket(session.id, latestPacket)}
                title={`Latest memo · ${fmtWhen(latestPacket.generated_at)}`}>
                <Download className="h-4 w-4" /> Latest memo
              </Button>
            )}
            <Button size="sm" variant="secondary" disabled={!hasAssistant || generating} onClick={() => void exportMemo()}
              title={hasAssistant ? 'Generate + download an analysis memo PDF' : 'Chat first — the memo is built from the analysis'}>
              {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />} Memo PDF
            </Button>
          </div>
          {error && <p className="text-[11px] text-red-400">{error}</p>}
        </div>
      </div>

      <SystemsStrip key={session.id} context={context} />

      {generating && (
        <div className="flex items-center gap-2 border-t border-emerald-500/20 bg-emerald-500/[0.04] px-5 py-1.5">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-emerald-300/90">
            Assembling memo — rendering the grounded analysis + citations
          </span>
        </div>
      )}
    </div>
  )
}

function SystemsStrip({ context }: { context: ContextPreview | null }) {
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(true))
    return () => cancelAnimationFrame(id)
  }, [])

  const systems = deriveSystems(context)

  return (
    <div className="mt-3 flex items-stretch divide-x divide-white/[0.06] overflow-x-auto border-t border-white/[0.06]">
      <div className="flex shrink-0 items-center gap-2.5 py-2.5 pl-5 pr-4">
        <span className={LABEL}>In scope</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-emerald-400">
          {context ? context.total : '·'}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-wide text-zinc-600">records</span>
      </div>
      {SOURCE_META.map((s, i) => {
        const records = systems[s.key]
        const active = !!records && records.length > 0
        const Icon = s.icon
        return (
          <div
            key={s.key}
            className={`flex shrink-0 items-center gap-2 px-4 py-2.5 transition-opacity duration-300 motion-reduce:transition-none ${shown ? 'opacity-100' : 'opacity-0'}`}
            style={{ transitionDelay: `${i * 40}ms` }}
            title={active ? `${s.label}: ${records.length} record(s)` : `${s.label}: none on file`}
          >
            <Icon className={`h-3.5 w-3.5 ${active ? 'text-emerald-400' : 'text-zinc-700'}`} />
            <span className={`text-[10px] font-medium uppercase tracking-[0.15em] ${active ? 'text-zinc-300' : 'text-zinc-600'}`}>
              {s.label}
            </span>
            <span className={`font-mono text-xs tabular-nums ${active ? 'text-zinc-100' : 'text-zinc-700'}`}>
              {active ? records.length : '—'}
            </span>
          </div>
        )
      })}
    </div>
  )
}
