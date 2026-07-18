import { Loader2 } from 'lucide-react'
import type { DemoDatasetKey } from '../../../api/analysis-pilot/analysisPilot'
import type { AnalysisExample } from './shared'

// --------------------------------------------------------------------------- //
// ExamplesTab — browsable example prompts. Click to prefill the chat composer.
// --------------------------------------------------------------------------- //

export function ExamplesTab({ items, onUse, loadingKey }: {
  items: AnalysisExample[]; onUse: (item: AnalysisExample) => void; loadingKey: DemoDatasetKey | null
}) {
  return (
    <div className="p-4">
      <p className="text-sm text-zinc-500 mb-3">
        These use a small bundled sample dataset — clicking one opens (or reuses) a dedicated demo
        session and asks the question for real, so your own analyses stay untouched.
      </p>
      <div className="space-y-1.5">
        {items.map((item) => {
          const loading = loadingKey === item.key
          return (
            <button key={item.key}
              onClick={() => onUse(item)}
              disabled={loadingKey !== null}
              className="block w-full text-left rounded-lg px-3 py-2.5 transition-colors hover:bg-zinc-800/60 disabled:cursor-wait disabled:opacity-60"
            >
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-zinc-500">
                {item.label} <span className="text-zinc-700">·</span> {item.shape}
                {loading && <Loader2 className="h-3 w-3 animate-spin text-emerald-400" />}
              </div>
              <div className="text-[13px] text-zinc-300 mt-0.5">{item.question}</div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
