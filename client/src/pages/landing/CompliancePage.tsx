import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Scale, Layers, Radar, ClipboardCheck, AlertTriangle, MessageSquare } from 'lucide-react'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { JurisdictionCascade } from '../../components/landing/JurisdictionCascade'
import { TimelineConstructor } from '../../components/landing/TimelineConstructor'
import { FocusSection, useScrollFocus } from '../../components/landing/ScrollFocus'
import { PricingContactModal } from '../../components/PricingContactModal'
import { ComplianceHeroAnimation } from './ComplianceHeroAnimation'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const FEATURES: { id: string; icon: typeof Scale; title: string; caption: string; visual: React.ComponentType }[] = [
  {
    id: 'jurisdiction',
    icon: Scale,
    title: 'Jurisdiction-aware checks',
    caption:
      'Every federal, state, and local requirement that applies to each of your locations — resolved from structured data, a curated repository, and live AI research when the books are thin.',
    visual: LayerPulse,
  },
  {
    id: 'preemption',
    icon: Layers,
    title: 'Preemption engine',
    caption:
      'Overlapping federal / state / local rules stacked and de-conflicted, so you see the one standard that actually governs — not six contradictory ones.',
    visual: StackResolve,
  },
  {
    id: 'legislation',
    icon: Radar,
    title: 'Legislation watch',
    caption:
      'Grounded monitoring surfaces new and amended law before it takes effect, with the delta against your current posture flagged for review.',
    visual: RadarSweep,
  },
  {
    id: 'actions',
    icon: ClipboardCheck,
    title: 'Action plans & reminders',
    caption:
      'Each gap becomes an assignable action with an owner, due date, and SLA. Overdue items escalate — nothing lapses quietly.',
    visual: ChecklistCascade,
  },
  {
    id: 'wage',
    icon: AlertTriangle,
    title: 'Wage-violation alerts',
    caption:
      'Minimum-wage, overtime, and pay-transparency exposure detected per location and surfaced against the governing rate.',
    visual: SeverityGauge,
  },
  {
    id: 'ask',
    icon: MessageSquare,
    title: 'Ask compliance, anything',
    caption:
      'A grounded assistant answers "what applies to us in X?" with citations to the requirements behind the answer — not a generic chatbot.',
    visual: ChatPulse,
  },
]

export default function CompliancePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const focus = useScrollFocus()

  const sections = [
    <JurisdictionSection key="jurisdiction" />,
    <TimelineSection key="timeline" />,
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

      <CtaBand onContactClick={() => setIsPricingOpen(true)} />
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
              Jurisdiction-aware compliance
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
            Matcha Compliance.
          </h1>
          <p
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-[15px] sm:text-base px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Track every federal, state, and local requirement that applies to your
            team. Preemption-aware checks, live legislation watch, and AI-built
            action plans — so nothing lapses before you know about it.
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
          <p className="mt-4 text-[12px]" style={{ color: MUTED }}>
            Onboarding is white-glove — new accounts are reviewed before activation.
          </p>
        </div>

        {/* Live compliance-monitor panel inside the hero frame */}
        <div className="mt-12 sm:mt-16 flex justify-center -mx-2 sm:mx-auto">
          <ComplianceHeroAnimation />
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Jurisdiction stack
// ---------------------------------------------------------------------------

function JurisdictionSection() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-2xl mb-10 sm:mb-12">
          <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
            Built from your locations up
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            Every jurisdiction you operate in, stacked.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Add a location and Matcha assembles the full federal → state → county →
            city requirement stack that governs it, then resolves the overlaps so
            you read one answer instead of arguing six.
          </p>
        </div>

        <div className="max-w-5xl mx-auto -mx-2 sm:mx-auto">
          <div
            className="relative rounded-lg sm:rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{ boxShadow: '0 40px 80px -25px rgba(31, 29, 26, 0.3)', borderColor: 'rgba(0,0,0,0.08)' }}
          >
            <JurisdictionCascade />
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Signal → action plan timeline
// ---------------------------------------------------------------------------

const TIMELINE_BULLETS = [
  { label: 'Signal', desc: 'Grounded legislation watch catches new and amended law in the jurisdictions you operate in.' },
  { label: 'Impact', desc: 'Each change is scored against your current posture — what lapses, who it affects, by when.' },
  { label: 'Action plan', desc: 'A concrete plan is drafted: the steps to close the gap, mapped to owners and due dates.' },
  { label: 'Reminders', desc: 'Open items are chased on an SLA; overdue work escalates before the effective date arrives.' },
]

function TimelineSection() {
  return (
    <section className="py-16 sm:py-24 md:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div>
            <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
              Legislation watch
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 4vw, 3rem)', lineHeight: 1.05 }}
            >
              From signal to action plan, before it takes effect.
            </h2>
            <p className="mt-4 text-base" style={{ color: MUTED, lineHeight: 1.6 }}>
              The work that usually surfaces in an audit — a rule changed, nobody
              caught it — runs continuously instead. Watch turns into impact, impact
              into a plan, plan into reminders.
            </p>
            <ul className="mt-7 space-y-5">
              {TIMELINE_BULLETS.map(item => (
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
            <div
              className="relative rounded-lg sm:rounded-xl overflow-hidden ring-1 shadow-2xl"
              style={{ boxShadow: '0 40px 80px -25px rgba(31, 29, 26, 0.3)', borderColor: 'rgba(0,0,0,0.08)' }}
            >
              <TimelineConstructor />
            </div>
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
          <div className="text-[11px] uppercase tracking-wider font-medium mb-3 sm:mb-4" style={{ color: MUTED }}>
            What's inside
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3.25rem)', lineHeight: 1.05 }}
          >
            The full compliance surface — and nothing you don't need.
          </h2>
          <p className="mt-4 sm:mt-5 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            Matcha Compliance is the compliance system on its own — priced by
            headcount and the number of jurisdictions you operate in. No bundle,
            no modules you'll never open.
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
// Closing CTA band
// ---------------------------------------------------------------------------

function CtaBand({ onContactClick }: { onContactClick: () => void }) {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-2xl mx-auto px-5 sm:px-10 text-center">
        <h2
          className="tracking-tight"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 5vw, 3rem)', lineHeight: 1.05 }}
        >
          See your jurisdiction stack.
        </h2>
        <p className="mt-4 text-base sm:text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us where you operate and how many people you employ. We'll review
          your account, then walk you through the requirements that apply to you.
        </p>
        <div className="mt-8 flex justify-center">
          <button
            onClick={onContactClick}
            className="inline-flex items-center justify-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
            style={{ backgroundColor: INK, color: BG }}
          >
            Contact us
          </button>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Per-card mini animations — looped while in view, idle otherwise.
// ---------------------------------------------------------------------------

function LayerPulse() {
  return (
    <div className="flex flex-col gap-[3px]">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.25 }}
          whileInView={{ opacity: [0.25, 0.9, 0.25] }}
          viewport={{ once: false }}
          transition={{ duration: 2, repeat: Infinity, delay: i * 0.3, ease: 'easeInOut' }}
          className="h-[3px] rounded-full"
          style={{ width: `${28 - i * 6}px`, backgroundColor: INK }}
        />
      ))}
    </div>
  )
}

