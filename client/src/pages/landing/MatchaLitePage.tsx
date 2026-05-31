import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import { ShieldAlert, FileText, MapPin, Calculator, Bell, Loader2, Brain, ClipboardList } from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { MatchaLiteMockup } from '../../components/landing/MatchaLiteMockup'
import { IrAnalysisPanel } from '../../components/landing/IrAnalysisPanel'
import { PricingContactModal } from '../../components/PricingContactModal'
import { api } from '../../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const FEATURES: { id: string; icon: typeof ShieldAlert; title: string; caption: string; visual: React.ComponentType }[] = [
  {
    id: 'incidents',
    icon: ShieldAlert,
    title: 'Incident reporting',
    caption:
      'Workplace and field safety intake — photo evidence, witness capture, and an anonymous reporting channel. Every incident logged with a defensible chain of custody, no compliance team required.',
    visual: IncidentBars,
  },
  {
    id: 'ir_analysis',
    icon: Brain,
    title: 'IR analysis',
    caption:
      'Intelligent Theme Analysis flags suggested categorization and severity on every incident. Cross-incident pattern detection surfaces repeat behaviors and emerging risk clusters for your team to review.',
    visual: SeverityGauge,
  },
  {
    id: 'osha',
    icon: ClipboardList,
    title: 'OSHA 300 / 300A logs',
    caption:
      'Recordable incident tracking tied to your intake flow. Tallies auto-populate — print or export an audit-ready 300A summary any time.',
    visual: LogRows,
  },
  {
    id: 'resources',
    icon: FileText,
    title: 'HR resource hub',
    caption:
      'Editable templates (offer letters, PIPs, terminations, severance) and 50+ job descriptions across industries.',
    visual: TemplateStack,
  },
  {
    id: 'states',
    icon: MapPin,
    title: 'State-by-state guides',
    caption:
      'Pay transparency, leave laws, sick time, and termination rules for all 50 states + DC. Updated as legislation changes — flag the deltas before they hit you.',
    visual: StateDots,
  },
  {
    id: 'calculators',
    icon: Calculator,
    title: 'HR calculators',
    caption:
      'PTO accrual, turnover cost, overtime, and total comp. Quick math, no login, results emailable. The numbers your CFO asks for in the all-hands.',
    visual: NumberTicker,
  },
  {
    id: 'audit',
    icon: Bell,
    title: 'Compliance audit',
    caption:
      '12-question self-audit covering posters, handbooks, I-9s, classification, leave, harassment, lactation, and pay transparency. Gap report delivered to your inbox.',
    visual: ChecklistCascade,
  },
]

export default function MatchaLitePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const waitlistRef = useRef<HTMLDivElement>(null)

  function scrollToWaitlist() {
    waitlistRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onWaitlistClick={scrollToWaitlist} />

      <main>
        <FeatureGrid />
        <IrAnalysisSection />
        <OshaSection />
        <WaitlistSection waitlistRef={waitlistRef} />
      </main>

      <MarketingFooter />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero({ onWaitlistClick }: { onWaitlistClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 100%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-10 pt-28 sm:pt-36 pb-12 sm:pb-16">
        <div className="text-center max-w-3xl mx-auto">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6 sm:mb-8"
            style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#86efac' }} />
            <span className="text-[10px] sm:text-[11px] uppercase tracking-wider font-medium">
              Self-serve HR risk + compliance
            </span>
            <span
              className="text-[9px] uppercase tracking-wider font-medium px-1.5 py-[1px] rounded ml-1"
              style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}
            >
              Coming Soon
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight px-2"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(2.25rem, 7vw, 5.25rem)',
            }}
          >
            Matcha Lite.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-[15px] sm:text-base px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Incident reporting, intelligent analysis, and OSHA 300 logs — plus a
            full HR library with state guides, calculators, templates, and
            a compliance audit. Bundled for small teams that don't need a
            bespoke engagement.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
            <button
              onClick={onWaitlistClick}
              className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: INK, color: BG }}
            >
              Join the waitlist
            </button>
            <Link
              to="/resources"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Browse free resources →
            </Link>
          </div>
        </div>

        {/* Product mockup inside dark frame — mirrors MatchaWorkPage hero */}
        <div className="mt-12 sm:mt-16 max-w-6xl mx-auto -mx-2 sm:mx-auto">
          <div
            className="relative rounded-lg sm:rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{
              boxShadow: '0 40px 80px -25px rgba(31, 29, 26, 0.3)',
              borderColor: 'rgba(0,0,0,0.08)',
            }}
          >
            <MatchaLiteMockup />
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Feature grid
// ---------------------------------------------------------------------------

