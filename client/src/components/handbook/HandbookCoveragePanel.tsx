import { Card, Badge } from '../ui'
import type { HandbookCoverage } from '../../types/handbook'

type Props = {
  coverage: HandbookCoverage | null
  loading?: boolean
}

const STRENGTH_VARIANT: Record<string, 'success' | 'warning' | 'danger'> = {
  strong: 'success',
  moderate: 'warning',
  weak: 'danger',
}

export function HandbookCoveragePanel({ coverage, loading }: Props) {
  if (!coverage) {
    return (
      <Card>
        <h3 className="text-sm font-semibold text-zinc-300 mb-2">Coverage</h3>
        <p className="text-xs text-zinc-600">{loading ? 'Loading coverage...' : 'Coverage data unavailable.'}</p>
      </Card>
    )
  }

  return (
    <Card>
      <div className="flex items-center gap-3 mb-3">
        <h3 className="text-sm font-semibold text-zinc-300">Coverage</h3>
        <Badge variant={STRENGTH_VARIANT[coverage.strength_label] ?? 'neutral'}>
          {coverage.strength_score}% &mdash; {coverage.strength_label}
        </Badge>
        <span className="text-xs text-zinc-500">{coverage.industry_label}</span>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-3">
        {[
          { label: 'Core', count: coverage.core_sections },
          { label: 'State', count: coverage.state_sections },
          { label: 'Custom', count: coverage.custom_sections },
          { label: 'Uploaded', count: coverage.uploaded_sections },
        ].map(({ label, count }) => (
          <div key={label} className="text-center">
            <p className="text-lg font-semibold text-zinc-200">{count}</p>
            <p className="text-xs text-zinc-500">{label}</p>
          </div>
        ))}
      </div>

      {coverage.state_coverage.length > 0 && (
        <div className="mb-3">
          <p className="text-xs font-medium text-zinc-400 mb-1.5">State Coverage</p>
          <div className="space-y-1">
            {coverage.state_coverage.map((sc) => (
              <div key={sc.state} className="flex items-center gap-2 text-xs">
                <span className="text-zinc-300 w-6 font-medium">{sc.state}</span>
                <span className="text-zinc-500">{sc.state_name}</span>
                <Badge variant={sc.has_addendum ? 'success' : 'neutral'}>
                  {sc.has_addendum ? 'Addendum' : 'No addendum'}
                </Badge>
                {sc.missing_categories.length > 0 && (
                  <span className="text-zinc-600">{sc.missing_categories.length} missing</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {coverage.missing_sections.length > 0 && (
        <div>
          <p className="text-xs font-medium text-zinc-400 mb-1.5">Missing Sections</p>
          <div className="space-y-1">
            {coverage.missing_sections.map((ms) => (
              <div key={ms.section_key} className="flex items-center gap-2 text-xs">
                <Badge variant={ms.priority === 'required' ? 'danger' : 'warning'}>{ms.priority}</Badge>
                <span className="text-zinc-300">{ms.title}</span>
                <span className="text-zinc-600">{ms.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
