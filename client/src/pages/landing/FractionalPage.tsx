import { useState } from 'react'

import { useSEO } from '../../hooks/useSEO'
import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { PricingContactModal } from '../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

type EngagementDetail = { label: string; value: string }

type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  deliverables: string[]
  highlight: string
  engagement: EngagementDetail[]
}

const PILLARS: Pillar[] = [
  {
    id: 'chro',
    number: '01',
    title: 'Fractional CHRO',
    tagline: 'Senior HR leadership, without the full-time cost.',
    description:
      'A seasoned CHRO embedded in your leadership team on a part-time basis. We own the people strategy, sit in board meetings, and build the function alongside you — without the six-figure salary, equity dilution, or eighteen-month search. Designed for Series A–C companies and PE-backed businesses that need executive HR but aren’t ready to commit to a permanent hire.',
    deliverables: [
      'People strategy and OKR alignment with executive team',
      'Board and investor HR reporting',
      'Compensation philosophy and equity benchmarking',
      'Executive hiring, offboarding, and succession planning',
      'Culture audits and organizational design',
    ],
    highlight:
      'Executive HR leadership on a standing retainer — strategy, board presence, and people ops all in one engagement, at a fraction of the full-time cost.',
    engagement: [
      { label: 'Commitment', value: '2 days/wk' },
      { label: 'Min term', value: '3 months' },
      { label: 'Best for', value: 'Series A–C' },
    ],
  },
  {
    id: 'director',
    number: '02',
    title: 'Fractional HR Director',
    tagline: 'Day-to-day HR, handled.',
    description:
      'Operational HR leadership embedded in your team on a scheduled basis. We run the people function end-to-end — policies, hiring processes, manager coaching, performance cycles, and compliance — so your founders and operators can focus on the business. The right fit for companies with 15–150 employees who need consistent HR presence without a full-time headcount.',
    deliverables: [
      'Multi-state employee handbook drafting and maintenance',
      'Hiring process design, offer letters, and onboarding',
      'Manager coaching and performance management rollout',
      'Termination risk review and offboarding',
      'HR compliance calendar and audit readiness',
    ],
    highlight:
      'Consistent HR presence — policies, hiring, performance, and compliance — without adding headcount to your org chart.',
    engagement: [
      { label: 'Commitment', value: '1–3 days/wk' },
      { label: 'Min term', value: '2 months' },
      { label: 'Best for', value: '15–150 employees' },
    ],
  },
  {
    id: 'buildout',
    number: '03',
    title: 'HR Function Buildout',
    tagline: 'Build the people function from scratch.',
    description:
      'A structured engagement to stand up your entire HR infrastructure. We scope the function, write every policy, select and implement your HRIS, and design your performance and compensation programs — then hand off to your team with playbooks they can actually run. This is the engagement for companies that have been operating on informal people ops and need to catch up fast.',
    deliverables: [
      'HR infrastructure assessment and gap analysis',
      'Employee handbook and core policy suite',
      'HRIS selection, configuration, and data migration',
      'Compensation framework and job architecture',
      'Performance review cycle design and manager training',
    ],
    highlight:
      'Full HR function built in eight weeks — handbook, HRIS, comp framework, and performance cycle — handed off with the playbooks to run it.',
    engagement: [
      { label: 'Duration', value: '8 weeks' },
      { label: 'Scope', value: 'Full buildout' },
      { label: 'Outcome', value: 'Audit-ready' },
    ],
  },
  {
    id: 'reset',
    number: '04',
    title: 'HR Audit & Reset',
    tagline: 'Find the gaps before they find you.',
    description:
      'A diagnostic engagement for companies that have grown quickly and suspect their HR infrastructure hasn’t kept up. We audit your existing policies, employment practices, classification decisions, and compliance posture across every jurisdiction you operate in — then deliver a prioritized remediation plan with a clear owner and timeline for each finding.',
    deliverables: [
      'Employment practices audit across all operating states',
      'Worker classification review (exempt/non-exempt, contractor/employee)',
      'Handbook and policy gap analysis against current law',
      'I-9, wage-and-hour, and leave compliance review',
      'Prioritized remediation roadmap with risk scoring',
    ],
    highlight:
      'Full employment practices audit across every jurisdiction you operate in — gaps prioritized by risk, with a written remediation plan your counsel can act on.',
    engagement: [
      { label: 'Duration', value: '2–3 weeks' },
      { label: 'Scope', value: 'All jurisdictions' },
      { label: 'Outcome', value: 'Risk-scored report' },
    ],
  },
]

