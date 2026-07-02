import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ShieldAlert, Scale, Users, Gavel, Activity, Brain } from 'lucide-react'

import MarketingNav from '../landing/MarketingNav'
import MarketingFooter from '../landing/MarketingFooter'
import { LazyMount } from '../landing/LazyMount'
import { EnforcementTotalsTicker } from '../../components/landing/EnforcementTotalsTicker'
import { PricingContactModal } from '../../components/PricingContactModal'

const AgentReasoningAnimation = lazy(() => import('../landing/AgentReasoningAnimation'))

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'
const AMBER = '#F59E0B' // the one emphasis color — everything else stays grayscale
const AMBER_600 = '#D97706' // eyebrow labels specifically

// ---------------------------------------------------------------------------
// Simplified /platform — the full Matcha platform (EHS + GRC + ER unified on
// one agentic brain) told in outcome-level marketing copy only. No mechanism
// detail, no dense product dashboards — the same design language as the
// simplified /matcha-compliance page: a live hero panel, four full-width
// alternating pillar rows each with a bespoke grayscale+amber instrument, a
// coverage recap grid, an editorial cut, and the monochrome newsletter band.
// ---------------------------------------------------------------------------

type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  included: string[]
  highlight: string
}

const PILLARS: Pillar[] = [
  {
    id: 'ehs',
    number: '01',
    title: 'Safety & EHS',
    tagline: 'Every incident captured, categorized, and routed.',
    description:
      'Frontline intake, OSHA logs, and pattern detection — so nothing slips and every record is defensible.',
    included: [
      'Magic-link incident intake, per location',
      'OSHA 300 & 300A, audit-ready',
      'Patterns surfaced across sites and shifts',
    ],
    highlight: 'The safety layer that runs itself.',
  },
  {
    id: 'grc',
    number: '02',
    title: 'Governance & Compliance',
    tagline: 'The rules that govern you, always current.',
    description:
      'Jurisdiction-aware monitoring across every location, with the deltas flagged before they land.',
    included: [
      'Federal → city requirements, per site',
      'Change alerts before law takes effect',
      'Every finding tracked to an owner',
    ],
    highlight: 'Audit-ready, without the fire drill.',
  },
  {
    id: 'er',
    number: '03',
    title: 'Employee Relations',
    tagline: 'Cases handled before they become claims.',
    description:
      'Investigations, progressive discipline, and separation risk — defensible from first note to final memo.',
    included: [
      'Investigations with counsel-ready records',
      'Progressive discipline workflows',
      'Separation risk mapped pre-decision',
    ],
    highlight: 'The hard conversations, documented right.',
  },
  {
    id: 'convergence',
    number: '04',
    title: 'One Brain',
    tagline: 'Three disciplines, one live record.',
    description:
      'A safety incident, a compliance gap, and an ER case inform each other in real time — one composite view of your risk.',
    included: [
      'Shared data model across EHS, GRC, ER',
      'Composite risk index, always live',
      'Signals cross domains automatically',
    ],
    highlight: 'Risk surfaces before it compounds.',
  },
]

export default function SimplePlatformPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <EnforcementTotalsTicker mono />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <PillarsGrid />
        <CoverageGrid />
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
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: AMBER }} />
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
            systems. Matcha runs them on one platform, where every signal talks
            to the others.
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
// grayscale diagram, with one amber mark for the node it resolves to and an
// oversized ghost numeral bleeding off the copy side. Grayscale everywhere.
// ---------------------------------------------------------------------------

function PulseDot({ size = 8 }: { size?: number }) {
  return (
    <span className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <motion.span
        className="absolute rounded-full"
        style={{ width: size, height: size, backgroundColor: AMBER }}
        animate={{ scale: [1, 2.4, 1], opacity: [0.35, 0, 0.35] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'easeInOut' }}
      />
      <span className="relative block rounded-full" style={{ width: size, height: size, backgroundColor: AMBER }} />
    </span>
  )
}

function InstrumentFrame({ caption, foot, children }: { caption: string; foot: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border overflow-hidden" style={{ borderColor: LINE, backgroundColor: 'rgba(31,29,26,0.015)' }}>
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: MUTED }}>{caption}</span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: MUTED }}>
          <PulseDot size={5} />
          Live
        </span>
      </div>
      <div className="px-5 py-6">{children}</div>
      <div className="px-5 py-3 border-t text-[10px] font-mono uppercase tracking-[0.12em]" style={{ borderColor: LINE, color: MUTED }}>
        {foot}
      </div>
    </div>
  )
}

