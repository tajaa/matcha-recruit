import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './landing/MarketingNav'
import MarketingFooter from './landing/MarketingFooter'
import { PricingContactModal } from '../components/PricingContactModal'
import { useSEO } from '../hooks/useSEO'

// ---------------------------------------------------------------------------
// Palette — editorial / culture-brand. Near-black canvas, bone type, electric
// matcha accent. Deliberately NOT the ivory product-page system; this is the
// brand front door.
// ---------------------------------------------------------------------------

const NOIR = '#0E0E0C'
const BONE = '#F5F2ED'
const ASH = '#8F8B80'
const MATCHA = '#F5F2ED'
const LINE_D = 'rgba(245,242,237,0.14)'
const DISPLAY = 'var(--font-display)' // Fraunces

type Product = {
  n: string
  name: string
  blurb: string
  to: string
  accent: string
}

// 2×2 in spirit (software / people) but presented as a stacked editorial index.
const PRODUCTS: Product[] = [
  {
    n: '01',
    name: 'The Platform',
    blurb: 'Agentic risk management — safety, compliance, and employee relations on one brain.',
    to: '/platform',
    accent: '#F5F2ED',
  },
  {
    n: '02',
    name: 'Matcha Lite',
    blurb: 'Incident reporting, OSHA 300 logs, and a full HR library. Bundled for small teams.',
    to: '/matcha-lite',
    accent: '#F2C14E',
  },
  {
    n: '03',
    name: 'Fractional',
    blurb: 'Senior HR leaders, embedded. CHRO to Director — without the full-time cost.',
    to: '/fractional',
    accent: '#E2725B',
  },
  {
    n: '04',
    name: 'Consulting',
    blurb: 'Bespoke HR, governance, and employee-relations counsel. Senior practitioners, in the room.',
    to: '/services',
    accent: '#7FB2C9',
  },
]

const MARQUEE_WORDS = [
  'WORKPLACE SAFETY',
  'COMPLIANCE',
  'EMPLOYEE RELATIONS',
  'RISK MANAGEMENT',
  'PEOPLE STRATEGY',
  'FRACTIONAL LEADERSHIP',
]

const HOME_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Matcha',
  url: 'https://hey-matcha.com/',
  description:
    'Full-service HR — an agentic risk & compliance platform, Matcha Lite for small teams, embedded fractional HR leadership, and senior advisory.',
  makesOffer: [
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'HR Risk & Compliance Platform' } },
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Matcha Lite — Incident Reporting & HR Records' } },
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Fractional HR Leadership' } },
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'HR & Compliance Consulting' } },
  ],
}

export default function Home() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: 'Matcha — Full-Service HR: Platform, Lite, Fractional & Consulting',
    description:
      'Full-service HR for modern companies — an agentic risk & compliance platform, Matcha Lite for small teams, embedded fractional HR leaders, and senior advisory. One standard of rigor across software and people.',
    canonical: 'https://hey-matcha.com/',
    jsonLd: HOME_JSON_LD,
  })

  return (
    <div style={{ backgroundColor: NOIR, color: BONE }} className="min-h-screen overflow-x-hidden">
      <PageStyle />
      <GrainOverlay />

      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <MarketingNav onDemoClick={() => setIsPricingOpen(true)} />

      <Hero onDemoClick={() => setIsPricingOpen(true)} />
      <ProductIndex />
      <Manifesto />
      <CTABand onDemoClick={() => setIsPricingOpen(true)} />

      <div style={{ backgroundColor: BONE, color: 'var(--color-ivory-ink)' }}>
        <MarketingFooter newsletterVariant="matcha" />
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Grain + keyframes
// ---------------------------------------------------------------------------

function GrainOverlay() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-[60]"
      style={{
        backgroundImage: "url('/textures/asfalt-light.png')",
        backgroundRepeat: 'repeat',
        opacity: 0.05,
        mixBlendMode: 'soft-light',
      }}
    />
  )
}

