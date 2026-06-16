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
    id: 'radar',
    number: '01',
    title: 'Renewal Risk Radar',
    tagline: 'See the renewal before it hits your desk.',
    description:
      'Every client you put on Matcha feeds a live signal stream — turnover trends, lost workdays, near misses, and behavioral incidents — that we score into a single renewal-risk band per account. You walk into renewal prep already knowing which books are deteriorating, why, and where. Drill into any client by location or department, watch the period-over-period deltas, and download a Workforce Stabilization Kit you can hand the employer before the carrier ever re-rates them.',
    deliverables: [
      'Per-client risk band — Critical / Elevated / Stable',
      'Turnover, lost-workday, near-miss, and behavioral-incident signals',
      'Location- and department-level deep dives with trend deltas',
      'Workforce Stabilization Kit with prioritized recommendations',
      'Early warning months ahead of the carrier re-rate',
    ],
    highlight:
      'Workforce instability predicts the claim before the claim predicts the premium. The radar puts that signal in your hands first.',
    engagement: [
      { label: 'Bands', value: '3 tiers' },
      { label: 'Cadence', value: 'Live' },
      { label: 'Output', value: 'Stabilization kit' },
    ],
  },
  {
    id: 'wc',
    number: '02',
    title: "Workers' Comp Portfolio",
    tagline: 'Loss control across the whole book, sorted by risk.',
    description:
      'Stop chasing loss runs one client at a time. Matcha rolls every employer\'s safety data into a single portfolio view — TRIR, DART rate, recordable cases, and lost days, banded from critical to good — so you can triage your book in seconds. Sort by deterioration to find the accounts that need a loss-control conversation now, and see net premium exposure per client so you know which interventions actually move the needle.',
    deliverables: [
      'TRIR and DART rate computed per client',
      'Recordable cases and lost-day counts at a glance',
      'Severity banding — critical / at-risk / fair / good',
      'Net premium exposure per account',
      'Sort-by-risk triage across the entire book',
    ],
    highlight:
      'One screen ranks every client by safety deterioration — so the loss-control call goes to the account that needs it, not the one that shouts loudest.',
    engagement: [
      { label: 'Metrics', value: 'TRIR / DART' },
      { label: 'View', value: 'Whole book' },
      { label: 'Triage', value: 'By risk' },
    ],
  },
  {
    id: 'benefits',
    number: '03',
    title: 'Benefits Eligibility & Premium-Leak Detection',
    tagline: 'Find the money your clients are quietly losing.',
    description:
      'Matcha ingests each client\'s roster — via Finch or a CSV — and cross-references it against benefits enrollment to surface two problems employers almost never catch on their own: new hires drifting past their enrollment window, and terminated employees still carrying active health deductions. The first is a compliance gap; the second is a live premium leak we quantify in dollars per month. Nudge the client\'s HR directly from the exception, then resolve or dismiss.',
    deliverables: [
      'New-hire enrollment-gap detection with a window countdown',
      'Termination premium-leak detection, quantified in $/month',
      'Source-agnostic roster ingest — Finch or CSV',
      'One-click "Ping Client HR" nudge from any exception',
      'Resolve / dismiss workflow with an audit trail',
    ],
    highlight:
      'A terminated employee still on the plan is a leak you can put a dollar figure on — and bring to the client as found money, not a fire drill.',
    engagement: [
      { label: 'Source', value: 'Finch + CSV' },
      { label: 'Flags', value: 'Gaps + leaks' },
      { label: 'Unit', value: '$ / month' },
    ],
  },
  {
    id: 'command',
    number: '04',
    title: 'Book-of-Business Command Center',
    tagline: 'Every account, every signal, one queue.',
    description:
      'The dashboard is your whole book on one screen — total clients, headcount across the portfolio, at-risk count, and compliance posture per account. The Action Center turns the underlying signals into a worked queue: unread risk alerts with badges, and positive milestones like incident-free streaks or a TRIR below benchmark. Each one comes with AI-drafted outreach in a celebratory, advisory, or urgent tone, so a flagged signal becomes a client conversation in a click — not a blank email.',
    deliverables: [
      'Portfolio dashboard — clients, headcount, at-risk count, posture',
      'Unified action queue with unread risk-alert badges',
      'Positive milestones — incident-free streaks, TRIR below benchmark',
      'AI-drafted outreach in celebratory / advisory / urgent tone',
      'Handbook-coverage reporting to spot weak HR infrastructure',
    ],
    highlight:
      'Good news is outreach too. The command center surfaces the wins worth a call, not just the fires worth a worry.',
    engagement: [
      { label: 'Queue', value: 'Unified' },
      { label: 'Outreach', value: 'AI-drafted' },
      { label: 'Tone', value: '3 modes' },
    ],
  },
]

