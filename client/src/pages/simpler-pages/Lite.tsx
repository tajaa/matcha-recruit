import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, useInView, useReducedMotion } from 'framer-motion'
import { ShieldAlert, Users, Brain, ClipboardList, FileText } from 'lucide-react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { RiskInsightsHero } from '../../components/landing/RiskInsightsHero'
import { PricingContactModal } from '../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'
const GREEN = '#A3C57D'
const GREEN_600 = '#5B7F3E'

// Instrument cards run dark (black bg / cream text) inside the otherwise ivory page.
const CARD_BG = INK
const CARD_TEXT = BG
const CARD_MUTED = 'rgba(245,242,237,0.5)'
const CARD_LINE = 'rgba(245,242,237,0.14)'

// Counts a number up from 0 once in view, and again every time `trigger` changes.
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
// Simplified /matcha-daily (Matcha Lite). Outcome-level marketing copy, the
// simpler-pages design language: clean centered hero, four full-width
// alternating pillar rows with bespoke grayscale+green instruments, a
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
    id: 'incidents',
    number: '01',
    title: 'Incident Reporting',
    tagline: 'A magic link per location. No login, no app.',
    description:
      'A link anyone can open and file into in seconds — so incidents get reported when they happen, not weeks later in a binder no one reads.',
    highlight: 'Every incident, a defensible record — no compliance team required.',
  },
  {
    id: 'hris',
    number: '02',
    title: 'HRIS/CSV Import',
    tagline: 'Your employee roster, already there.',
    description:
      'Connect Gusto, Rippling, BambooHR, or ADP — or just drop in a CSV. Every incident and OSHA log pulls from the same roster, so no one re-types a name.',
    highlight: 'One less spreadsheet to keep in sync.',
  },
  {
    id: 'ir_analysis',
    number: '03',
    title: 'IR Analysis',
    tagline: 'The signal in the noise, surfaced early.',
    description:
      'Repeat problems get flagged before they compound — so a small issue gets handled while it’s still small, not after it’s a claim.',
    highlight: 'The pattern no single manager would catch.',
  },
  {
    id: 'osha',
    number: '04',
    title: 'OSHA Logs',
    tagline: 'The logs an audit asks for — always current.',
    description:
      'The recordkeeping that usually means a year-end scramble stays up to date on its own, a click from ready whenever you need it.',
    highlight: 'Audit-ready any time, no re-keying.',
  },
]

export default function SimpleLitePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <CoverageGrid />
      </main>

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
      <MarketingFooter newsletterVariant="matcha" />
    </div>
  )
}

// ── Hero — clean centered statement, with a compact live intake instrument ──

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
              Built for daily use, not a once-a-year binder
            </span>
          </div>
          <h1
            className="leading-[0.95] tracking-tight px-2"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: GREEN,
              WebkitTextStroke: '1.5px #57534a',
              fontSize: 'clamp(2.25rem, 7vw, 5.25rem)',
            }}
          >
            Matcha Lite.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: '#4A463D', lineHeight: 1.55 }}
          >
            The everyday intake layer for your team — a magic link anyone can
            text, type into, or talk into. OSHA logs that fill themselves, risk
            insights from your own data, and a full HR library underneath.
          </p>
          <div className="mt-8 sm:mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4">
            <button
              onClick={onContactClick}
              className="inline-flex items-center justify-center w-full sm:w-auto px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: INK, color: BG }}
            >
              Talk to sales
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

        {/* Live risk-insights dashboard — the product's signature read. */}
        <div className="mt-12 sm:mt-16 max-w-5xl mx-auto -mx-2 sm:mx-auto">
          <div
            className="relative rounded-lg sm:rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{ boxShadow: '0 40px 80px -25px rgba(31, 29, 26, 0.3)', borderColor: 'rgba(0,0,0,0.08)' }}
          >
            <RiskInsightsHero />
          </div>
        </div>
      </div>
    </section>
  )
}

