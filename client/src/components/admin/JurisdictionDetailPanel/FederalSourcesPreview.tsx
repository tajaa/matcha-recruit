import { getCategoryLabel } from './helpers'

type FedPreview = { results: any[]; by_category: Record<string, any[]>; total: number }

type Props = {
  fedPreview: FedPreview
  fedApplying: boolean
  setFedPreview: (v: FedPreview | null) => void
  applyFedSources: () => void
}

export default function FederalSourcesPreview({ fedPreview, fedApplying, setFedPreview, applyFedSources }: Props) {
  return (
    <div className="border border-amber-500/30 rounded-lg px-3 py-2.5 mb-3 bg-amber-500/5">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[11px] font-medium text-amber-400">
          {fedPreview.total} results from government APIs · {Object.keys(fedPreview.by_category).length} categories
        </p>
        <div className="flex gap-1.5">
          <button onClick={() => setFedPreview(null)}
            className="px-2 py-1 text-[11px] text-zinc-400 border border-zinc-700 rounded hover:bg-zinc-800 transition-colors">
            Dismiss
          </button>
          <button onClick={applyFedSources} disabled={fedApplying}
            className="px-2 py-1 text-[11px] font-medium text-amber-400 border border-amber-500/40 rounded hover:bg-amber-500/10 disabled:opacity-30 transition-colors">
            {fedApplying ? 'Applying...' : `Apply ${fedPreview.total}`}
          </button>
        </div>
      </div>
      <div className="max-h-64 overflow-y-auto space-y-2">
        {Object.entries(fedPreview.by_category).sort(([a], [b]) => a.localeCompare(b)).map(([cat, items]) => (
          <div key={cat}>
            <p className="text-[10px] font-medium text-zinc-300 uppercase tracking-wider mb-0.5">
              {getCategoryLabel(cat)} <span className="text-zinc-600">({items.length})</span>
            </p>
            {items.map((item: any, i: number) => (
              <div key={i} className="ml-2 mb-1">
                <p className="text-[11px] text-zinc-300 leading-4">
                  {item.title}
                  {item.source_url && (
                    <a href={item.source_url} target="_blank" rel="noreferrer"
                      className="ml-1 text-amber-500/60 hover:text-amber-400 text-[10px]">↗</a>
                  )}
                </p>
                {item.description && (
                  <p className="text-[10px] text-zinc-600 leading-3.5 mt-0.5">{item.description}</p>
                )}
                <p className="text-[10px] text-zinc-600">
                  {item.source_name}{item.effective_date ? ` · ${item.effective_date}` : ''}
                </p>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
