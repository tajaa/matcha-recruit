import { useRef, useState } from 'react'
import { motion, useInView } from 'framer-motion'

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
  visual: 'risk-curve' | 'wc' | 'command'
}

const PILLARS: Pillar[] = [
  {
    id: 'risk-curve',
    number: '01',
    title: 'Risk Curve',
    tagline: 'See the renewal before it hits your desk.',
    description:
      'Every client you put on Matcha feeds a live signal stream — lost workdays, near misses, property damage, and behavioral incidents — that we roll into an exposure-weighted risk curve for the whole book. You walk into renewal prep already knowing which accounts are deteriorating, why, and where. Matcha doesn\'t just flag the trend — it arms you with risk alerts and concrete suggestions for resolving it, so you can step in and support the client well before the carrier re-rates them.',
    deliverables: [
      'Exposure-weighted loss curve, modeled headcount- or premium-basis',
      'Aggregate risk band per account — Strong / Adequate / Developing / Exposed',
      'Lost-workday, near-miss, property-damage, and behavioral-incident signals',
      'Risk alerts with suggested actions for resolving negative trends',
      'Early warning months ahead of the carrier re-rate',
    ],
    highlight:
      'A loss curve you can act on beats a loss run you can only read. See the exposure shift, get the suggested fix, make the call before renewal is impacted.',
    engagement: [
      { label: 'Bands', value: '4 tiers' },
      { label: 'Cadence', value: 'Live' },
      { label: 'Output', value: 'Risk alerts' },
    ],
    visual: 'risk-curve',
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
      'Net premium exposure per account, and rolled up across the book',
    ],
    highlight:
      'One screen ranks every client by safety deterioration — so the loss-control call goes to the account that needs it, not the one that shouts loudest.',
    engagement: [
      { label: 'Metrics', value: 'TRIR / DART' },
      { label: 'View', value: 'Whole book' },
      { label: 'Triage', value: 'By risk' },
    ],
    visual: 'wc',
  },
  {
    id: 'command',
    number: '03',
    title: 'Book-of-Business Command Center',
    tagline: 'Every account, every signal, one queue.',
    description:
      'The dashboard is your whole book on one screen — total clients, headcount across the portfolio, at-risk count, and compliance posture per account. The Action Center turns the underlying signals into a worked queue: unread risk alerts, ranked by severity, each with AI-drafted outreach in an advisory or urgent tone. A flagged trend becomes a client conversation with the talking points already written — not a blank email you have to draft from scratch.',
    deliverables: [
      'Portfolio dashboard — clients, headcount, at-risk count, posture',
      'Unified action queue with unread risk-alert badges',
      'Risk alerts ranked by severity across the whole book',
      'AI-drafted outreach in advisory / urgent tone',
      'Handbook-coverage reporting to spot weak HR infrastructure',
    ],
    highlight:
      'Every alert is a client conversation waiting to happen. The command center hands you the talking points so the fix starts before the renewal does.',
    engagement: [
      { label: 'Queue', value: 'Unified' },
      { label: 'Outreach', value: 'AI-drafted' },
      { label: 'Tone', value: '2 modes' },
    ],
    visual: 'command',
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
    blurb: 'Safety and loss data from every employer rolls up into one book-of-business view automatically.',
  },
  {
    number: '03',
    title: 'Surface',
    blurb: 'The risk curve flags deteriorating accounts, and the WC portfolio ranks loss control across the book — per account.',
  },
  {
    number: '04',
    title: 'Act',
    blurb: 'AI-drafted outreach turns each flagged issue into a client conversation, with the talking points already written.',
  },
]

// Hero risk-curve card — an animated read of a book of business. Fictional clients;
// the values illustrate the signal types (TRIR, DART, loss trend), not real accounts.
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
    blurb: 'Invite your team with owner / admin / member roles, and run every client from submitted to live on a draft-to-active onboarding pipeline.',
    suits: 'Multi-user brokerages',
  },
]

const BROKERS_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Service',
  name: 'Matcha for Brokers',
  url: 'https://hey-matcha.com/brokers',
  description:
    'A book-of-business intelligence layer for P&C brokers — exposure-weighted risk curve, workers\' comp loss-control portfolio, and AI-drafted client outreach.',
  serviceType: 'Insurance brokerage software',
  hasOfferCatalog: {
    '@type': 'OfferCatalog',
    name: 'Broker Tools',
    itemListElement: [
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Book Risk Curve' } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: "Workers' Comp Portfolio" } },
      { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Book-of-Business Command Center' } },
    ],
  },
}