function FeatureGrid() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div
            className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4"
            style={{ color: MUTED }}
          >
            What's in the bundle
          </div>
          <h2
            className="tracking-tight"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(1.875rem, 5vw, 3.25rem)',
              lineHeight: 1.05,
            }}
          >
            Safety intake, intelligent analysis, OSHA logs — and a full HR library.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Each tool stands on its own. Together they cover the everyday
            HR risk surface for a small team without a dedicated compliance
            function — plus a 20-minute handbook consult with a Matcha
            Professional to turn your audit results into action.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
          {FEATURES.map((f, i) => {
            const Icon = f.icon
            const Visual = f.visual
            return (
              <motion.div
                key={f.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.5, delay: i * 0.08, ease: 'easeOut' }}
                className="p-6 sm:p-8 flex flex-col"
                style={{ backgroundColor: BG }}
              >
                <div className="flex items-start justify-between mb-5">
                  <div
                    className="w-10 h-10 rounded-lg flex items-center justify-center"
                    style={{ backgroundColor: 'rgba(31,29,26,0.06)' }}
                  >
                    <Icon className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  <div className="h-10 flex items-center">
                    <Visual />
                  </div>
                </div>
                <h3
                  className="text-lg sm:text-xl mb-2"
                  style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}
                >
                  {f.title}
                </h3>
                <p className="text-sm" style={{ color: MUTED, lineHeight: 1.6 }}>
                  {f.caption}
                </p>
              </motion.div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Waitlist
// ---------------------------------------------------------------------------

function WaitlistSection({ waitlistRef }: { waitlistRef: React.RefObject<HTMLDivElement | null> }) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [honeypot, setHoneypot] = useState('')

  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!valid || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      const hc = parseInt(headcount, 10)
      await api.post('/resources/waitlist/lite', {
        email: email.trim(),
        name: name.trim() || undefined,
        company_name: companyName.trim() || undefined,
        headcount: !isNaN(hc) && hc > 0 ? hc : undefined,
        website: honeypot,
      })
      setSubmitted(true)
    } catch (err: any) {
      setError(err?.message ?? 'Something went wrong. Try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section ref={waitlistRef} className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1100px] mx-auto px-5 sm:px-10">
        <div className="grid md:grid-cols-2 gap-10 md:gap-16 items-start">
          <div>
            <h2
              className="tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(1.75rem, 4vw, 2.75rem)',
                lineHeight: 1.1,
              }}
            >
              Join the Matcha Lite waitlist.
            </h2>
            <p className="mt-4 text-base" style={{ color: MUTED, lineHeight: 1.6 }}>
              Lite is rolling out to broker partners first. Drop your details
              and we'll reach out as soon as a slot opens.
            </p>
          </div>

          {submitted ? (
            <div
              className="p-8 rounded-2xl"
              style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(31,29,26,0.03)' }}
            >
              <h3 className="text-xl mb-2" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
                You're on the list.
              </h3>
              <p className="text-sm" style={{ color: MUTED }}>
                We'll email you the moment Lite opens up. Thanks for the interest.
              </p>
            </div>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="p-6 sm:p-8 rounded-2xl flex flex-col gap-4"
              style={{ border: `1px solid ${LINE}`, backgroundColor: 'rgba(31,29,26,0.03)' }}
            >
              <input type="text" name="website" tabIndex={-1} autoComplete="off"
                aria-hidden="true" value={honeypot} onChange={e => setHoneypot(e.target.value)}
                style={{position:'absolute',left:'-9999px',width:1,height:1,opacity:0}} />
              <Field label="Work email *" type="email" value={email} onChange={setEmail} required />
              <Field label="Your name" value={name} onChange={setName} />
              <Field label="Company name" value={companyName} onChange={setCompanyName} />
              <Field label="Headcount" type="number" value={headcount} onChange={setHeadcount} />

              {error && <p className="text-sm" style={{ color: '#c1543a' }}>{error}</p>}

              <button
                type="submit"
                disabled={!valid || submitting}
                className="inline-flex items-center justify-center gap-2 px-5 h-11 rounded-full text-sm font-medium transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: INK, color: BG }}
              >
                {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {submitting ? 'Submitting…' : 'Notify me'}
              </button>
              <p className="text-xs" style={{ color: MUTED }}>
                We won't share your email. One announcement when Lite opens, that's it.
              </p>
            </form>
          )}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// IR Analysis section
// ---------------------------------------------------------------------------

const IR_BULLETS = [
  { label: 'Suggested categorization', desc: 'Behavioral, safety, property, or harassment — flagged for manager review on submission.' },
  { label: 'Severity scoring', desc: 'Low / Medium / High with justification attached to every incident — reviewed and confirmed by your team.' },
  { label: 'Pattern detection', desc: 'Cross-incident analysis surfaces recurring patterns across locations, shifts, and case types — for your team to review.' },
]

function IrAnalysisSection() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div>
            <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
              Risk Insights
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 4vw, 3rem)', lineHeight: 1.05 }}
            >
              Pattern analysis that surfaces what your team needs to see.
            </h2>
            <p className="mt-4 text-base" style={{ color: MUTED, lineHeight: 1.6 }}>
              Cross-incident pattern detection surfaces what no single manager would catch — repeat locations, shift clusters, escalating severity trends.
            </p>
            <ul className="mt-7 space-y-5">
              {IR_BULLETS.map(item => (
                <li key={item.label} className="flex gap-3">
                  <div className="w-1.5 h-1.5 rounded-full mt-[7px] shrink-0" style={{ backgroundColor: INK }} />
                  <div>
                    <span className="text-sm font-medium" style={{ color: INK }}>{item.label}</span>
                    <p className="text-sm mt-0.5" style={{ color: MUTED, lineHeight: 1.55 }}>{item.desc}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          <IrAnalysisPanel />
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// OSHA 300 section
// ---------------------------------------------------------------------------

const OSHA_ROWS = [
  { date: 'May 12', loc: 'Atlanta — Store 7', type: 'Strain/sprain', days: 3, recordable: true },
  { date: 'Apr 28', loc: 'Phoenix — Warehouse', type: 'Laceration', days: 1, recordable: true },
  { date: 'Mar 31', loc: 'Seattle — Store 12', type: 'Eye irritation', days: 2, recordable: true },
  { date: 'Mar 15', loc: 'Denver — HQ', type: 'Slip/fall', days: 0, recordable: false },
]

const OSHA_BULLETS = [
  { label: 'Recordable / non-recordable', desc: 'Classification tied to your incident intake — no duplicate data entry.' },
  { label: 'Days away and restricted', desc: 'Track days away from work and restricted duty automatically from each incident.' },
  { label: 'Audit-ready export', desc: '300A summary auto-tallied. Export PDF for Feb 1 posting or any OSHA audit.' },
]

function OshaSection() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div className="order-2 lg:order-1">
            <OshaLogPanel />
          </div>
          <div className="order-1 lg:order-2">
            <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
              OSHA 300 / 300A
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 4vw, 3rem)', lineHeight: 1.05 }}
            >
              OSHA logs, auto-filled.
            </h2>
            <p className="mt-4 text-base" style={{ color: MUTED, lineHeight: 1.6 }}>
              Every recordable flows from intake to log. No manual re-entry, no spreadsheet — print or export an audit-ready 300A summary any time of year.
            </p>
            <ul className="mt-7 space-y-5">
              {OSHA_BULLETS.map(item => (
                <li key={item.label} className="flex gap-3">
                  <div className="w-1.5 h-1.5 rounded-full mt-[7px] shrink-0" style={{ backgroundColor: INK }} />
                  <div>
                    <span className="text-sm font-medium" style={{ color: INK }}>{item.label}</span>
                    <p className="text-sm mt-0.5" style={{ color: MUTED, lineHeight: 1.55 }}>{item.desc}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  )
}

function OshaLogPanel() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  return (
    <div ref={ref} className="rounded-xl overflow-x-auto border font-sans" style={{ borderColor: 'rgba(63,63,70,0.5)', backgroundColor: '#09090b' }}>
    <div className="min-w-[400px]">
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)', backgroundColor: 'rgba(24,24,27,0.3)' }}>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold" style={{ color: '#e4e4e7' }}>OSHA 300 Log</span>
          <span className="px-1.5 py-0.5 rounded text-[9px] font-medium" style={{ backgroundColor: 'rgba(16,185,129,0.15)', color: '#6ee7b7', border: '1px solid rgba(16,185,129,0.25)' }}>IR</span>
        </div>
        <div className="px-2.5 py-1 rounded text-[9px] font-medium" style={{ backgroundColor: '#27272a', border: '1px solid #3f3f46', color: '#d4d4d8' }}>
          Export 300A
        </div>
      </div>
      <div className="flex items-center gap-4 px-5 py-2 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <span className="text-[9px]" style={{ color: '#52525b' }}>Recordables YTD: <span style={{ color: '#e4e4e7' }}>3</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span className="text-[9px]" style={{ color: '#52525b' }}>Days away: <span style={{ color: '#e4e4e7' }}>6</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span className="text-[9px]" style={{ color: '#10b981' }}>Auto-tallied</span>
      </div>
      <div className="grid px-5 py-2" style={{ gridTemplateColumns: '72px 1fr 100px 48px 60px', backgroundColor: 'rgba(39,39,42,0.4)' }}>
        {['Date', 'Location', 'Type', 'Days', 'Rec.'].map(h => (
          <span key={h} className="text-[9px] font-bold uppercase tracking-wider" style={{ color: '#52525b' }}>{h}</span>
        ))}
      </div>
      {OSHA_ROWS.map((row, i) => (
        <motion.div
          key={row.date + row.loc}
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : { opacity: 0 }}
          transition={{ delay: i * 0.1 + 0.2 }}
          className="grid px-5 py-2.5 border-t"
          style={{ gridTemplateColumns: '72px 1fr 100px 48px 60px', borderColor: 'rgba(39,39,42,0.6)', backgroundColor: 'rgba(24,24,27,0.2)' }}
        >
          <span className="text-[10px]" style={{ color: '#71717a' }}>{row.date}</span>
          <span className="text-[10px] truncate pr-2" style={{ color: '#d4d4d8' }}>{row.loc}</span>
          <span className="text-[10px]" style={{ color: '#a1a1aa' }}>{row.type}</span>
          <span className="text-[10px]" style={{ color: '#a1a1aa' }}>{row.days}d</span>
          <span className="text-[9px] font-medium" style={{ color: row.recordable ? '#fbbf24' : '#52525b' }}>
            {row.recordable ? '● Yes' : '○ No'}
          </span>
        </motion.div>
      ))}
      <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: 'rgba(39,39,42,0.5)', backgroundColor: 'rgba(24,24,27,0.2)' }}>
        <span className="text-[10px]" style={{ color: '#71717a' }}>300A summary ready for Feb 1 posting</span>
        <span className="text-[9px] font-medium" style={{ color: '#34d399', backgroundColor: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)', padding: '2px 8px', borderRadius: 4 }}>
          Export PDF
        </span>
      </div>
    </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function Field({
  label, value, onChange, type = 'text', required,
}: {
  label: string; value: string; onChange: (v: string) => void; type?: string; required?: boolean
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs uppercase tracking-wider" style={{ color: MUTED }}>{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="px-3 h-10 rounded-lg text-sm outline-none"
        style={{ backgroundColor: 'transparent', border: `1px solid ${LINE}`, color: INK }}
      />
    </label>
  )
}

// ---------------------------------------------------------------------------
// Per-card mini animations — looped while the card is in view, idle otherwise.
// ---------------------------------------------------------------------------

function useInViewRef() {
  const ref = useRef<HTMLDivElement>(null)
  const inView = useInView(ref, { margin: '-40px' })
  return { ref, inView }
}

function IncidentBars() {
  const { ref, inView } = useInViewRef()
  const heights = [0.4, 0.85, 0.55, 0.95, 0.3, 0.7]
  return (
    <div ref={ref} className="flex items-end gap-[3px] h-8">
      {heights.map((h, i) => (
        <motion.div
          key={i}
          initial={{ height: 4 }}
          animate={inView ? { height: [4, h * 28, 4] } : { height: 4 }}
          transition={{
            duration: 1.6, repeat: Infinity, repeatType: 'loop',
            delay: i * 0.12, ease: 'easeInOut',
          }}
          className="w-[5px] rounded-sm"
          style={{ backgroundColor: i === 3 ? '#ce9178' : i === 1 ? '#d7ba7d' : '#c1c1bb' }}
        />
      ))}
    </div>
  )
}

function TemplateStack() {
  const { ref, inView } = useInViewRef()
  return (
    <div ref={ref} className="relative w-12 h-9">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ x: 0, y: 0, opacity: 0.4 }}
          animate={inView ? { x: i * 4, y: -i * 3, opacity: 0.45 + i * 0.2 } : {}}
          transition={{ duration: 0.6, delay: i * 0.15, ease: 'easeOut' }}
          className="absolute inset-0 rounded-sm"
          style={{
            border: `1px solid ${LINE}`,
            backgroundColor: BG,
          }}
        >
          <div className="px-1.5 pt-1.5 flex flex-col gap-[3px]">
            <div className="h-[2px] w-6 rounded-full" style={{ backgroundColor: 'rgba(31,29,26,0.25)' }} />
            <div className="h-[2px] w-4 rounded-full" style={{ backgroundColor: 'rgba(31,29,26,0.15)' }} />
            <div className="h-[2px] w-5 rounded-full" style={{ backgroundColor: 'rgba(31,29,26,0.15)' }} />
          </div>
        </motion.div>
      ))}
    </div>
  )
}

