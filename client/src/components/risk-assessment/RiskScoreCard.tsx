import { Badge } from '../ui'
import { BAND_BADGE, capitalize } from '../../types/risk-assessment'

type Props = {
  score: number
  band: string
  report?: string
}

export function RiskScoreCard({ score, band, report }: Props) {
  return (
    <div className="border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center gap-4 mb-3">
        <span className="text-5xl font-bold text-zinc-100">{score}</span>
        <div>
          <span className="text-sm text-zinc-500">/ 100</span>
          <div className="mt-1">
            <Badge variant={BAND_BADGE[band] ?? 'neutral'}>
              {capitalize(band)} Risk
            </Badge>
          </div>
        </div>
      </div>
      {report && (
        <p className="text-sm text-zinc-400 leading-relaxed">{report}</p>
      )}
    </div>
  )
}