export default function BrokersPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: "Matcha for Brokers | Book Risk Curve & Book-of-Business Intelligence",
    description:
      "Give your P&C clients a live safety intake system — and get the intelligence layer back. Exposure-weighted risk curve, workers' comp loss control, and AI-drafted outreach across your whole book.",
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
              Matcha Lite replaces the client's static, paperwork-driven safety process with a live intake system woven into how they already work. While the client runs safer, more compliant operations, you get back what no carrier portal gives you: real-time performance metrics — TRIR, DART, loss trends — plus risk alerts and suggested actions, across every account you manage.
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

// Animated hero card — a live read of a book of business. A scanline sweeps the
// client rows; risk bands on the volatile accounts pulse to draw the eye.
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
      {/* Header */}
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
          <span
            className="text-[10px] font-mono uppercase tracking-[0.18em]"
            style={{ color: '#e4ded2' }}
          >
            Book Risk Curve
          </span>
        </div>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          Book · 24 clients
        </span>
      </div>

      {/* Rows + scanline */}
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
                    animate={
                      inView && volatile
                        ? { opacity: [1, 0.45, 1] }
                        : { opacity: 1 }
                    }
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

      {/* Footer summary */}
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

// Per-pillar mini mockup cards. Fictional illustrative data, styled to match the
// hero risk-curve card (dark, mono labels) — not live product screenshots.

const WC_ROWS: { client: string; trir: string; dart: string; band: 'critical' | 'at_risk' | 'fair' | 'good' }[] = [
  { client: 'Northgate Logistics', trir: '6.2', dart: '3.4', band: 'critical' },
  { client: 'Cedar Valley Mfg', trir: '3.1', dart: '1.8', band: 'at_risk' },
  { client: 'Harbor Foods Co', trir: '1.4', dart: '1.1', band: 'fair' },
  { client: 'Summit Builders', trir: '0.9', dart: '0.4', band: 'good' },
]

const WC_BAND_COLOR: Record<string, string> = {
  critical: '#ff6b6b',
  at_risk: '#f5b545',
  fair: '#8fd6ef',
  good: '#6ee7a8',
}

const WC_BAND_LABEL: Record<string, string> = {
  critical: 'Critical',
  at_risk: 'At risk',
  fair: 'Fair',
  good: 'Good',
}

