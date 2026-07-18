/**
 * One compliance gap, rendered richly — shared by the persistent Gap Dashboard
 * (pages/admin/GapDashboard.tsx) and the onboarding wizard's gap step so they
 * look identical.
 *
 * A gap is, by definition, a requirement NOT yet in the compliance bank, so the
 * only per-gap data we have today is category + jurisdiction + why-flagged. The
 * way to FILL it is to dispatch research (Gemini researches the requirement for
 * that jurisdiction and writes it to the bank, after which it shows as covered
 * and gains rich detail). The `<Phase 2>` slot below is where AI-generated
 * "how to comply" steps will render once they exist.
 */
import { Loader2, Search, Square, CheckSquare, MapPin, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { ResolvedScopeMissing } from '../../../api/admin/adminOnboarding'

export function humanizeCategory(slug: string): string {
  return slug
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function jurisdictionLabel(m: { city?: string | null; county?: string | null; state?: string | null }): string {
  const parts = [m.city, m.county, m.state].filter(Boolean)
  return parts.length ? parts.join(', ') : 'Federal'
}

type GapCardProps = {
  gap: ResolvedScopeMissing
  selected: boolean
  onToggle: () => void
  /** Per-card "Research" action. Omit to hide the button (e.g. the wizard
   *  dispatches research in bulk by session rather than per-card). */
  onResearch?: () => void
  researching?: boolean
  disabled?: boolean
}

export default function GapCard({ gap, selected, onToggle, onResearch, researching, disabled }: GapCardProps) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className={`rounded-lg border bg-vsc-panel transition-colors ${
        selected ? 'border-vsc-accent/60' : 'border-vsc-border'
      }`}
    >
      <div className="flex items-start gap-3 p-3">
        <button
          onClick={onToggle}
          disabled={disabled}
          className="mt-0.5 shrink-0 disabled:opacity-50"
          aria-label={selected ? 'Deselect gap' : 'Select gap'}
        >
          {selected
            ? <CheckSquare className="w-4 h-4 text-vsc-accent" />
            : <Square className="w-4 h-4 text-zinc-600" />}
        </button>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-zinc-100">{humanizeCategory(gap.category_slug)}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-vsc-border uppercase tracking-wide">
              {gap.scope_level}
            </span>
            <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
              <MapPin className="w-2.5 h-2.5" /> {jurisdictionLabel(gap)}
            </span>
          </div>

          {gap.reason && (
            <p className="text-xs text-zinc-400 mt-1.5 leading-relaxed">
              <span className="text-zinc-500">Why flagged: </span>{gap.reason}
            </p>
          )}

          <button
            onClick={() => setOpen((v) => !v)}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300"
          >
            <ChevronRight className={`w-3 h-3 transition-transform ${open ? 'rotate-90' : ''}`} />
            How to fill
          </button>
          {open && (
            <div className="mt-1.5 text-[11px] text-zinc-400 leading-relaxed border-l border-vsc-border pl-3">
              Dispatch research for this requirement. Gemini researches{' '}
              <span className="text-zinc-300">{humanizeCategory(gap.category_slug)}</span> for{' '}
              <span className="text-zinc-300">{jurisdictionLabel(gap)}</span>, writes it to the
              compliance bank with its rule, current value, source, and step-by-step
              "how to comply" guidance — after which it moves to
              <span className="text-emerald-300"> Covered</span>, where the steps show in the detail.
            </div>
          )}
        </div>

        {onResearch && (
          <button
            onClick={onResearch}
            disabled={disabled || researching}
            className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-vsc-accent text-vsc-bg text-[11px] font-medium hover:opacity-90 disabled:opacity-50"
          >
            {researching ? <Loader2 className="w-3 h-3 animate-spin" /> : <Search className="w-3 h-3" />}
            Research
          </button>
        )}
      </div>
    </div>
  )
}
