import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './landing/MarketingNav'
import MarketingFooter from './landing/MarketingFooter'
import { LazyMount } from './landing/LazyMount'
// import LandingIntro from '../components/landing/LandingIntro' // muted — WIP, revisit

const AgentReasoningAnimation = lazy(() => import('./landing/AgentReasoningAnimation'))
const ConvergenceAnimation = lazy(() =>
  import('./landing/animations/ConvergenceAnimation').then((m) => ({ default: m.ConvergenceAnimation })),
)
// Muted for now — revisit the mesh concept.
// const NeuralConvergenceAnimation = lazy(() =>
//   import('./landing/animations/NeuralConvergenceAnimation').then((m) => ({ default: m.NeuralConvergenceAnimation })),
// )
import { ANIMATION_BY_SIZZLE_ID } from './landing/animations'
import { EnforcementTotalsTicker } from '../components/landing/EnforcementTotalsTicker'
import { IrAnalysisPanel } from '../components/landing/IrAnalysisPanel'
import { PricingContactModal } from '../components/PricingContactModal'
import { useLandingMedia } from '../hooks/useLandingMedia'
import type { LandingMedia, LandingSizzleVideo, LandingCustomerLogo, LandingTestimonial } from '../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const HERO_HEADLINE = 'The Platform: Agentic Risk Management'
const HERO_SUBCOPY =
  'EHS, governance & compliance, and employee relations — usually three siloed systems. Matcha runs them on one platform, where every signal talks to the others.'

const DEFAULT_SIZZLES: LandingSizzleVideo[] = [
  {
    id: 'hr',
    title: 'People strategy, with precision.',
    caption:
      'Compensation, handbooks, performance programs, and organizational design — guided by seasoned HR practitioners.',
    url: null,
  },
  {
    id: 'grc',
    title: 'Governance, risk, and compliance.',
    caption:
      'Frameworks tailored to your jurisdiction, industry, and stage of growth. Built to scale, audit-ready from day one.',
    url: null,
  },
  {
    id: 'er',
    title: 'Employee relations, handled with care.',
    caption:
      'Workplace investigations, conflict resolution, and ER case strategy led by experienced employment specialists.',
    url: null,
  },
  {
    id: 'termination',
    title: 'Separation risk, mapped.',
    caption:
      'Pre-termination analysis across documentation, policy adherence, legal exposure, and consistency — so every separation decision is defensible.',
    url: null,
  },
]

export default function Landing() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const { data } = useLandingMedia()

  const sizzles = data.sizzle_videos.length > 0 ? data.sizzle_videos : DEFAULT_SIZZLES

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      {/* <LandingIntro> muted — WIP, revisit */}
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />
      <EnforcementTotalsTicker />

      <Hero data={data} onContactClick={() => setIsPricingOpen(true)} />

      <main>
        <ConvergenceSection />

        <IncidentIntakeSection />

        {sizzles.map((s, i) => (
          <ProductSizzle key={s.id} sizzle={s} reverse={i % 2 === 1} />
        ))}

        <Testimonials testimonials={data.testimonials} />
      </main>

      <MarketingFooter />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero({ data, onContactClick }: { data: LandingMedia; onContactClick: () => void }) {
  if (data.hero_video_url) return <VideoHero data={data} onContactClick={onContactClick} />
  return <AnimationHero data={data} onContactClick={onContactClick} />
}

// Full-bleed cinematic video with overlaid text
function VideoHero({ data, onContactClick }: { data: LandingMedia; onContactClick: () => void }) {
  return (
    <section className="relative w-full h-[100svh] min-h-[640px] overflow-hidden" style={{ backgroundColor: '#1a1a1a' }}>
      <video
        className="absolute inset-0 w-full h-full object-cover"
        src={data.hero_video_url ?? undefined}
        poster={data.hero_poster_url ?? undefined}
        autoPlay
        muted
        loop
        playsInline
      />
      <div
        className="absolute inset-0"
        style={{
          background:
            'linear-gradient(90deg, rgba(10,10,8,0.72) 0%, rgba(10,10,8,0.45) 35%, rgba(10,10,8,0) 70%)',
        }}
      />
      <div className="relative z-10 h-full max-w-[1440px] mx-auto px-6 sm:px-10 flex flex-col">
        <div className="flex-1 flex items-center">
          <div className="max-w-2xl pt-28">
            <h1
              className="text-white leading-[0.95] tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(2.5rem, 6vw, 5rem)' }}
            >
              {HERO_HEADLINE}
            </h1>
            <p className="mt-6 text-white/80 max-w-xl" style={{ fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.5 }}>
              {HERO_SUBCOPY}
            </p>
            <div className="mt-10 flex items-center gap-4">
              <button
                onClick={onContactClick}
                className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium bg-white hover:bg-white/90 transition-colors cursor-pointer"
                style={{ color: INK }}
              >
                Book a Consultation
              </button>
              <Link
                to="/services"
                className="inline-flex items-center h-12 text-[15px] text-white/80 hover:text-white transition-colors"
              >
                Explore services →
              </Link>
            </div>
          </div>
        </div>
        {data.customer_logos.length > 0 && (
          <div className="pb-10">
            <LogoStrip logos={data.customer_logos} dark />
          </div>
        )}
      </div>
    </section>
  )
}