// ── Instruments ────────────────────────────────────────────────────────────

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

// 01 — magic-link intake: a real text arrives, resolves to logged. No pipeline detail.
function IntakeInstrument() {
  const [logged, setLogged] = useState(false)
  useEffect(() => {
    const t = setInterval(() => setLogged((v) => !v), 5200)
    return () => clearInterval(t)
  }, [])
  return (
    <InstrumentFrame caption="Magic link · intake" foot="No login, no app — a defensible record">
      <div className="flex items-center justify-center py-3" style={{ minHeight: 84 }}>
        <AnimatePresence mode="wait">
          {!logged ? (
            <motion.div
              key="text"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.35 }}
              className="max-w-[280px] rounded-2xl rounded-bl-sm px-4 py-3 text-[13px] border"
              style={{ backgroundColor: CARD_TEXT, borderColor: CARD_LINE, color: CARD_BG, lineHeight: 1.4 }}
            >
              "Wet floor by the loading dock, no injury, cleaned up"
            </motion.div>
          ) : (
            <motion.div
              key="logged"
              initial={{ opacity: 0, scale: 0.92 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.92 }}
              transition={{ duration: 0.35 }}
              className="flex items-center gap-2.5"
            >
              <span style={{ color: GREEN, fontSize: '1.1rem' }}>✓</span>
              <span style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.4rem', color: CARD_TEXT }}>
                Logged.
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <div className="mt-2 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Dallas — Store 3</span>
        <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>Reported in seconds</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — HRIS/CSV roster import, already synced. No import-flow detail.
function RosterInstrument() {
  const sources = ['Gusto', 'Rippling', 'BambooHR', 'ADP', 'CSV']
  const [active, setActive] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setActive((v) => (v + 1) % sources.length), 1400)
    return () => clearInterval(t)
  }, [sources.length])
  return (
    <InstrumentFrame caption="Roster · import" foot="Every report pre-fills the right employee">
      <div className="flex flex-wrap justify-center gap-2 py-2">
        {sources.map((s, i) => (
          <motion.span
            key={s}
            className="px-3 py-1.5 rounded-full text-[11px] font-mono uppercase tracking-wider"
            animate={{
              color: i === active ? CARD_TEXT : CARD_MUTED,
              borderColor: i === active ? GREEN : CARD_LINE,
              fontWeight: i === active ? 600 : 400,
            }}
            transition={{ duration: 0.3 }}
            style={{ border: '1px solid' }}
          >
            {s}
          </motion.span>
        ))}
      </div>
      <div className="mt-5 pt-5 border-t flex items-center justify-between" style={{ borderColor: CARD_LINE }}>
        <span className="flex items-center gap-2">
          <PulseDot size={7} />
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Synced</span>
        </span>
        <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>312 employees</span>
      </div>
    </InstrumentFrame>
  )
}

// 03 — recent incidents with severity, one High flagged + a pattern note.
function AnalysisInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const rows = [
    { loc: 'Atlanta — Store 7', type: 'Customer escalation', sev: 'High', lit: true },
    { loc: 'Phoenix — Warehouse', type: 'Slip / fall', sev: 'Med' },
    { loc: 'Dallas — Store 3', type: 'Near-miss', sev: 'Low' },
  ]
  return (
    <InstrumentFrame caption="Incidents · analysis" foot="Auto-categorized — your team confirms">
      <div ref={ref}>
        <div key={cycle} className="flex flex-col gap-3">
          {rows.map((r, i) => (
            <motion.div
              key={r.loc}
              className="flex items-center gap-3"
              initial={{ opacity: 0, x: -8 }}
              animate={inView ? { opacity: 1, x: 0 } : {}}
              transition={{ duration: 0.4, delay: i * 0.14, ease: 'easeOut' }}
            >
              <span className="shrink-0">
                {r.lit ? <PulseDot size={6} /> : <span className="block rounded-full" style={{ width: 6, height: 6, backgroundColor: CARD_LINE }} />}
              </span>
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: r.lit ? CARD_TEXT : CARD_MUTED, fontWeight: r.lit ? 600 : 400 }}>{r.loc}</span>
              <span className="text-[10px] font-mono truncate hidden sm:inline shrink-0" style={{ color: CARD_MUTED }}>{r.type}</span>
              <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-10 text-right" style={{ color: r.lit ? GREEN : CARD_MUTED }}>{r.sev}</span>
            </motion.div>
          ))}
        </div>
        <motion.div
          className="mt-5 pt-5 border-t flex items-center justify-between"
          style={{ borderColor: CARD_LINE }}
          initial={{ opacity: 0 }}
          animate={inView ? { opacity: 1 } : {}}
          transition={{ duration: 0.4, delay: rows.length * 0.14 + 0.2 }}
        >
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: GREEN }}>Pattern detected</span>
          <span className="text-[11px] font-mono" style={{ color: CARD_TEXT }}>A repeat, surfaced early</span>
        </motion.div>
      </div>
    </InstrumentFrame>
  )
}