function StateDots() {
  const { ref, inView } = useInViewRef()
  // Approximate US silhouette with a 6x4 dot grid; brighten different cells over time.
  const cells = Array.from({ length: 24 }, (_, i) => i)
  return (
    <div ref={ref} className="grid grid-cols-6 gap-[3px]">
      {cells.map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.18 }}
          animate={inView ? { opacity: [0.18, 0.85, 0.18] } : { opacity: 0.18 }}
          transition={{
            duration: 2.4, repeat: Infinity, ease: 'easeInOut',
            delay: ((i * 1.7) % 6) * 0.18,
          }}
          className="w-[5px] h-[5px] rounded-full"
          style={{ backgroundColor: INK }}
        />
      ))}
    </div>
  )
}

function NumberTicker() {
  const { ref, inView } = useInViewRef()
  const [val, setVal] = useState(0)
  useEffect(() => {
    if (!inView) return
    let raf = 0
    const start = performance.now()
    const target = 12480
    const tick = () => {
      const t = Math.min(1, (performance.now() - start) / 1400)
      const eased = 1 - Math.pow(1 - t, 3)
      setVal(Math.round(eased * target))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [inView])
  return (
    <div ref={ref} className="flex items-baseline gap-1">
      <span className="text-[9px]" style={{ color: MUTED }}>$</span>
      <span style={{ fontFamily: DISPLAY, fontSize: '1.1rem', fontWeight: 500, color: INK }}>
        {val.toLocaleString()}
      </span>
    </div>
  )
}

function SeverityGauge() {
  const { ref, inView } = useInViewRef()
  const levels = [
    { color: '#86efac' },
    { color: '#d7ba7d' },
    { color: '#ce9178' },
  ]
  return (
    <div ref={ref} className="flex flex-col gap-1">
      {levels.map((l, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.25 }}
          animate={inView ? { opacity: [0.25, 1, 0.25] } : { opacity: 0.25 }}
          transition={{ duration: 2, repeat: Infinity, delay: i * 0.55, ease: 'easeInOut' }}
          className="flex items-center gap-1.5"
        >
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: l.color }} />
          <div className="h-[2px] rounded-full" style={{ width: `${12 + i * 8}px`, backgroundColor: 'rgba(31,29,26,0.2)' }} />
        </motion.div>
      ))}
    </div>
  )
}

