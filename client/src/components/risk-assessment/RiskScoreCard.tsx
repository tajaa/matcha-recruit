import { HelpCircle } from 'lucide-react'
import {
  BAND_COLOR, BAND_LABEL, DIMENSION_ORDER, DIMENSION_LABELS, DIMENSION_HELP,
  type Band, type DimensionResult,
} from '../../types/riskAssessment'
import { HoverTip } from './InfoTip'
import { MetricStrip } from '../ui/MetricStrip'

function HelpTooltip({ text }: { text: string }) {
  // The bubble itself is portalled (see HoverTip) — the grid below is
  // `rounded-2xl overflow-hidden`, which clipped the old absolute bubble.
  return (
    <HoverTip text={text}>
      <HelpCircle className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity cursor-help" />
    </HoverTip>
  )
}

function ScoreBar({ score, band }: { score: number; band: Band }) {
  return (
    <div className="h-px w-full bg-white/10 relative overflow-hidden">
      <div
        className={`absolute inset-y-0 left-0 ${BAND_COLOR[band].bar} transition-all duration-700`}
        style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
      />
    </div>
  )
}

function BandBadge({ band }: { band: Band }) {
  const c = BAND_COLOR[band]
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${c.badge}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {BAND_LABEL[band]}
    </span>
  )
}

type Props = {
  score: number
  band: string
  dimensions: Record<string, DimensionResult>
  weights?: Record<string, number>
}

export function RiskScoreCard({ score, band, dimensions, weights }: Props) {
  const b = band as Band

  return (
    <div>
      <MetricStrip cols="grid-cols-5">
        {/* Big number */}
        <div className="col-span-2 bg-zinc-900 p-8 flex flex-col justify-between group">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold flex items-center gap-1.5">
            Overall Risk Score
            <HelpTooltip text={DIMENSION_HELP.overall} />
          </div>
          <div className="flex items-end gap-4 mt-4">
            <span className={`text-8xl font-light font-mono ${BAND_COLOR[b].text}`}>
              {score}
            </span>
            <div className="mb-2 flex flex-col gap-2">
              <BandBadge band={b} />
              <span className="text-[9px] text-zinc-600 font-mono">/100</span>
            </div>
          </div>
          <div className="mt-6">
            <ScoreBar score={score} band={b} />
          </div>
        </div>

        {/* Dimension mini-stats */}
        {DIMENSION_ORDER.map(key => {
          const dim = dimensions[key]
          if (!dim) return null
          const c = BAND_COLOR[dim.band as Band]
          const weightPct = weights?.[key] != null ? `${Math.round(weights[key] * 100)}%` : null
          return (
            <div key={key} className="bg-zinc-900 p-6 flex flex-col justify-between group">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
                {DIMENSION_LABELS[key]}
                <HelpTooltip text={DIMENSION_HELP[key]} />
              </div>
              <div className={`text-3xl font-light font-mono mt-2 ${c.text}`}>{dim.score}</div>
              <div className="mt-3 space-y-2">
                {weightPct && <div className="text-[9px] text-zinc-600 uppercase tracking-widest">{weightPct} weight</div>}
                <BandBadge band={dim.band as Band} />
              </div>
            </div>
          )
        })}
      </MetricStrip>
    </div>
  )
}
