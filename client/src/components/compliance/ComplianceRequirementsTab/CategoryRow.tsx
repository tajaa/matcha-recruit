import type { ComplianceRequirement } from '../../../types/compliance'
import { CATEGORY_LABELS } from '../../../types/compliance'
import { RequirementRow } from './RequirementRow'
import type { CategoryRowShared } from './types'

type Props = CategoryRowShared & {
  cat: string
  reqs: ComplianceRequirement[]
  keyPrefix?: string
}

// One category accordion row — the single renderer for every view (topic,
// jurisdiction, lite preview). `keyPrefix` namespaces the expansion key: the
// same category appears under several authorities in the jurisdiction lens,
// and an unprefixed key would open all of them at once.
export function CategoryRow({
  cat,
  reqs,
  keyPrefix = '',
  expanded,
  toggle,
  missingCoverage,
  knownAuthorities,
  highlightId,
  readOnly,
  onPin,
}: Props) {
  const key = `${keyPrefix}${cat}`
  return (
    <div key={key} className="border-b border-white/[0.06] last:border-0">
      <button type="button" onClick={() => toggle(key)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-white/[0.02] transition-colors">
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium text-zinc-200 uppercase tracking-wide">
            {CATEGORY_LABELS[cat] || cat}
          </span>
          <span className="text-[11px] text-zinc-600">{reqs.length} active</span>
          {missingCoverage.has(cat) && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-400 border border-amber-800/40">Missing Coverage</span>
          )}
        </div>
        <span className="text-xs text-zinc-600">{expanded.has(key) ? '−' : '+'}</span>
      </button>
      {expanded.has(key) && (
        <div className="divide-y divide-white/[0.04]">
          {reqs.length === 0 ? (
            <p className="px-4 py-4 text-xs text-zinc-600">
              {missingCoverage.has(cat)
                ? 'Coverage pending. Run a compliance check or admin refresh.'
                : 'No active requirements detected yet.'}
            </p>
          ) : (
            reqs.map((req) => (
              <RequirementRow
                key={req.id}
                req={req}
                knownAuthorities={knownAuthorities}
                highlightId={highlightId}
                readOnly={readOnly}
                onPin={onPin}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}
