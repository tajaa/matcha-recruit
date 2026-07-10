import { useEffect, useRef, useState } from 'react'
import { motion, useInView, useReducedMotion } from 'framer-motion'
import { useSEO } from '../../hooks/useSEO'
import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'
const GREEN = '#A3C57D' // the one emphasis color — everything else grayscale
const GREEN_600 = '#5B7F3E' // eyebrow labels

// Pillar instrument cards run dark (black bg / cream text) inside the otherwise
// ivory page — same instrument grammar as /brokers.
const CARD_BG = INK
const CARD_TEXT = BG
const CARD_MUTED = 'rgba(245,242,237,0.5)'
const CARD_LINE = 'rgba(245,242,237,0.14)'

// Ticks up once every `intervalMs` while `active` (the instrument is in view),
// so a `key={cycle}` on the animated content replays its entrance.
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
// /risk-analysis — the business-facing risk story. Where /brokers is the
// book-wide view a P&C broker gets, this is what the employer itself sees:
// one composite risk index, the controls it can prove, and the coverage gaps
// it can close before renewal. Reuses the simpler-pages design language:
// dark-card instruments on an ivory page, grayscale + a single green accent.
// ---------------------------------------------------------------------------

const RISK_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Service',
  name: 'Matcha Risk Analysis',
  url: 'https://hey-matcha.com/risk-analysis',
  description:
    'A live risk profile for your business — a composite risk index across workers’ comp, employment practices, and compliance, a proof-of-controls register underwriters recognize, and a limit-adequacy engine that finds your coverage gaps before renewal.',
  serviceType: 'Enterprise risk management software',
}

// ── Hero instrument — the composite risk index gauge ───────────────────────

type Band = { label: string; value: number; weight: string }

const INDEX_COMPONENTS: Band[] = [
  { label: 'Workers’ comp', value: 74, weight: '40%' },
  { label: 'Employment practices', value: 61, weight: '35%' },
  { label: 'Compliance', value: 82, weight: '25%' },
]
const COMPOSITE_SCORE = 71 // weighted roll-up, illustrative

function RiskIndexCard() {
  const ref = useRef(null)
  const inView = useInView(ref, { amount: 0.3 })
  const reduce = useReducedMotion()

  return (
    <div
      ref={ref}
      className="relative rounded-xl overflow-hidden border"
      style={{
        borderColor: 'rgba(0,0,0,0.08)',
        backgroundColor: '#0e0d0b',
        boxShadow: '0 40px 80px -20px rgba(31, 29, 26, 0.28)',
      }}
    >
      <div
        className="px-5 sm:px-6 py-4 flex items-center justify-between border-b"
        style={{ borderColor: 'rgba(255,255,255,0.06)' }}
      >
        <div className="flex items-center gap-2.5">
          <span className="relative flex w-2 h-2">
            <motion.span
              className="absolute inline-flex w-full h-full rounded-full"
              style={{ backgroundColor: GREEN }}
              animate={inView && !reduce ? { opacity: [0.6, 0, 0.6], scale: [1, 2.4, 1] } : { opacity: 0.6 }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
            />
            <span className="relative inline-flex w-2 h-2 rounded-full" style={{ backgroundColor: GREEN }} />
          </span>
          <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: '#e4ded2' }}>
            Risk Index
          </span>
        </div>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          Composite · 0–100
        </span>
      </div>

      {/* Composite score */}
      <div className="px-5 sm:px-6 pt-7 pb-5 flex items-end gap-4">
        <motion.span
          className="tabular-nums leading-none"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: '#F5F2ED', fontSize: 'clamp(3.5rem, 8vw, 5rem)' }}
          initial={{ opacity: 0, y: 10 }}
          animate={inView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        >
          {COMPOSITE_SCORE}
        </motion.span>
        <div className="pb-2">
          <div className="text-[11px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>
            Manageable
          </div>
          <div className="text-[10.5px] mt-1" style={{ color: 'rgba(245,242,237,0.45)' }}>
            ▲ 6 pts this quarter
          </div>
        </div>
      </div>

      {/* Component breakdown */}
      <ul className="px-5 sm:px-6 pb-4">
        {INDEX_COMPONENTS.map((c, i) => (
          <li key={c.label} className="py-3 border-t" style={{ borderColor: 'rgba(255,255,255,0.045)' }}>
            <div className="flex items-center justify-between mb-2">
              <span className="text-[12.5px]" style={{ color: 'rgba(245,242,237,0.9)' }}>
                {c.label}
              </span>
              <span className="text-[11px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.5)' }}>
                {c.value} · {c.weight}
              </span>
            </div>
            <div className="relative h-1.5 rounded-full" style={{ backgroundColor: 'rgba(255,255,255,0.07)' }}>
              <motion.div
                className="absolute inset-y-0 left-0 rounded-full"
                style={{ backgroundColor: GREEN }}
                initial={{ width: 0 }}
                animate={inView ? { width: `${c.value}%` } : {}}
                transition={{ duration: 0.7, delay: 0.2 + i * 0.12, ease: [0.16, 1, 0.3, 1] }}
              />
            </div>
          </li>
        ))}
      </ul>

      <div
        className="px-5 sm:px-6 py-3.5 text-[10px] font-mono uppercase tracking-[0.12em]"
        style={{ backgroundColor: 'rgba(255,255,255,0.015)', color: 'rgba(245,242,237,0.5)' }}
      >
        Weighted roll-up · WC + EPL + compliance
      </div>
    </div>
  )
}

