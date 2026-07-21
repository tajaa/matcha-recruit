import { HelpCircle, AlertTriangle, MapPin, Sparkles } from 'lucide-react'
import { MetricStrip } from '../../ui/MetricStrip'
import {
  IR_DIMENSION_ORDER,
  IR_DIMENSION_LABELS,
  IR_DIMENSION_HELP,
  type IRSyntheticAssessment,
} from './synth'

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

export function IRRiskHeroCard({
  assessment,
  periodDays,
}: {
  assessment: IRSyntheticAssessment
  periodDays: number | string
}) {
  const flagged = assessment.flagged_count
  const critical = assessment.critical_themes
  return (
    <div>
      <MetricStrip cols="grid-cols-1 lg:grid-cols-7">
        {/* Big number — span 2 of 7 */}
        <div className="lg:col-span-2 bg-zinc-900 p-8 flex flex-col justify-between">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold">
            Incidents · last {periodDays} days
          </div>
          <div className="flex items-end gap-4 mt-4">
            <span className="text-8xl font-light font-mono text-zinc-100">
              {assessment.total_incidents}
            </span>
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-3 text-[11px]">
            {flagged > 0 && (
              <span className="inline-flex items-center gap-1.5 text-orange-400">
                <MapPin className="w-3 h-3" />
                {flagged} flagged hotspot{flagged === 1 ? '' : 's'}
              </span>
            )}
            {critical > 0 && (
              <span className="inline-flex items-center gap-1.5 text-red-400">
                <AlertTriangle className="w-3 h-3" />
                {critical} critical theme{critical === 1 ? '' : 's'}
              </span>
            )}
            {flagged === 0 && critical === 0 && (
              <span className="inline-flex items-center gap-1.5 text-zinc-600">
                <Sparkles className="w-3 h-3" />
                No flagged locations or critical patterns
              </span>
            )}
          </div>
        </div>

        {/* Per-incident-type counts */}
        {IR_DIMENSION_ORDER.map((key) => {
          const dim = assessment.dimensions[key]
          if (!dim) return null
          const isZero = dim.count === 0
          const numTone = isZero
            ? 'text-zinc-700'
            : dim.flagged_locations > 0
              ? 'text-orange-400'
              : 'text-zinc-200'
          return (
            <div key={key} className="bg-zinc-900 p-6 flex flex-col justify-between group">
              <div className="text-[9px] text-zinc-600 uppercase tracking-widest font-bold flex items-center gap-1.5">
                {IR_DIMENSION_LABELS[key]}
                <HelpTooltip text={IR_DIMENSION_HELP[key]} />
              </div>
              <div className={`text-3xl font-light font-mono mt-2 ${numTone}`}>{dim.count}</div>
              <div className="mt-3 space-y-1">
                {dim.count > 0 ? (
                  <>
                    <div className="text-[9px] text-zinc-600 uppercase tracking-widest">
                      avg sev {dim.severity_avg.toFixed(1)}
                    </div>
                    {dim.flagged_locations > 0 && (
                      <div className="text-[9px] text-orange-400 uppercase tracking-widest">
                        {dim.flagged_locations} hotspot{dim.flagged_locations === 1 ? '' : 's'}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-[9px] text-zinc-700 uppercase tracking-widest">none</div>
                )}
              </div>
            </div>
          )
        })}
      </MetricStrip>

      {assessment.report && (
        <p className="text-sm text-zinc-400 leading-relaxed mt-4">{assessment.report}</p>
      )}
    </div>
  )
}
