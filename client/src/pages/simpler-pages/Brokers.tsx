import { useEffect, useRef, useState } from 'react'
import { motion, useInView, useReducedMotion } from 'framer-motion'
import { useSEO } from '../../hooks/useSEO'
import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/marketing/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'
const GREEN = '#A3C57D' // the one emphasis color — everything else grayscale
const GREEN_600 = '#5B7F3E' // eyebrow labels

// Pillar instrument cards run dark (black bg / cream text) inside the otherwise
// ivory page. The hero's Book-Risk-Curve card is already its own dark design
// and is left untouched.
const CARD_BG = INK
const CARD_TEXT = BG
const CARD_MUTED = 'rgba(245,242,237,0.5)'
const CARD_LINE = 'rgba(245,242,237,0.14)'

// Ticks up once every `intervalMs` while `active` (the instrument is in
// view), so a `key={cycle}` on the animated content replays its entrance.
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
// Simplified /brokers. Keeps the original colorful Book-Risk-Curve hero card
// (the signature the user wanted to preserve), then simplifies the rest into
// the simpler-pages design language: full-width alternating pillar rows with
// bespoke grayscale+green instruments, a coverage recap grid, an editorial
// cut, and the monochrome newsletter band.
// ---------------------------------------------------------------------------

// ── Hero (kept from the original /brokers page) ────────────────────────────

type RiskBand = 'critical' | 'elevated' | 'stable'

const BAND_COLOR: Record<RiskBand, string> = {
  critical: '#ff6b6b',
  elevated: '#f5b545',
  stable: '#6ee7a8',
}

const RADAR_ROWS: { client: string; band: RiskBand; metric: string; delta: string }[] = [
  { client: 'Northgate Logistics', band: 'critical', metric: 'TRIR 6.2', delta: '+1.4' },
  { client: 'Cedar Valley Mfg', band: 'elevated', metric: 'Lost days 14', delta: '+5.0' },
  { client: 'Harbor Foods Co', band: 'stable', metric: 'DART 1.1', delta: '−0.3' },
  { client: 'Atlas Care Group', band: 'elevated', metric: 'Near miss ×3', delta: 'new' },
  { client: 'Summit Builders', band: 'stable', metric: 'TRIR 0.9', delta: '−0.2' },
]

const BROKERS_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Service',
  name: 'Matcha for Brokers',
  url: 'https://hey-matcha.com/matcha-brokers',
  description:
    "A book-of-business intelligence layer for P&C brokers — exposure-weighted risk curve, workers' comp loss-control portfolio, and AI-drafted client outreach.",
  serviceType: 'Insurance brokerage software',
}

// ── Simplified pillars ─────────────────────────────────────────────────────

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
    id: 'risk-curve',
    number: '01',
    title: 'Risk Curve',
    tagline: 'See the renewal before it hits your desk.',
    description:
      'Walk into renewal prep already knowing which accounts are deteriorating — months before the carrier re-rates them.',
    highlight: 'A loss curve you can act on beats a loss run you can only read.',
  },
  {
    id: 'wc',
    number: '02',
    title: 'Loss Control',
    tagline: 'The whole book, ranked by who needs you.',
    description:
      'Triage your book in seconds, so the loss-control call goes to the account that needs it — not the one that shouts loudest.',
    highlight: 'One screen ranks every client by safety deterioration.',
  },
  {
    id: 'command',
    number: '03',
    title: 'Command Center',
    tagline: 'Every account, every signal, one queue.',
    description:
      'A flagged trend becomes a client conversation with the talking points already written — so outreach starts before the renewal does.',
    highlight: 'Every alert is a client conversation waiting to happen.',
  },
]

export default function SimpleBrokersPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: 'Matcha for Brokers | Book-of-Business Intelligence',
    description:
      "Give your P&C clients a live safety intake system — and get the intelligence layer back. Exposure-weighted risk curve, workers' comp loss control, and AI-drafted outreach across your whole book.",
    canonical: 'https://hey-matcha.com/matcha-brokers',
    jsonLd: BROKERS_JSON_LD,
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
                For P&amp;C brokers
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
              The intelligence layer for your whole book.
            </h1>
            <p
              className="mt-6 max-w-lg"
              style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
            >
              Your clients run a live safety intake system. You get back what no
              carrier portal gives you — real-time TRIR, DART, and loss trends,
              plus risk alerts and suggested actions, across every account you
              manage.
            </p>
            <div className="mt-10 flex items-center gap-4 flex-wrap">
              <button
                onClick={onBookClick}
                className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: INK, color: BG }}
              >
                Book a Walkthrough
              </button>
            </div>
          </div>

          <BookRiskCurveCard />
        </div>
      </div>
    </section>
  )
}

