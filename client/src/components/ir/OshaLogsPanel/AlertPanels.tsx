import { AlertTriangle } from 'lucide-react'
import { Button } from '../../ui'
import { missingLabel } from './constants'
import type { ItaProblem, Summary300A } from './types'

// Generic "the fetch failed" banner — distinct in color/wording from the
// amber advisory panels below (those are "review this", this is "we
// couldn't load your data"), with an optional retry action.
export function LoadErrorBanner({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="bg-red-500/[0.06] border border-red-500/20 rounded-lg p-4 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2 text-red-300 text-sm">
        <AlertTriangle size={15} className="shrink-0" />
        {message}
      </div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  )
}

// ITA validation errors
export function ItaValidationErrors({ itaProblems }: { itaProblems: ItaProblem[] | null }) {
  if (itaProblems === null) return null
  return (
    <div className="bg-amber-500/[0.06] border border-amber-500/20 rounded-lg p-4">
      <div className="flex items-center gap-2 text-amber-300 text-sm font-semibold">
        <AlertTriangle size={15} />
        {itaProblems.length === 0
          ? 'ITA export failed — check establishment data and retry.'
          : itaProblems.every((p) => p.missing.includes('unassigned_location'))
            ? 'Review before filing — these incidents are excluded from the export:'
            : 'Cannot export ITA file — fill these establishment fields first:'}
      </div>
      {itaProblems.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {itaProblems.map((p) => (
            <li key={p.location_id ?? 'unassigned'} className="text-[12px] text-amber-200/90">
              <span className="font-medium">{p.establishment_name || 'Unnamed location'}</span>
              {' — missing '}
              {p.missing.map((m) => missingLabel[m] ?? m).join(', ')}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// 300A data-quality warnings — recordables missing a classification or a
// location won't foot / file correctly. Non-blocking.
export function DataQualityWarnings({ summary }: { summary: Summary300A | null }) {
  if (!summary || !summary.data_quality_warnings || summary.data_quality_warnings.length === 0) {
    return null
  }
  return (
    <div className="bg-amber-500/[0.06] border border-amber-500/20 rounded-lg p-4">
      <div className="flex items-center gap-2 text-amber-300 text-sm font-semibold">
        <AlertTriangle size={15} />
        Data quality — review before filing
      </div>
      <ul className="mt-3 space-y-1.5">
        {summary.data_quality_warnings.map((w, i) => (
          <li key={i} className="text-[12px] text-amber-200/90">{w}</li>
        ))}
      </ul>
    </div>
  )
}
