import type { JobWeights } from '../../api/matchaWork/jobSearch'

const ROWS: [keyof JobWeights, string][] = [
  ['base', 'Base salary'],
  ['bonus', 'Bonus'],
  ['equity', 'Equity'],
  ['fit', 'Fit with what I asked'],
]

/** The four ranking weights, shared by the new-search form and the re-rank popover. */
export default function WeightSliders({ weights, onChange }: { weights: JobWeights; onChange: (w: JobWeights) => void }) {
  return (
    <div className="space-y-1.5">
      {ROWS.map(([key, label]) => (
        <label key={key} className="flex items-center gap-3 text-xs text-w-text">
          <span className="w-36 shrink-0">{label}</span>
          <input
            type="range"
            min={0}
            max={100}
            step={1}
            value={Math.round(weights[key] * 100)}
            onChange={(e) => onChange({ ...weights, [key]: Number(e.target.value) / 100 })}
            className="min-w-0 flex-1 accent-[var(--color-w-accent)]"
            aria-label={label}
          />
          <span className="w-7 shrink-0 text-right font-mono text-[11px] text-w-dim">{Math.round(weights[key] * 100)}</span>
        </label>
      ))}
    </div>
  )
}