// Animated hero card — kept from the original page (colorful risk bands).
function BookRiskCurveCard() {
  const ref = useRef(null)
  const inView = useInView(ref, { amount: 0.3 })

  const counts = RADAR_ROWS.reduce(
    (acc, r) => ({ ...acc, [r.band]: (acc[r.band] ?? 0) + 1 }),
    {} as Record<RiskBand, number>,
  )

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
              style={{ backgroundColor: '#6ee7a8' }}
              animate={inView ? { opacity: [0.6, 0, 0.6], scale: [1, 2.4, 1] } : { opacity: 0.6 }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeOut' }}
            />
            <span className="relative inline-flex w-2 h-2 rounded-full" style={{ backgroundColor: '#6ee7a8' }} />
          </span>
          <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: '#e4ded2' }}>
            Book Risk Curve
          </span>
        </div>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          Book · 24 clients
        </span>
      </div>

      <div className="relative">
        <motion.div
          aria-hidden
          className="absolute inset-x-0 pointer-events-none z-10"
          style={{
            height: '38%',
            background:
              'linear-gradient(180deg, rgba(110,231,168,0) 0%, rgba(110,231,168,0.10) 50%, rgba(110,231,168,0) 100%)',
          }}
          animate={inView ? { top: ['-38%', '100%'] } : { top: '-38%' }}
          transition={{ duration: 3.4, repeat: Infinity, ease: 'linear' }}
        />

        <ul>
          {RADAR_ROWS.map((r, i) => {
            const volatile = r.band !== 'stable'
            return (
              <motion.li
                key={r.client}
                className="px-5 sm:px-6 py-3.5 flex items-center justify-between gap-3 border-b"
                style={{ borderColor: 'rgba(255,255,255,0.045)' }}
                initial={{ opacity: 0, y: 6 }}
                animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 6 }}
                transition={{ duration: 0.5, delay: i * 0.12, ease: 'easeOut' }}
              >
                <div className="min-w-0">
                  <div className="text-[13px] truncate" style={{ color: 'rgba(245,242,237,0.92)' }}>
                    {r.client}
                  </div>
                  <div className="text-[11px] mt-0.5 font-mono" style={{ color: 'rgba(245,242,237,0.4)' }}>
                    {r.metric}
                  </div>
                </div>
                <div className="flex items-center gap-2.5 shrink-0">
                  <span className="text-[10px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.5)' }}>
                    {r.delta}
                  </span>
                  <motion.span
                    className="text-[9px] font-medium uppercase tracking-wider px-2 py-1 rounded"
                    style={{
                      color: BAND_COLOR[r.band],
                      backgroundColor: `${BAND_COLOR[r.band]}1f`,
                    }}
                    animate={inView && volatile ? { opacity: [1, 0.45, 1] } : { opacity: 1 }}
                    transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut', delay: i * 0.2 }}
                  >
                    {r.band}
                  </motion.span>
                </div>
              </motion.li>
            )
          })}
        </ul>
      </div>

      <div
        className="px-5 sm:px-6 py-3.5 flex items-center gap-4"
        style={{ backgroundColor: 'rgba(255,255,255,0.015)' }}
      >
        {(['critical', 'elevated', 'stable'] as RiskBand[]).map((band) => (
          <div key={band} className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: BAND_COLOR[band] }} />
            <span className="text-[10px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.55)' }}>
              {counts[band] ?? 0} {band}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Positioning — kept succinct: what the client sees vs. what you see ──────

function Positioning() {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-2 gap-12 md:gap-20 items-start">
          <div className="max-w-md">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              The model
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              They get the platform. You get the signal.
            </h2>
          </div>
          <div className="grid sm:grid-cols-2 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                Your client sees
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Incident reporting</li>
                <li>Guided incident response</li>
                <li>Risk trends &amp; insights</li>
                <li>Pattern detection across cases</li>
              </ul>
            </div>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: GREEN_600 }}>
                You see
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Book-wide risk curve</li>
                <li>Loss-control ranking</li>
                <li>Risk alerts, ranked</li>
                <li>Outreach, AI-drafted</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Pillars — alternating rows with bespoke grayscale+green instruments ────

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