const PROCESS_STEPS = [
  {
    number: '01',
    title: 'Scope',
    blurb: 'We map your current state, headcount, jurisdictions, and the gaps that carry the most risk.',
  },
  {
    number: '02',
    title: 'Embed',
    blurb: 'Your fractional HR lead joins team meetings, Slack, and your existing workflows — no ramp-up lag.',
  },
  {
    number: '03',
    title: 'Build',
    blurb: 'Policies, programs, and infrastructure built to your stage, not a generic template.',
  },
  {
    number: '04',
    title: 'Handoff',
    blurb: 'Playbooks, training, and optional retainer continuity so nothing breaks when the engagement ends.',
  },
]

const HERO_STATS = [
  { label: 'Companies supported', value: '80+' },
  { label: 'Avg. employee count', value: '45' },
  { label: 'Policies written', value: '600+' },
  { label: 'Jurisdictions covered', value: '32' },
]

const MODELS = [
  {
    name: 'Monthly retainer',
    blurb: 'Scheduled weekly hours with a dedicated fractional HR lead. Scales up or down each quarter.',
    suits: 'Ongoing HR function',
  },
  {
    name: 'Project',
    blurb: 'Fixed scope, fixed timeline. Best for buildouts, audits, and handbook rewrites.',
    suits: 'Discrete initiatives',
  },
  {
    name: 'Advisory',
    blurb: 'Senior HR counsel for high-stakes decisions — hiring freezes, RIFs, investigations, M&A due diligence.',
    suits: 'Founders and GCs',
  },
]

const FRACTIONAL_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'ProfessionalService',
  name: 'Matcha Fractional HR',
  url: 'https://hey-matcha.com/fractional',
  description:
    'Senior HR leadership on a fractional basis — Fractional CHRO, HR Director, function buildouts, and employment audits for Series A–C companies.',
  hasOfferCatalog: {
    '@type': 'OfferCatalog',
    name: 'Fractional HR Services',
    itemListElement: [
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Fractional CHRO' } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Fractional HR Director' } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'HR Function Buildout' } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'HR Audit & Reset' } },
    ],
  },
}

export default function FractionalPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: 'Fractional HR Services | Fractional CHRO & HR Director | Matcha',
    description:
      'Senior HR leadership on a fractional basis — Fractional CHRO, HR Director, function buildouts, and employment audits for Series A–C companies. No full-time headcount.',
    canonical: 'https://hey-matcha.com/fractional',
    jsonLd: FRACTIONAL_JSON_LD,
  })

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onBookClick={() => setIsPricingOpen(true)} />

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
              <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#86efac' }} />
              <span className="text-[11px] uppercase tracking-wider font-medium">
                Four engagement models
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
              HR leadership, fractional.
            </h1>
            <p
              className="mt-6 max-w-lg"
              style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
            >
              Senior HR and people-ops professionals embedded in your company on a part-time basis — building the function, running the day-to-day, and getting out of the way when you don’t need us.
            </p>
            <div className="mt-10 flex items-center gap-4 flex-wrap">
              <button
                onClick={onBookClick}
                className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
                style={{ backgroundColor: INK, color: BG }}
              >
                Book a Consultation
              </button>
            </div>
          </div>

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
                <div key={s.label} className="p-6 sm:p-8 flex flex-col relative" style={border}>
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

function PillarSection({ pillar, reverse }: { pillar: Pillar; reverse: boolean }) {
  return (
    <section id={pillar.id} className="py-28 sm:py-36 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div
          className={`grid md:grid-cols-[1.15fr_1fr] gap-12 md:gap-20 items-start ${
            reverse ? 'md:[&>*:first-child]:order-2' : ''
          }`}
        >
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

            <div className="mt-10 pt-6 border-t" style={{ borderColor: LINE }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                Deliverables
              </div>
              <ol className="space-y-2.5">
                {pillar.deliverables.map((d, i) => (
                  <li key={d} className="flex items-baseline gap-4 text-[15px]" style={{ color: INK }}>
                    <span className="font-mono tabular-nums text-[11px] shrink-0 w-5" style={{ color: MUTED }}>
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <span style={{ lineHeight: 1.5 }}>{d}</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="md:pt-8">
            <div className="relative pl-6 pr-2" style={{ borderLeft: `2px solid ${INK}` }}>
              <p
                className="leading-snug"
                style={{
                  fontFamily: DISPLAY,
                  fontWeight: 400,
                  color: INK,
                  fontSize: 'clamp(1.35rem, 2.2vw, 1.75rem)',
                  lineHeight: 1.25,
                }}
              >
                {pillar.highlight}
              </p>
            </div>

            <div
              className="mt-10 grid grid-cols-3 gap-px rounded-lg overflow-hidden"
              style={{ backgroundColor: LINE }}
            >
              {pillar.engagement.map((d) => (
                <div key={d.label} className="p-4 flex flex-col" style={{ backgroundColor: BG }}>
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
            Embedded from day one.
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
              <div
                className="mt-6 pt-4 border-t text-[11px] uppercase tracking-wider font-mono"
                style={{ borderColor: LINE, color: MUTED }}
              >
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