// 01 — intake pipeline: report resolves through to routed.
function IntakeInstrument() {
  const steps = ['Report', 'Categorize', 'Severity', 'Routed']
  const activeIdx = 3
  return (
    <InstrumentFrame caption="Incident · intake" foot="Every report categorized, scored, and routed">
      <div className="relative py-2">
        <div className="absolute left-0 right-0 top-[9px] h-px" style={{ backgroundColor: LINE }} />
        <div className="relative flex items-start justify-between">
          {steps.map((s, i) => (
            <div key={s} className="flex flex-col items-center gap-3" style={{ width: 72 }}>
              {i === activeIdx ? (
                <PulseDot size={9} />
              ) : (
                <span className="block rounded-full" style={{ width: 7, height: 7, backgroundColor: i < activeIdx ? MUTED : LINE, border: i > activeIdx ? `1px solid ${LINE}` : 'none' }} />
              )}
              <span
                className="text-[9.5px] font-mono uppercase tracking-wider text-center"
                style={{ color: i === activeIdx ? INK : MUTED, fontWeight: i === activeIdx ? 600 : 400 }}
              >
                {s}
              </span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-6 pt-5 border-t flex items-center justify-between" style={{ borderColor: LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: MUTED }}>IR-2041 · Atlanta</span>
        <span className="text-[11px] font-mono" style={{ color: INK }}>Routed to manager</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — compliance monitor rows, one flagged.
function ComplianceInstrument() {
  const rows = [
    { j: 'FED', label: 'FLSA overtime threshold', status: 'clear' },
    { j: 'CA', label: 'Meal-period waivers', status: 'flag' },
    { j: 'NY', label: 'Paid sick-leave accrual', status: 'clear' },
    { j: 'WA', label: 'Predictive scheduling', status: 'clear' },
  ]
  return (
    <InstrumentFrame caption="Compliance · monitor" foot="Deltas flagged before they take effect">
      <div className="flex flex-col gap-3.5">
        {rows.map((r) => {
          const lit = r.status === 'flag'
          return (
            <div key={r.label} className="flex items-center gap-3">
              <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider" style={{ color: MUTED }}>{r.j}</span>
              <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: lit ? INK : MUTED, fontWeight: lit ? 600 : 400 }}>{r.label}</span>
              {lit ? (
                <span className="flex items-center gap-1.5 shrink-0">
                  <PulseDot size={6} />
                  <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: AMBER_600 }}>Flagged</span>
                </span>
              ) : (
                <span className="text-[9px] font-mono uppercase tracking-wider shrink-0" style={{ color: MUTED }}>Clear</span>
              )}
            </div>
          )
        })}
      </div>
    </InstrumentFrame>
  )
}

// 03 — case cluster: pattern detection surfaces a repeat.
function CaseInstrument() {
  // 5×3 scatter; the lit cells trace a repeat cluster.
  const litCells = new Set([2, 7, 12])
  return (
    <InstrumentFrame caption="Cases · pattern" foot="Repeat behavior surfaced across the record">
      <div className="grid grid-cols-5 gap-y-4 gap-x-3 place-items-center py-1">
        {Array.from({ length: 15 }).map((_, i) =>
          litCells.has(i) ? (
            <PulseDot key={i} size={8} />
          ) : (
            <span key={i} className="block rounded-full" style={{ width: 6, height: 6, backgroundColor: LINE }} />
          ),
        )}
      </div>
      <div className="mt-5 pt-5 border-t flex items-center justify-between" style={{ borderColor: LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: AMBER_600 }}>Pattern found</span>
        <span className="text-[11px] font-mono" style={{ color: INK }}>3 cases · Store 7 · late shift</span>
      </div>
    </InstrumentFrame>
  )
}

// 04 — domains feeding a single composite risk index.
function ConvergenceInstrument() {
  const domains = [
    { label: 'EHS', w: 70 },
    { label: 'GRC', w: 54 },
    { label: 'ER', w: 62 },
  ]
  return (
    <InstrumentFrame caption="Risk · composite" foot="Every domain rolled into one live index">
      <div className="flex items-center gap-6">
        <div className="flex-1 flex flex-col gap-3">
          {domains.map((d) => (
            <div key={d.label} className="flex items-center gap-3">
              <span className="w-9 shrink-0 text-[9px] font-mono uppercase tracking-wider text-right" style={{ color: MUTED }}>{d.label}</span>
              <div className="flex-1 h-1.5 rounded-full" style={{ backgroundColor: LINE }}>
                <div className="h-full rounded-full" style={{ width: `${d.w}%`, backgroundColor: MUTED }} />
              </div>
            </div>
          ))}
        </div>
        <span className="text-[11px] font-mono" style={{ color: MUTED }}>→</span>
        <div className="flex flex-col items-center gap-1 shrink-0">
          <div className="flex items-baseline gap-1">
            <span className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '2.75rem', color: AMBER }}>72</span>
          </div>
          <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: MUTED }}>Risk index</span>
        </div>
      </div>
    </InstrumentFrame>
  )
}

