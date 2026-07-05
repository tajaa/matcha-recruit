import { useState } from 'react'
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import type { ContextPreview } from '../../../api/brokerPilot'
import { SOURCE_LABEL } from './shared'

interface ContextPanelProps {
  context: ContextPreview | null
  onRefresh: () => void
}

export function ContextPanel({ context, onRefresh }: ContextPanelProps) {
  const [open, setOpen] = useState<Record<string, boolean>>({})

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs uppercase tracking-wide text-zinc-500">Grounding scope</h3>
        <button
          onClick={onRefresh}
          className="p-1 text-zinc-500 hover:text-zinc-200 transition-colors"
          title="Refresh"
        >
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      {!context ? (
        <p className="text-xs text-zinc-600">Scope unavailable.</p>
      ) : (
        <div className="space-y-2">
          {Object.entries(context.sources).map(([key, source]) => (
            <div key={key}>
              <button
                onClick={() => setOpen((prev) => ({ ...prev, [key]: !prev[key] }))}
                className="w-full flex items-center gap-1.5 text-left"
              >
                {open[key]
                  ? <ChevronDown className="h-3 w-3 text-zinc-600" />
                  : <ChevronRight className="h-3 w-3 text-zinc-600" />}
                <span className="text-xs text-zinc-300">{SOURCE_LABEL[key] ?? source.label}</span>
                <span className="text-[10px] text-zinc-600 ml-auto">{source.records.length}</span>
              </button>
              {open[key] && (
                <ul className="mt-1 ml-4 space-y-1">
                  {source.records.length === 0 && (
                    <li className="text-[11px] text-zinc-600">Nothing on file.</li>
                  )}
                  {source.records.map((r) => (
                    <li key={r.cid} className="text-[11px] text-zinc-500">
                      {r.ref && <span className="text-zinc-400">{r.ref}: </span>}
                      {r.summary}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
          {context.notes.length > 0 && (
            <ul className="pt-1 border-t border-zinc-800 space-y-0.5">
              {context.notes.map((n, i) => (
                <li key={i} className="text-[11px] text-zinc-600">{n}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
