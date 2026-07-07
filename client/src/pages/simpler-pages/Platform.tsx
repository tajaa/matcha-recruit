import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView, useReducedMotion } from 'framer-motion'
import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { LazyMount } from '../landing/LazyMount'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/PricingContactModal'

const AgentReasoningAnimation = lazy(() => import('../landing/AgentReasoningAnimation'))

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'
const GREEN = '#A3C57D' // the one emphasis color — everything else stays grayscale
const GREEN_600 = '#5B7F3E' // eyebrow labels specifically

// Instrument cards run dark (black bg / cream text) inside the otherwise ivory page.
const CARD_BG = INK
const CARD_TEXT = BG
const CARD_MUTED = 'rgba(245,242,237,0.5)'
const CARD_LINE = 'rgba(245,242,237,0.14)'

// Counts a number up from 0 once its instrument scrolls into view, and again
// every time `trigger` changes (drives the looping replay).
function useCountUp(target: number, active: boolean, duration = 900, trigger = 0) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (!active) return
    let raf: number
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      setValue(Math.round(target * eased))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [active, target, duration, trigger])
  return value
}

// Ticks up once every `intervalMs` while `active` (the instrument is in
// view), so a `key={cycle}` on the animated content replays its entrance.
// Off-screen or reduced-motion, it stays put — no wasted cycles.
const CARD_LOOP_MS = 4000
function useLoopCycle(active: boolean, intervalMs = CARD_LOOP_MS) {
  const reduce = useReducedMotion()
  const [cycle, setCycle] = useState(0)
  useEffect(() => {
    if (!active || reduce) return
    const id = setInterval(() => setCycle((c) => c + 1), intervalMs)
    return () => clearInterval(id)
  }, [active, reduce, intervalMs])
  return cycle
}

// ---------------------------------------------------------------------------
// Simplified /platform — the full Matcha platform (EHS + GRC + ER unified on
// one agentic brain) told in outcome-level marketing copy only. No mechanism
// detail, no dense product dashboards — the same design language as the
// simplified /matcha-compliance page: a live hero panel, four full-width
// alternating pillar rows each with a bespoke grayscale+green instrument, a
// coverage recap grid, an editorial cut, and the monochrome newsletter band.
// ---------------------------------------------------------------------------

type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  highlight: string
}

const PILLARS: Pillar[] = [
  {
    id: 'ehs',
    number: '01',
    title: 'Safety & EHS',
    tagline: 'Every incident captured, categorized, and routed.',
    description:
      'The safety work that usually slips through the cracks — captured the moment it happens, and defensible when it matters.',
    highlight: 'The safety layer that runs itself.',
  },
  {
    id: 'grc',
    number: '02',
    title: 'Governance & Compliance',
    tagline: 'The rules that govern you, always current.',
    description:
      'Know what the law asks of you everywhere you operate — and hear about the changes before they land.',
    highlight: 'Audit-ready, without the fire drill.',
  },
  {
    id: 'er',
    number: '03',
    title: 'Employee Relations',
    tagline: 'Cases handled before they become claims.',
    description:
      'The hard people problems, handled and documented right — so a difficult conversation never turns into a lawsuit.',
    highlight: 'The hard conversations, documented right.',
  },
  {
    id: 'convergence',
    number: '04',
    title: 'One Brain',
    tagline: 'Three disciplines, one live record.',
    description:
      'Safety, compliance, and people problems inform each other in real time — one honest view of where your risk really sits.',
    highlight: 'Risk surfaces before it compounds.',
  },
]

export default function SimplePlatformPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <ThePoint />
      </main>

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hero — centered headline + CTAs over the live agent-reasoning panel.
// ---------------------------------------------------------------------------

