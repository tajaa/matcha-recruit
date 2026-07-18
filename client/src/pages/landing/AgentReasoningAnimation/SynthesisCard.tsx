import { SYNTHESIS } from './data'
import type { Palette } from './types'

export function SynthesisCard({ p }: { p: Palette }) {
  return (
    <div
      className="rounded-lg px-6 py-5"
      style={{
        backgroundColor: 'rgba(24,26,24,0.92)',
        backdropFilter: 'blur(8px)',
        border: `1px solid ${p.emerald}28`,
        boxShadow: `0 0 18px ${p.emerald}12`,
      }}
    >
      <div className="flex items-baseline gap-2 mb-3">
        <span
          className="font-mono text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: p.emerald }}
        >
          Draft remediation plan · for your review
        </span>
        <span className="font-mono text-[8.5px]" style={{ color: '#6a737d' }}>
          5 steps sequenced · draft
        </span>
      </div>

      <div className="grid grid-cols-4 gap-3">
        <SynthesisStat label="Timeline" value={SYNTHESIS.timeline} accent={p.live} />
        <SynthesisStat label="Internal labor" value={SYNTHESIS.laborHours} accent="#cbd5e1" />
        <SynthesisStat label="Cost" value={SYNTHESIS.cost} accent="#cbd5e1" />
        <SynthesisStat label="Exposure avoided" value={SYNTHESIS.exposureAvoided} accent={p.live} large />
      </div>

      <div className="mt-3 pt-3 border-t flex items-center gap-3" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span className="font-mono text-[8.5px]" style={{ color: '#6a737d' }}>Sources</span>
        <span className="font-mono text-[9px]" style={{ color: '#9a8a70' }}>
          CA Lab §6401.9 · Cal/OSHA enforcement guidance
        </span>
      </div>
    </div>
  )
}

function SynthesisStat({ label, value, accent, large = false }: { label: string; value: string; accent: string; large?: boolean }) {
  return (
    <div>
      <div className="font-mono text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>
        {label}
      </div>
      <div
        className={`font-mono font-semibold tabular-nums ${large ? 'text-[18px]' : 'text-[14px]'}`}
        style={{ color: accent, marginTop: 2 }}
      >
        {value}
      </div>
    </div>
  )
}