const PROCESS_STEPS = [
  {
    number: '01',
    title: 'Deploy',
    blurb: 'Stand up Matcha across your clients with seat pools, branded referral links, and a tracked onboarding pipeline — no per-client billing admin.',
  },
  {
    number: '02',
    title: 'Aggregate',
    blurb: 'Workforce, safety, and benefits data from every employer rolls up into one book-of-business view automatically.',
  },
  {
    number: '03',
    title: 'Surface',
    blurb: 'The radar flags renewal risk, the portfolio ranks loss control, and eligibility scans quantify premium leaks — per client.',
  },
  {
    number: '04',
    title: 'Act',
    blurb: 'AI-drafted outreach turns each signal into a client conversation, with the talking points already written.',
  },
]

// Capability specs — what the book-of-business layer gives a broker, not
// traction claims. Broker is a new distribution channel; no client-count metrics.
const HERO_STATS = [
  { label: 'Whole book', value: '1 view' },
  { label: 'Renewal signals', value: 'Live' },
  { label: 'Premium leaks', value: '$/mo' },
  { label: 'Client setup', value: 'Self-serve' },
]

const MODELS = [
  {
    name: 'Seat pools',
    blurb: 'Allocate Matcha Lite and Matcha-X seats across your book, track committed vs. redeemed, and provision clients without per-account billing.',
    suits: 'Managed deployment',
  },
  {
    name: 'Referral revenue share',
    blurb: 'Branded, expiring referral tokens for Matcha Lite self-serve. Choose who covers the subscription — you or the employer — and track redemptions.',
    suits: 'Self-serve distribution',
  },
  {
    name: 'Team & onboarding',
    blurb: 'Invite your team with owner / admin / member roles, run a draft-to-active onboarding pipeline, and preconfigure the modules each client gets.',
    suits: 'Multi-user brokerages',
  },
]

const BROKERS_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Service',
  name: 'Matcha for Brokers',
  url: 'https://hey-matcha.com/brokers',
  description:
    'A book-of-business intelligence layer for insurance and benefits brokers — renewal risk radar, workers\' comp loss-control portfolio, benefits premium-leak detection, and AI-drafted client outreach.',
  serviceType: 'Insurance brokerage software',
  hasOfferCatalog: {
    '@type': 'OfferCatalog',
    name: 'Broker Tools',
    itemListElement: [
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Renewal Risk Radar' } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: "Workers' Comp Portfolio" } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Benefits Premium-Leak Detection' } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Book-of-Business Command Center' } },
    ],
  },
}

export default function BrokersPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: "Matcha for Brokers | Renewal Risk Radar & Book-of-Business Intelligence",
    description:
      "Give your clients HR, safety, and compliance software — and get the intelligence layer back. Renewal risk radar, workers' comp loss control, benefits premium-leak detection, and AI-drafted outreach across your whole book.",
    canonical: 'https://hey-matcha.com/brokers',
    jsonLd: BROKERS_JSON_LD,
    noindex: true, // unlisted — reachable by direct link only, kept out of search indexes
  })

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onBookClick={() => setIsPricingOpen(true)} />

      <main>
        <Positioning />
        {PILLARS.map((p, i) => (
          <PillarSection key={p.id} pillar={p} reverse={i % 2 === 1} />
        ))}
        <Process />
        <Distribution onPricingClick={() => setIsPricingOpen(true)} />
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
                For insurance &amp; benefits brokers
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
              Put Matcha in front of your clients for HR, safety, and compliance — and get back what no carrier portal gives you: a live read on renewal risk, loss control, and premium leaks across every account you manage.
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
                    style={{ color: '#e4ded2', fontSize: 'clamp(28px, 3.4vw, 42px)' }}
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

function Positioning() {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-2 gap-12 md:gap-20 items-start">
          <div className="max-w-md">
            <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
              The model
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2.25rem, 4vw, 3.5rem)', lineHeight: 1.05 }}
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
                <li>HR records &amp; handbooks</li>
                <li>Incident reporting &amp; OSHA</li>
                <li>Compliance &amp; risk insights</li>
                <li>Benefits administration</li>
              </ul>
            </div>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                You see
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Renewal risk per account</li>
                <li>Loss-control ranking across the book</li>
                <li>Premium leaks in dollars</li>
                <li>Outreach moments, AI-drafted</li>
              </ul>
            </div>
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
                What you get
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
            How it works
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2.25rem, 4vw, 3.5rem)', lineHeight: 1.05 }}
          >
            Deploy once. Read the book continuously.
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

function Distribution({ onPricingClick }: { onPricingClick: () => void }) {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="max-w-xl mb-14">
          <div className="text-[11px] uppercase tracking-wider font-mono mb-4" style={{ color: MUTED }}>
            Distribution
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2.25rem, 4vw, 3.5rem)', lineHeight: 1.05 }}
          >
            Get your book onto Matcha, your way.
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
            Book a Walkthrough
          </button>
        </div>
      </div>
    </section>
  )
}
