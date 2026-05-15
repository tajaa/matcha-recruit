import {
  IR_DIMENSION_HELP,
  type IRSyntheticAssessment,
  type IRDimension,
} from './synth'

function HelpTooltip({ text }: { text: string }) {
  return (
    <span className="relative group/help inline-flex">
      <span className="text-[8px] text-zinc-600 opacity-0 group-hover:opacity-100 transition-opacity cursor-help">?</span>
      <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 text-[10px] leading-relaxed text-zinc-300 bg-zinc-900 border border-white/10 shadow-xl opacity-0 group-hover/help:opacity-100 transition-opacity z-50">
        {text}
      </span>
    </span>
  )
}

function DimensionCard({ dim }: { dim: IRDimension }) {
  const tone = dim.flagged_locations > 0 ? 'text-orange-400' : 'text-zinc-100'
  return (
    <div className="bg-zinc-900 border border-white/10 rounded-2xl overflow-hidden">
      <div className="flex">
        <div className="w-32 shrink-0 p-5 flex flex-col items-center justify-center border-r border-white/5">
          <span className={`text-5xl font-light font-mono ${tone}`}>{dim.count}</span>
          <div className="text-[9px] text-zinc-600 uppercase tracking-widest mt-2">
            incidents
          </div>
          <div className="text-[9px] text-zinc-500 uppercase tracking-widest mt-1 font-mono">
            sev {dim.severity_avg.toFixed(1)}
          </div>
          {dim.flagged_locations > 0 && (
            <div className="text-[9px] text-orange-400 uppercase tracking-widest mt-2 font-bold">
              {dim.flagged_locations} hotspot{dim.flagged_locations === 1 ? '' : 's'}
            </div>
          )}
        </div>
        <div className="flex-1 p-5 min-w-0">
          <div className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-3 flex items-center gap-1.5">
            {dim.label}
            <HelpTooltip text={IR_DIMENSION_HELP[dim.key]} />
          </div>
          <div className="flex flex-col gap-1.5">
            {dim.factors.map((factor, i) => (
              <div key={i} className="flex items-start gap-2 text-[11px] text-zinc-400 leading-snug">
                <span className="mt-1.5 w-1 h-1 rounded-full bg-zinc-600 shrink-0" />
                {factor}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

export function IRDimensionsGrid({ assessment }: { assessment: IRSyntheticAssessment }) {
  const dims = Object.values(assessment.dimensions)
    .filter((d) => d.count > 0)
    .sort((a, b) => (b.flagged_locations - a.flagged_locations) || (b.count - a.count))

  if (dims.length === 0) {
    return null
  }

  return (
    <div>
      <h2 className="text-[10px] text-zinc-500 uppercase tracking-widest font-bold mb-4">
        Breakdown by Type
      </h2>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {dims.map((dim) => <DimensionCard key={dim.key} dim={dim} />)}
      </div>
    </div>
  )
}