// ── Pillars ─────────────────────────────────────────────────────────────────

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
    id: 'index',
    number: '01',
    title: 'Risk Index',
    tagline: 'One number for where you actually stand.',
    description:
      'A composite score across workers’ comp, employment practices, and compliance — with the component breakdown behind it and the highest-leverage fixes ranked first. The same engine your broker sees, pointed at your own book.',
    highlight: 'A score you can move beats a binder you can only file.',
  },
  {
    id: 'controls',
    number: '02',
    title: 'Proof of Controls',
    tagline: 'The controls you already run, made legible.',
    description:
      'Anti-harassment policy and signatures, training, discipline, incident response, wage-hour, credentialing, safety programs — auto-compiled from data you already hold, verified by you, and exported as an underwriter-ready packet.',
    highlight: 'Underwriters price uncertainty. Show them less of it.',
  },
  {
    id: 'limits',
    number: '03',
    title: 'Limit Adequacy',
    tagline: 'Find the coverage gap before the claim does.',
    description:
      'Record the limits you carry and upload the contracts that demand them. We diff line by line — “you carry $1M GL, this contract requires $2M” — flag endorsement gaps, and read each indemnity clause for whether the risk transfer is even insurable.',
    highlight: 'The gap you find at review is cheaper than the one you find at claim.',
  },
]

export default function RiskAnalysisPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: 'Risk Analysis | Matcha',
    description:
      'A live risk profile for your business — a composite risk index across workers’ comp, employment practices, and compliance, a proof-of-controls register underwriters recognize, and a limit-adequacy engine that finds coverage gaps before renewal.',
    canonical: 'https://hey-matcha.com/risk-analysis',
    jsonLd: RISK_JSON_LD,
  })

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onBookClick={() => setIsPricingOpen(true)} />

      <main>
        <Positioning />
        <PillarsGrid />
        <ReadinessBand />
        <ThePoint />
      </main>

      <CtaBand onBookClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}