function LogRows() {
  const { ref, inView } = useInViewRef()
  return (
    <div ref={ref} className="flex flex-col gap-[4px]">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.2 }}
          animate={inView ? { opacity: [0.2, 0.85, 0.2] } : { opacity: 0.2 }}
          transition={{ duration: 2.2, repeat: Infinity, delay: i * 0.4, ease: 'easeInOut' }}
          className="flex gap-[4px]"
        >
          <div className="h-[3px] rounded-full w-[10px]" style={{ backgroundColor: 'rgba(31,29,26,0.4)' }} />
          <div className="h-[3px] rounded-full w-[28px]" style={{ backgroundColor: 'rgba(31,29,26,0.18)' }} />
          <div className="h-[3px] rounded-full w-[18px]" style={{ backgroundColor: 'rgba(31,29,26,0.18)' }} />
        </motion.div>
      ))}
    </div>
  )
}

function ChecklistCascade() {
  const { ref, inView } = useInViewRef()
  return (
    <div ref={ref} className="flex flex-col gap-1">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.3 }}
          animate={inView ? { opacity: [0.3, 1, 1] } : { opacity: 0.3 }}
          transition={{
            duration: 2.4, repeat: Infinity,
            delay: i * 0.4, ease: 'easeOut', times: [0, 0.4, 1],
          }}
          className="flex items-center gap-1.5"
        >
          <div
            className="w-2.5 h-2.5 rounded-sm flex items-center justify-center"
            style={{ border: `1px solid ${INK}`, backgroundColor: INK }}
          >
            <svg width="6" height="6" viewBox="0 0 8 8" fill="none">
              <path d="M1 4l2 2 4-4" stroke={BG} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="h-[2px] w-6 rounded-full" style={{ backgroundColor: 'rgba(31,29,26,0.2)' }} />
        </motion.div>
      ))}
    </div>
  )
}
