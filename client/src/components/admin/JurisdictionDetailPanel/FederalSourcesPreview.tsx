import type { FederalSourcePreview } from '../../../types/adminJurisdiction'
import { AdminButton } from '../AdminUI'
import { getCategoryLabel } from './helpers'

function previewField(item: unknown, key: string): string | undefined {
  if (item === null || typeof item !== 'object') return undefined
  const value: unknown = Reflect.get(item, key)
  return typeof value === 'string' ? value : undefined
}

type Props = {
  fedPreview: FederalSourcePreview
  fedApplying: boolean
  setFedPreview: (v: FederalSourcePreview | null) => void
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
          <AdminButton onClick={() => setFedPreview(null)}
           variant="secondary">
            Dismiss
          </AdminButton>
          <AdminButton onClick={applyFedSources} disabled={fedApplying}
            className="text-amber-400 disabled:opacity-30" variant="ghost">
            {fedApplying ? 'Applying...' : `Apply ${fedPreview.total}`}
          </AdminButton>
        </div>
      </div>
      <div className="max-h-64 overflow-y-auto space-y-2">
        {Object.entries(fedPreview.by_category).sort(([a], [b]) => a.localeCompare(b)).map(([cat, items]) => (
          <div key={cat}>
            <p className="text-[10px] font-medium text-zinc-300 uppercase tracking-wider mb-0.5">
              {getCategoryLabel(cat)} <span className="text-zinc-600">({items.length})</span>
            </p>
            {items.map((item, i) => (
              <div key={i} className="ml-2 mb-1">
                <p className="text-[11px] text-zinc-300 leading-4">
                  {previewField(item, 'title')}
                  {previewField(item, 'source_url') && (
                    <a href={previewField(item, 'source_url')} target="_blank" rel="noreferrer"
                      className="ml-1 text-amber-500/60 hover:text-amber-400 text-[10px]">↗</a>
                  )}
                </p>
                {previewField(item, 'description') && (
                  <p className="text-[10px] text-zinc-600 leading-3.5 mt-0.5">{previewField(item, 'description')}</p>
                )}
                <p className="text-[10px] text-zinc-600">
                  {previewField(item, 'source_name')}{previewField(item, 'effective_date') ? ` · ${previewField(item, 'effective_date')}` : ''}
                </p>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