// Ivory hero with compliance dashboard animation on the right
function AnimationHero({ data, onContactClick }: { data: LandingMedia; onContactClick: () => void }) {
  return (
    <section
      className="relative w-full sm:min-h-[100svh] overflow-hidden"
      style={{ backgroundColor: BG }}
    >
      {/* Subtle warm radial glow from the animation side */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 60% 80% at 80% 50%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 60%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-5 sm:px-10 pt-28 sm:pt-36 lg:pt-44 pb-12 sm:pb-16 sm:min-h-[100svh] flex flex-col">
        {/* Stacked layout — headline + CTAs centered up top, full-width animation card below */}
        <div className="flex-1 flex flex-col items-center text-center">
          <h1
            className="leading-[0.95] tracking-tight max-w-4xl"
            style={{
              fontFamily: DISPLAY,
              fontWeight: 400,
              color: INK,
              fontSize: 'clamp(2.25rem, 4.2vw, 3.75rem)',
            }}
          >
            {HERO_HEADLINE}
          </h1>
          <p
            className="mt-5 max-w-2xl"
            style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
          >
            {HERO_SUBCOPY}
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-4">
            <button
              onClick={onContactClick}
              className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90 cursor-pointer"
              style={{ backgroundColor: INK, color: BG }}
            >
              Book a Consultation
            </button>
            <Link
              to="/services"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Explore services →
            </Link>
          </div>

          {/* Wide animation card — hidden on mobile, 5-column tree unreadable below 640px */}
          <div className="hidden sm:flex mt-8 w-full overflow-hidden justify-center">
            <LazyMount minHeight={440} fallback={<div className="w-full max-w-[900px] mx-auto rounded-xl" style={{ height: 440, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}><Suspense fallback={<div className="w-full max-w-[900px] mx-auto rounded-xl" style={{ height: 440, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}><AgentReasoningAnimation /></Suspense></LazyMount>
          </div>

          {/* Mobile-only simplified static card */}
          <MobileHeroCard />
        </div>

        {/* Logo strip */}
        {data.customer_logos.length > 0 && (
          <div className="pt-10 mt-10 border-t" style={{ borderColor: LINE }}>
            <LogoStrip logos={data.customer_logos} />
          </div>
        )}
      </div>
    </section>
  )
}

const MOBILE_ROWS = [
  { label: 'Written WVP Plan', cite: '§6401.9(c)' },
  { label: 'Annual Training', cite: '§6401.9(e)' },
  { label: 'Violent Incident Log', cite: '§6401.9(f)' },
  { label: 'Hazard Assessment', cite: '§6401.9(c)(2)' },
  { label: 'Annual Review', cite: '§6401.9(d)' },
]

function MobileHeroCard() {
  return (
    <div
      className="sm:hidden mt-8 w-full rounded-xl overflow-hidden"
      style={{
        backgroundColor: '#0a0a08',
        border: '1px solid rgba(255,255,255,0.08)',
        boxShadow: '0 20px 40px -12px rgba(31, 29, 26, 0.25)',
      }}
    >
      <div
        className="px-4 py-3 flex items-center justify-between border-b"
        style={{ borderColor: 'rgba(255,255,255,0.06)' }}
      >
        <div>
          <div className="text-[10px] tracking-[0.18em] uppercase" style={{ color: 'rgba(255,255,255,0.45)' }}>
            CA · SB 553
          </div>
          <div className="text-[13px] mt-0.5" style={{ color: 'rgba(255,255,255,0.92)', fontFamily: DISPLAY }}>
            Workplace Violence Prevention
          </div>
        </div>
        <div
          className="text-[10px] font-medium px-2 py-1 rounded"
          style={{ color: '#ff6b6b', backgroundColor: 'rgba(255,107,107,0.12)' }}
        >
          5 GAPS
        </div>
      </div>
      <ul className="divide-y" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
        {MOBILE_ROWS.map((r, i) => (
          <li
            key={r.cite}
            className="px-4 py-3 flex items-center justify-between mobile-row-fade"
            style={{
              borderColor: 'rgba(255,255,255,0.04)',
              animationDelay: `${i * 120}ms`,
            }}
          >
            <div className="min-w-0 flex-1 pr-3">
              <div className="text-[13px] truncate" style={{ color: 'rgba(255,255,255,0.88)' }}>
                {r.label}
              </div>
              <div className="text-[11px] mt-0.5 font-mono" style={{ color: 'rgba(255,255,255,0.4)' }}>
                {r.cite}
              </div>
            </div>
            <span
              className="text-[10px] font-medium px-1.5 py-0.5 rounded"
              style={{ color: '#ff6b6b', backgroundColor: 'rgba(255,107,107,0.12)' }}
            >
              GAP
            </span>
          </li>
        ))}
      </ul>
      <style>{`
        .mobile-row-fade {
          opacity: 0;
          animation: mobileRowFade 0.5s ease-out forwards;
        }
        @keyframes mobileRowFade {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}

function LogoStrip({ logos, dark = false }: { logos: LandingCustomerLogo[]; dark?: boolean }) {
  return (
    <div className="flex items-center gap-10 sm:gap-14 flex-wrap opacity-70">
      {logos.map((logo) => (
        <img
          key={logo.name}
          src={logo.url}
          alt={logo.name}
          className="h-6 sm:h-7 w-auto object-contain"
          style={{
            filter: dark
              ? 'brightness(0) invert(1)'
              : 'brightness(0) saturate(100%) invert(10%)',
          }}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product sizzle
// ---------------------------------------------------------------------------

function ProductSizzle({ sizzle, reverse }: { sizzle: LandingSizzleVideo; reverse: boolean }) {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div
          className={`grid md:grid-cols-2 gap-10 md:gap-16 items-center ${
            reverse ? 'md:[&>*:first-child]:order-2' : ''
          }`}
        >
          <div className="max-w-xl">
            <h2
              className="tracking-tight"
              style={{
                fontFamily: DISPLAY,
                fontWeight: 400,
                color: INK,
                fontSize: 'clamp(2.25rem, 4vw, 3.5rem)',
                lineHeight: 1.05,
              }}
            >
              {sizzle.title}
            </h2>
            {sizzle.caption && (
              <p className="mt-5 text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
                {sizzle.caption}
              </p>
            )}
          </div>

          <SizzleVisual sizzle={sizzle} />
        </div>
      </div>
    </section>
  )
}

function SizzleVisual({ sizzle }: { sizzle: LandingSizzleVideo }) {
  const Animation = ANIMATION_BY_SIZZLE_ID[sizzle.id]
  return (
    <div
      className="relative rounded-xl overflow-hidden ring-1 shadow-2xl"
      style={{
        backgroundColor: '#151412',
        boxShadow: '0 40px 80px -20px rgba(31, 29, 26, 0.28)',
        borderColor: 'rgba(0,0,0,0.08)',
      }}
    >
      <div className="aspect-[16/10] w-full">
        {sizzle.url ? (
          <video
            className="w-full h-full object-cover"
            src={sizzle.url}
            autoPlay
            muted
            loop
            playsInline
          />
        ) : Animation ? (
          <LazyMount fallback={<div className="w-full h-full" style={{ backgroundColor: '#0e0d0b' }} />}>
            <Suspense fallback={<div className="w-full h-full" style={{ backgroundColor: '#0e0d0b' }} />}>
              <Animation />
            </Suspense>
          </LazyMount>
        ) : (
          <div
            className="w-full h-full flex items-center justify-center"
            style={{
              background:
                'linear-gradient(135deg, #2a2826 0%, #1f1d1a 60%, #14130f 100%)',
            }}
          >
            <span className="text-white/30 text-sm tracking-wide uppercase">
              Coming soon
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Convergence — the "EHS + GRC + ER on one platform" selling point
// ---------------------------------------------------------------------------

const CONVERGENCE_DOMAINS: { tag: string; title: string; blurb: string }[] = [
  {
    tag: 'EHS',
    title: 'Environmental, Health & Safety',
    blurb: 'Intelligent incident intake, theme analysis with pattern detection, OSHA logs, and hazard tracking for proactive safety.',
  },
  {
    tag: 'GRC',
    title: 'Governance, Risk & Compliance',
    blurb: 'Jurisdiction-aware compliance monitoring, policy gaps, and audit-ready frameworks.',
  },
  {
    tag: 'ER',
    title: 'Employee Relations',
    blurb: 'Investigations, progressive discipline, separation risk, and ER case strategy.',
  },
]

function ConvergenceSection() {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="max-w-3xl">
          <div className="text-[11px] uppercase tracking-wider font-medium mb-3" style={{ color: MUTED }}>
            One platform
          </div>
          <h2
            className="tracking-tight"
            style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 4vw, 3rem)', lineHeight: 1.05 }}
          >
            Three disciplines that finally talk to each other.
          </h2>
          <p className="mt-5 text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
            EHS, GRC, and employee relations are usually bought as separate tools that never share a record. On
            Matcha they run on one data model — a safety incident, a compliance gap, and an ER case all inform each
            other in real time, so risk surfaces before it compounds.
          </p>
        </div>

        {/* Animation card — one incident fanning out to all three domains.
            (Neural-mesh card muted for now — revisit.) */}
        <div className="mt-10 sm:mt-14">
          <LazyMount minHeight={480} fallback={<div className="w-full max-w-[900px] mx-auto rounded-xl" style={{ height: 480, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}>
            <Suspense fallback={<div className="w-full max-w-[900px] mx-auto rounded-xl" style={{ height: 480, backgroundColor: '#0a0a08', border: '1px solid rgba(255,255,255,0.08)' }} />}>
              <ConvergenceAnimation />
            </Suspense>
          </LazyMount>
        </div>

        <div className="mt-10 sm:mt-12 grid md:grid-cols-3 gap-px rounded-xl overflow-hidden" style={{ backgroundColor: LINE }}>
          {CONVERGENCE_DOMAINS.map((d) => (
            <div key={d.tag} className="flex flex-col p-6 sm:p-7" style={{ backgroundColor: BG }}>
              <span
                className="inline-flex items-center self-start text-[11px] font-mono font-medium px-2 py-1 rounded mb-4"
                style={{ color: INK, border: `1px solid ${LINE}` }}
              >
                {d.tag}
              </span>
              <h3 className="text-base font-medium" style={{ color: INK }}>{d.title}</h3>
              <p className="mt-2 text-sm" style={{ color: MUTED, lineHeight: 1.55 }}>{d.blurb}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Intelligent Incident Intake — categorization, severity, pattern detection
// ---------------------------------------------------------------------------

const INTAKE_BULLETS: { label: string; desc: string }[] = [
  {
    label: 'Categorization',
    desc: 'Behavioral, safety, property, or harassment — flagged for manager review the moment an incident is submitted.',
  },
  {
    label: 'Severity scoring',
    desc: 'Low / Medium / High with mandatory justification attached to every incident, reviewed and confirmed by your team.',
  },
  {
    label: 'Pattern detection',
    desc: 'Cross-incident analysis surfaces recurring patterns across locations, shifts, and case types before they compound.',
  },
]

function IncidentIntakeSection() {
  return (
    <section className="py-20 sm:py-28 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-5 sm:px-10">
        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          <div className="max-w-xl">
            <div className="text-[11px] uppercase tracking-wider font-medium mb-3" style={{ color: MUTED }}>
              Intelligent Incident Intake
            </div>
            <h2
              className="tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(1.875rem, 4vw, 3rem)', lineHeight: 1.05 }}
            >
              Every incident categorized, scored, and connected.
            </h2>
            <p className="mt-5 text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
              Intake flags suggested categorization and severity on submission, then cross-incident pattern
              detection surfaces what no single manager would catch — repeat locations, shift clusters, and
              escalating severity trends.
            </p>
            <ul className="mt-7 space-y-5">
              {INTAKE_BULLETS.map((item) => (
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

          <IrAnalysisPanel />
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Testimonials
// ---------------------------------------------------------------------------

function Testimonials({ testimonials }: { testimonials: LandingTestimonial[] }) {
  if (testimonials.length === 0) return null
  return (
    <section id="about" className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div className="grid md:grid-cols-3 gap-12">
          {testimonials.map((t, i) => (
            <figure key={i}>
              <blockquote
                className="text-2xl leading-snug"
                style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK }}
              >
                &ldquo;{t.quote}&rdquo;
              </blockquote>
              <figcaption className="mt-6 text-sm" style={{ color: MUTED }}>
                <div className="font-medium" style={{ color: INK }}>{t.author}</div>
                <div>{t.title}</div>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  )
}

