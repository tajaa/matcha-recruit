import { useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type Testimonial = {
  quote: string
  author: string
  title: string
  company: string
}

type EngagementDetail = { label: string; value: string }

type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  deliverables: string[]
  testimonial: Testimonial
  engagement: EngagementDetail[]
}

const PILLARS: Pillar[] = [
  {
    id: 'hr',
    number: '01',
    title: 'HR Consulting',
    tagline: 'People strategy, with precision.',
    description:
      'HR infrastructure built by senior practitioners — the kind of work that usually lands in a CHRO\u2019s inbox their first week. Designed for companies that have outgrown ad-hoc policies but aren\u2019t ready to hire a full in-house team. We embed for the duration, deliver the artifacts, and hand off to your team with playbooks.',
    deliverables: [
      'Compensation frameworks and pay-equity analysis',
      'Multi-state handbook drafting and remediation',
      'Performance programs and organizational design',
      'Hiring, termination, and classification review',
      'Advisory retainers with standing senior access',
    ],
    testimonial: {
      quote:
        'Matcha\u2019s HR team built our entire people function in six weeks — the kind of work we\u2019d have hired a full-time CHRO for.',
      author: 'Sarah Chen',
      title: 'CEO',
      company: 'Aurora Biotech',
    },
    engagement: [
      { label: 'Duration', value: '6 weeks' },
      { label: 'Scope', value: 'Full HR buildout' },
      { label: 'Outcome', value: 'Audit-ready' },
    ],
  },
  {
    id: 'grc',
    number: '02',
    title: 'GRC Consulting',
    tagline: 'Governance, risk, and compliance.',
    description:
      'Jurisdiction-aware governance frameworks for regulated industries. We run full gap analyses, build compliance programs, and prepare teams for audits under CMS, Joint Commission, OSHA, DOL, and state boards. Our engagements end with a written baseline you can hand to counsel or the board.',
    deliverables: [
      'Regulatory gap analysis across all operating jurisdictions',
      'Risk assessments with statistical modeling and peer benchmarks',
      'Compliance program design for healthcare and manufacturing',
      'Audit preparation and remediation',
      'Credential and license program setup',
    ],
    testimonial: {
      quote:
        'They ran a full-stack compliance gap analysis across seven states in ten days. We closed forty-two findings before our SOC 2 renewal.',
      author: 'Mark Weiss',
      title: 'COO',
      company: 'Helix Health',
    },
    engagement: [
      { label: 'Duration', value: '10 days' },
      { label: 'Coverage', value: '7 states' },
      { label: 'Outcome', value: '42 gaps closed' },
    ],
  },
  {
    id: 'er',
    number: '03',
    title: 'Employee Relations',
    tagline: 'Investigations, handled with care.',
    description:
      'Workplace investigations and employee-relations case strategy run by experienced employment specialists. Defensible documentation, counsel-ready memos, and pattern detection across cases. We take the load off your in-house team when the stakes are too high for an ad-hoc approach.',
    deliverables: [
      'Independent workplace investigations',
      'Conflict resolution and mediation',
      'Separation risk review and pre-termination intel',
      'ER case strategy and documentation',
      'Cross-case pattern detection and remediation playbooks',
    ],
    testimonial: {
      quote:
        'We had three interlocking cases we couldn\u2019t untangle internally. Matcha ran the investigation end-to-end with a defensible memo in two weeks.',
      author: 'Jennifer Park',
      title: 'General Counsel',
      company: 'Stratify Labs',
    },
    engagement: [
      { label: 'Duration', value: '2 weeks' },
      { label: 'Scope', value: '3 interlocking cases' },
      { label: 'Outcome', value: 'Counsel-ready memo' },
    ],
  },
  {
    id: 'ai',
    number: '04',
    title: 'AI Integration Analysis',
    tagline: 'AI, integrated responsibly.',
    description:
      'Independent evaluation of the AI tools you\u2019re considering or already running. We surface compliance, bias, privacy, and operational risk before they become production incidents. Engagement ends with a board-ready brief and a deployment playbook you can actually follow.',
    deliverables: [
      'Multi-dimensional tool evaluation across accuracy, bias, cost, latency, and privacy',
      'Bias and compliance audits against SOC 2, HIPAA, and sector standards',
      'Build-vs-buy analysis and AI roadmapping',
      'Deployment playbooks and change-management',
      'Board-ready AI risk reporting',
    ],
    testimonial: {
      quote:
        'They flagged a BIPA violation in a vendor we almost signed a $400k contract with. We saved a lot more than the engagement fee.',
      author: 'David Riaz',
      title: 'CTO',
      company: 'Northwind Ops',
    },
    engagement: [
      { label: 'Duration', value: '3 weeks' },
      { label: 'Scope', value: '5 AI vendors' },
      { label: 'Outcome', value: 'Risk cleared' },
    ],
  },
]

