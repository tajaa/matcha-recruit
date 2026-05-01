import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import { ShieldAlert, FileText, MapPin, Calculator, Bell, Loader2 } from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { MatchaLiteMockup } from '../../components/landing/MatchaLiteMockup'
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
      'Behavior + safety tracking with AI summaries, witness statements, photo evidence, and trend analysis across locations. Built for SMBs that need a defensible record without a heavy compliance team.',
    visual: IncidentBars,
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
      <MarketingNav onPricingClick={() => setIsPricingOpen(true)} onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onWaitlistClick={scrollToWaitlist} />

      <main>
        <FeatureGrid />
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
            Incident reporting plus a full HR resource library — state
            guides, calculators, templates, and a compliance audit.
            Bundled for small teams that don't need a bespoke engagement.
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
            Incident reporting + resources, in one bundle.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Each tool stands on its own. Together they cover the everyday
            HR risk surface for a small team without a dedicated compliance
            function.
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

function WaitlistSection({ waitlistRef }: { waitlistRef: React.RefObject<HTMLDivElement> }) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [companyName, setCompanyName] = useState('')
  const [headcount, setHeadcount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
            <p className="mt-3 text-sm" style={{ color: MUTED }}>
              Already have a broker referral link?{' '}
              <Link to="/auth/lite-signup" className="underline" style={{ color: INK }}>
                Use it here →
              </Link>
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