const INSTRUMENTS: Record<string, () => JSX.Element> = {
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
            <div className="text-[12px] uppercase tracking-[0.2em] font-mono mb-6" style={{ color: AMBER_600 }}>
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
            <p className="mt-4 text-[15px] sm:text-base max-w-md" style={{ color: MUTED, lineHeight: 1.6 }}>
              {pillar.description}
            </p>
            <ul className="mt-8 pt-7 border-t space-y-2.5 max-w-md" style={{ borderColor: LINE }}>
              {pillar.included.map((d) => (
                <li key={d} className="flex items-baseline gap-3 text-[14.5px]" style={{ color: INK }}>
                  <span className="font-mono text-[11px]" style={{ color: MUTED }}>—</span>
                  <span style={{ lineHeight: 1.5 }}>{d}</span>
                </li>
              ))}
            </ul>
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
// Coverage recap — a hairline feature grid summarizing the whole platform.
// ---------------------------------------------------------------------------

function GlyphBars() {
  return (
    <div className="flex items-end gap-1 h-6">
      {[10, 16, 12, 22, 14].map((h, i) => (
        <span key={i} className="w-[3px] rounded-full" style={{ height: h, backgroundColor: i === 3 ? AMBER : LINE }} />
      ))}
    </div>
  )
}
function GlyphBrain() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 1 ? AMBER : MUTED }} />
          <span className="h-[2px] rounded-full" style={{ width: i === 1 ? 16 : 12, backgroundColor: LINE }} />
        </span>
      ))}
    </div>
  )
}
function GlyphScale() {
  return (
    <div className="flex flex-col items-end gap-1">
      {[16, 12, 9].map((w, i) => (
        <span key={w} className="h-[3px] rounded-full" style={{ width: w, backgroundColor: i === 2 ? AMBER : LINE }} />
      ))}
    </div>
  )
}
function GlyphSteps() {
  return (
    <div className="flex items-center gap-1.5">
      {[0, 1, 2].map((i) => (
        <span key={i} className="rounded-full" style={{ width: 6, height: 6, backgroundColor: i === 2 ? AMBER : 'transparent', border: i === 2 ? 'none' : `1px solid ${LINE}` }} />
      ))}
    </div>
  )
}
function GlyphGauge() {
  return (
    <span className="tabular-nums" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.5rem', color: AMBER, lineHeight: 1 }}>72</span>
  )
}
function GlyphCluster() {
  return (
    <div className="grid grid-cols-3 gap-1">
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <span key={i} className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 4 ? AMBER : LINE }} />
      ))}
    </div>
  )
}

const COVERAGE: { id: string; icon: typeof ShieldAlert; title: string; caption: string; glyph: () => JSX.Element }[] = [
  {
    id: 'intake',
    icon: ShieldAlert,
    title: 'Incident intake',
    caption: 'A magic link per location — photo evidence, witnesses, anonymous channel, and a defensible chain of custody.',
    glyph: GlyphBars,
  },
  {
    id: 'analysis',
    icon: Brain,
    title: 'IR analysis',
    caption: 'Suggested categorization and severity on every incident, with cross-incident pattern detection for your team to review.',
    glyph: GlyphBrain,
  },
  {
    id: 'compliance',
    icon: Scale,
    title: 'Compliance',
    caption: 'Jurisdiction-aware monitoring across every location, with new and amended law flagged before it takes effect.',
    glyph: GlyphScale,
  },
  {
    id: 'discipline',
    icon: Gavel,
    title: 'Discipline & ER',
    caption: 'Progressive discipline, investigations, and separation risk — every case documented and defensible.',
    glyph: GlyphSteps,
  },
  {
    id: 'risk',
    icon: Activity,
    title: 'Composite risk',
    caption: 'One live index rolling up safety, compliance, and employee-relations signals into a single view of exposure.',
    glyph: GlyphGauge,
  },
  {
    id: 'relations',
    icon: Users,
    title: 'People, connected',
    caption: 'Every signal shares one record, so a safety incident, a compliance gap, and an ER case inform each other in real time.',
    glyph: GlyphCluster,
  },
]

function CoverageGrid() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-12 sm:mb-16">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-3 sm:mb-4" style={{ color: MUTED }}>
            The whole platform
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            The entire risk function, in one place.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Six capabilities, one brain. Each stands on its own; together they
            cover the safety, compliance, and people risk a growing company
            can’t afford to run on spreadsheets.
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