const PROCESS_STEPS = [
  {
    number: '01',
    title: 'Discovery',
    blurb: 'Scope, stakeholders, and the questions that actually matter. Usually one week.',
  },
  {
    number: '02',
    title: 'Diagnosis',
    blurb: 'Full gap analysis, risk scoring, and a written baseline you can trust.',
  },
  {
    number: '03',
    title: 'Design',
    blurb: 'Frameworks, policies, remediation plans, and defensible documentation.',
  },
  {
    number: '04',
    title: 'Delivery',
    blurb: 'Implementation, training, and optional retainer handoff for ongoing coverage.',
  },
]

const HERO_STATS = [
  { label: 'Engagements delivered', value: '140+' },
  { label: 'Jurisdictions covered', value: '32' },
  { label: 'Median response', value: '4h' },
  { label: 'Client retention', value: '94%' },
]

export default function ServicesPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onPricingClick={() => setIsPricingOpen(true)} />

      <Hero />

      <main>
        {PILLARS.map((p, i) => (
          <PillarSection key={p.id} pillar={p} reverse={i % 2 === 1} />
        ))}
        <Process />
        <EngagementModels onPricingClick={() => setIsPricingOpen(true)} />
      </main>

      <MarketingFooter />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero() {
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
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#86efac' }} />
              <span className="text-[11px] uppercase tracking-wider font-medium">
                Four practice areas
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
              Consulting that protects.
            </h1>
            <p
              className="mt-6 max-w-lg"
              style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
            >
              Bespoke HR, governance, employee relations, and AI integration consulting — led by senior practitioners who\u2019ve been in the room when it mattered.
            </p>
            <div className="mt-10 flex items-center gap-4 flex-wrap">
              <Link
                to="/login"
                className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
                style={{ backgroundColor: INK, color: BG }}
              >
                Book a Consultation
              </Link>
              <Link
                to="/matcha-work"
                className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
                style={{ color: INK }}
              >
                See Matcha Work →
              </Link>
            </div>
          </div>

          {/* Stat grid */}
          <div
            className="rounded-xl overflow-hidden border grid grid-cols-2"
            style={{
              borderColor: 'rgba(0,0,0,0.08)',
              backgroundColor: '#0e0d0b',
              boxShadow: '0 40px 80px -20px rgba(31, 29, 26, 0.28)',
            }}
          >
            {HERO_STATS.map((s, i) => {
              const border: React.CSSProperties = {
                borderColor: 'rgba(255,255,255,0.06)',
              }
              if (i % 2 === 0) border.borderRight = '1px solid rgba(255,255,255,0.06)'
              if (i < 2) border.borderBottom = '1px solid rgba(255,255,255,0.06)'
              return (
                <div
                  key={s.label}
                  className="p-6 sm:p-8 flex flex-col relative"
                  style={border}
                >
                  <div
                    className="text-[9px] font-mono uppercase tracking-wider"
                    style={{ color: '#6a737d' }}
                  >
                    {s.label}
                  </div>
                  <div
                    className="mt-2 font-light font-mono leading-none tabular-nums"
                    style={{ color: '#e4ded2', fontSize: 'clamp(36px, 4.5vw, 54px)' }}
                  >
                    {s.value}
                  </div>
                  <div
                    className="mt-2 h-[2px] rounded-full"
                    style={{ backgroundColor: 'rgba(215,186,125,0.4)', width: '32px' }}
                  />
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pillar section
// ---------------------------------------------------------------------------

function PillarSection({ pillar, reverse }: { pillar: Pillar; reverse: boolean }) {
  return (
    <section id={pillar.id} className="py-28 sm:py-36 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div
          className={`grid md:grid-cols-[1.15fr_1fr] gap-12 md:gap-20 items-start ${
            reverse ? 'md:[&>*:first-child]:order-2' : ''
          }`}
        >
          {/* Left: editorial text */}
          <div className="max-w-xl">
            <div
              className="text-[11px] uppercase tracking-[0.2em] font-mono mb-6"
              style={{ color: MUTED }}
            >
              {pillar.number} — {pillar.title}
            </div>
            <h2
              className="tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(2.25rem, 4.5vw, 4rem)',
                lineHeight: 1.02,
              }}
            >
              {pillar.tagline}
            </h2>
            <p className="mt-6 text-[17px]" style={{ color: MUTED, lineHeight: 1.65 }}>
              {pillar.description}
            </p>

            <div
              className="mt-10 pt-6 border-t"
              style={{ borderColor: LINE }}
            >
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                Deliverables
              </div>
              <ol className="space-y-2.5">
                {pillar.deliverables.map((d, i) => (
                  <li key={d} className="flex items-baseline gap-4 text-[15px]" style={{ color: INK }}>
                    <span
                      className="font-mono tabular-nums text-[11px] shrink-0 w-5"
                      style={{ color: MUTED }}
                    >
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span style={{ lineHeight: 1.5 }}>{d}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          {/* Right: pull quote + engagement card */}
          <div className="md:pt-8">
            <figure
              className="relative pl-6 pr-2"
              style={{ borderLeft: `2px solid ${INK}` }}
            >
              <blockquote
                className="italic leading-snug"
                style={{
                  fontFamily: DISPLAY,
                  fontWeight: 400,
                  color: INK,
                  fontSize: 'clamp(1.35rem, 2.2vw, 1.75rem)',
                  lineHeight: 1.25,
                }}
              >
                &ldquo;{pillar.testimonial.quote}&rdquo;
              </blockquote>
              <figcaption className="mt-5 text-sm" style={{ color: MUTED }}>
                <div className="font-medium" style={{ color: INK }}>
                  {pillar.testimonial.author}
                </div>
                <div>
                  {pillar.testimonial.title}, {pillar.testimonial.company}
                </div>
              </figcaption>
            </figure>

            <div
              className="mt-10 grid grid-cols-3 gap-px rounded-lg overflow-hidden"
              style={{ backgroundColor: LINE }}
            >
              {pillar.engagement.map((d) => (
                <div
                  key={d.label}
                  className="p-4 flex flex-col"
                  style={{ backgroundColor: BG }}
                >
                  <span className="text-[9px] uppercase tracking-[0.2em] font-mono" style={{ color: MUTED }}>
                    {d.label}
                  </span>
                  <span
                    className="mt-2 text-[15px]"
                    style={{ color: INK, fontFamily: DISPLAY, fontWeight: 500, lineHeight: 1.2 }}
                  >
                    {d.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Process
// ---------------------------------------------------------------------------

function Process() {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="max-w-xl mb-14">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
            How we work
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2.25rem, 4vw, 3.5rem)', lineHeight: 1.05 }}
          >
            Four stages, honestly scoped.
          </h2>
        </div>

        <div className="grid md:grid-cols-4 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
          {PROCESS_STEPS.map((step) => (
            <div key={step.number} className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[11px] font-mono uppercase tracking-wider mb-6" style={{ color: MUTED }}>
                {step.number}
              </div>
              <h3
                className="text-2xl tracking-tight"
                style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK, lineHeight: 1.1 }}
              >
                {step.title}
              </h3>
              <p className="mt-4 text-[14px]" style={{ color: MUTED, lineHeight: 1.6 }}>
                {step.blurb}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Engagement models
// ---------------------------------------------------------------------------

const MODELS = [
  {
    name: 'Project',
    blurb: 'Fixed scope, fixed timeline. Best for gap analyses, handbook rewrites, audit prep, or tool evaluations.',
    suits: 'Discrete initiatives',
  },
  {
    name: 'Retainer',
    blurb: 'Ongoing senior access on a monthly basis. Standing hours across all four practice areas.',
    suits: 'Companies without in-house HR/GRC',
  },
  {
    name: 'Advisory',
    blurb: 'Board and executive counsel for high-stakes decisions, investigations, and AI deployments.',
    suits: 'Founders and GCs',
  },
]

function EngagementModels({ onPricingClick }: { onPricingClick: () => void }) {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="max-w-xl mb-14">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
            Engagement
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2.25rem, 4vw, 3.5rem)', lineHeight: 1.05 }}
          >
            How we work with you.
          </h2>
        </div>

        <div className="grid md:grid-cols-3 gap-8">
          {MODELS.map((model) => (
            <div
              key={model.name}
              className="p-8 rounded-xl border"
              style={{ borderColor: LINE, backgroundColor: 'rgba(31,29,26,0.02)' }}
            >
              <h3
                className="text-3xl tracking-tight"
                style={{ fontFamily: DISPLAY, fontWeight: 500, color: INK }}
              >
                {model.name}
              </h3>
              <p className="mt-4 text-[14px]" style={{ color: MUTED, lineHeight: 1.6 }}>
                {model.blurb}
              </p>
              <div className="mt-6 pt-4 border-t text-[11px] uppercase tracking-wider font-mono" style={{ borderColor: LINE, color: MUTED }}>
                Suits · {model.suits}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-14 text-center">
          <button
            onClick={onPricingClick}
            className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: INK, color: BG }}
          >
            Book a Consultation
          </button>
        </div>
      </div>
    </section>
  )
}