function WcPortfolioVisual() {
  return (
    <div
      className="relative rounded-xl overflow-hidden border"
      style={{ borderColor: 'rgba(0,0,0,0.08)', backgroundColor: '#0e0d0b', boxShadow: '0 30px 60px -18px rgba(31, 29, 26, 0.24)' }}
    >
      <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: '#e4ded2' }}>
          WC Portfolio
        </span>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          Sorted worst-first
        </span>
      </div>
      <ul>
        {WC_ROWS.map((r) => (
          <li
            key={r.client}
            className="px-5 py-3 flex items-center justify-between gap-3 border-b"
            style={{ borderColor: 'rgba(255,255,255,0.045)' }}
          >
            <div className="min-w-0 text-[13px] truncate" style={{ color: 'rgba(245,242,237,0.9)' }}>
              {r.client}
            </div>
            <div className="flex items-center gap-4 shrink-0">
              <span className="text-[10px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.5)' }}>
                TRIR {r.trir}
              </span>
              <span className="text-[10px] font-mono tabular-nums" style={{ color: 'rgba(245,242,237,0.5)' }}>
                DART {r.dart}
              </span>
              <span
                className="text-[9px] font-medium uppercase tracking-wider px-2 py-1 rounded"
                style={{ color: WC_BAND_COLOR[r.band], backgroundColor: `${WC_BAND_COLOR[r.band]}1f` }}
              >
                {WC_BAND_LABEL[r.band]}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

const COMMAND_ALERTS: { client: string; issue: string; tone: 'advisory' | 'urgent' }[] = [
  { client: 'Northgate Logistics', issue: 'TRIR trending up 3 months straight', tone: 'urgent' },
  { client: 'Cedar Valley Mfg', issue: 'Lost-day count above book average', tone: 'advisory' },
  { client: 'Atlas Care Group', issue: 'Near-miss reports up 40% this quarter', tone: 'advisory' },
]

const COMMAND_TONE_COLOR: Record<string, string> = { advisory: '#f5b545', urgent: '#ff6b6b' }

function CommandCenterVisual() {
  return (
    <div
      className="relative rounded-xl overflow-hidden border"
      style={{ borderColor: 'rgba(0,0,0,0.08)', backgroundColor: '#0e0d0b', boxShadow: '0 30px 60px -18px rgba(31, 29, 26, 0.24)' }}
    >
      <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: '#e4ded2' }}>
          Action Center
        </span>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          {COMMAND_ALERTS.length} unread
        </span>
      </div>
      <ul>
        {COMMAND_ALERTS.map((a) => (
          <li
            key={a.client}
            className="px-5 py-3.5 flex items-start gap-3 border-b"
            style={{ borderColor: 'rgba(255,255,255,0.045)' }}
          >
            <span
              className="mt-1.5 w-1.5 h-1.5 rounded-full shrink-0"
              style={{ backgroundColor: COMMAND_TONE_COLOR[a.tone] }}
            />
            <div className="min-w-0 flex-1">
              <div className="text-[13px]" style={{ color: 'rgba(245,242,237,0.92)' }}>{a.client}</div>
              <div className="text-[11px] mt-0.5" style={{ color: 'rgba(245,242,237,0.45)' }}>{a.issue}</div>
            </div>
            <span
              className="text-[9px] font-medium uppercase tracking-wider px-2 py-1 rounded shrink-0"
              style={{ color: COMMAND_TONE_COLOR[a.tone], backgroundColor: `${COMMAND_TONE_COLOR[a.tone]}1f` }}
            >
              {a.tone}
            </span>
          </li>
        ))}
      </ul>
      <div className="px-5 py-3 text-[11px]" style={{ color: 'rgba(245,242,237,0.4)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        Outreach drafted for every flagged issue — advisory or urgent tone.
      </div>
    </div>
  )
}

function RiskCurveMiniVisual() {
  return (
    <div
      className="relative rounded-xl overflow-hidden border"
      style={{ borderColor: 'rgba(0,0,0,0.08)', backgroundColor: '#0e0d0b', boxShadow: '0 30px 60px -18px rgba(31, 29, 26, 0.24)' }}
    >
      <div className="px-5 py-4 flex items-center justify-between border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: '#e4ded2' }}>
          Loss Curve
        </span>
        <span className="text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          Exposure-weighted
        </span>
      </div>
      <div className="px-5 py-6">
        <svg viewBox="0 0 320 100" className="w-full h-24" preserveAspectRatio="none">
          <defs>
            <linearGradient id="lossCurveFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6ee7a8" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#6ee7a8" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path
            d="M0,88 C40,86 60,78 90,60 C120,42 140,34 180,24 C220,15 260,10 320,4 L320,100 L0,100 Z"
            fill="url(#lossCurveFill)"
          />
          <path
            d="M0,88 C40,86 60,78 90,60 C120,42 140,34 180,24 C220,15 260,10 320,4"
            fill="none"
            stroke="#6ee7a8"
            strokeWidth="1.5"
          />
        </svg>
        <div className="flex items-center justify-between mt-2 text-[9px] font-mono uppercase tracking-wider" style={{ color: '#6a737d' }}>
          <span>Low loss</span>
          <span>Annual loss ($)</span>
          <span>High loss</span>
        </div>
      </div>
      <div className="px-5 py-3.5 flex items-center gap-4 border-t" style={{ borderColor: 'rgba(255,255,255,0.045)', backgroundColor: 'rgba(255,255,255,0.015)' }}>
        {(['strong', 'adequate', 'developing', 'exposed'] as const).map((band) => (
          <div key={band} className="flex items-center gap-1.5">
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: band === 'strong' ? '#6ee7a8' : band === 'adequate' ? '#8fd6ef' : band === 'developing' ? '#f5b545' : '#ff6b6b' }}
            />
            <span className="text-[10px] font-mono capitalize" style={{ color: 'rgba(245,242,237,0.55)' }}>
              {band}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function PillarVisual({ kind }: { kind: Pillar['visual'] }) {
  if (kind === 'wc') return <WcPortfolioVisual />
  if (kind === 'command') return <CommandCenterVisual />
  return <RiskCurveMiniVisual />
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
                <li>Incidents</li>
                <li>IR Copilot</li>
                <li>Risk Insights</li>
                <li>Theme Analysis</li>
              </ul>
            </div>
            <div className="p-8" style={{ backgroundColor: BG }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                You see
              </div>
              <ul className="space-y-2.5 text-[15px]" style={{ color: INK }}>
                <li>Book-wide risk curve, weighted by exposure</li>
                <li>Loss-control ranking across the book</li>
                <li>Risk alerts, ranked by severity</li>
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
            <PillarVisual kind={pillar.visual} />

            <div className="mt-10 relative pl-6 pr-2" style={{ borderLeft: `2px solid ${INK}` }}>
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
