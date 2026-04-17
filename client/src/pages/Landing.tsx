import { lazy, Suspense, useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './landing/MarketingNav'
import MarketingFooter from './landing/MarketingFooter'
import { LazyMount } from './landing/LazyMount'

const AgentReasoningAnimation = lazy(() => import('./landing/AgentReasoningAnimation'))
import { ANIMATION_BY_SIZZLE_ID } from './landing/animations'
import { ComplianceTicker } from '../components/landing/ComplianceTicker'
import { PricingContactModal } from '../components/PricingContactModal'
import { useLandingMedia } from '../hooks/useLandingMedia'
import type { LandingMedia, LandingSizzleVideo, LandingCustomerLogo, LandingTestimonial } from '../api/client'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const HERO_HEADLINE = 'Agentic Risk Management'
const HERO_SUBCOPY =
  'Bespoke HR, governance, employee relations, and AI integration consulting — for organizations that can\u2019t afford to guess.'

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
    id: 'ai',
    title: 'AI integration, analyzed.',
    caption:
      'Independent evaluation of the AI tools you\u2019re considering — surfacing compliance, bias, and operational risk before you deploy.',
    url: null,
  },
]

export default function Landing() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)
  const { data } = useLandingMedia()

  const sizzles = data.sizzle_videos.length > 0 ? data.sizzle_videos : DEFAULT_SIZZLES

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen overflow-x-hidden">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <MarketingNav onPricingClick={() => setIsPricingOpen(true)} onDemoClick={() => setIsPricingOpen(true)} />
      <ComplianceTicker />

      <Hero data={data} onContactClick={() => setIsPricingOpen(true)} />

      <main>
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

