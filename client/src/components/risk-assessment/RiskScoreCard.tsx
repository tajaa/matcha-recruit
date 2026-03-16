import { HelpCircle } from 'lucide-react'
import {
  BAND_COLOR, BAND_LABEL, DIMENSION_ORDER, DIMENSION_LABELS, DIMENSION_HELP,
  type Band, type DimensionResult,
} from '../../types/risk-assessment'

function HelpTooltip({ text }: { text: string }) {
  return (
    <span className="relative group/help inline-flex">
      <HelpCircle className="w-3 h-3 text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity cursor-help" />
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 text-[10px] leading-relaxed text-zinc-300 bg-zinc-900 border border-white/10 shadow-xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
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
  report?: string
  dimensions: Record<string, DimensionResult>
  weights?: Record<string, number>
}

export function RiskScoreCard({ score, band, report, dimensions, weights }: Props) {
  const b = band as Band

  return (
    <div>
      <div className="grid grid-cols-5 gap-px bg-white/10 border border-white/10 rounded-2xl overflow-hidden">
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
      </div>

      {/* Timestamp removed — shown in parent header */}
      {report && (
        <p className="text-sm text-zinc-400 leading-relaxed mt-4">{report}</p>
      )}
    </div>
  )
}
