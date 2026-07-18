import { useState } from 'react'
import { BookOpen, CheckCircle2, FileText, Loader2, Trash2 } from 'lucide-react'
import {
  updatePilotDraft, deletePilotDraft, promotePilotDrafts,
  type PilotSession, type PilotDraft, type PromoteResult,
} from '../../../api/handbook-pilot/handbookPilot'
import { HelpHint } from '../../../components/ui/HelpHint'

// --------------------------------------------------------------------------- //
// DraftsPanel — review/edit candidate drafts, select, promote.
// --------------------------------------------------------------------------- //

export function DraftsPanel({ session, onChange }: { session: PilotSession; onChange: () => void }) {
  const pending = (session.drafts ?? []).filter((d) => d.status === 'pending')
  const promoted = (session.drafts ?? []).filter((d) => d.status === 'promoted')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<PromoteResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const toggle = (id: string) =>
    setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  const promote = async () => {
    if (selected.size === 0 || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await promotePilotDrafts(session.id, { draft_ids: [...selected] })
      setResult(res)
      setSelected(new Set())
      onChange()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Promotion failed — please try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
      <div className="px-3 py-2.5 border-b border-zinc-800 flex items-center justify-between">
        <span className="text-sm font-semibold text-zinc-200">Drafts</span>
        {pending.length > 0 && (
          <div className="flex items-center gap-1.5">
            <HelpHint
              text="Promote creates a new draft handbook section or policy for you to finish publishing — it never goes live automatically."
              align="right"
            />
            <button
              onClick={() => void promote()}
              disabled={selected.size === 0 || busy}
              className="text-xs px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white inline-flex items-center gap-1"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
              Promote{selected.size ? ` (${selected.size})` : ''}
            </button>
          </div>
        )}
      </div>
      <div className="p-2 space-y-2 max-h-[42vh] overflow-y-auto">
        {pending.length === 0 && promoted.length === 0 && (
          <p className="text-xs text-zinc-600 p-2">Drafts the pilot proposes will appear here to review and promote.</p>
        )}
        {pending.map((d) => (
          <DraftRow key={d.id} draft={d} selected={selected.has(d.id)} onToggle={() => toggle(d.id)} onChange={onChange} />
        ))}
        {promoted.map((d) => (
          <div key={d.id} className="px-2.5 py-2 rounded-lg bg-zinc-900/40 border border-zinc-800/60 flex items-center gap-2">
            {d.kind === 'policy' ? <FileText className="h-3.5 w-3.5 text-emerald-500" /> : <BookOpen className="h-3.5 w-3.5 text-emerald-500" />}
            <span className="text-xs text-zinc-400 truncate flex-1">{d.title}</span>
            <span className="text-[10px] uppercase tracking-wide text-emerald-500">promoted</span>
          </div>
        ))}
      </div>
      {error && (
        <div className="px-3 py-2 border-t border-zinc-800 text-xs text-amber-400">⚠ {error}</div>
      )}
      {result && (
        <div className="px-3 py-2 border-t border-zinc-800 text-xs text-zinc-400 space-y-1">
          {result.handbook && (
            <a href={`/app/handbook/${result.handbook.id}`} className="text-emerald-400 hover:underline block">
              → Handbook draft created: {result.handbook.title}
            </a>
          )}
          {result.policies.map((p) => (
            <a key={p.id} href="/app/policies" className="text-emerald-400 hover:underline block">→ Policy draft: {p.title}</a>
          ))}
          {result.failed.map((f) => (
            <div key={f.draft_id} className="text-amber-400">⚠ Couldn't promote “{f.title}”: {f.error}</div>
          ))}
        </div>
      )}
    </div>
  )
}

function DraftRow({ draft, selected, onToggle, onChange }: {
  draft: PilotDraft; selected: boolean; onToggle: () => void; onChange: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(draft.title)
  const [content, setContent] = useState(draft.content)
  const [busy, setBusy] = useState(false)

  const save = async () => {
    setBusy(true)
    try {
      await updatePilotDraft(draft.id, { title, content })
      setEditing(false)
      onChange()
    } finally { setBusy(false) }
  }
  const remove = async () => {
    setBusy(true)
    try { await deletePilotDraft(draft.id); onChange() } finally { setBusy(false) }
  }

  return (
    <div className={`rounded-lg border ${selected ? 'border-emerald-500/40 bg-emerald-500/5' : 'border-zinc-800 bg-zinc-900/40'}`}>
      <div className="flex items-center gap-2 px-2.5 py-2">
        <input type="checkbox" checked={selected} onChange={onToggle} className="accent-emerald-500" />
        {draft.kind === 'policy' ? <FileText className="h-3.5 w-3.5 text-zinc-500" /> : <BookOpen className="h-3.5 w-3.5 text-zinc-500" />}
        <span className="text-xs text-zinc-200 truncate flex-1">{draft.title}</span>
        <button onClick={() => setEditing((e) => !e)} className="text-[11px] text-zinc-500 hover:text-emerald-400">{editing ? 'Close' : 'Edit'}</button>
        <button onClick={() => void remove()} disabled={busy} className="text-zinc-600 hover:text-red-400"><Trash2 className="h-3.5 w-3.5" /></button>
      </div>
      {editing ? (
        <div className="px-2.5 pb-2.5 space-y-2">
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs text-zinc-200" />
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={8} className="w-full rounded bg-zinc-900 border border-zinc-700 px-2 py-1 text-xs text-zinc-300 font-mono leading-relaxed" />
          <button onClick={() => void save()} disabled={busy} className="text-xs px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white">Save</button>
        </div>
      ) : (
        <div className="px-2.5 pb-2.5">
          <p className="text-[11px] text-zinc-500 line-clamp-3 whitespace-pre-wrap">{draft.content}</p>
          {draft.citations && draft.citations.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1">
              <span className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-zinc-600">
                Cited
                <HelpHint text="Each cited id links to a real jurisdiction requirement your company is actually subject to." />
              </span>
              {draft.citations.map((c) => (
                <span key={c} className="px-1.5 py-0.5 rounded bg-zinc-800/60 border border-zinc-700/50 text-[10px] font-mono text-zinc-400">
                  {c}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