function StackResolve() {
  return (
    <div className="relative w-10 h-9">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ x: i * 4, y: -i * 3, opacity: 0.4 }}
          whileInView={{ x: 0, y: 0, opacity: i === 0 ? 1 : 0.15 }}
          viewport={{ once: false }}
          transition={{ duration: 1.4, repeat: Infinity, repeatType: 'reverse', delay: i * 0.1, ease: 'easeInOut' }}
          className="absolute inset-0 rounded-sm"
          style={{ border: `1px solid ${INK}`, backgroundColor: BG }}
        />
      ))}
    </div>
  )
}

function RadarSweep() {
  return (
    <div className="relative w-9 h-9 rounded-full" style={{ border: `1px solid rgba(31,29,26,0.25)` }}>
      <motion.div
        className="absolute inset-0 rounded-full"
        style={{ background: `conic-gradient(from 0deg, ${INK}33, transparent 35%)` }}
        animate={{ rotate: 360 }}
        transition={{ duration: 2.4, repeat: Infinity, ease: 'linear' }}
      />
      <div className="absolute left-1/2 top-1/2 w-1 h-1 -ml-0.5 -mt-0.5 rounded-full" style={{ backgroundColor: INK }} />
    </div>
  )
}

function ChecklistCascade() {
  return (
    <div className="flex flex-col gap-1">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.3 }}
          whileInView={{ opacity: [0.3, 1, 1] }}
          viewport={{ once: false }}
          transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.4, ease: 'easeOut', times: [0, 0.4, 1] }}
          className="flex items-center gap-1.5"
        >
          <div className="w-2.5 h-2.5 rounded-sm flex items-center justify-center" style={{ border: `1px solid ${INK}`, backgroundColor: INK }}>
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

function SeverityGauge() {
  const levels = ['#86efac', '#d7ba7d', '#ce9178']
  return (
    <div className="flex flex-col gap-1">
      {levels.map((c, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.25 }}
          whileInView={{ opacity: [0.25, 1, 0.25] }}
          viewport={{ once: false }}
          transition={{ duration: 2, repeat: Infinity, delay: i * 0.55, ease: 'easeInOut' }}
          className="flex items-center gap-1.5"
        >
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: c }} />
          <div className="h-[2px] rounded-full" style={{ width: `${12 + i * 8}px`, backgroundColor: 'rgba(31,29,26,0.2)' }} />
        </motion.div>
      ))}
    </div>
  )
}

function ChatPulse() {
  return (
    <div className="flex items-center gap-[3px]">
      {[0, 1, 2].map((i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0.25 }}
          whileInView={{ opacity: [0.25, 1, 0.25] }}
          viewport={{ once: false }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.18, ease: 'easeInOut' }}
          className="w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: INK }}
        />
      ))}
    </div>
  )
}
