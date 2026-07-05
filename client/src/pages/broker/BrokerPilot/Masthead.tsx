import { useState } from 'react'
import { Building2, Check, Download, FileText, Globe, Loader2, Pencil, X } from 'lucide-react'
import {
  updatePilotSession, generatePilotMemo, downloadPilotPacket,
  type PilotSession,
} from '../../../api/brokerPilot'
import { fmtWhen } from './shared'

interface MastheadProps {
  session: PilotSession
  onChanged: () => void
}

export function Masthead({ session, onChanged }: MastheadProps) {
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
    <div className="flex items-start justify-between gap-4 pb-4 border-b border-zinc-800">
      <div className="min-w-0">
        {editing ? (
          <div className="flex items-center gap-2">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void saveTitle(); if (e.key === 'Escape') { setEditing(false); setTitle(session.title) } }}
              className="bg-zinc-900 border border-zinc-700 rounded-md px-2 py-1 text-lg font-semibold text-zinc-100 w-80"
              autoFocus
            />
            <button onClick={() => void saveTitle()} className="text-emerald-400 hover:text-emerald-300"><Check className="h-4 w-4" /></button>
            <button onClick={() => { setEditing(false); setTitle(session.title) }} className="text-zinc-500 hover:text-zinc-300"><X className="h-4 w-4" /></button>
          </div>
        ) : (
          <div className="flex items-center gap-2 min-w-0">
            <h2 className="text-lg font-semibold text-zinc-100 truncate">{session.title}</h2>
            <button onClick={() => setEditing(true)} className="text-zinc-600 hover:text-zinc-300 flex-shrink-0" title="Rename">
              <Pencil className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
        <div className="flex items-center gap-2 mt-1 text-xs text-zinc-500">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-300">
            {session.subject_kind === 'company'
              ? <Building2 className="h-3 w-3" />
              : <Globe className="h-3 w-3" />}
            {session.subject_name ?? 'Client'}
            <span className="text-zinc-500">· {session.subject_kind === 'company' ? 'Platform' : 'External'}</span>
          </span>
          {session.status === 'closed' && <span className="text-amber-500">Closed</span>}
        </div>
      </div>

      <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
        <div className="flex items-center gap-2">
          {latestPacket && (
            <button
              onClick={() => void downloadPilotPacket(session.id, latestPacket)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-zinc-700 text-zinc-300 hover:text-zinc-100 hover:border-zinc-600 transition-colors"
              title={`Latest memo · ${fmtWhen(latestPacket.generated_at)}`}
            >
              <Download className="h-3.5 w-3.5" />
              Latest memo
            </button>
          )}
          <button
            onClick={() => void exportMemo()}
            disabled={!hasAssistant || generating}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-emerald-700 text-white hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            title={hasAssistant ? 'Generate + download an analysis memo PDF' : 'Chat first — the memo is built from the analysis'}
          >
            {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
            Export memo
          </button>
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>
    </div>
  )
}
