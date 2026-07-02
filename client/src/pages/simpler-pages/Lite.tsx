import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ShieldAlert, Mic, Brain, ClipboardList, FileText, MapPin } from 'lucide-react'

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
const AMBER = '#F59E0B'
const AMBER_600 = '#D97706'

// ---------------------------------------------------------------------------
// Simplified /matcha-daily (Matcha Lite). Outcome-level marketing copy, the
// simpler-pages design language: clean centered hero, four full-width
// alternating pillar rows with bespoke grayscale+amber instruments, a
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
    id: 'incidents',
    number: '01',
    title: 'Incident Reporting',
    tagline: 'A magic link per location. No login, no app.',
    description:
      'Texted, QR-coded, or bookmarked at the register — intake opens pre-filled with that site, ready for photos, witnesses, and an anonymous channel.',
    included: [
      'A magic link per location',
      'Photo evidence + witness capture',
      'Anonymous reporting channel',
    ],
    highlight: 'Every incident, a defensible record — no compliance team required.',
  },
  {
    id: 'voice',
    number: '02',
    title: 'Voice Intake',
    tagline: 'Talk through what happened. We write the report.',
    description:
      'Tap Dictate on any magic link — Matcha transcribes in real time and fills reporter, witnesses, location, date, and a suggested category, for them to review before it submits.',
    included: [
      'Real-time transcription',
      'Fields filled automatically',
      'Reviewed before it submits',
    ],
    highlight: 'Hands-free reporting, reviewed before it submits.',
  },
  {
    id: 'ir_analysis',
    number: '03',
    title: 'IR Analysis',
    tagline: 'Every incident categorized, scored, connected.',
    description:
      'Suggested categorization and severity on every incident, with cross-incident pattern detection surfacing repeat behaviors and emerging risk clusters for your team to confirm.',
    included: [
      'Suggested category and severity',
      'Cross-incident pattern detection',
      'Your team confirms every call',
    ],
    highlight: 'The pattern no single manager would catch.',
  },
  {
    id: 'osha',
    number: '04',
    title: 'OSHA 300 / 300A Logs',
    tagline: 'OSHA logs that fill themselves.',
    description:
      'Recordable tracking tied to your intake flow — tallies auto-populate, so you can print or export an audit-ready 300A summary any time.',
    included: [
      'Recordables auto-tallied',
      '300, 300A, and ITA export',
      'Audit-ready any time',
    ],
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
        <ThePoint />
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
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: AMBER }} />
            <span className="text-[10px] sm:text-[11px] uppercase tracking-wider font-medium">
              Built for daily use, not a once-a-year binder
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
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
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

// 01 — magic-link intake pipeline, resolves to logged.
function IntakeInstrument() {
  const steps = ['Open link', 'Fill', 'Review', 'Logged']
  const activeIdx = 3
  return (
    <InstrumentFrame caption="Magic link · intake" foot="No login, no app — a defensible record">
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
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: MUTED }}>IR-2044 · Dallas</span>
        <span className="text-[11px] font-mono" style={{ color: INK }}>Logged · chain of custody</span>
      </div>
    </InstrumentFrame>
  )
}

// 02 — voice waveform + extracted fields.
const WAVE = [0.3, 0.6, 0.85, 0.5, 0.95, 0.4, 0.7, 0.55, 0.9, 0.35, 0.65, 0.45, 0.8, 0.5]
function VoiceInstrument() {
  return (
    <InstrumentFrame caption="Voice · dictate" foot="Transcribed and filled — reviewed before submit">
      <div className="flex flex-col items-center py-1">
        <div className="flex items-end gap-[3px] h-8 mb-4">
          {WAVE.map((v, i) => (
            <motion.div
              key={i}
              className="w-[3px] rounded-full"
              style={{ backgroundColor: i === 4 ? AMBER : MUTED, opacity: i === 4 ? 1 : 0.5 }}
              animate={{ height: [`${v * 45}%`, `${v * 100}%`, `${v * 45}%`] }}
              transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.05, ease: 'easeInOut' }}
            />
          ))}
        </div>
        <span className="text-[10px] font-mono" style={{ color: AMBER_600 }}>Report ready for review</span>
      </div>
      <div className="mt-5 pt-5 border-t grid grid-cols-2 gap-4" style={{ borderColor: LINE }}>
        <div>
          <div className="text-[8px] font-mono uppercase tracking-widest mb-1" style={{ color: MUTED }}>Category</div>
          <div className="text-[12px]" style={{ color: INK }}>Customer escalation</div>
        </div>
        <div>
          <div className="text-[8px] font-mono uppercase tracking-widest mb-1" style={{ color: MUTED }}>Severity</div>
          <div className="text-[12px] font-medium" style={{ color: AMBER_600 }}>Medium</div>
        </div>
      </div>
    </InstrumentFrame>
  )
}