function Hero({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 70% 80% at 50% 30%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-10 pt-28 sm:pt-36 pb-12 sm:pb-16">
        <div className="text-center max-w-3xl mx-auto">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-6 sm:mb-8"
            style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: GREEN }} />
            <span className="text-[10px] sm:text-[11px] uppercase tracking-wider font-medium">
              The full platform
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight px-2"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(2.25rem, 6vw, 5rem)',
            }}
          >
            One brain for the
            <br />
            whole <span style={{ fontStyle: 'italic' }}>risk</span> function.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Safety, compliance, and employee relations — usually three siloed
            systems. Matcha runs them on one platform where every signal talks
            to the others — so your real risk reads as a single live number, not
            twelve disconnected reports.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
            <button
              onClick={onContactClick}
              className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: INK, color: BG }}
            >
              Book a consultation
            </button>
            <Link
              to="/services"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Explore services →
            </Link>
          </div>
        </div>

        {/* Live agent-reasoning panel — the platform's signature visual */}
        <div className="hidden sm:flex mt-12 sm:mt-16 w-full overflow-hidden justify-center">
          <LazyMount
            minHeight={600}
            fallback={<div className="w-full max-w-[1060px] mx-auto rounded-xl" style={{ height: 600, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}
          >
            <Suspense fallback={<div className="w-full max-w-[1060px] mx-auto rounded-xl" style={{ height: 600, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}>
              <AgentReasoningAnimation mono />
            </Suspense>
          </LazyMount>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pillars — four full-width editorial rows (≈ two pages of scroll). Each
// pillar alternates copy / instrument sides and gets its own bespoke
// grayscale diagram, with one green mark for the node it resolves to and an
// oversized ghost numeral bleeding off the copy side. Grayscale everywhere.
// ---------------------------------------------------------------------------

function PulseDot({ size = 8 }: { size?: number }) {
  return (
    <span className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <motion.span
        className="absolute rounded-full"
        style={{ width: size, height: size, backgroundColor: GREEN }}
        animate={{ scale: [1, 2.4, 1], opacity: [0.35, 0, 0.35] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span className="relative block rounded-full" style={{ width: size, height: size, backgroundColor: GREEN }} />
    </span>
  )
}

function InstrumentFrame({ caption, foot, children }: { caption: string; foot: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: CARD_LINE, backgroundColor: CARD_BG }}>
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: CARD_MUTED }}>{caption}</span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: CARD_MUTED }}>
          <PulseDot size={5} />
          Live
        </span>
      </div>
      <div className="px-5 py-6">{children}</div>
      <div className="px-5 py-3 border-t text-[10px] font-mono uppercase tracking-[0.12em]" style={{ borderColor: CARD_LINE, color: CARD_MUTED }}>
        {foot}
      </div>
    </div>
  )
}

// 01 — incident intake, resolved to routed. No pipeline detail.
function IntakeInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const words = ['Reported.', 'Scored.', 'Routed.']
  return (
    <InstrumentFrame caption="Incident · intake" foot="Every report categorized, scored, and routed">
      <div ref={ref} className="flex flex-col items-center text-center gap-4 py-3">
        <PulseDot size={10} />
        <p key={cycle} style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.6rem', color: CARD_TEXT, lineHeight: 1.2 }}>
          {words.map((w, i) => (
            <motion.span
              key={w}
              className="inline-block mr-2"
              initial={{ opacity: 0, y: 8 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: 0.15 + i * 0.22, ease: 'easeOut' }}
            >
              {w}
            </motion.span>
          ))}
        </p>
      </div>
      <div className="mt-6 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Atlanta — Store 7</span>
        <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>In the right hands</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — compliance monitor rows, one flagged.
function ComplianceInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { j: 'A', label: 'Wage & hour rules', status: 'clear' },
    { j: 'B', label: 'Break requirements', status: 'flag' },
    { j: 'C', label: 'Leave policies', status: 'clear' },
    { j: 'D', label: 'Scheduling rules', status: 'clear' },
  ]
  return (
    <InstrumentFrame caption="Compliance · monitor" foot="Deltas flagged before they take effect">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {rows.map((r, i) => {
            const lit = r.status === 'flag'
            return (
              <motion.div
                key={r.label}
                className="flex items-center gap-3"
                initial={{ opacity: 0, x: -8 }}
                animate={inView ? { opacity: 1, x: 0 } : {}}
                transition={{ duration: 0.4, delay: i * 0.12, ease: 'easeOut' }}
              >
                <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>{r.j}</span>
                <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: lit ? CARD_TEXT : CARD_MUTED, fontWeight: lit ? 600 : 400 }}>{r.label}</span>
                {lit ? (
                  <motion.span
                    className="flex items-center gap-1.5 shrink-0"
                    initial={{ opacity: 0 }}
                    animate={inView ? { opacity: 1 } : {}}
                    transition={{ duration: 0.3, delay: i * 0.12 + 0.35 }}
                  >
                    <PulseDot size={6} />
                    <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Flagged</span>
                  </motion.span>
                ) : (
                  <span className="text-[9px] font-mono uppercase tracking-wider shrink-0" style={{ color: CARD_MUTED }}>Clear</span>
                )}
              </motion.div>
            )
          })}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — case cluster: pattern detection surfaces a repeat.
function CaseInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  // 5×3 scatter; the lit cells trace a repeat cluster, in scan order.
  const litOrder = [2, 7, 12]
  const litRank = new Map(litOrder.map((cell, i) => [cell, i]))
  return (
    <InstrumentFrame caption="Cases · pattern" foot="Repeat behavior surfaced across the record">
      <div ref={ref}>
        <div key={cycle}>
          <div className="grid grid-cols-5 gap-y-4 gap-x-3 place-items-center py-1">
            {Array.from({ length: 15 }).map((_, i) => {
              const rank = litRank.get(i)
              return rank === undefined ? (
                <motion.span
                  key={i}
                  className="block rounded-full"
                  style={{ width: 6, height: 6, backgroundColor: CARD_LINE }}
                  initial={{ opacity: 0 }}
                  animate={inView ? { opacity: 1 } : {}}
                  transition={{ duration: 0.4, delay: 0.02 * i }}
                />
              ) : (
                <motion.span
                  key={i}
                  initial={{ opacity: 0, scale: 0.4 }}
                  animate={inView ? { opacity: 1, scale: 1 } : {}}
                  transition={{ duration: 0.35, delay: 0.5 + rank * 0.3, ease: 'backOut' }}
                >
                  <PulseDot size={8} />
                </motion.span>
              )
            })}
          </div>
          <motion.div
            className="mt-5 pt-5 border-t flex items-center justify-between"
            style={{ borderColor: CARD_LINE }}
            initial={{ opacity: 0 }}
            animate={inView ? { opacity: 1 } : {}}
            transition={{ duration: 0.4, delay: 0.5 + litOrder.length * 0.3 }}
          >
            <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Pattern found</span>
            <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>A repeat, one location</span>
          </motion.div>
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 04 — domains feeding a single composite risk index.
function ConvergenceInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const riskIndex = useCountUp(72, inView, 1100, cycle)
  const domains = [
    { label: 'EHS', w: 70 },
    { label: 'GRC', w: 54 },
    { label: 'ER', w: 62 },
  ]
  return (
    <InstrumentFrame caption="Risk · composite" foot="Every domain rolled into one live index">
      <div ref={ref}>
        <div key={cycle} className="flex items-center gap-6">
          <div className="flex-1 flex flex-col gap-3">
            {domains.map((d, i) => (
              <div key={d.label} className="flex items-center gap-3">
                <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider text-right" style={{ color: CARD_MUTED }}>{d.label}</span>
                <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: CARD_LINE }}>
                  <motion.div
                    className="h-full rounded-full"
                    style={{ backgroundColor: CARD_MUTED }}
                    initial={{ width: 0 }}
                    animate={inView ? { width: `${d.w}%` } : {}}
                    transition={{ duration: 0.8, delay: i * 0.15, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              </div>
            ))}
          </div>
          <span className="text-[11px] font-mono" style={{ color: CARD_MUTED }}>→</span>
          <div className="flex flex-col items-center gap-1 shrink-0">
            <div className="flex items-baseline gap-1">
              <span className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '2.75rem', color: GREEN }}>{riskIndex}</span>
            </div>
            <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Risk index</span>
          </div>
        </div>
      </div>
    </InstrumentFrame>
  )
}