// 01 — risk-band ladder, resolving to the exposed account.
function RiskCurveInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const bands = [
    { label: 'Strong', w: 30 },
    { label: 'Adequate', w: 52 },
    { label: 'Developing', w: 74 },
    { label: 'Exposed', w: 96, lit: true },
  ]
  return (
    <InstrumentFrame caption="Book · risk curve" foot="The account deteriorating before its re-rate">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3">
          {bands.map((b, i) => (
            <div key={b.label} className="flex items-center gap-4">
              <div className="w-20 shrink-0 text-[10px] font-mono uppercase tracking-wider text-right" style={{ color: b.lit ? CARD_TEXT : CARD_MUTED, fontWeight: b.lit ? 600 : 400 }}>
                {b.label}
              </div>
              <div className="relative flex-1 h-2">
                <motion.div
                  className="absolute inset-y-0 left-0 rounded-full"
                  style={{ backgroundColor: b.lit ? GREEN : CARD_LINE }}
                  initial={{ width: 0 }}
                  animate={inView ? { width: `${b.w}%` } : {}}
                  transition={{ duration: 0.6, delay: i * 0.15, ease: [0.16, 1, 0.3, 1] }}
                />
                {b.lit && (
                  <motion.span
                    className="absolute top-1/2 -translate-y-1/2"
                    style={{ left: `${b.w}%` }}
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={inView ? { opacity: 1, scale: 1 } : {}}
                    transition={{ duration: 0.3, delay: i * 0.15 + 0.5 }}
                  >
                    <PulseDot size={7} />
                  </motion.span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 02 — WC portfolio rows, worst-first, top row flagged.
function WcInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { client: 'Northgate Logistics', lit: true },
    { client: 'Cedar Valley Mfg' },
    { client: 'Harbor Foods Co' },
    { client: 'Summit Builders' },
  ]
  return (
    <InstrumentFrame caption="The book · ranked" foot="The account that needs you, first">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {rows.map((r, i) => (
            <motion.div
              key={r.client}
              className="flex items-center gap-3"
              initial={{ opacity: 0, x: -8 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.12, ease: 'easeOut' }}
            >
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: r.lit ? CARD_TEXT : CARD_MUTED, fontWeight: r.lit ? 600 : 400 }}>{r.client}</span>
              {r.lit ? (
                <span className="flex items-center gap-1.5 shrink-0 w-24 justify-end">
                  <PulseDot size={6} />
                  <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Needs a call</span>
                </span>
              ) : (
                <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-24 text-right" style={{ color: CARD_MUTED }}>Stable</span>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — action queue, top alert urgent.
function CommandInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const alerts = [
    { client: 'Northgate Logistics', issue: 'Safety trend deteriorating', lit: true },
    { client: 'Cedar Valley Mfg', issue: 'Running above the book' },
    { client: 'Atlas Care Group', issue: 'Rising incident volume' },
  ]
  return (
    <InstrumentFrame caption="Command center · queue" foot="Each flagged trend, an outreach already drafted">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3.5">
          {alerts.map((a, i) => (
            <motion.div
              key={a.client}
              className="flex items-start gap-3"
              initial={{ opacity: 0, y: 6 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.15, ease: 'easeOut' }}
            >
              <span className="mt-1 shrink-0">
                {a.lit ? <PulseDot size={6} /> : <span className="block rounded-full" style={{ width: 6, height: 6, border: `1px solid ${CARD_LINE}` }} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[12px]" style={{ color: a.lit ? CARD_TEXT : CARD_MUTED, fontWeight: a.lit ? 600 : 400 }}>{a.client}</div>
                <div className="text-[10.5px] mt-0.5" style={{ color: CARD_MUTED }}>{a.issue}</div>
              </div>
              <span className="text-[9px] font-mono uppercase tracking-wider shrink-0" style={{ color: a.lit ? GREEN : CARD_MUTED }}>
                {a.lit ? 'Urgent' : 'Advisory'}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
    </InstrumentFrame>
  )
}

const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  'risk-curve': RiskCurveInstrument,
  wc: WcInstrument,
  command: CommandInstrument,
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
              Three reads on your whole book.
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
          A loss run tells you what already happened. We hand you the trend
          while it’s still <span style={{ fontStyle: 'italic' }}>fixable</span> —
          and the conversation to fix it.
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
          Put your book on Matcha.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us how many accounts you manage and how you want to deploy.
          We’ll walk you through the rest.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onBookClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            Book a Walkthrough
          </button>
        </div>
      </div>
    </section>
  )
}
