import { Badge } from '../ui'
import { BAND_BADGE, DIMENSION_LABELS, fmtMoney, capitalize } from '../../types/risk-assessment'
import type { DimensionResult } from '../../types/risk-assessment'

type Props = {
  dimensions: Record<string, DimensionResult>
}

export function RiskDimensionsGrid({ dimensions }: Props) {
  return (
    <div>
      <h2 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
        Dimensions
      </h2>
      <div className="grid gap-3 grid-cols-5">
        {Object.entries(dimensions).map(([key, dim]) => {
          const costOfRisk = (dim.raw_data?.cost_of_risk as Record<string, unknown> | undefined)?.total
          return (
            <div key={key} className="border border-zinc-800 rounded-xl p-4">
              <p className="text-xs text-zinc-500 uppercase tracking-wide mb-1">
                {DIMENSION_LABELS[key] ?? key}
              </p>
              <p className="text-2xl font-bold text-zinc-100 mb-1">{dim.score}</p>
              <Badge variant={BAND_BADGE[dim.band] ?? 'neutral'} className="mb-2">
                {capitalize(dim.band)}
              </Badge>
              {dim.factors.slice(0, 2).length > 0 && (
                <ul className="mt-2 space-y-1">
                  {dim.factors.slice(0, 2).map((f, i) => (
                    <li key={i} className="text-[11px] text-zinc-500 leading-snug">
                      • {f}
                    </li>
                  ))}
                </ul>
              )}
              {typeof costOfRisk === 'number' && costOfRisk > 0 && (
                <p className="mt-2 text-[11px] text-zinc-500">
                  Est. cost: {fmtMoney(costOfRisk)}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