const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  ehs: IntakeInstrument,
  grc: ComplianceInstrument,
  er: CaseInstrument,
  convergence: ConvergenceInstrument,
}

function PillarRow({ pillar, index }: { pillar: Pillar; index: number }) {
  const reverse = index % 2 === 1
  const Instrument = INSTRUMENTS[pillar.id]
  return (
    <section
      id={pillar.id}
      className="relative overflow-hidden border-t py-20 sm:py-28"
      style={{ borderColor: LINE }}
    >
      <span
        className="absolute top-6 select-none pointer-events-none leading-none"
        style={{
          [reverse ? 'right' : 'left']: '-0.5rem',
          fontFamily: DISPLAY,
          fontWeight: 300,
          fontSize: 'clamp(9rem, 20vw, 20rem)',
          color: INK,
          opacity: 0.035,
        } as React.CSSProperties}
        aria-hidden
      >
        {pillar.number}
      </span>

      <div className="relative max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className={`grid md:grid-cols-2 gap-12 lg:gap-24 items-center ${reverse ? 'md:[&>*:first-child]:order-2' : ''}`}>
          <motion.div
            className="max-w-xl"
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="text-[12px] uppercase tracking-[0.2em] font-mono mb-6" style={{ color: GREEN_600 }}>
              {pillar.number} · {pillar.title}
            </div>
            <h3
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 3.4vw, 3.25rem)', lineHeight: 1.04 }}
            >
              {pillar.tagline}
            </h3>
            <p
              className="mt-6"
              style={{ fontFamily: DISPLAY, fontStyle: 'italic', fontWeight: 400, color: INK, fontSize: 'clamp(1.1rem, 1.5vw, 1.4rem)', lineHeight: 1.35 }}
            >
              <span style={{ color: MUTED, opacity: 0.55 }}>“</span>
              {pillar.highlight}
              <span style={{ color: MUTED, opacity: 0.55 }}>”</span>
            </p>
            <p className="mt-5 text-[16px] sm:text-lg max-w-md" style={{ color: MUTED, lineHeight: 1.65 }}>
              {pillar.description}
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ duration: 0.6, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            <Instrument />
          </motion.div>
        </div>
      </div>
    </section>
  )
}

function PillarsGrid() {
  return (
    <>
      <section className="pt-20 sm:pt-28 pb-2 border-t" style={{ borderColor: LINE }}>
        <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
          <div className="max-w-xl">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              What it unifies
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              Three disciplines, one platform.
            </h2>
          </div>
        </div>
      </section>

      {PILLARS.map((pillar, i) => (
        <PillarRow key={pillar.id} pillar={pillar} index={i} />
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// The point — a hard editorial cut before the close.
// ---------------------------------------------------------------------------

function ThePoint() {
  return (
    <section className="py-24 sm:py-36 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10">
        <span className="text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: MUTED }}>
          The point
        </span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, lineHeight: 1.08, fontSize: 'clamp(2rem, 5vw, 4.25rem)' }}
        >
          We don’t hand you another dashboard. We run the whole risk and people
          function — safety, compliance, and the <span style={{ fontStyle: 'italic' }}>human</span> calls
          — on one brain.
        </p>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Closing CTA band
// ---------------------------------------------------------------------------

function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-2xl mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
        >
          See the whole platform.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us where you operate and how your team is structured. We’ll walk
          you through the rest.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onContactClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            Book a consultation
          </button>
        </div>
      </div>
    </section>
  )
}
