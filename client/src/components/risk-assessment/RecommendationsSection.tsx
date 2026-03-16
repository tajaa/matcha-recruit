import { Badge } from '../ui'
import { PRIORITY_BADGE, DIMENSION_LABELS, capitalize } from '../../types/risk-assessment'
import type { Recommendation } from '../../types/risk-assessment'

type Props = {
  recommendations: Recommendation[]
}

export function RecommendationsSection({ recommendations }: Props) {
  if (recommendations.length === 0) return null

  return (
    <div>
      <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
        Recommendations
      </h2>
      <div className="border border-zinc-800 rounded-xl divide-y divide-zinc-800/60">
        {recommendations.map((rec, i) => (
          <div key={i} className="px-4 py-3">
            <div className="flex items-center gap-2 mb-1">
              <Badge variant={PRIORITY_BADGE[rec.priority] ?? 'neutral'}>
                {capitalize(rec.priority)}
              </Badge>
              <span className="text-xs text-zinc-500">
                {DIMENSION_LABELS[rec.dimension] ?? rec.dimension}
              </span>
            </div>
            <p className="text-sm font-medium text-zinc-200">{rec.title}</p>
            <p className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{rec.guidance}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
