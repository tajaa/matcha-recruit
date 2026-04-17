import { useEffect, useState } from 'react'
import { Info, ChevronDown, ChevronUp, X } from 'lucide-react'

const STORAGE_KEY = 'retention_explainer_dismissed_v1'

/**
 * Inline explainer for the Wage Gap + Flight Risk widgets.
 * Dismissible — preference persists in localStorage. A small "What is this?"
 * link surfaces it again after dismissal.
 */
export function RetentionExplainer() {
  const [open, setOpen] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    setDismissed(localStorage.getItem(STORAGE_KEY) === '1')
  }, [])

  const dismiss = () => {
    localStorage.setItem(STORAGE_KEY, '1')
    setDismissed(true)
    setOpen(false)
  }

  const reopen = () => {
    localStorage.removeItem(STORAGE_KEY)
    setDismissed(false)
    setOpen(true)
  }

  if (dismissed && !open) {
    return (
      <button
        onClick={reopen}
        className="mt-4 inline-flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        <Info className="h-3 w-3" />
        How do these widgets work?
      </button>
    )
  }

  return (
    <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/40 overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-zinc-900/60 transition-colors"
      >
        <div className="flex items-center gap-2.5">
          <Info className="h-4 w-4 text-zinc-400" />
          <span className="text-sm font-medium text-zinc-200">
            How retention widgets work
          </span>
          <span className="text-[10px] uppercase tracking-wider px-1.5 py-[1px] rounded bg-zinc-800 text-zinc-400">
            QSR retention plan §3.1 + §3.3
          </span>
        </div>
        {open ? (
          <ChevronUp className="h-4 w-4 text-zinc-500" />
        ) : (
          <ChevronDown className="h-4 w-4 text-zinc-500" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 text-sm text-zinc-400 space-y-5 border-t border-zinc-800">
          <Section
            title="Wage Gap vs. Market"
            tagline="Are you paying competitively for the local market?"
          >
            <p>
              Compares each hourly employee&apos;s pay rate against{' '}
              <strong className="text-zinc-300">BLS OEWS percentile wages</strong>{' '}
              (median = p50) for their job class (SOC code) and metro area. Three-tier
              fallback: metro → state → national.
            </p>
            <p>
              An employee is <strong className="text-amber-400">below market</strong>{' '}
              when their pay is ≥10% under the local p50. The widget surfaces:
            </p>
            <ul className="list-disc ml-5 space-y-0.5 text-zinc-400">
              <li><strong className="text-zinc-300">$/hr to close gap</strong> — combined raises across roster</li>
              <li><strong className="text-zinc-300">Annual cost to lift</strong> — $/hr × 2,080 hrs/employee</li>
              <li><strong className="text-zinc-300">Max exposure</strong> — upper bound assuming every below-market employee quits at $5,864 fully-loaded replacement cost (Restroworks 2024)</li>
            </ul>
            <p className="text-xs text-zinc-500">
              Drill-down: name, current rate, target rate (p25 + p50), $/hr raise needed,
              annualized cost, flight-risk tier. CSV export ready for payroll.
            </p>
          </Section>

          <Section
            title="Flight Risk"
            tagline="Who's likely to leave in the next 30-180 days?"
          >
            <p>
              Composite score 0-100 per active employee, summing six signals
              (max contribution per signal in parens):
            </p>
            <ul className="list-disc ml-5 space-y-0.5 text-zinc-400">
              <li><strong className="text-zinc-300">Wage gap (30)</strong> — % below local p50 from the wage benchmark</li>
              <li><strong className="text-zinc-300">Tenure (20)</strong> — quit-curve multiplier; QSR turnover concentrates in the 30-180 day window</li>
              <li><strong className="text-zinc-300">ER case (15)</strong> — employee relations cases involving the employee, open or recently closed</li>
              <li><strong className="text-zinc-300">IR incident (10)</strong> — safety/behavioral incidents in the last 90 days</li>
              <li><strong className="text-zinc-300">Cohort (15)</strong> — tenure-band risk concentration vs. company average</li>
              <li><strong className="text-zinc-300">Manager (10)</strong> — annualized turnover under the same manager</li>
            </ul>
            <p>
              <strong className="text-zinc-300">Tiers</strong>: Low (0-39) · Elevated (40-59) ·{' '}
              <strong className="text-amber-400">High (60-79)</strong> ·{' '}
              <strong className="text-red-400">Critical (80-100)</strong>. The widget headlines
              high+critical count and the upper-bound expected loss
              (count × $5,864 replacement cost).
            </p>
            <p className="text-xs text-zinc-500">
              Drill-down: per-employee score, top driver, expandable factor breakdown
              with a one-line narrative for each (e.g. &quot;$1.20/hr below market p50 in Denver metro&quot;).
            </p>
          </Section>

          <Section title="What these don't include yet">
            <p className="text-zinc-400">
              Pulse-survey sentiment (§4.1), schedule volatility (§3.2), 1:1 cadence (§4.2),
              and exit-interview themes (§5.4) are upstream features still pending. Score is
              honest about what it knows — adding signals later is additive.
            </p>
          </Section>

          <div className="flex items-center justify-between pt-2 border-t border-zinc-800">
            <button
              onClick={dismiss}
              className="inline-flex items-center gap-1.5 text-[11px] text-zinc-500 hover:text-zinc-300"
            >
              <X className="h-3 w-3" />
              Dismiss (you can reopen this later)
            </button>
            <span className="text-[10px] text-zinc-600">
              Sources: BLS OEWS · Restroworks 2024 · QSR_RETENTION_PLAN.md
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function Section({
  title,
  tagline,
  children,
}: {
  title: string
  tagline?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <h4 className="text-sm font-semibold text-zinc-100">{title}</h4>
      {tagline && <p className="text-xs text-zinc-500 mt-0.5 mb-2">{tagline}</p>}
      <div className="space-y-2 text-sm">{children}</div>
    </div>
  )
}
