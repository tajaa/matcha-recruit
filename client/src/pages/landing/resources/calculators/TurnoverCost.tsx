import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import MarketingNav from '../../MarketingNav'
import MarketingFooter from '../../MarketingFooter'
import { PricingContactModal } from '../../../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

// Replacement cost multipliers from SHRM / Work Institute / CAP research.
// Front-line: 30-50% of salary. Mid-level: 100-150%. Highly skilled: 200%+.
type RoleTier = 'frontline' | 'mid' | 'senior' | 'executive'

const TIER_MULTIPLIER: Record<RoleTier, number> = {
  frontline: 0.4,
  mid: 1.25,
  senior: 1.75,
  executive: 2.13,
}

const TIER_LABEL: Record<RoleTier, string> = {
  frontline: 'Front-line / hourly (30–50%)',
  mid: 'Mid-level / professional (100–150%)',
  senior: 'Senior / specialized (150–200%)',
  executive: 'Executive (200%+)',
}

function fmtUSD(n: number): string {
  if (!isFinite(n)) return '—'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function fmtPct(n: number): string {
  return `${(n * 100).toFixed(1)}%`
}

function mkT(embedded?: boolean) {
  return embedded ? {
    ink: '#e4e4e7', bg: 'transparent', muted: '#71717a',
    line: '#3f3f46', display: 'inherit',
    cardBg: '#18181b',
    btnPrimary: { backgroundColor: '#15803d', color: '#fff' } as React.CSSProperties,
  } : {
    ink: INK, bg: BG, muted: MUTED,
    line: LINE, display: DISPLAY,
    cardBg: 'rgba(15,15,15,0.03)',
    btnPrimary: { backgroundColor: INK, color: BG } as React.CSSProperties,
  }
}

export default function TurnoverCost({ embedded }: { embedded?: boolean }) {
  const [headcount, setHeadcount] = useState(100)
  const [annualLeavers, setAnnualLeavers] = useState(15)
  const [avgSalary, setAvgSalary] = useState(65000)
  const [tier, setTier] = useState<RoleTier>('mid')
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    document.title = 'Turnover Cost Calculator — Matcha'
  }, [])

  const result = useMemo(() => {
    const multiplier = TIER_MULTIPLIER[tier]
    const replacementCostPerLeaver = avgSalary * multiplier
    const annualCost = replacementCostPerLeaver * annualLeavers
    const monthlyCost = annualCost / 12
    const turnoverRate = headcount > 0 ? annualLeavers / headcount : 0
    return {
      multiplier,
      replacementCostPerLeaver,
      annualCost,
      monthlyCost,
      turnoverRate,
    }
  }, [headcount, annualLeavers, avgSalary, tier])

  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? 'pt-0 pb-8 max-w-[1100px]' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: t.muted }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <Link to={`${root}/calculators`} className="hover:opacity-60">Calculators</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: t.ink }}>Turnover Cost</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className="text-4xl sm:text-5xl tracking-tight"
            style={{ fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            Turnover Cost Calculator
          </h1>
          <p className="mt-4 text-base" style={{ color: t.muted }}>
            Estimate what voluntary turnover is costing you. Multipliers
            based on SHRM and Work Institute research — covers recruiting,
            onboarding, lost productivity, and ramp time.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section
            className="p-6 rounded-2xl"
            style={{ border: `1px solid ${t.line}` }}
          >
            <h2
              className="text-xl mb-6"
              style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}
            >
              Inputs
            </h2>
            <div className="flex flex-col gap-5">
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Total headcount</label>
                <input
                  type="number"
                  min={0}
                  value={headcount}
                  onChange={e => setHeadcount(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Voluntary leavers per year</label>
                <input
                  type="number"
                  min={0}
                  value={annualLeavers}
                  onChange={e => setAnnualLeavers(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Average salary</label>
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={avgSalary}
                  onChange={e => setAvgSalary(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Role tier (replacement cost multiplier)</label>
                <select
                  value={tier}
                  onChange={e => setTier(e.target.value as RoleTier)}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                >
                  {(Object.keys(TIER_LABEL) as RoleTier[]).map(t => (
                    <option key={t} value={t}>{TIER_LABEL[t]}</option>
                  ))}
                </select>
                <p className="text-xs mt-2" style={{ color: t.muted }}>
                  Range based on SHRM, Work Institute, and Center for American Progress meta-analyses.
                </p>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <ResultBox t={t} label="Annual turnover cost" value={fmtUSD(result.annualCost)} sub={`${fmtUSD(result.monthlyCost)}/month`} large />
            <div className="grid grid-cols-2 gap-4">
              <ResultBox t={t} label="Per-leaver cost" value={fmtUSD(result.replacementCostPerLeaver)} sub={`${(result.multiplier * 100).toFixed(0)}% of salary`} />
              <ResultBox t={t} label="Turnover rate" value={fmtPct(result.turnoverRate)} sub="leavers ÷ headcount" />
            </div>
            <div
              className="p-5 rounded-xl text-sm"
              style={{ border: `1px solid ${t.line}`, color: t.muted }}
            >
              Replacement cost typically includes:
              <ul className="list-disc pl-5 mt-2 flex flex-col gap-1">
                <li>Recruiting (job ads, agency fees, internal time)</li>
                <li>Lost productivity during vacancy</li>
                <li>Onboarding & training (3–6 months to full ramp)</li>
                <li>Knowledge transfer + project disruption</li>
              </ul>
            </div>
          </section>
        </div>

        <section
          className="mt-16 p-8 rounded-2xl"
          style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            Reduce turnover with better people ops
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
            Matcha runs eNPS, vibe checks, exit-interview analytics, and
            stay-interview workflows so you spot retention risk before it
            walks out the door.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/auth/resources-signup"
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={t.btnPrimary}
            >
              Create free account →
            </Link>
            <button
              onClick={() => setShowPricing(true)}
              className="inline-flex items-center px-5 h-10 rounded-full text-sm font-medium"
              style={{ border: `1px solid ${t.line}`, color: t.ink }}
            >
              Talk to sales
            </button>
          </div>
        </section>
      </main>

      {!embedded && <MarketingFooter />}
      <PricingContactModal isOpen={showPricing} onClose={() => setShowPricing(false)} />
    </div>
  )
}

function ResultBox({ t, label, value, sub, large }: { t: ReturnType<typeof mkT>; label: string; value: string; sub?: string; large?: boolean }) {
  return (
    <div
      className="p-5 rounded-xl"
      style={{ border: `1px solid ${t.line}` }}
    >
      <div className="text-xs mb-1" style={{ color: t.muted }}>{label}</div>
      <div
        style={{
          fontFamily: t.display,
          color: t.ink,
          fontWeight: 500,
          fontSize: large ? '2.5rem' : '1.5rem',
          lineHeight: 1.1,
        }}
      >
        {value}
      </div>
      {sub && <div className="text-xs mt-2" style={{ color: t.muted }}>{sub}</div>}
    </div>
  )
}
