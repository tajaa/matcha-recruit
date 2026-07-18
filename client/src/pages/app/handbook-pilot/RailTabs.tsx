import { useState } from 'react'
import type { ContextPreview, CoverageEntry } from '../../../api/handbook-pilot/handbookPilot'
import RequirementsPanel from './RequirementsPanel'

// --------------------------------------------------------------------------- //
// RailTabs — the requirements gap list (what's left to draft) and the grounding
// corpus preview (what the pilot is reading), tabbed. Drafts stays pinned above
// both: it's the surface the user acts on after every turn.
// --------------------------------------------------------------------------- //

export function RailTabs({ sessionId, refreshKey, context, onDraft }: {
  sessionId: string
  refreshKey: number
  context: ContextPreview | null
  onDraft: (req: CoverageEntry) => void
}) {
  const [tab, setTab] = useState<'requirements' | 'grounding'>('requirements')
  return (
    <div className="flex flex-col gap-2">
      <div className="inline-flex items-center gap-1 self-start rounded-lg border border-zinc-800 bg-zinc-950/40 p-0.5">
        {([['requirements', 'Requirements'], ['grounding', 'Grounding']] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-2.5 py-1 text-[11px] rounded-md ${
              tab === k ? 'bg-zinc-800 text-emerald-400' : 'text-zinc-500 hover:text-zinc-300'}`}>
            {label}
          </button>
        ))}
      </div>
      {tab === 'requirements'
        ? <RequirementsPanel sessionId={sessionId} refreshKey={refreshKey} onDraft={onDraft} />
        : <ContextPanel context={context} />}
    </div>
  )
}

// --------------------------------------------------------------------------- //
// ContextPanel — grounding corpus preview.
// --------------------------------------------------------------------------- //

function ContextPanel({ context }: { context: ContextPreview | null }) {
  if (!context) return null
  return (
    <div className="border border-zinc-800 rounded-xl bg-zinc-950/40">
      <div className="px-3 py-2.5 border-b border-zinc-800">
        <span className="text-sm font-semibold text-zinc-200">Grounding</span>
        <span className="text-xs text-zinc-500 ml-2">{context.total} records</span>
      </div>
      <div className="p-3 space-y-1.5">
        {Object.entries(context.sources).map(([k, s]) => (
          <div key={k} className="flex items-center justify-between text-xs">
            <span className="text-zinc-400">{s.label}</span>
            <span className="text-zinc-500">{s.count}</span>
          </div>
        ))}
        {context.notes.map((n, i) => (
          <p key={i} className="text-[11px] text-amber-400/70 pt-1">{n}</p>
        ))}
      </div>
    </div>
  )
}
