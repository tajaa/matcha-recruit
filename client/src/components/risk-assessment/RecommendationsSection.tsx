import { PRIORITY_COLOR, DIMENSION_LABELS } from '../../types/risk-assessment'
import type { Recommendation } from '../../types/risk-assessment'

type Props = {
  recommendations: Recommendation[]
  report?: string
}

export function RecommendationsSection({ recommendations, report }: Props) {
  if (!report && recommendations.length === 0) return null

  return (
    <div>
      <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">
        Consultation Analysis
      </h2>

      {report && (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 mb-4">
          <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-line">{report}</div>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="bg-zinc-900 border border-white/10 rounded-2xl divide-y divide-white/10 overflow-hidden">
          {recommendations.map((rec, i) => (
            <div key={i} className="px-6 py-5 flex items-start gap-4">
              <span className={`shrink-0 inline-flex items-center px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${PRIORITY_COLOR[rec.priority]?.badge ?? ''}`}>
                {rec.priority}
              </span>
              <div className="flex flex-col gap-2 min-w-0">
                <span className="text-[10px] text-zinc-600 uppercase tracking-widest font-bold">
                  {DIMENSION_LABELS[rec.dimension] ?? rec.dimension}
                </span>
                <span className="text-sm text-zinc-200 font-medium leading-snug">{rec.title}</span>
                <span className="text-sm text-zinc-400 leading-relaxed">{rec.guidance}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
