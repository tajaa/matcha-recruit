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

type Frequency = 'weekly' | 'biweekly' | 'semimonthly' | 'monthly'

const PERIODS_PER_YEAR: Record<Frequency, number> = {
  weekly: 52,
  biweekly: 26,
  semimonthly: 24,
  monthly: 12,
}

const FREQ_LABEL: Record<Frequency, string> = {
  weekly: 'Weekly (52)',
  biweekly: 'Bi-weekly (26)',
  semimonthly: 'Semi-monthly (24)',
  monthly: 'Monthly (12)',
}

function toHours(value: number, unit: 'days' | 'hours', hoursPerDay: number): number {
  return unit === 'days' ? value * hoursPerDay : value
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

export default function PtoAccrual({ embedded }: { embedded?: boolean }) {
  const [annual, setAnnual] = useState(15)
  const [unit, setUnit] = useState<'days' | 'hours'>('days')
  const [hoursPerDay, setHoursPerDay] = useState(8)
  const [hoursPerWeek, setHoursPerWeek] = useState(40)
  const [frequency, setFrequency] = useState<Frequency>('biweekly')
  const [tenureMonths, setTenureMonths] = useState(12)
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    document.title = 'PTO Accrual Calculator — Matcha'
  }, [])

  const result = useMemo(() => {
    const annualHours = toHours(annual, unit, hoursPerDay)
    const annualHoursWorked = hoursPerWeek * 52
    const accrualPerHourWorked = annualHoursWorked > 0 ? annualHours / annualHoursWorked : 0
    const accrualPerPeriod = annualHours / PERIODS_PER_YEAR[frequency]
    const monthlyAccrual = annualHours / 12
    const projectedHours = monthlyAccrual * tenureMonths
    return {
      annualHours,
      accrualPerHourWorked,
      accrualPerPeriod,
      monthlyAccrual,
      projectedHours,
      projectedDays: projectedHours / hoursPerDay,
    }
  }, [annual, unit, hoursPerDay, hoursPerWeek, frequency, tenureMonths])

  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        <nav className={`flex items-center gap-2 text-xs mb-8 flex-wrap ${embedded ? 'text-vsc-text/40' : ''}`} style={embedded ? undefined : { color: t.muted }}>
          <Link to={root} className={embedded ? 'hover:text-vsc-text/70 transition-colors' : 'hover:opacity-60'}>Resources</Link>
          <ChevronRight className={`w-3 h-3 ${embedded ? 'text-vsc-text/20' : ''}`} />
          <Link to={`${root}/calculators`} className={embedded ? 'hover:text-vsc-text/70 transition-colors' : 'hover:opacity-60'}>Calculators</Link>
          <ChevronRight className={`w-3 h-3 ${embedded ? 'text-vsc-text/20' : ''}`} />
          <span className={embedded ? 'text-vsc-text/60' : ''} style={embedded ? undefined : { color: t.ink }}>PTO Accrual</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className={embedded ? "text-2xl font-semibold text-vsc-text" : "text-4xl sm:text-5xl tracking-tight"}
            style={embedded ? undefined : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            PTO Accrual Calculator
          </h1>
          <p className={`mt-4 text-base ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
            Convert annual PTO into per-pay-period accruals, hourly rates,
            and projected balances by tenure.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section
            className={`p-6 rounded-xl ${embedded ? 'border border-vsc-border bg-vsc-panel' : 'rounded-2xl'}`}
            style={embedded ? undefined : { border: `1px solid ${t.line}` }}
          >
            <h2
              className={embedded ? 'text-base font-semibold text-vsc-text mb-5' : 'text-xl mb-6'}
              style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}
            >
              Inputs
            </h2>
            <div className="flex flex-col gap-5">
              <div>
                <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Annual PTO</label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    min={0}
                    value={annual}
                    onChange={e => setAnnual(Number(e.target.value))}
                    className={`flex-1 px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
                    style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                  />
                  <select
                    value={unit}
                    onChange={e => setUnit(e.target.value as 'days' | 'hours')}
                    className={`px-3 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
                    style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                  >
                    <option value="days">days</option>
                    <option value="hours">hours</option>
                  </select>
                </div>
              </div>
              <div>
                <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Standard hours per day</label>
                <input
                  type="number"
                  min={1}
                  max={24}
                  value={hoursPerDay}
                  onChange={e => setHoursPerDay(Number(e.target.value))}
                  className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
                  style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Hours worked per week</label>
                <input
                  type="number"
                  min={0}
                  max={80}
                  value={hoursPerWeek}
                  onChange={e => setHoursPerWeek(Number(e.target.value))}
                  className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
                  style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Pay frequency</label>
                <select
                  value={frequency}
                  onChange={e => setFrequency(e.target.value as Frequency)}
                  className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
                  style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                >
                  {(Object.keys(FREQ_LABEL) as Frequency[]).map(f => (
                    <option key={f} value={f}>{FREQ_LABEL[f]}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className={`block text-xs mb-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>Project balance after (months)</label>
                <input
                  type="number"
                  min={0}
                  max={120}
                  value={tenureMonths}
                  onChange={e => setTenureMonths(Number(e.target.value))}
                  className={`w-full px-4 h-11 rounded-lg text-sm outline-none ${embedded ? 'bg-vsc-bg border border-vsc-border text-vsc-text focus:border-vsc-text/50 transition-colors' : ''}`}
                  style={embedded ? undefined : { backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <ResultBox t={t} embedded={embedded} label="Per pay period" value={`${result.accrualPerPeriod.toFixed(2)} hrs`} sub={`${(result.accrualPerPeriod / hoursPerDay).toFixed(2)} days`} />
            <ResultBox t={t} embedded={embedded} label="Per hour worked" value={`${result.accrualPerHourWorked.toFixed(4)} hrs`} sub="multiply by hours worked in period" />
            <ResultBox t={t} embedded={embedded} label="Per month" value={`${result.monthlyAccrual.toFixed(2)} hrs`} sub={`${(result.monthlyAccrual / hoursPerDay).toFixed(2)} days`} />
            <ResultBox
              t={t}
              embedded={embedded}
              label={`Projected balance at ${tenureMonths} months`}
              value={`${result.projectedHours.toFixed(1)} hrs`}
              sub={`${result.projectedDays.toFixed(1)} days (assumes no use, no cap)`}
            />
            <p className={`text-xs mt-2 ${embedded ? 'text-vsc-text/50' : ''}`} style={embedded ? undefined : { color: t.muted }}>
              Heads-up: many states (CA, CO, MA, IL, NE, ND) treat accrued
              PTO as wages, banning use-it-or-lose-it forfeiture and
              requiring payout at separation. Caps must be reasonable.
              See your state's <Link to={`${root}/states`} className={embedded ? 'text-vsc-text underline hover:text-white' : ''} style={embedded ? undefined : { color: t.ink }}>compliance guide</Link>.
            </p>
          </section>
        </div>

        <section
          className={`mt-12 ${embedded ? 'rounded-xl border border-vsc-border bg-vsc-panel p-6' : 'mt-16 p-8 rounded-2xl'}`}
          style={embedded ? undefined : { border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <h2 className={embedded ? 'text-base font-semibold text-vsc-text mb-2' : 'text-2xl mb-3'} style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            Run accruals on autopilot
          </h2>
          <p className={embedded ? 'text-sm text-vsc-text/50 mb-5 max-w-2xl' : 'text-sm mb-6 max-w-2xl'} style={embedded ? undefined : { color: t.muted }}>
            Matcha tracks accruals per employee, per state, with
            tenure tiers, caps, carryover rules, and payout-on-separation
            built in.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              to="/auth/resources-signup"
              className={embedded
                ? 'inline-flex items-center h-9 px-4 rounded-lg text-xs font-medium bg-zinc-700 hover:bg-zinc-600 text-white transition-colors'
                : 'inline-flex items-center px-5 h-10 rounded-full text-sm font-medium'}
              style={embedded ? undefined : t.btnPrimary}
            >
              Create free account →
            </Link>
            <button
              onClick={() => setShowPricing(true)}
              className={embedded
                ? 'inline-flex items-center h-9 px-4 rounded-lg text-xs font-medium border border-vsc-border text-vsc-text/70 hover:text-vsc-text hover:border-vsc-text/40 transition-colors'
                : 'inline-flex items-center px-5 h-10 rounded-full text-sm font-medium'}
              style={embedded ? undefined : { border: `1px solid ${t.line}`, color: t.ink }}
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

function ResultBox({ t, embedded, label, value, sub }: { t: ReturnType<typeof mkT>; embedded?: boolean; label: string; value: string; sub?: string }) {
  return (
    <div
      className={`p-5 rounded-xl ${embedded ? 'border border-vsc-border bg-vsc-panel' : ''}`}
      style={embedded ? undefined : { border: `1px solid ${t.line}` }}
    >
      <div className={`text-[10px] uppercase tracking-wider mb-1 ${embedded ? 'text-vsc-text/40' : ''}`} style={embedded ? undefined : { color: t.muted }}>{label}</div>
      <div className={embedded ? 'text-3xl font-bold text-vsc-text' : 'text-2xl'} style={embedded ? undefined : { fontFamily: t.display, color: t.ink, fontWeight: 500 }}>{value}</div>
      {sub && <div className={`text-xs mt-1 ${embedded ? 'text-vsc-text/40' : ''}`} style={embedded ? undefined : { color: t.muted }}>{sub}</div>}
    </div>
  )
}