// 04 — OSHA 300A tally tiles.
function OshaInstrument() {
  const ref = useRef(null)
  const inView = useInView(ref, { margin: '-40px' })
  const cycle = useLoopCycle(inView)
  const tiles = [
    { label: 'Recordables', target: 7, lit: true },
    { label: 'Lost days', target: 18 },
    { label: 'Cases', target: 5 },
  ]
  return (
    <InstrumentFrame caption="OSHA 300A · summary" foot="Tallies auto-populate — export any time">
      <div ref={ref}>
        <div key={cycle} className="grid grid-cols-3 rounded-lg overflow-hidden border" style={{ borderColor: CARD_LINE }}>
          {tiles.map((t, i) => (
            <OshaTile key={t.label} label={t.label} target={t.target} lit={t.lit} active={inView} last={i === tiles.length - 1} />
          ))}
        </div>
        <div className="mt-4 flex items-center gap-2">
          <PulseDot size={5} />
          <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: CARD_MUTED }}>Export-ready, any time</span>
        </div>
      </div>
    </InstrumentFrame>
  )
}

function OshaTile({ label, target, lit, active, last }: { label: string; target: number; lit?: boolean; active: boolean; last: boolean }) {
  const value = useCountUp(target, active, 900)
  return (
    <div className="px-3 py-4" style={{ borderRight: last ? undefined : `1px solid ${CARD_LINE}` }}>
      <div className="text-[8px] font-mono uppercase tracking-widest mb-1.5" style={{ color: CARD_MUTED }}>{label}</div>
      <div className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.75rem', color: lit ? GREEN : CARD_TEXT }}>{value}</div>
    </div>
  )
}

const INSTRUMENTS: Record<string, () => React.ReactElement> = {
  incidents: IntakeInstrument,
  hris: RosterInstrument,
  ir_analysis: AnalysisInstrument,
  osha: OshaInstrument,
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
              What’s in the bundle
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 4vw, 3.25rem)', lineHeight: 1.05 }}
            >
              Intake, analysis, and OSHA — the daily layer.
            </h2>
          </div>
        </div>
      </section>

      {PILLARS.slice(0, 2).map((pillar, i) => (
        <PillarRow key={pillar.id} pillar={pillar} index={i} />
      ))}
      <ThePoint />
      {PILLARS.slice(2).map((pillar, i) => (
        <PillarRow key={pillar.id} pillar={pillar} index={i + 2} />
      ))}
    </>
  )
}

// ── Coverage recap ─────────────────────────────────────────────────────────