function Hero({ onBookClick }: { onBookClick: () => void }) {
  return (
    <section className="relative w-full overflow-hidden" style={{ backgroundColor: BG }}>
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 70% 80% at 85% 40%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-6 sm:px-10 pt-36 pb-20">
        <div className="grid lg:grid-cols-[1.15fr_1fr] gap-12 lg:gap-20 items-center">
          <div className="max-w-xl">
            <div
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-8"
              style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
            >
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: GREEN }} />
              <span className="text-[11px] uppercase tracking-wider font-medium">
                Risk analysis
              </span>
            </div>
            <h1
              className="leading-[0.95] tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(2.75rem, 6vw, 5.25rem)',
              }}
            >
              Know your risk before the underwriter does.
            </h1>
            <p
              className="mt-6 max-w-lg"
              style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
            >
              Matcha turns the HR, safety, and compliance data you already run
              into one live risk profile — a composite index, the controls you
              can prove, and the coverage gaps you can close. Walk into renewal
              with the story already told.
            </p>
            <div className="mt-10 flex items-center gap-4 flex-wrap">
              <button
                onClick={onBookClick}
                className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: INK, color: BG }}
              >
                See Your Risk Profile
              </button>
            </div>
          </div>

          <RiskIndexCard />
        </div>
      </div>
    </section>
  )
}

// ── Positioning — what a loss run gives you vs. what Matcha gives you ────────

function Positioning() {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-2 gap-12 md:gap-20 items-start">
          <div className="max-w-md">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              The shift
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              Stop reporting risk. Start managing it.
            </h2>
          </div>
          <div className="grid sm:grid-cols-2 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                A loss run tells you
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>What already happened</li>
                <li>Last year’s numbers</li>
                <li>Claims, after the fact</li>
                <li>One line of business at a time</li>
              </ul>
            </div>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: GREEN_600 }}>
                Matcha tells you
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Where you stand right now</li>
                <li>Which fix moves the score most</li>
                <li>The controls you can prove today</li>
                <li>Every gap, before renewal</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Instrument shell + shared bits ──────────────────────────────────────────

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

