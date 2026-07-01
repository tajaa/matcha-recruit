import { useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { ComplianceMockup } from '../../components/landing/ComplianceProductMockup'
import { PricingContactModal } from '../../components/PricingContactModal'
import { ComplianceHeroAnimation } from './ComplianceHeroAnimation'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

// ---------------------------------------------------------------------------
// Four-pillar product model. Matcha Compliance is sold standalone (like
// Matcha-lite): jurisdictional compliance + handbook audit + policy management
// + credentialing, each a real, shipping feature (built for Matcha-X). Each
// pillar renders a full app-window mockup (ComplianceMockup) beneath its copy.
// Copy is kept accurate deliberately — see the guardrail notes per pillar.
// ---------------------------------------------------------------------------

type Screen = 'jurisdiction' | 'handbook' | 'policy' | 'credential'

type Pillar = {
  id: string
  number: string
  title: string
  tagline: string
  description: string
  deliverables: string[]
  screen: Screen
}

const PILLARS: Pillar[] = [
  {
    id: 'jurisdiction',
    number: '01',
    title: 'Jurisdictional Compliance',
    tagline: 'Every rule that governs each location, resolved.',
    description:
      'Add a location and Matcha assembles the full federal → state → county → city requirement stack that applies to it, de-conflicts the overlaps, and keeps watching for change. This is the robust engine at the core of the product — structured data, a curated repository, and grounded AI research when the books are thin.',
    deliverables: [
      'Federal → state → county → city requirement stack, per location',
      'Preemption engine resolves overlapping rules to the one that governs',
      'Grounded legislation watch flags new and amended law before it takes effect',
      'Every gap becomes an assignable action with an owner, due date, and SLA',
      'Wage-violation alerts — minimum wage, overtime, pay transparency',
      'Ask compliance anything — answered with citations to the governing rule',
    ],
    screen: 'jurisdiction',
  },
  {
    id: 'handbook-audit',
    number: '02',
    title: 'Handbook Audit',
    tagline: 'Find the gaps before an auditor does.',
    description:
      'Upload an employee handbook and pick the operating state. Matcha extracts each section and grades it against that state’s requirements — surfacing what’s missing, what’s weak, and what good looks like. Informational, not legal advice; one state per run.',
    deliverables: [
      'Upload a handbook (PDF) and choose the operating state',
      'AI extracts each section and grades it against that state’s requirements',
      'Gaps ranked critical / important / recommended, each with a citation',
      '“What good looks like” guidance for every missing or weak section',
      'Exportable PDF report to hand to counsel or leadership',
    ],
    screen: 'handbook',
  },
  {
    id: 'policy-management',
    number: '03',
    title: 'Policy Management',
    tagline: 'Draft, store, and keep policies current.',
    description:
      'A living policy library. Draft a new policy from a topic and jurisdiction with grounded AI, or bring your own — then track each one from draft to active with review dates that don’t slip. Gap suggestions surface the policies you’re missing, mined from your own incident and case patterns.',
    deliverables: [
      'Create from text, or upload existing PDF / DOCX (auto text-extracted)',
      'AI drafts jurisdiction-grounded policy language with citations',
      'Category taxonomy — HR, compliance, safety, HIPAA, clinical, and more',
      'Draft → active → archived lifecycle with effective and review dates',
      'Gap suggestions surfaced from your own incident and ER case patterns',
    ],
    screen: 'policy',
  },
  {
    id: 'credentialing',
    number: '04',
    title: 'Credentialing',
    tagline: 'The right credentials, tracked to the date.',
    description:
      'Define the credentials each role needs in each jurisdiction — researched for you — then let Matcha assign them to every employee automatically and verify the documents themselves. License numbers and expirations are read straight off the uploaded file, and expiring credentials are flagged in-app.',
    deliverables: [
      'Required credentials per role and jurisdiction, AI-researched',
      'Requirements auto-assigned to each employee at hire and on HRIS sync',
      'Upload license documents — OCR extracts the number and expiration',
      'Admin approve / reject with a per-employee requirement checklist',
      'Expiration badges flag expired, ≤30-day, and ≤90-day credentials',
    ],
    screen: 'credential',
  },
]

export default function CompliancePage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} mode="consultation" />
      <ComplianceTicker />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onContactClick={() => setIsPricingOpen(true)} />

      <main>
        {PILLARS.map(p => (
          <PillarSection key={p.id} pillar={p} />
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
              Standalone compliance platform
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
            className="mt-5 sm:mt-6 mx-auto max-w-xl text-base sm:text-lg px-2"
            style={{ color: MUTED, lineHeight: 1.55 }}
          >
            Four systems, one product: jurisdiction-aware compliance tracking,
            handbook auditing, policy management, and credentialing — assembled
            into the compliance platform your team actually runs on.
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
// Pillar section — editorial copy (heading + description + deliverables) above
// a full-width product-window mockup for that pillar.
// ---------------------------------------------------------------------------

function PillarSection({ pillar }: { pillar: Pillar }) {
  return (
    <section id={pillar.id} className="py-20 sm:py-28 md:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="grid lg:grid-cols-[1fr_1fr] gap-8 lg:gap-16 items-start mb-12 sm:mb-16">
          <div className="max-w-xl">
            <div className="text-[11px] uppercase tracking-[0.2em] font-mono mb-6" style={{ color: MUTED }}>
              {pillar.number} — {pillar.title}
            </div>
            <h2
              className="tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(2.25rem, 5vw, 4rem)',
                lineHeight: 1.02,
              }}
            >
              {pillar.tagline}
            </h2>
          </div>

          <div className="max-w-xl lg:pt-2">
            <p className="text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
              {pillar.description}
            </p>

            <div className="mt-8 pt-6 border-t" style={{ borderColor: LINE }}>
              <div className="text-[10.5px] uppercase tracking-[0.2em] font-mono mb-4" style={{ color: MUTED }}>
                What’s included
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
        </div>

        {/* Full-width product-window mockup */}
        <ComplianceMockup screen={pillar.screen} />
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
          See the whole compliance stack.
        </h2>
        <p className="mt-4 text-lg sm:text-xl" style={{ color: MUTED, lineHeight: 1.6 }}>
          Tell us where you operate and how many people you employ. We’ll review
          your account, then walk you through compliance, handbooks, policies, and
          credentialing — the way they’ll work for you.
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