function GlyphBars() {
  return (
    <div className="flex items-end gap-1 h-6">
      {[10, 16, 12, 22, 14].map((h, i) => (
        <span key={i} className="w-[3px] rounded-full" style={{ height: h, backgroundColor: i === 3 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphPeople() {
  return (
    <div className="flex -space-x-1.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="rounded-full border"
          style={{ width: 10, height: 10, backgroundColor: i === 1 ? GREEN : BG, borderColor: i === 1 ? GREEN : LINE }}
        />
      ))}
    </div>
  )
}
function GlyphBrain() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 0 ? GREEN : MUTED }} />
          <span className="h-[2px] rounded-full" style={{ width: i === 0 ? 16 : 12, backgroundColor: LINE }} />
        </span>
      ))}
    </div>
  )
}
function GlyphLog() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[16, 13, 16, 10].map((w, i) => (
        <span key={i} className="h-[2px] rounded-full" style={{ width: w, backgroundColor: i === 0 ? GREEN : LINE }} />
      ))}
    </div>
  )
}
function GlyphStack() {
  return (
    <div className="relative w-5 h-6">
      {[0, 1, 2].map((i) => (
        <span key={i} className="absolute rounded-sm border" style={{ width: 14, height: 16, left: i * 3, top: i * 2, borderColor: i === 0 ? GREEN : LINE, backgroundColor: BG }} />
      ))}
    </div>
  )
}

const COVERAGE: { id: string; icon: typeof ShieldAlert; title: string; caption: string; glyph: () => React.ReactElement }[] = [
  {
    id: 'incidents',
    icon: ShieldAlert,
    title: 'Incident reporting',
    caption: 'A link anyone can file into in seconds, so nothing goes unreported — and every record holds up later.',
    glyph: GlyphBars,
  },
  {
    id: 'hris',
    icon: Users,
    title: 'HRIS/CSV import',
    caption: 'Connect Gusto, Rippling, BambooHR, ADP — or drop in a CSV. One roster, everywhere it’s needed.',
    glyph: GlyphPeople,
  },
  {
    id: 'analysis',
    icon: Brain,
    title: 'IR analysis',
    caption: 'The repeat problems no single manager would catch, surfaced early enough to act on.',
    glyph: GlyphBrain,
  },
  {
    id: 'osha',
    icon: ClipboardList,
    title: 'OSHA logs',
    caption: 'The recordkeeping an audit asks for, kept current on its own and ready whenever you need it.',
    glyph: GlyphLog,
  },
  {
    id: 'resources',
    icon: FileText,
    title: 'HR resource hub',
    caption: 'The everyday HR documents your team reaches for, ready to use — no starting from a blank page.',
    glyph: GlyphStack,
  },
]

function CoverageGrid() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-3 sm:mb-4" style={{ color: MUTED }}>
            The whole bundle
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            Everyday HR risk, covered.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Five tools, one bundle. Each stands on its own; together they cover
            the everyday HR risk surface for a small team without a dedicated
            compliance function.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
          {COVERAGE.map((f, i) => {
            const Icon = f.icon
            const Glyph = f.glyph
            return (
              <motion.div
                key={f.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ duration: 0.5, delay: (i % 3) * 0.08, ease: 'easeOut' }}
                className="p-6 sm:p-8 flex flex-col"
                style={{ backgroundColor: BG }}
              >
                <div className="flex items-start justify-between mb-5">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ backgroundColor: 'rgba(31,29,26,0.06)' }}>
                    <Icon className="w-5 h-5" style={{ color: INK }} />
                  </div>
                  <div className="h-10 flex items-center">
                    <Glyph />
                  </div>
                </div>
                <h3 className="text-lg sm:text-xl mb-2" style={{ fontFamily: DISPLAY, color: INK, fontWeight: 500 }}>
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
          Compliance shouldn’t live in a binder nobody opens. Matcha Lite makes
          it something your team <span style={{ fontStyle: 'italic' }}>uses</span>,
          every day, without thinking about it.
        </p>
      </div>
    </section>
  )
}

function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-2xl mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
        >
          Give your team the daily layer.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us your headcount and where you operate. We’ll walk you through
          the rest.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onContactClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            Talk to sales
          </button>
        </div>
      </div>
    </section>
  )
}