function PageStyle() {
  return (
    <style>{`
      @keyframes homeRise {
        from { opacity: 0; transform: translateY(0.45em); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes homeFadeUp {
        from { opacity: 0; transform: translateY(18px); }
        to { opacity: 1; transform: translateY(0); }
      }
      @keyframes homeMarquee {
        from { transform: translateX(0); }
        to { transform: translateX(-50%); }
      }
      @keyframes homePulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.45; transform: scale(0.8); }
      }
      .home-rise > span { display: inline-block; animation: homeRise 0.9s cubic-bezier(0.16,1,0.3,1) both; }
      .home-fade { opacity: 0; animation: homeFadeUp 0.8s ease-out forwards; }
      .home-marquee-track { animation: homeMarquee 32s linear infinite; }
      .home-pulse { animation: homePulse 2.4s ease-in-out infinite; }
      @media (prefers-reduced-motion: reduce) {
        .home-rise > span, .home-fade { animation: none !important; opacity: 1 !important; transform: none !important; }
        .home-marquee-track, .home-pulse { animation: none !important; }
      }
    `}</style>
  )
}

// ---------------------------------------------------------------------------
// Hero — magazine cover
// ---------------------------------------------------------------------------

function Hero({ onDemoClick }: { onDemoClick: () => void }) {
  return (
    <section className="relative w-full min-h-[100svh] flex flex-col">
      {/* Masthead row */}
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10 pt-20 sm:pt-24">
        <div
          className="flex items-center justify-between border-b pb-3 home-fade"
          style={{ borderColor: LINE_D, animationDelay: '0.05s' }}
        >
          <span className="text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: ASH }}>
            Full-service HR
          </span>
          <span className="hidden sm:inline text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: ASH }}>
            Software · Practitioners
          </span>
          <span className="text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: ASH }}>
            Vol. 01
          </span>
        </div>
      </div>

      {/* Ticker — pulled high so it reads immediately, no scroll required */}
      <div className="mt-6 sm:mt-7">
        <Marquee />
      </div>

      {/* Headline + supporting content */}
      <div className="relative max-w-[1600px] mx-auto w-full px-6 sm:px-10 flex-1 flex flex-col justify-center py-8 sm:py-10">
        {/* Risk card — floats in upper-right dead space on large screens. Decorative. */}
        <div
          className="hidden lg:block absolute top-1/2 -translate-y-1/2 right-6 xl:right-10 w-[480px] xl:w-[560px] home-fade z-10"
          style={{ animationDelay: '0.6s' }}
          aria-hidden
        >
          <RiskCard />
        </div>

        <span
          className="home-fade inline-flex items-center gap-2.5 self-start rounded-full px-3.5 py-1.5 mb-7"
          style={{ border: `1px solid ${LINE_D}`, animationDelay: '0.1s' }}
        >
          <span className="home-pulse w-1.5 h-1.5 rounded-full" style={{ backgroundColor: MATCHA }} />
          <span className="text-[11px] font-mono uppercase tracking-[0.18em]" style={{ color: BONE }}>
            New — Fractional &amp; Consulting practices now open
          </span>
        </span>

        <h1
          className="home-rise tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 0.86, fontSize: 'clamp(2.75rem, 9.5vw, 9rem)' }}
        >
          <span style={{ animationDelay: '0.16s' }}>We run</span>
          <br />
          <span style={{ animationDelay: '0.26s' }}>the whole</span>
          <br />
          <span style={{ animationDelay: '0.36s', color: MATCHA, fontStyle: 'italic' }}>risk</span>
          <span style={{ animationDelay: '0.44s' }}>&nbsp;&amp;</span>
          <br />
          <span style={{ animationDelay: '0.54s', color: MATCHA, fontStyle: 'italic' }}>people</span>
          <span style={{ animationDelay: '0.62s' }}>&nbsp;function.</span>
        </h1>

        <div
          className="mt-9 flex flex-col lg:flex-row lg:items-end lg:justify-between gap-7 home-fade"
          style={{ animationDelay: '0.66s' }}
        >
          <p className="max-w-2xl text-lg sm:text-xl" style={{ color: BONE, lineHeight: 1.45 }}>
            From software you run yourself to senior practitioners who run it for you.{' '}
            <span style={{ color: ASH }}>
              Workplace safety, compliance, and the human side of the job — one standard of rigor across all four.
            </span>
          </p>
          <div className="flex items-center gap-5 shrink-0">
            <button
              onClick={onDemoClick}
              className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-transform hover:-translate-y-0.5 cursor-pointer"
              style={{ backgroundColor: MATCHA, color: NOIR }}
            >
              Request a Demo
            </button>
            <a
              href="#index"
              className="inline-flex items-center gap-2 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: BONE }}
            >
              Find your starting line
              <span aria-hidden>↓</span>
            </a>
          </div>
        </div>

        {/* Inline four-vertical index — quick nav + a preview of what's below */}
        <div
          className="mt-10 pt-6 border-t grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-4 home-fade"
          style={{ borderColor: LINE_D, animationDelay: '0.8s' }}
        >
          {PRODUCTS.map((p) => (
            <Link key={p.name} to={p.to} className="group flex items-baseline gap-3">
              <span className="font-mono text-xs" style={{ color: p.accent }}>
                {p.n}
              </span>
              <span
                className="text-base sm:text-lg tracking-tight transition-colors"
                style={{ fontFamily: DISPLAY, fontWeight: 400, color: BONE }}
              >
                <span className="group-hover:opacity-60 transition-opacity">{p.name}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Marquee
// ---------------------------------------------------------------------------

function Marquee() {
  const row = [...MARQUEE_WORDS, ...MARQUEE_WORDS]
  return (
    <div
      className="relative overflow-hidden border-y py-2 select-none"
      style={{ borderColor: LINE_D, backgroundColor: MATCHA }}
    >
      <div className="home-marquee-track flex w-max items-center whitespace-nowrap">
        {row.map((w, i) => (
          <span key={i} className="flex items-center">
            <span
              className="px-5 text-[clamp(0.7rem,1.4vw,1.15rem)] tracking-tight"
              style={{ fontFamily: DISPLAY, fontWeight: 400, color: NOIR }}
            >
              {w}
            </span>
            <span className="text-[0.7rem]" style={{ color: NOIR }}>✦</span>
          </span>
        ))}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Risk card — editorial "instrument" showing how we model risk. Composite
// index readout + an animated lognormal loss-distribution curve. Palette-locked
// to the hero (noir/bone/matcha/Fraunces); pure SVG + one rAF loop, no deps.
// ---------------------------------------------------------------------------

const RISK_BANDS = [
  { max: 39, label: 'Exposed', color: '#ce5a4f' },
  { max: 59, label: 'Developing', color: '#d98c4f' },
  { max: 79, label: 'Adequate', color: '#d9b65f' },
  { max: 100, label: 'Strong', color: '#86efac' },
] as const

function riskBand(score: number) {
  return RISK_BANDS.find((b) => score <= b.max) ?? RISK_BANDS[RISK_BANDS.length - 1]
}

const CURVE_N = 48

function lognormal(x: number, mu = Math.log(0.32), sigma = 0.62) {
  const lnx = Math.log(Math.max(x, 0.001))
  return Math.exp(-((lnx - mu) ** 2) / (2 * sigma * sigma)) / (x * sigma * Math.sqrt(2 * Math.PI))
}

const VBW = 320
const VBH = 132

// Curve heights for a given animation phase — the loss-distribution peak drifts
// and its spread breathes over time so the curve is always in motion.
function curveHeights(phase: number) {
  const mu = Math.log(0.3) + 0.12 * Math.sin(phase)
  const sigma = 0.6 + 0.08 * Math.sin(phase * 0.7 + 1)
  const raw = Array.from({ length: CURVE_N }, (_, i) => lognormal((i + 0.5) / CURVE_N, mu, sigma))
  const max = Math.max(...raw)
  return raw.map((v) => v / max) // normalized 0..1
}

function curvePath(phase: number) {
  const pts = curveHeights(phase).map((h, i) => {
    const x = (i / (CURVE_N - 1)) * VBW
    const y = VBH - h * (VBH - 14) - 6 // 6px floor padding, 14px headroom
    return [x, y] as const
  })
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${VBW},${VBH} L0,${VBH} Z`
  return { line, area }
}

function RiskCard() {
  const TARGET = 73
  const reduce =
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  const [score, setScore] = useState(reduce ? TARGET : 0)
  const [drawn, setDrawn] = useState(reduce ? 1 : 0) // 0..1 draw-on progress
  const [scanX, setScanX] = useState(-1) // -1 hidden, else 0..1
  const [phase, setPhase] = useState(0)
  const raf = useRef(0)
  const start = useRef(0)

  useEffect(() => {
    if (reduce) return
    const DUR = 1500 // intro draw-on + count-up
    const SCAN = 3400 // scan sweep period (loops forever)

    const loop = (now: number) => {
      if (!start.current) start.current = now
      const e = now - start.current
      const intro = Math.min(1, e / DUR)
      const eased = 1 - Math.pow(1 - intro, 3)
      setDrawn(eased)
      setPhase(e / 1100) // curve perpetually drifts/breathes
      // count up to target, then gentle ±1 live jitter
      const jitter = intro >= 1 ? Math.round(Math.sin(e / 650) * 1.4) : 0
      setScore(Math.round(eased * TARGET) + jitter)
      setScanX((e % SCAN) / SCAN) // continuous left→right sweep
      raf.current = requestAnimationFrame(loop)
    }

    raf.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf.current)
  }, [reduce])

  const { line, area } = curvePath(phase)
  const band = riskBand(score)
  const pathLen = VBW * 1.4 // generous over-estimate for dashoffset draw-on
  const ticks = [0.5, 1]
  const pMarkers = [
    { f: 0.18, l: 'P50' },
    { f: 0.46, l: 'P90' },
    { f: 0.74, l: 'P99' },
  ]

  return (
    <div
      className="w-full rounded-2xl backdrop-blur-sm"
      style={{ border: `1px solid ${LINE_D}`, backgroundColor: 'rgba(245,242,237,0.025)' }}
    >
      {/* header */}
      <div
        className="flex items-center justify-between px-5 pt-4 pb-3 border-b"
        style={{ borderColor: LINE_D }}
      >
        <span className="text-[10px] font-mono uppercase tracking-[0.22em]" style={{ color: ASH }}>
          Composite Risk Index
        </span>
        <span
          className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em]"
          style={{ color: ASH }}
        >
          <span className="home-pulse w-1.5 h-1.5 rounded-full" style={{ backgroundColor: MATCHA }} />
          Modeled
        </span>
      </div>

      {/* readout */}
      <div className="px-5 pt-4 flex items-end justify-between">
        <span
          className="tabular-nums leading-none"
          style={{ fontFamily: DISPLAY, fontWeight: 300, fontSize: '5.5rem', color: band.color }}
        >
          {score}
          <span className="ml-1 align-top text-[1rem]" style={{ color: ASH }}>
            /100
          </span>
        </span>
        <div className="text-right">
          <div
            className="text-[11px] font-mono uppercase tracking-[0.2em]"
            style={{ color: band.color }}
          >
            {band.label}
          </div>
          <div className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>
            WC · EPL · Compliance
          </div>
        </div>
      </div>

      {/* curve */}
      <div className="px-3 pb-3 pt-2">
        <svg
          viewBox={`0 0 ${VBW} ${VBH}`}
          preserveAspectRatio="none"
          className="w-full"
          style={{ height: 230 }}
        >
          <defs>
            <linearGradient id="riskStroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#86efac" />
              <stop offset="44%" stopColor="#d9b65f" />
              <stop offset="100%" stopColor="#ce5a4f" />
            </linearGradient>
            <linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d9b65f" stopOpacity="0.38" />
              <stop offset="48%" stopColor="#c07a4a" stopOpacity="0.16" />
              <stop offset="100%" stopColor="#ce5a4f" stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((f) => (
            <line
              key={f}
              x1={0}
              x2={VBW}
              y1={VBH - f * (VBH - 14)}
              y2={VBH - f * (VBH - 14)}
              stroke={LINE_D}
              strokeWidth={1}
              strokeDasharray={f === 1 ? '0' : '2 4'}
            />
          ))}
          <path d={area} fill="url(#riskFill)" opacity={drawn} />
          <path
            d={line}
            fill="none"
            stroke="url(#riskStroke)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
            strokeDasharray={pathLen}
            strokeDashoffset={pathLen * (1 - drawn)}
          />
          {pMarkers.map((m) => (
            <line
              key={m.l}
              x1={m.f * VBW}
              x2={m.f * VBW}
              y1={6}
              y2={VBH}
              stroke={BONE}
              strokeOpacity={0.18 * drawn}
              strokeWidth={1}
              strokeDasharray="2 3"
            />
          ))}
          {scanX >= 0 && (
            <line
              x1={scanX * VBW}
              x2={scanX * VBW}
              y1={0}
              y2={VBH}
              stroke={MATCHA}
              strokeWidth={1.5}
              opacity={0.5}
            />
          )}
        </svg>
        <div
          className="flex justify-between mt-1 px-1 text-[9px] font-mono uppercase tracking-[0.16em]"
          style={{ color: ASH }}
        >
          <span>$0</span>
          <span>Annual loss exposure →</span>
          <span>PML</span>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Product index — big editorial rows that color-wash on hover
// ---------------------------------------------------------------------------

function ProductIndex() {
  const [hovered, setHovered] = useState<number | null>(null)

  return (
    <section id="index" className="scroll-mt-16 py-20 sm:py-28">
      <div className="max-w-[1600px] mx-auto w-full px-6 sm:px-10">
        <div className="flex items-baseline justify-between mb-2">
          <h2 className="text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: ASH }}>
            Four ways in
          </h2>
          <span className="text-[11px] tracking-[0.3em] font-mono uppercase" style={{ color: ASH }}>
            Index
          </span>
        </div>

        <div className="border-t" style={{ borderColor: LINE_D }}>
          {PRODUCTS.map((p, i) => {
            const active = hovered === i
            return (
              <Link
                key={p.name}
                to={p.to}
                onMouseEnter={() => setHovered(i)}
                onMouseLeave={() => setHovered(null)}
                className="group relative grid grid-cols-[auto_1fr] sm:grid-cols-[auto_1fr_auto] items-center gap-x-5 sm:gap-x-10 border-b px-2 sm:px-6 py-7 sm:py-10 transition-colors duration-300"
                style={{
                  borderColor: LINE_D,
                  backgroundColor: active ? p.accent : 'transparent',
                  color: active ? NOIR : BONE,
                }}
              >
                <span
                  className="font-mono text-sm sm:text-base self-start pt-2 sm:pt-4 transition-colors duration-300"
                  style={{ color: active ? NOIR : p.accent }}
                >
                  {p.n}
                </span>

                <div className="min-w-0">
                  <h3
                    className="tracking-[-0.02em] transition-transform duration-300 group-hover:translate-x-2"
                    style={{
                      fontFamily: DISPLAY,
                      fontWeight: 400,
                      lineHeight: 0.95,
                      fontSize: 'clamp(2.25rem, 7vw, 5.5rem)',
                    }}
                  >
                    {p.name}
                  </h3>
                  <p
                    className="mt-3 max-w-2xl text-[15px] sm:text-lg transition-colors duration-300"
                    style={{ color: active ? 'rgba(14,14,12,0.72)' : ASH, lineHeight: 1.5 }}
                  >
                    {p.blurb}
                  </p>
                </div>

                <span
                  className="hidden sm:inline-flex items-center gap-2 font-mono text-sm uppercase tracking-[0.2em] justify-self-end transition-all duration-300"
                  style={{ color: active ? NOIR : BONE, opacity: active ? 1 : 0.55 }}
                >
                  Enter
                  <span className="transition-transform duration-300 group-hover:translate-x-1.5" aria-hidden>
                    →
                  </span>
                </span>
              </Link>
            )
          })}
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Manifesto — full-bleed matcha color block, hard editorial cut
// ---------------------------------------------------------------------------

function Manifesto() {
  return (
    <section style={{ backgroundColor: MATCHA, color: NOIR }} className="py-24 sm:py-36">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10">
        <span className="text-[11px] tracking-[0.3em] font-mono uppercase">The point</span>
        <p
          className="mt-8 tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 1.04, fontSize: 'clamp(2rem, 5.5vw, 4.75rem)' }}
        >
          We don&rsquo;t ship software and walk away. We take responsibility for the hardest,
          most <span style={{ fontStyle: 'italic' }}>human</span> part of your company.
        </p>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Closing CTA
// ---------------------------------------------------------------------------

function CTABand({ onDemoClick }: { onDemoClick: () => void }) {
  return (
    <section className="py-28 sm:py-40">
      <div className="max-w-[1400px] mx-auto px-6 sm:px-10 text-center">
        <h2
          className="tracking-[-0.02em]"
          style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 0.92, fontSize: 'clamp(2.75rem, 9vw, 8rem)' }}
        >
          Find your <span style={{ color: MATCHA, fontStyle: 'italic' }}>starting line.</span>
        </h2>
        <p className="mt-7 mx-auto max-w-lg text-lg" style={{ color: ASH, lineHeight: 1.5 }}>
          Tell us where you are. We&rsquo;ll tell you which of the four is the right place to begin.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-5">
          <button
            onClick={onDemoClick}
            className="inline-flex items-center px-8 rounded-full text-base font-medium transition-transform hover:-translate-y-0.5 cursor-pointer"
            style={{ backgroundColor: MATCHA, color: NOIR, height: 56 }}
          >
            Request a Demo
          </button>
          <a
            href="#index"
            className="inline-flex items-center gap-2 text-base transition-opacity hover:opacity-60"
            style={{ color: BONE }}
          >
            Browse the four
            <span aria-hidden>↑</span>
          </a>
        </div>
      </div>
    </section>
  )
}
