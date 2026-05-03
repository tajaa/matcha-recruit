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

type OtState = 'federal' | 'california' | 'alaska' | 'nevada' | 'colorado'

const STATE_LABELS: Record<OtState, string> = {
  federal: 'Federal (FLSA) — most states',
  california: 'California (daily + weekly)',
  alaska: 'Alaska (daily + weekly)',
  nevada: 'Nevada (daily + weekly)',
  colorado: 'Colorado (daily + weekly)',
}

function fmtUSD(n: number): string {
  if (!isFinite(n)) return '—'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
}

function fmtHrs(n: number): string {
  return n.toFixed(2) + ' hrs'
}

type DayRow = { day: string; hours: number }

const DEFAULT_DAYS: DayRow[] = [
  { day: 'Mon', hours: 8 },
  { day: 'Tue', hours: 8 },
  { day: 'Wed', hours: 8 },
  { day: 'Thu', hours: 8 },
  { day: 'Fri', hours: 8 },
  { day: 'Sat', hours: 0 },
  { day: 'Sun', hours: 0 },
]

function calcOT(days: DayRow[], rate: number, state: OtState) {
  const dailyOT = state !== 'federal'

  let regularHours = 0
  let ot15Hours = 0
  let ot2xHours = 0

  if (dailyOT) {
    for (const d of days) {
      const h = Math.max(0, d.hours)
      if (state === 'california') {
        // CA: 1.5x after 8/day, 2x after 12/day; 1.5x for first 8 on 7th day, 2x after that
        regularHours += Math.min(h, 8)
        ot15Hours += Math.max(0, Math.min(h, 12) - 8)
        ot2xHours += Math.max(0, h - 12)
      } else if (state === 'alaska' || state === 'nevada') {
        // AK/NV: 1.5x after 8/day
        regularHours += Math.min(h, 8)
        ot15Hours += Math.max(0, h - 8)
      } else if (state === 'colorado') {
        // CO: 1.5x after 12/day (daily) + weekly 40h threshold
        regularHours += Math.min(h, 12)
        ot2xHours += Math.max(0, h - 12)
      }
    }

    // Weekly OT on top (for hours that haven't already been upgraded)
    const totalWeekly = days.reduce((s, d) => s + Math.max(0, d.hours), 0)
    if (state === 'colorado') {
      // CO: 1.5x weekly OT kicks in over 40 total (on top of daily >12 which is 2x)
      const dailyUpgraded = ot2xHours
      const weeklyEligible = Math.max(0, totalWeekly - dailyUpgraded - 40)
      if (weeklyEligible > 0) {
        ot15Hours += weeklyEligible
        regularHours = Math.max(0, regularHours - weeklyEligible)
      }
    } else {
      const weeklyOTBucket = Math.max(0, totalWeekly - 40)
      const alreadyOT = ot15Hours + ot2xHours
      const addlWeeklyOT = Math.max(0, weeklyOTBucket - alreadyOT)
      if (addlWeeklyOT > 0) {
        ot15Hours += addlWeeklyOT
        regularHours = Math.max(0, regularHours - addlWeeklyOT)
      }
    }
  } else {
    // Federal: weekly threshold only
    const totalWeekly = days.reduce((s, d) => s + Math.max(0, d.hours), 0)
    regularHours = Math.min(totalWeekly, 40)
    ot15Hours = Math.max(0, totalWeekly - 40)
  }

  const regularPay = regularHours * rate
  const ot15Pay = ot15Hours * rate * 1.5
  const ot2xPay = ot2xHours * rate * 2
  const totalPay = regularPay + ot15Pay + ot2xPay
  const totalHours = days.reduce((s, d) => s + Math.max(0, d.hours), 0)

  return { regularHours, ot15Hours, ot2xHours, regularPay, ot15Pay, ot2xPay, totalPay, totalHours }
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

export default function Overtime({ embedded }: { embedded?: boolean }) {
  const [rate, setRate] = useState(25)
  const [state, setState] = useState<OtState>('federal')
  const [days, setDays] = useState<DayRow[]>(DEFAULT_DAYS)
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    document.title = 'Overtime Calculator — Matcha'
  }, [])

  const result = useMemo(() => calcOT(days, rate, state), [days, rate, state])
  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  function setDayHours(i: number, hours: number) {
    setDays(prev => prev.map((d, idx) => idx === i ? { ...d, hours: Math.max(0, hours) } : d))
  }

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: t.muted }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <Link to={`${root}/calculators`} className="hover:opacity-60">Calculators</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: t.ink }}>Overtime</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className={embedded ? "text-2xl font-semibold" : "text-4xl sm:text-5xl tracking-tight"}
            style={embedded ? { color: t.ink } : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            Overtime Calculator
          </h1>
          <p className="mt-4 text-base" style={{ color: t.muted }}>
            FLSA weekly OT plus state daily-OT rules for CA, AK, NV, and CO.
            Enter hours by day to see exactly what's owed at 1.5× and 2×.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section className="p-6 rounded-2xl" style={{ border: `1px solid ${t.line}` }}>
            <h2 className="text-xl mb-6" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
              Inputs
            </h2>
            <div className="flex flex-col gap-5">
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Regular hourly rate ($)</label>
                <input
                  type="number"
                  min={0}
                  step={0.25}
                  value={rate}
                  onChange={e => setRate(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>State OT rules</label>
                <select
                  value={state}
                  onChange={e => setState(e.target.value as OtState)}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                >
                  {(Object.keys(STATE_LABELS) as OtState[]).map(s => (
                    <option key={s} value={s}>{STATE_LABELS[s]}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-4" style={{ color: t.muted }}>Hours worked by day</label>
                <div className="grid grid-cols-7 gap-2">
                  {days.map((d, i) => (
                    <div key={d.day} className="flex flex-col items-center gap-1">
                      <span className="text-[10px]" style={{ color: t.muted }}>{d.day}</span>
                      <input
                        type="number"
                        min={0}
                        max={24}
                        step={0.5}
                        value={d.hours}
                        onChange={e => setDayHours(i, Number(e.target.value))}
                        className="w-full px-1 h-10 rounded-lg text-sm text-center outline-none"
                        style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                      />
                    </div>
                  ))}
                </div>
                <p className="text-xs mt-3" style={{ color: t.muted }}>
                  Total: <strong style={{ color: t.ink }}>{result.totalHours.toFixed(1)} hrs</strong> this week
                </p>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <ResultBox t={t} label="Total weekly pay" value={fmtUSD(result.totalPay)} large />
            <div className="grid grid-cols-1 gap-3">
              <ResultBox
                t={t}
                label={`Regular (${fmtHrs(result.regularHours)})`}
                value={fmtUSD(result.regularPay)}
                sub={`${fmtHrs(result.regularHours)} × ${fmtUSD(rate)}`}
              />
              <ResultBox
                t={t}
                label={`OT at 1.5× (${fmtHrs(result.ot15Hours)})`}
                value={fmtUSD(result.ot15Pay)}
                sub={result.ot15Hours > 0 ? `${fmtHrs(result.ot15Hours)} × ${fmtUSD(rate * 1.5)}` : 'No OT this week'}
              />
              {result.ot2xHours > 0 && (
                <ResultBox
                  t={t}
                  label={`Double-time 2× (${fmtHrs(result.ot2xHours)})`}
                  value={fmtUSD(result.ot2xPay)}
                  sub={`${fmtHrs(result.ot2xHours)} × ${fmtUSD(rate * 2)}`}
                />
              )}
            </div>
            {state !== 'federal' && (
              <p className="text-xs" style={{ color: t.muted }}>
                {state === 'california' && 'CA: 1.5× after 8 hrs/day or 40 hrs/week; 2× after 12 hrs/day or 8 hrs on 7th day.'}
                {state === 'alaska' && 'AK: 1.5× after 8 hrs/day and after 40 hrs/week.'}
                {state === 'nevada' && 'NV: 1.5× after 8 hrs/day (if hourly rate < 1.5× NV min wage) and after 40 hrs/week.'}
                {state === 'colorado' && 'CO: 1.5× after 40 hrs/week or 12 hrs/day; 2× after 12 hrs/day under state COMPS rules.'}
              </p>
            )}
            <p className="text-xs" style={{ color: t.muted }}>
              Calculations follow FLSA regular-rate rules. Bonuses, commissions, and shift differentials
              may increase the regular rate and therefore the OT rate — consult counsel for complex situations.
            </p>
          </section>
        </div>

        <section
          className="mt-16 p-8 rounded-2xl"
          style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            Stay on top of wage-and-hour compliance
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
            Matcha tracks OT thresholds, minimum wage changes, and
            pay-frequency rules for all 50 states — and alerts you when
            the rules change for your locations.
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

function ResultBox({ t, label, value, sub, large }: {
  t: ReturnType<typeof mkT>; label: string; value: string; sub?: string; large?: boolean
}) {
  return (
    <div className="p-5 rounded-xl" style={{ border: `1px solid ${t.line}` }}>
      <div className="text-xs mb-1" style={{ color: t.muted }}>{label}</div>
      <div style={{
        fontFamily: t.display, color: t.ink, fontWeight: 500,
        fontSize: large ? '2.5rem' : '1.5rem', lineHeight: 1.1,
      }}>
        {value}
      </div>
      {sub && <div className="text-xs mt-1" style={{ color: t.muted }}>{sub}</div>}
    </div>
  )
}
