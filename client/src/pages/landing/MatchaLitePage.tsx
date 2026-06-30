import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion, useInView } from 'framer-motion'
import { ShieldAlert, FileText, MapPin, Bell, Brain, ClipboardList } from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { MatchaLiteMockup } from '../../components/landing/MatchaLiteMockup'
import { IrAnalysisPanel } from '../../components/landing/IrAnalysisPanel'
import { RiskInsightsHero } from '../../components/landing/RiskInsightsHero'
import { FocusSection, useScrollFocus } from '../../components/landing/ScrollFocus'
import { PricingContactModal } from '../../components/PricingContactModal'

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
  const focus = useScrollFocus()

  const sections = [
    <RiskInsightsShowcase key="risk" />,
    <IrAnalysisSection key="ir" />,
    <OshaSection key="osha" />,
    <FeatureGrid key="grid" />,
  ]

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        {sections.map((node, i) => (
          <FocusSection key={i} idx={i} focus={focus}>{node}</FocusSection>
        ))}
      </main>

      <MarketingFooter />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero({ onContactClick }: { onContactClick: () => void }) {
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
              HR risk + compliance, bundled
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
            Matcha Daily.
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
// Risk Insights showcase — live-moving dashboard hero
// ---------------------------------------------------------------------------

function RiskInsightsShowcase() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-10 sm:mb-12">
          <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
            Live risk dashboard
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            Every incident, rolled into one risk picture.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            A location-by-location risk matrix, a live incident trend, and your
            workers-comp posture — TRIR, DART, lost days — all auto-computed from
            intake. The numbers a safety review actually asks for.
          </p>
        </div>

        <div className="max-w-5xl mx-auto -mx-2 sm:mx-auto">
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
          <div className="min-w-0">
            <IrAnalysisPanel />
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// OSHA 300 section
// ---------------------------------------------------------------------------

const OSHA_ROWS = [
  { date: 'May 12', loc: 'Atlanta — Store 7', type: 'Strain/sprain', cls: 'Days away', days: 3, recordable: true },
  { date: 'Apr 28', loc: 'Phoenix — Warehouse', type: 'Laceration', cls: 'Restricted', days: 1, recordable: true },
  { date: 'Apr 14', loc: 'Dallas — Store 3', type: 'Burn (minor)', cls: 'Med. treatment', days: 2, recordable: true },
  { date: 'Mar 31', loc: 'Seattle — Store 12', type: 'Eye irritation', cls: 'Days away', days: 2, recordable: true },
  { date: 'Mar 15', loc: 'Denver — HQ', type: 'Slip/fall', cls: 'First aid', days: 0, recordable: false },
]

const OSHA_BULLETS = [
  { label: 'Automatic recordability', desc: 'Every incident screened against 29 CFR 1904 — first aid vs. medical treatment, restricted duty, days away, loss of consciousness — recordable or not, flagged for you.' },
  { label: 'Forms 300, 300A & 301', desc: 'The full set generated from one intake: the 300 log, the 300A annual summary, and a 301 incident report per case.' },
  { label: 'Days away, restricted & transfer', desc: 'DART rate, lost-day and restricted-duty counts roll up automatically from each incident’s status.' },
  { label: 'Electronic ITA submission', desc: 'Establishments required to e-file get an export formatted for OSHA’s Injury Tracking Application.' },
  { label: 'Per-location logs + posting reminders', desc: 'A separate log per establishment, rolled into one view, with Feb 1–Apr 30 posting nudges.' },
]

function OshaSection() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div className="order-2 lg:order-1 min-w-0">
            <OshaLogPanel />
          </div>
          <div className="order-1 lg:order-2">
            <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
              OSHA 300 · 300A · 301
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 4vw, 3rem)', lineHeight: 1.05 }}
            >
              OSHA logs, auto-filled.
            </h2>
            <p className="mt-4 text-base" style={{ color: MUTED, lineHeight: 1.6 }}>
              Every incident is screened against the 1904 criteria, classified, and tallied — no manual re-entry, no spreadsheet. The 300, 300A and 301 generate themselves, and e-file straight to OSHA’s ITA when you’re required to.
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
  const COLS = '64px 1fr 104px 100px 40px 52px'
  return (
    <div ref={ref} className="rounded-xl overflow-x-auto border font-sans" style={{ borderColor: 'rgba(63,63,70,0.5)', backgroundColor: '#0d0d10' }}>
    <div className="min-w-[520px]">
      <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <div className="flex items-center gap-2.5">
          <span className="text-sm font-bold" style={{ color: '#f4f4f5' }}>OSHA 300 Log</span>
          <div className="flex items-center gap-1">
            {['300', '300A', '301'].map((t, i) => (
              <span key={t} className="px-1.5 py-0.5 rounded text-[8px] font-bold tracking-wider"
                style={i === 0
                  ? { backgroundColor: '#27272a', color: '#e4e4e7', border: '1px solid #3f3f46' }
                  : { color: '#52525b', border: '1px solid transparent' }}>{t}</span>
            ))}
          </div>
        </div>
        <span className="px-2 py-1 rounded text-[8px]" style={{ backgroundColor: '#18181b', border: '1px solid #27272a', color: '#71717a' }}>Export 300A</span>
      </div>
      <div className="flex items-center gap-3 px-5 py-2.5 border-b" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <span className="text-[8px] font-mono uppercase tracking-widest" style={{ color: '#52525b' }}>Recordables YTD <span style={{ color: '#e4e4e7' }}>4</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span className="text-[8px] font-mono uppercase tracking-widest" style={{ color: '#52525b' }}>DART <span style={{ color: '#c98a3e' }}>2.1</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span className="text-[8px] font-mono uppercase tracking-widest" style={{ color: '#52525b' }}>Restricted <span style={{ color: '#e4e4e7' }}>2d</span></span>
        <span style={{ color: '#3f3f46' }}>·</span>
        <span className="text-[8px] font-mono uppercase tracking-widest" style={{ color: '#2f9e74' }}>Auto-classified</span>
      </div>
      <div className="grid px-5 py-2" style={{ gridTemplateColumns: COLS }}>
        {['Date', 'Location', 'Type', 'Determination', 'Days', 'Rec.'].map(h => (
          <span key={h} className="text-[7px] font-mono font-bold uppercase tracking-widest" style={{ color: '#52525b' }}>{h}</span>
        ))}
      </div>
      {OSHA_ROWS.map((row, i) => (
        <motion.div
          key={row.date + row.loc}
          initial={{ opacity: 0, x: -8 }}
          animate={inView ? { opacity: 1, x: 0 } : { opacity: 0 }}
          transition={{ delay: i * 0.1 + 0.2 }}
          className="grid px-5 py-3 border-t items-center"
          style={{ gridTemplateColumns: COLS, borderColor: 'rgba(39,39,42,0.6)' }}
        >
          <span className="text-[10px] font-mono" style={{ color: '#52525b' }}>{row.date}</span>
          <span className="text-[12px] truncate pr-2" style={{ color: '#e4e4e7' }}>{row.loc}</span>
          <span className="text-[10px]" style={{ color: '#a1a1aa' }}>{row.type}</span>
          <span className="text-[9px] font-medium uppercase tracking-wide" style={{ color: row.recordable ? '#c98a3e' : '#3f3f46' }}>{row.cls}</span>
          <span className="text-[10px] font-mono" style={{ color: '#a1a1aa' }}>{row.days}d</span>
          <span className="text-[9px] font-bold uppercase tracking-wider" style={{ color: row.recordable ? '#c98a3e' : '#3f3f46' }}>
            {row.recordable ? '● Yes' : '○ No'}
          </span>
        </motion.div>
      ))}
      <div className="flex items-center justify-between px-5 py-3 border-t" style={{ borderColor: 'rgba(39,39,42,0.5)' }}>
        <span className="text-[10px]" style={{ color: '#52525b' }}>Forms 300 · 300A · 301 generated · 300A posted Feb 1</span>
        <span className="text-[8px] font-medium px-2 py-0.5 rounded" style={{ color: '#6ee7b7', backgroundColor: 'rgba(16,185,129,0.12)', border: '1px solid rgba(16,185,129,0.25)' }}>
          ITA e-file ready
        </span>
      </div>
    </div>
    </div>
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
