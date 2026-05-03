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

function fmtUSD(n: number): string {
  if (!isFinite(n) || isNaN(n)) return '—'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
}

function pct(n: number): string {
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

// Employer payroll tax rates (2024):
// FICA Social Security: 6.2% on wages up to $168,600
// FICA Medicare: 1.45% (no wage cap)
// FUTA: 0.6% on first $7,000 (after SUTA credit)
// SUTA varies; we use a representative 2.7% average on first $10,000
const SS_RATE = 0.062
const SS_CAP = 168600
const MEDICARE_RATE = 0.0145
const FUTA_RATE = 0.006
const FUTA_CAP = 7000
const SUTA_RATE = 0.027
const SUTA_CAP = 10000

function calcTaxes(salary: number) {
  const ss = Math.min(salary, SS_CAP) * SS_RATE
  const medicare = salary * MEDICARE_RATE
  const futa = Math.min(salary, FUTA_CAP) * FUTA_RATE
  const suta = Math.min(salary, SUTA_CAP) * SUTA_RATE
  return { ss, medicare, futa, suta, total: ss + medicare + futa + suta }
}

export default function TotalComp({ embedded }: { embedded?: boolean }) {
  const [baseSalary, setBaseSalary] = useState(85000)
  const [bonusPct, setBonusPct] = useState(10)
  const [healthCost, setHealthCost] = useState(7200)
  const [dentalVision, setDentalVision] = useState(900)
  const [k401MatchPct, setK401MatchPct] = useState(4)
  const [k401MatchCap, setK401MatchCap] = useState(6)
  const [lifeInsurance, setLifeInsurance] = useState(300)
  const [otherBenefits, setOtherBenefits] = useState(0)
  const [showPricing, setShowPricing] = useState(false)

  useEffect(() => {
    document.title = 'Total Compensation Calculator — Matcha'
  }, [])

  const result = useMemo(() => {
    const bonus = baseSalary * (bonusPct / 100)
    const cashComp = baseSalary + bonus
    const k401Match = baseSalary * Math.min(k401MatchPct, k401MatchCap) / 100
    const benefitsCost = healthCost + dentalVision + k401Match + lifeInsurance + otherBenefits
    const taxes = calcTaxes(cashComp)
    const totalCostToCompany = cashComp + benefitsCost + taxes.total
    const effectiveHourlyRate = totalCostToCompany / 2080
    const benefitsPct = totalCostToCompany > 0 ? benefitsCost / totalCostToCompany : 0
    const taxesPct = totalCostToCompany > 0 ? taxes.total / totalCostToCompany : 0
    return {
      bonus, cashComp, k401Match, benefitsCost, taxes,
      totalCostToCompany, effectiveHourlyRate, benefitsPct, taxesPct,
    }
  }, [baseSalary, bonusPct, healthCost, dentalVision, k401MatchPct, k401MatchCap, lifeInsurance, otherBenefits])

  const root = embedded ? '/app/resources' : '/resources'
  const t = mkT(embedded)

  return (
    <div style={embedded ? { color: t.ink } : { backgroundColor: t.bg, color: t.ink, minHeight: '100vh' }}>
      {!embedded && <MarketingNav onPricingClick={() => setShowPricing(true)} onDemoClick={() => setShowPricing(true)} />}

      <main className={embedded ? '' : 'pt-28 pb-20 max-w-[1100px] mx-auto px-6 sm:px-10'}>
        <nav className="flex items-center gap-2 text-xs mb-8 flex-wrap" style={{ color: t.muted }}>
          <Link to={root} className="hover:opacity-60">Resources</Link>
          <ChevronRight className="w-3 h-3" />
          <Link to={`${root}/calculators`} className="hover:opacity-60">Calculators</Link>
          <ChevronRight className="w-3 h-3" />
          <span style={{ color: t.ink }}>Total Comp</span>
        </nav>

        <header className="mb-10 max-w-2xl">
          <h1
            className={embedded ? "text-2xl font-semibold" : "text-4xl sm:text-5xl tracking-tight"}
            style={embedded ? { color: t.ink } : { fontFamily: t.display, fontWeight: 500, color: t.ink }}
          >
            Total Compensation Calculator
          </h1>
          <p className="mt-4 text-base" style={{ color: t.muted }}>
            Salary + bonus + benefits + employer payroll taxes.
            See what an employee actually costs — and what they actually receive.
          </p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <section className="p-6 rounded-2xl" style={{ border: `1px solid ${t.line}` }}>
            <h2 className="text-xl mb-6" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
              Inputs
            </h2>
            <div className="flex flex-col gap-5">
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Base salary ($)</label>
                <input
                  type="number"
                  min={0}
                  step={1000}
                  value={baseSalary}
                  onChange={e => setBaseSalary(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Target annual bonus (%)</label>
                <input
                  type="number"
                  min={0}
                  max={200}
                  step={1}
                  value={bonusPct}
                  onChange={e => setBonusPct(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>

              <hr style={{ borderColor: t.line, borderTopWidth: 1 }} />
              <p className="text-xs -mt-2" style={{ color: t.muted }}>Annual employer cost per employee</p>

              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Health insurance (employer portion)</label>
                <input
                  type="number"
                  min={0}
                  step={100}
                  value={healthCost}
                  onChange={e => setHealthCost(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Dental + vision (employer portion)</label>
                <input
                  type="number"
                  min={0}
                  step={50}
                  value={dentalVision}
                  onChange={e => setDentalVision(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>401(k) match (%)</label>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <span className="text-[10px]" style={{ color: t.muted }}>Match rate</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={k401MatchPct}
                      onChange={e => setK401MatchPct(Number(e.target.value))}
                      className="w-full px-3 h-10 rounded-lg text-sm outline-none mt-1"
                      style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                    />
                  </div>
                  <div>
                    <span className="text-[10px]" style={{ color: t.muted }}>Up to (% of salary)</span>
                    <input
                      type="number"
                      min={0}
                      max={100}
                      step={0.5}
                      value={k401MatchCap}
                      onChange={e => setK401MatchCap(Number(e.target.value))}
                      className="w-full px-3 h-10 rounded-lg text-sm outline-none mt-1"
                      style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                    />
                  </div>
                </div>
                <p className="text-[10px] mt-1" style={{ color: t.muted }}>
                  Employer contributes {fmtUSD(result.k401Match)}/yr
                </p>
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Life insurance & other insured benefits</label>
                <input
                  type="number"
                  min={0}
                  step={50}
                  value={lifeInsurance}
                  onChange={e => setLifeInsurance(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
              <div>
                <label className="block text-xs mb-2" style={{ color: t.muted }}>Other benefits (stipends, wellness, etc.)</label>
                <input
                  type="number"
                  min={0}
                  step={100}
                  value={otherBenefits}
                  onChange={e => setOtherBenefits(Number(e.target.value))}
                  className="w-full px-4 h-11 rounded-lg text-sm outline-none"
                  style={{ backgroundColor: 'transparent', border: `1px solid ${t.line}`, color: t.ink }}
                />
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-4">
            <ResultBox t={t} label="Total cost to company" value={fmtUSD(result.totalCostToCompany)} large />
            <div className="grid grid-cols-2 gap-3">
              <ResultBox t={t} label="Cash comp" value={fmtUSD(result.cashComp)} sub={`Base ${fmtUSD(baseSalary)} + bonus ${fmtUSD(result.bonus)}`} />
              <ResultBox t={t} label="Effective hourly cost" value={fmtUSD(result.effectiveHourlyRate)} sub="÷ 2,080 hrs/yr" />
            </div>

            <div className="p-5 rounded-xl" style={{ border: `1px solid ${t.line}` }}>
              <div className="text-xs mb-3" style={{ color: t.muted }}>Employer benefits cost breakdown</div>
              <div className="flex flex-col gap-2">
                {[
                  { label: 'Health insurance', value: healthCost },
                  { label: 'Dental + vision', value: dentalVision },
                  { label: `401(k) match`, value: result.k401Match },
                  { label: 'Life / other insured', value: lifeInsurance },
                  { label: 'Other benefits', value: otherBenefits },
                ].filter(r => r.value > 0).map(r => (
                  <div key={r.label} className="flex justify-between text-xs">
                    <span style={{ color: t.muted }}>{r.label}</span>
                    <span style={{ color: t.ink }}>{fmtUSD(r.value)}</span>
                  </div>
                ))}
                <div className="flex justify-between text-xs pt-2" style={{ borderTop: `1px solid ${t.line}` }}>
                  <span style={{ color: t.ink }}>Benefits subtotal</span>
                  <span style={{ color: t.ink }}>{fmtUSD(result.benefitsCost)} ({pct(result.benefitsPct)})</span>
                </div>
              </div>
            </div>

            <div className="p-5 rounded-xl" style={{ border: `1px solid ${t.line}` }}>
              <div className="text-xs mb-3" style={{ color: t.muted }}>Employer payroll taxes (est.)</div>
              <div className="flex flex-col gap-2">
                {[
                  { label: 'Social Security (6.2%)', value: result.taxes.ss },
                  { label: 'Medicare (1.45%)', value: result.taxes.medicare },
                  { label: 'FUTA (0.6% on first $7k)', value: result.taxes.futa },
                  { label: 'SUTA (avg 2.7% on first $10k)', value: result.taxes.suta },
                ].map(r => (
                  <div key={r.label} className="flex justify-between text-xs">
                    <span style={{ color: t.muted }}>{r.label}</span>
                    <span style={{ color: t.ink }}>{fmtUSD(r.value)}</span>
                  </div>
                ))}
                <div className="flex justify-between text-xs pt-2" style={{ borderTop: `1px solid ${t.line}` }}>
                  <span style={{ color: t.ink }}>Payroll tax subtotal</span>
                  <span style={{ color: t.ink }}>{fmtUSD(result.taxes.total)} ({pct(result.taxesPct)})</span>
                </div>
              </div>
            </div>

            <p className="text-xs" style={{ color: t.muted }}>
              Payroll tax estimates use 2024 federal rates. SUTA rate is a national average — your state rate varies.
              Does not include workers' comp, unemployment insurance, or state-specific taxes.
            </p>
          </section>
        </div>

        <section
          className="mt-16 p-8 rounded-2xl"
          style={{ border: `1px solid ${t.line}`, backgroundColor: t.cardBg }}
        >
          <h2 className="text-2xl mb-3" style={{ fontFamily: t.display, color: t.ink, fontWeight: 500 }}>
            Track comp across your whole team
          </h2>
          <p className="text-sm mb-6 max-w-2xl" style={{ color: t.muted }}>
            Matcha gives you a compensation dashboard per employee —
            salary, benefits, payroll taxes, and equity value in one place.
            Spot gaps and run pay equity analysis across your org.
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