// 03 — recent incidents with severity, one High flagged + a pattern note.
function AnalysisInstrument() {
  const rows = [
    { loc: 'Atlanta — Store 7', type: 'Customer escalation', sev: 'High', lit: true },
    { loc: 'Phoenix — Warehouse', type: 'Slip / fall', sev: 'Med' },
    { loc: 'Dallas — Store 3', type: 'Near-miss', sev: 'Low' },
  ]
  return (
    <InstrumentFrame caption="Incidents · analysis" foot="Auto-categorized — your team confirms">
      <div className="flex flex-col gap-3">
        {rows.map((r) => (
          <div key={r.loc} className="flex items-center gap-3">
            <span className="shrink-0">
              {r.lit ? <PulseDot size={6} /> : <span className="block rounded-full" style={{ width: 6, height: 6, backgroundColor: LINE }} />}
            </span>
            <span className="flex-1 min-w-0 text-[12px] truncate" style={{ color: r.lit ? INK : MUTED, fontWeight: r.lit ? 600 : 400 }}>{r.loc}</span>
            <span className="text-[10px] font-mono truncate hidden sm:inline shrink-0" style={{ color: MUTED }}>{r.type}</span>
            <span className="text-[9px] font-mono uppercase tracking-wider shrink-0 w-10 text-right" style={{ color: r.lit ? AMBER_600 : MUTED }}>{r.sev}</span>
          </div>
        ))}
      </div>
      <div className="mt-5 pt-5 border-t flex items-center justify-between" style={{ borderColor: LINE }}>
        <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: AMBER_600 }}>Pattern detected</span>
        <span className="text-[11px] font-mono" style={{ color: INK }}>3rd escalation · Store 7 · 14 days</span>
      </div>
    </InstrumentFrame>
  )
}

// 04 — OSHA 300A tally tiles.
function OshaInstrument() {
  const tiles = [
    { label: 'Recordables', value: '7', lit: true },
    { label: 'Lost days', value: '18' },
    { label: 'Cases', value: '5' },
  ]
  return (
    <InstrumentFrame caption="OSHA 300A · summary" foot="Tallies auto-populate — export any time">
      <div className="grid grid-cols-3 rounded-lg overflow-hidden border" style={{ borderColor: LINE }}>
        {tiles.map((t, i) => (
          <div
            key={t.label}
            className="px-3 py-4"
            style={{ borderRight: i < tiles.length - 1 ? `1px solid ${LINE}` : undefined }}
          >
            <div className="text-[8px] font-mono uppercase tracking-widest mb-1.5" style={{ color: MUTED }}>{t.label}</div>
            <div className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: '1.75rem', color: t.lit ? AMBER : INK }}>{t.value}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-2 flex-wrap">
        {['300 CSV', '300A CSV', '300A PDF', 'ITA export'].map((e) => (
          <span key={e} className="text-[9px] font-mono uppercase tracking-wider px-2 py-1 rounded-full" style={{ color: MUTED, border: `1px solid ${LINE}` }}>{e}</span>
        ))}
      </div>
    </InstrumentFrame>
  )
}

const INSTRUMENTS: Record<string, () => JSX.Element> = {
  incidents: IntakeInstrument,
  voice: VoiceInstrument,
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

      {PILLARS.map((pillar, i) => (
        <PillarRow key={pillar.id} pillar={pillar} index={i} />
      ))}
    </>
  )
}

// ── Coverage recap ─────────────────────────────────────────────────────────

function GlyphBars() {
  return (
    <div className="flex items-end gap-1 h-6">
      {[10, 16, 12, 22, 14].map((h, i) => (
        <span key={i} className="w-[3px] rounded-full" style={{ height: h, backgroundColor: i === 3 ? AMBER : LINE }} />
      ))}
    </div>
  )
}
function GlyphWave() {
  return (
    <div className="flex items-end gap-[3px] h-6">
      {[0.4, 0.8, 0.5, 1, 0.6, 0.85, 0.45].map((v, i) => (
        <span key={i} className="w-[2.5px] rounded-full" style={{ height: `${v * 100}%`, backgroundColor: i === 3 ? AMBER : LINE }} />
      ))}
    </div>
  )
}
function GlyphBrain() {
  return (
    <div className="flex flex-col gap-1 items-end">
      {[0, 1, 2].map((i) => (
        <span key={i} className="flex items-center gap-1">
          <span className="rounded-full" style={{ width: 4, height: 4, backgroundColor: i === 0 ? AMBER : MUTED }} />
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
        <span key={i} className="h-[2px] rounded-full" style={{ width: w, backgroundColor: i === 0 ? AMBER : LINE }} />
      ))}
    </div>
  )
}
function GlyphStack() {
  return (
    <div className="relative w-5 h-6">
      {[0, 1, 2].map((i) => (
        <span key={i} className="absolute rounded-sm border" style={{ width: 14, height: 16, left: i * 3, top: i * 2, borderColor: i === 0 ? AMBER : LINE, backgroundColor: BG }} />
      ))}
    </div>
  )
}
function GlyphDots() {
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
    id: 'incidents',
    icon: ShieldAlert,
    title: 'Incident reporting',
    caption: 'A magic link per location — photo evidence, witness capture, an anonymous channel, and a defensible chain of custody.',
    glyph: GlyphBars,
  },
  {
    id: 'voice',
    icon: Mic,
    title: 'Voice intake',
    caption: 'Tap Dictate and talk it through — transcribed in real time and filled for review before it submits.',
    glyph: GlyphWave,
  },
  {
    id: 'analysis',
    icon: Brain,
    title: 'IR analysis',
    caption: 'Suggested categorization and severity on every incident, with cross-incident pattern detection for your team.',
    glyph: GlyphBrain,
  },
  {
    id: 'osha',
    icon: ClipboardList,
    title: 'OSHA 300 / 300A',
    caption: 'Recordable tracking tied to intake — tallies auto-populate, print or export an audit-ready 300A any time.',
    glyph: GlyphLog,
  },
  {
    id: 'resources',
    icon: FileText,
    title: 'HR resource hub',
    caption: 'Editable templates — offer letters, PIPs, terminations, severance — and 50+ job descriptions across industries.',
    glyph: GlyphStack,
  },
  {
    id: 'states',
    icon: MapPin,
    title: 'State-by-state guides',
    caption: 'Pay transparency, leave, sick time, and termination rules for all 50 states + DC, updated as legislation changes.',
    glyph: GlyphDots,
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
            Six tools, one bundle. Each stands on its own; together they cover
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