// 01 — top fixes ranked by score impact.
function IndexInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const fixes = [
    { label: 'Close 3 open EPL controls', delta: '+8', lit: true },
    { label: 'Document safety training', delta: '+5' },
    { label: 'Resolve 2 wage-hour flags', delta: '+3' },
    { label: 'Refresh handbook policies', delta: '+2' },
  ]
  return (
    <InstrumentFrame caption="Risk index · top fixes" foot="Ranked by how much each moves the score">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {fixes.map((f, i) => (
            <motion.div
              key={f.label}
              className="flex items-center gap-3"
              initial={{ opacity: 0, x: -8 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.12, ease: 'easeOut' }}
            >
              <span className="shrink-0">
                {f.lit ? <PulseDot size={6} /> : <span className="block rounded-full" style={{ width: 6, height: 6, border: `1px solid ${CARD_LINE}` }} />}
              </span>
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: f.lit ? CARD_TEXT : CARD_MUTED, fontWeight: f.lit ? 600 : 400 }}>
                {f.label}
              </span>
              <span className="text-[11px] font-mono tabular-nums shrink-0" style={{ color: f.lit ? GREEN : CARD_MUTED }}>
                {f.delta} pts
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 02 — controls register, filling to verified.
function ControlsInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const controls = [
    { label: 'Anti-harassment policy', done: true },
    { label: 'Training completion', done: true },
    { label: 'Incident response', done: true },
    { label: 'Multi-state wage-hour', done: true },
    { label: 'Credentialing currency', lit: true },
    { label: 'Safety programs' },
    { label: 'Discipline records' },
    { label: 'ER case handling' },
  ]
  const verified = controls.filter((c) => c.done).length
  return (
    <InstrumentFrame caption="Proof of controls · register" foot={`${verified} of ${controls.length} verified · underwriter packet ready`}>
      <div ref={ref}>
        <div key={cycle} className="grid grid-cols-2 gap-x-4 gap-y-3">
          {controls.map((c, i) => (
            <motion.div
              key={c.label}
              className="flex items-center gap-2"
              initial={{ opacity: 0, y: 6 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.35, delay: i * 0.08, ease: 'easeOut' }}
            >
              <span className="shrink-0">
                {c.done ? (
                  <span
                    className="flex items-center justify-center rounded-full"
                    style={{ width: 14, height: 14, backgroundColor: GREEN }}
                  >
                    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                      <path d="M1.5 4L3 5.5L6.5 2" stroke="#0e0d0b" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                ) : c.lit ? (
                  <PulseDot size={6} />
                ) : (
                  <span className="block rounded-full" style={{ width: 14, height: 14, border: `1px solid ${CARD_LINE}` }} />
                )}
              </span>
              <span className="text-[11.5px] truncate" style={{ color: c.done || c.lit ? 'rgba(245,242,237,0.9)' : CARD_MUTED }}>
                {c.label}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — limit gaps, carried vs. required.
function LimitsInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const lines = [
    { line: 'General liability', carried: '$1M', required: '$2M', gap: true },
    { line: 'Auto liability', carried: '$1M', required: '$1M' },
    { line: 'Umbrella / excess', carried: '$5M', required: '$5M' },
    { line: 'Employment practices', carried: '$1M', required: '$3M', gap: true },
  ]
  return (
    <InstrumentFrame caption="Limit adequacy · contract diff" foot="Where a contract asks more than you carry">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {lines.map((l, i) => (
            <motion.div
              key={l.line}
              className="flex items-center gap-3"
              initial={{ opacity: 0, x: -8 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.12, ease: 'easeOut' }}
            >
              <span className="shrink-0">
                {l.gap ? <PulseDot size={6} /> : (
                  <span className="flex items-center justify-center rounded-full" style={{ width: 14, height: 14, backgroundColor: 'rgba(245,242,237,0.14)' }}>
                    <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                      <path d="M1.5 4L3 5.5L6.5 2" stroke="rgba(245,242,237,0.6)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                )}
              </span>
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: l.gap ? CARD_TEXT : CARD_MUTED, fontWeight: l.gap ? 600 : 400 }}>
                {l.line}
              </span>
              <span className="text-[10.5px] font-mono tabular-nums shrink-0" style={{ color: CARD_MUTED }}>
                {l.carried}
              </span>
              <span className="text-[10px] font-mono shrink-0" style={{ color: 'rgba(245,242,237,0.3)' }}>→</span>
              <span className="text-[10.5px] font-mono tabular-nums shrink-0 w-10 text-right" style={{ color: l.gap ? GREEN : CARD_MUTED }}>
                {l.required}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  index: IndexInstrument,
  controls: ControlsInstrument,
  limits: LimitsInstrument,
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
              What you get
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              Three reads on your own risk.
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

// ── Submission-readiness recap ──────────────────────────────────────────────

function ReadinessBand() {
  const items = [
    { k: 'Composite index', v: 'Scored' },
    { k: 'Controls verified', v: '4 / 8' },
    { k: 'Coverage gaps', v: '2 open' },
    { k: 'Submission packet', v: 'Ready' },
  ]
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-[1fr_1.1fr] gap-12 md:gap-20 items-center">
          <div className="max-w-md">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              Submission readiness
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.9rem, 3.6vw, 3rem)', lineHeight: 1.06 }}
            >
              Finish the checklist. Walk in underwriter-ready.
            </h2>
            <p className="mt-5 text-[16px] sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
              Every risk profile carries a completeness score — the short list of
              items that, once done, turn a thin submission into a tight one. Your
              broker sees the same banner on the packet.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
            {items.map((it) => (
              <div key={it.k} className="p-7 sm:p-8" style={{ backgroundColor: BG }}>
                <div className="text-[10.5px] uppercase tracking-[0.18em] font-mono mb-3" style={{ color: MUTED }}>
                  {it.k}
                </div>
                <div style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.6rem, 3vw, 2.25rem)', lineHeight: 1 }}>
                  {it.v}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

// ── The point + CTA ────────────────────────────────────────────────────────

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
          Underwriters price the risk they can’t see. We help you show them
          the risk you <span style={{ fontStyle: 'italic' }}>can</span> —
          and everything you’re already doing about it.
        </p>
      </div>
    </section>
  )
}

function CtaBand({ onBookClick }: { onBookClick: () => void }) {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-2xl mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
        >
          See where your risk actually stands.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us a little about your business and we’ll walk you through your
          risk profile — the index, the controls, and the gaps.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onBookClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            See Your Risk Profile
          </button>
        </div>
      </div>
    </section>
  )
}
