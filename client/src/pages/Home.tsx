import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion, MotionConfig } from 'framer-motion'
import { AlertTriangle, CheckCircle2, Loader2, Lock, Mic, Sparkles } from 'lucide-react'

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
    to: '/matcha-daily',
    accent: '#F2C14E',
  },
  {
    n: '03',
    name: 'Compliance',
    blurb: 'Multi-state regulatory tracking, jurisdiction-aware alerts, and audit-ready records.',
    to: '/compliance',
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

// First 3 of the 4 — the carousel in the hero shows the software products;
// Consulting is people, not an instrument, and stays text-only in the index below.
const CAROUSEL_PRODUCTS = PRODUCTS.slice(0, 3)

const MARQUEE_WORDS = [
  'WORKPLACE SAFETY',
  'COMPLIANCE',
  'EMPLOYEE RELATIONS',
  'RISK MANAGEMENT',
  'PEOPLE STRATEGY',
  'REGULATORY TRACKING',
]

const HOME_JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'Organization',
  name: 'Matcha',
  url: 'https://hey-matcha.com/',
  description:
    'Full-service HR — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory.',
  makesOffer: [
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'HR Risk & Compliance Platform' } },
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Matcha Lite — Incident Reporting & HR Records' } },
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'Compliance — Multi-State Regulatory Tracking' } },
    { '@type': 'Offer', itemOffered: { '@type': 'Service', name: 'HR & Compliance Consulting' } },
  ],
}

export default function Home() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  useSEO({
    title: 'Matcha — Full-Service HR: Platform, Lite, Compliance & Consulting',
    description:
      'Full-service HR for modern companies — an agentic risk & compliance platform, Matcha Lite for small teams, multi-state compliance tracking, and senior advisory. One standard of rigor across software and people.',
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
      @keyframes showcaseProgress {
        from { transform: scaleX(0); }
        to { transform: scaleX(1); }
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

      {/* Headline + supporting content. Below xl: stacked (carousel in normal
          flow under the CTAs, full width). xl+: real two-column grid — the
          carousel needs its own column to grow properly instead of fighting
          the headline for dead space, which is what capped it small before. */}
      <div className="relative max-w-[1600px] mx-auto w-full px-6 sm:px-10 flex-1 flex flex-col justify-center py-8 sm:py-10">
        <div className="xl:grid xl:grid-cols-[1fr_1.05fr] xl:gap-14 2xl:gap-20 xl:items-center">
          <div>
            <h1
              className="home-rise tracking-[-0.02em] text-[clamp(2.75rem,9.5vw,9rem)] xl:text-[clamp(2.75rem,5.4vw,6.75rem)]"
              style={{ fontFamily: DISPLAY, fontWeight: 300, lineHeight: 0.86 }}
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
              className="mt-9 flex flex-col lg:flex-row lg:items-end lg:justify-between xl:flex-col xl:items-start gap-7 home-fade"
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
          </div>

          <div className="mt-14 xl:mt-0 home-fade" style={{ animationDelay: '0.8s' }}>
            <ProductCarousel />
          </div>
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
// Instrument carousel — bespoke "instrument" graphics in the hero's own
// palette (noir/bone/Fraunces), not the real product pages' dense dashboards
// scaled down. Each is self-contained SVG/CSS + a count-up, same restrained
// language as the rest of the hero. Autoplays (paused on hover), dots only —
// floats in the same hero as the headline, not a separate section.
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
const VBH = 110

function curveHeights(phase: number) {
  const mu = Math.log(0.3) + 0.12 * Math.sin(phase)
  const sigma = 0.6 + 0.08 * Math.sin(phase * 0.7 + 1)
  const raw = Array.from({ length: CURVE_N }, (_, i) => lognormal((i + 0.5) / CURVE_N, mu, sigma))
  const max = Math.max(...raw)
  return raw.map((v) => v / max)
}

function curvePath(phase: number) {
  const pts = curveHeights(phase).map((h, i) => {
    const x = (i / (CURVE_N - 1)) * VBW
    const y = VBH - h * (VBH - 10) - 4
    return [x, y] as const
  })
  const line = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const area = `${line} L${VBW},${VBH} L0,${VBH} Z`
  return { line, area }
}

function useReducedMotion() {
  return useRef(
    typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches,
  ).current
}

// Cycles 0..length-1 on an interval — used by the small "live AI" callouts
// (ER Copilot insight, voice-intake phase) so they feel alive without each
// instrument hand-rolling its own setInterval bookkeeping.
function useCyclingIndex(length: number, intervalMs: number, reduce: boolean) {
  const [i, setI] = useState(0)
  useEffect(() => {
    if (reduce || length <= 1) return
    const t = window.setInterval(() => setI((v) => (v + 1) % length), intervalMs)
    return () => window.clearInterval(t)
  }, [length, intervalMs, reduce])
  return i
}

function InstrumentFrame({ label, accent, children }: { label: string; accent: string; children: React.ReactNode }) {
  return (
    <div className="w-full rounded-2xl backdrop-blur-sm" style={{ border: `1px solid ${LINE_D}`, backgroundColor: 'rgba(245,242,237,0.025)' }}>
      <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b" style={{ borderColor: LINE_D }}>
        <span className="text-[10px] font-mono uppercase tracking-[0.22em]" style={{ color: ASH }}>
          {label}
        </span>
        <span className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-[0.18em]" style={{ color: ASH }}>
          <span className="home-pulse w-1.5 h-1.5 rounded-full" style={{ backgroundColor: accent }} />
          Live
        </span>
      </div>
      {children}
    </div>
  )
}

function clampScore(n: number) {
  return Math.max(0, Math.min(100, n))
}

const ER_INSIGHTS = [
  'Pattern detected: 3 escalating conflicts, Store 7 late shift.',
  'Suggested action: schedule mediation before Friday closeout.',
  '2 cases auto-categorized — severity confirmed by manager.',
]

function PlatformInstrument() {
  const TARGET = 73
  const reduce = useReducedMotion()
  const [score, setScore] = useState(reduce ? TARGET : 0)
  const [drawn, setDrawn] = useState(reduce ? 1 : 0)
  const [scanX, setScanX] = useState(-1)
  const [phase, setPhase] = useState(0)
  const raf = useRef(0)
  const start = useRef(0)
  const erIndex = useCyclingIndex(ER_INSIGHTS.length, 3200, reduce)

  useEffect(() => {
    if (reduce) return
    const DUR = 1400
    const SCAN = 3400
    const loop = (now: number) => {
      if (!start.current) start.current = now
      const e = now - start.current
      const intro = Math.min(1, e / DUR)
      const eased = 1 - Math.pow(1 - intro, 3)
      setDrawn(eased)
      setPhase(e / 1100)
      const jitter = intro >= 1 ? Math.round(Math.sin(e / 650) * 1.4) : 0
      setScore(Math.round(eased * TARGET) + jitter)
      setScanX((e % SCAN) / SCAN)
      raf.current = requestAnimationFrame(loop)
    }
    raf.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf.current)
  }, [reduce])

  const { line, area } = curvePath(phase)
  const band = riskBand(score)
  const pathLen = VBW * 1.4
  const ticks = [0.33, 0.66, 1]
  const pMarkers = [
    { f: 0.18, l: 'P50' },
    { f: 0.46, l: 'P90' },
    { f: 0.74, l: 'P99' },
  ]
  const subMetrics = [
    { label: 'WC', value: clampScore(score - 6) },
    { label: 'EPL', value: clampScore(score + 9) },
    { label: 'ER', value: clampScore(score + 2) },
    { label: 'COMPLIANCE', value: clampScore(score - 13) },
  ]

  return (
    <InstrumentFrame label="Composite Risk Index" accent={MATCHA}>
      <div className="px-5 pt-4 flex items-end justify-between">
        <span className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 300, fontSize: '3.5rem', color: band.color }}>
          {score}
          <span className="ml-1 align-top text-[0.9rem]" style={{ color: ASH }}>/100</span>
        </span>
        <div className="text-right">
          <div className="text-[11px] font-mono uppercase tracking-[0.2em]" style={{ color: band.color }}>{band.label}</div>
          <div className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>Modeled · updated live</div>
        </div>
      </div>
      <div className="px-3 pt-2">
        <svg viewBox={`0 0 ${VBW} ${VBH}`} preserveAspectRatio="none" className="w-full" style={{ height: 150 }}>
          <defs>
            <linearGradient id="homeRiskStroke" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#86efac" />
              <stop offset="44%" stopColor="#d9b65f" />
              <stop offset="100%" stopColor="#ce5a4f" />
            </linearGradient>
            <linearGradient id="homeRiskFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#d9b65f" stopOpacity="0.38" />
              <stop offset="100%" stopColor="#ce5a4f" stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((f) => (
            <line
              key={f}
              x1={0}
              x2={VBW}
              y1={VBH - f * (VBH - 10)}
              y2={VBH - f * (VBH - 10)}
              stroke={LINE_D}
              strokeWidth={1}
              strokeDasharray={f === 1 ? '0' : '2 4'}
            />
          ))}
          <path d={area} fill="url(#homeRiskFill)" opacity={drawn} />
          <path
            d={line}
            fill="none"
            stroke="url(#homeRiskStroke)"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
            strokeDasharray={pathLen}
            strokeDashoffset={pathLen * (1 - drawn)}
          />
          {pMarkers.map((m) => (
            <g key={m.l} opacity={0.6 * drawn}>
              <line x1={m.f * VBW} x2={m.f * VBW} y1={8} y2={VBH} stroke={BONE} strokeOpacity={0.22} strokeWidth={1} strokeDasharray="2 3" />
              <text x={m.f * VBW + 3} y={16} fontSize={7} fontFamily="monospace" fill={ASH} letterSpacing={0.5}>
                {m.l}
              </text>
            </g>
          ))}
          {scanX >= 0 && (
            <line x1={scanX * VBW} x2={scanX * VBW} y1={0} y2={VBH} stroke={MATCHA} strokeWidth={1.5} opacity={0.45} />
          )}
        </svg>
        <div className="flex justify-between mt-1 px-1 text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>
          <span>$0</span>
          <span>Annual loss exposure →</span>
          <span>PML</span>
        </div>
      </div>
      <div className="px-5 pt-3 pb-1">
        <div
          className="rounded-lg px-3.5 py-2.5 flex items-start gap-2.5"
          style={{ border: `1px solid ${LINE_D}`, backgroundColor: 'rgba(245,242,237,0.03)' }}
        >
          <Sparkles className="w-3.5 h-3.5 mt-0.5 shrink-0" style={{ color: MATCHA }} />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 mb-1">
              <span className="text-[8px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>ER Copilot</span>
              <span className="home-pulse w-1 h-1 rounded-full" style={{ backgroundColor: MATCHA }} />
            </div>
            <AnimatePresence mode="wait">
              <motion.p
                key={erIndex}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.4 }}
                className="text-[11px] leading-snug"
                style={{ color: BONE }}
              >
                {ER_INSIGHTS[erIndex]}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-3 gap-y-3 px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        {subMetrics.map((m) => (
          <div key={m.label}>
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="text-[8px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>{m.label}</span>
              <span className="text-[11px] font-mono tabular-nums" style={{ color: BONE }}>{m.value}</span>
            </div>
            <div className="h-[3px] rounded-full overflow-hidden" style={{ backgroundColor: LINE_D }}>
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{ width: `${m.value}%`, backgroundColor: riskBand(m.value).color }}
              />
            </div>
          </div>
        ))}
      </div>
    </InstrumentFrame>
  )
}

const DAILY_BARS = [3, 5, 2, 6, 4, 1, 4] // Mon..Sun total — illustrative
const DAILY_LABELS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
// Illustrative category split per day — communicates the AI categorization,
// not just a raw count.
const DAILY_BEHAVIORAL_PCT = DAILY_BARS.map((v) => Math.round((Math.round(v * 0.6) / v) * 100))

// Illustrative waveform shape (not real audio) for the voice-intake demo —
// the magic link's "Dictate" button is a real shipped feature (see
// adminUpdates.ts "ir-magic-link-voice"), this animates what it looks like.
const VOICE_WAVEFORM = [0.3, 0.6, 0.85, 0.5, 0.95, 0.4, 0.7, 0.55, 0.9, 0.35, 0.65, 0.45]
// 0-2 are plain status text; phase 3 ("extracted") renders structured
// fields instead of a string — see the voicePhase === 3 branch below.
const VOICE_STATUS = ['Tap to dictate', 'Listening…', 'Transcribing…']
const VOICE_PHASE_COUNT = 4

function DailyInstrument() {
  const reduce = useReducedMotion()
  const total = DAILY_BARS.reduce((a, b) => a + b, 0)
  const max = Math.max(...DAILY_BARS)
  const voicePhase = useCyclingIndex(VOICE_PHASE_COUNT, 1900, reduce)
  const listening = voicePhase === 1

  return (
    <InstrumentFrame label="Daily Intake" accent="#F2C14E">
      <div className="px-5 pt-4 flex items-end justify-between">
        <div className="flex items-baseline gap-2">
          <span className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 300, fontSize: '3.5rem', color: '#F2C14E' }}>
            {total}
          </span>
          <span className="text-[0.9rem]" style={{ color: ASH }}>/week</span>
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{ color: '#86efac', backgroundColor: 'rgba(134,239,172,0.1)' }}
          >
            ▲ 18%
          </span>
        </div>
        <div className="text-right">
          <div className="text-[11px] font-mono uppercase tracking-[0.2em]" style={{ color: '#F2C14E' }}>Reports</div>
          <div className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>via magic link</div>
        </div>
      </div>
      <div className="px-5 pt-6 pb-2 flex items-end gap-2.5" style={{ height: 80 }}>
        {DAILY_BARS.map((v, i) => {
          const h = (v / max) * 60
          const pct = DAILY_BEHAVIORAL_PCT[i]
          return (
            <div key={i} className="flex-1 flex flex-col items-center gap-1.5">
              <motion.div
                className="w-full rounded-t-sm"
                style={{
                  background: `linear-gradient(to top, rgba(242,193,78,0.9) ${pct}%, rgba(242,193,78,0.38) ${pct}%)`,
                }}
                initial={{ height: 4 }}
                animate={reduce ? { height: h } : { height: [4, h, h * 0.85, h] }}
                transition={reduce ? { duration: 0 } : { duration: 2.2, repeat: Infinity, repeatType: 'mirror', delay: i * 0.12, ease: 'easeInOut' }}
              />
              <span className="text-[8px] font-mono" style={{ color: ASH }}>{DAILY_LABELS[i]}</span>
            </div>
          )
        })}
      </div>
      <div className="flex items-center gap-3 px-5 pb-3 pt-1 text-[8px] font-mono uppercase tracking-[0.12em]" style={{ color: ASH }}>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: 'rgba(242,193,78,0.9)' }} />
          Behavioral
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-sm" style={{ backgroundColor: 'rgba(242,193,78,0.38)' }} />
          Safety
        </span>
      </div>
      {/* Voice intake demo — same mockup as the dedicated section on
          /matcha-daily (magic link header, mic, waveform, extracted
          fields), just scaled to fit the hero card. */}
      <div className="px-5 pb-4 pt-1">
        <div
          className="rounded-lg overflow-hidden border transition-colors duration-300"
          style={{ borderColor: listening ? 'rgba(242,193,78,0.4)' : LINE_D }}
        >
          <div
            className="flex items-center gap-2 px-3.5 py-2 border-b"
            style={{ borderColor: LINE_D, backgroundColor: 'rgba(245,242,237,0.02)' }}
          >
            <Lock className="w-2.5 h-2.5 shrink-0" style={{ color: ASH }} />
            <span className="text-[9px] font-mono truncate" style={{ color: ASH }}>hey-matcha.com/intake/atl7</span>
            <span
              className="ml-auto shrink-0 text-[7px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
              style={{ border: `1px solid ${LINE_D}`, color: ASH }}
            >
              Public form
            </span>
          </div>

          <div className="px-4 py-5 flex flex-col items-center text-center" style={{ backgroundColor: 'rgba(245,242,237,0.015)' }}>
            <span className="text-[8px] font-mono uppercase tracking-widest mb-3" style={{ color: ASH }}>
              Atlanta — Store 7
            </span>
            <div
              className="relative w-11 h-11 rounded-full flex items-center justify-center mb-2.5 transition-colors duration-300"
              style={{
                backgroundColor: listening ? 'rgba(242,193,78,0.15)' : 'rgba(245,242,237,0.05)',
                border: `1px solid ${listening ? 'rgba(242,193,78,0.5)' : LINE_D}`,
              }}
            >
              {listening && (
                <span className="absolute inset-0 rounded-full animate-ping" style={{ backgroundColor: 'rgba(242,193,78,0.2)' }} />
              )}
              <Mic className="w-5 h-5 relative" style={{ color: listening ? '#F2C14E' : ASH }} />
            </div>
            <div className="flex items-end gap-[2.5px] h-4 mb-2.5">
              {VOICE_WAVEFORM.map((v, i) => (
                <motion.div
                  key={i}
                  className="w-[2.5px] rounded-full"
                  style={{ backgroundColor: listening ? 'rgba(242,193,78,0.8)' : LINE_D }}
                  animate={
                    reduce
                      ? { height: listening ? `${v * 100}%` : '20%' }
                      : { height: listening ? [`${v * 55}%`, `${v * 100}%`, `${v * 55}%`] : '20%' }
                  }
                  transition={
                    reduce ? { duration: 0 } : { duration: 0.8, repeat: listening ? Infinity : 0, delay: i * 0.05, ease: 'easeInOut' }
                  }
                />
              ))}
            </div>
            <AnimatePresence mode="wait">
              <motion.span
                key={voicePhase}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="text-[10px] font-mono"
                style={{ color: voicePhase === 1 ? '#F2C14E' : voicePhase === 3 ? '#86efac' : ASH }}
              >
                {voicePhase < 3 ? VOICE_STATUS[voicePhase] : 'Report ready for review'}
              </motion.span>
            </AnimatePresence>
          </div>

          <div
            className="border-t px-4 py-3 transition-opacity duration-500"
            style={{ borderColor: LINE_D, opacity: voicePhase === 3 ? 1 : 0.25 }}
          >
            <div className="grid grid-cols-2 gap-2.5">
              <div>
                <div className="text-[7px] font-mono uppercase tracking-widest mb-0.5" style={{ color: ASH }}>Category</div>
                <div className="text-[10px]" style={{ color: BONE }}>Customer escalation</div>
              </div>
              <div>
                <div className="text-[7px] font-mono uppercase tracking-widest mb-0.5" style={{ color: ASH }}>Severity</div>
                <div className="text-[10px] font-medium" style={{ color: '#F2C14E' }}>Medium</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="flex items-center justify-between px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>
          Reviewed before it submits
        </span>
        <span className="text-[9px] font-mono uppercase tracking-[0.16em] shrink-0 ml-2" style={{ color: ASH }}>
          Talk or type
        </span>
      </div>
    </InstrumentFrame>
  )
}

const COMPLIANCE_CHIPS = [
  { code: 'CA', resolved: true },
  { code: 'NY', resolved: true },
  { code: 'FED', resolved: false },
  { code: 'WA', resolved: false },
  { code: 'IL', resolved: false },
  { code: 'TX', resolved: false },
]

type FindingStatus = 'flagged' | 'fixing' | 'fixed'

const COMPLIANCE_FINDINGS: { state: string; text: string }[] = [
  { state: 'CA', text: 'Meal period waivers missing for 12 employees' },
  { state: 'NY', text: 'Paid sick leave accrual rate below statute' },
  { state: 'FED', text: 'FLSA overtime threshold update not applied' },
  { state: 'WA', text: 'Predictive scheduling notice window expired' },
  { state: 'IL', text: 'BIPA biometric consent forms unsigned' },
  { state: 'TX', text: 'Anti-retaliation posters out of date' },
]

const FINDING_ICON = { flagged: AlertTriangle, fixing: Loader2, fixed: CheckCircle2 } as const
const FINDING_COLOR = { flagged: '#E2725B', fixing: '#d9b65f', fixed: '#86efac' } as const

// Mirrors the real flag → fixing → fixed cascade from the actual /compliance
// page's live engine, staggered per row and looping, instead of a static list.
function useFindingsCascade(count: number, reduce: boolean) {
  const [statuses, setStatuses] = useState<FindingStatus[]>(() => Array(count).fill('flagged'))

  useEffect(() => {
    if (reduce) {
      setStatuses(Array.from({ length: count }, (_, i) => (i < 2 ? 'fixed' : 'flagged')))
      return
    }
    const STEP = 1600
    const ROW_STAGGER = 900
    const CYCLE = STEP * 2 + count * ROW_STAGGER + 2000
    let timers: number[] = []

    const runCycle = () => {
      setStatuses(Array(count).fill('flagged'))
      for (let i = 0; i < count; i++) {
        timers.push(
          window.setTimeout(() => {
            setStatuses((s) => s.map((v, j) => (j === i ? 'fixing' : v)))
          }, STEP + i * ROW_STAGGER),
        )
        timers.push(
          window.setTimeout(() => {
            setStatuses((s) => s.map((v, j) => (j === i ? 'fixed' : v)))
          }, STEP * 2 + i * ROW_STAGGER),
        )
      }
    }

    runCycle()
    const loop = window.setInterval(runCycle, CYCLE)
    return () => {
      timers.forEach((t) => window.clearTimeout(t))
      window.clearInterval(loop)
      timers = []
    }
  }, [count, reduce])

  return statuses
}

function ComplianceInstrument() {
  const TARGET = 60
  const reduce = useReducedMotion()
  const [score, setScore] = useState(reduce ? TARGET : 0)
  const findingStatuses = useFindingsCascade(COMPLIANCE_FINDINGS.length, reduce)

  useEffect(() => {
    if (reduce) return
    const DUR = 1200
    let raf = 0
    let start = 0
    const loop = (now: number) => {
      if (!start) start = now
      const e = now - start
      const intro = Math.min(1, e / DUR)
      const eased = 1 - Math.pow(1 - intro, 3)
      setScore(Math.round(eased * TARGET))
      if (intro < 1) raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [reduce])

  const resolvedCount = COMPLIANCE_CHIPS.filter((c) => c.resolved).length

  return (
    <InstrumentFrame label="Compliance Monitor" accent="#E2725B">
      <div className="px-5 pt-4 flex items-end justify-between">
        <span className="tabular-nums leading-none" style={{ fontFamily: DISPLAY, fontWeight: 300, fontSize: '3.5rem', color: '#E2725B' }}>
          {score}
          <span className="ml-1 align-top text-[0.9rem]" style={{ color: ASH }}>/100</span>
        </span>
        <div className="text-right">
          <div className="text-[11px] font-mono uppercase tracking-[0.2em]" style={{ color: '#E2725B' }}>
            {resolvedCount}/{COMPLIANCE_CHIPS.length} resolved
          </div>
          <div className="text-[10px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>Next: WA in 9d</div>
        </div>
      </div>
      <div className="px-5 pt-5 flex flex-wrap gap-2">
        {COMPLIANCE_CHIPS.map((c) => (
          <span
            key={c.code}
            className="px-2.5 py-1 rounded-full text-[10px] font-mono uppercase tracking-wider"
            style={{
              border: `1px solid ${c.resolved ? 'rgba(134,239,172,0.35)' : 'rgba(226,114,91,0.35)'}`,
              color: c.resolved ? '#86efac' : '#E2725B',
              backgroundColor: c.resolved ? 'rgba(134,239,172,0.08)' : 'rgba(226,114,91,0.08)',
            }}
          >
            {c.code} {c.resolved ? '✓' : '!'}
          </span>
        ))}
      </div>
      <div className="px-5 pb-1 pt-4 border-t mt-4" style={{ borderColor: LINE_D }}>
        {COMPLIANCE_FINDINGS.map((f, i) => {
          const status = findingStatuses[i]
          const Icon = FINDING_ICON[status]
          return (
            <div key={f.state} className="flex items-center gap-2.5 py-1.5">
              <span
                className="text-[9px] font-mono px-1.5 py-0.5 rounded shrink-0"
                style={{ border: `1px solid ${LINE_D}`, color: ASH }}
              >
                {f.state}
              </span>
              <span
                className="text-[11px] flex-1 truncate transition-colors duration-300"
                style={{
                  color: status === 'fixed' ? ASH : BONE,
                  textDecoration: status === 'fixed' ? 'line-through rgba(245,242,237,0.4)' : 'none',
                }}
              >
                {f.text}
              </span>
              <Icon
                className={`w-3.5 h-3.5 shrink-0 ${status === 'fixing' ? 'animate-spin' : ''}`}
                style={{ color: FINDING_COLOR[status] }}
              />
            </div>
          )
        })}
      </div>
      <div className="flex items-center justify-between px-5 pb-4 pt-3 border-t" style={{ borderColor: LINE_D }}>
        <span className="text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>247 requirements scanned</span>
        <span className="text-[9px] font-mono uppercase tracking-[0.16em]" style={{ color: ASH }}>Updated just now</span>
      </div>
    </InstrumentFrame>
  )
}

const INSTRUMENT_COMPONENTS = [PlatformInstrument, DailyInstrument, ComplianceInstrument]
const SHOWCASE_INTERVAL = 6000

function ProductCarousel() {
  const [index, setIndex] = useState(0)
  const [direction, setDirection] = useState(1)
  const [paused, setPaused] = useState(false)
  const reduceMotion = useReducedMotion()

  const goTo = (next: number, dir: number) => {
    setDirection(dir)
    setIndex(((next % CAROUSEL_PRODUCTS.length) + CAROUSEL_PRODUCTS.length) % CAROUSEL_PRODUCTS.length)
  }

  useEffect(() => {
    if (paused || reduceMotion) return
    const t = window.setInterval(() => goTo(index + 1, 1), SHOWCASE_INTERVAL)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, index, reduceMotion])

  const slide = CAROUSEL_PRODUCTS[index]
  const Instrument = INSTRUMENT_COMPONENTS[index]

  const variants = {
    enter: (dir: number) => ({ x: dir > 0 ? 32 : -32, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: dir > 0 ? -32 : 32, opacity: 0 }),
  }

  return (
    <div onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      {/* What you're about to see, ABOVE the card — and sized like a real
          heading, not a caption. */}
      <div className="flex items-end justify-between gap-4 mb-5">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={slide.n}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.3 }}
            className="flex items-baseline gap-3 min-w-0"
          >
            <span className="font-mono text-sm shrink-0" style={{ color: slide.accent }}>
              {slide.n}
            </span>
            <h3
              className="tracking-[-0.02em] truncate"
              style={{ fontFamily: DISPLAY, fontWeight: 400, fontSize: 'clamp(1.75rem, 2.4vw, 2.75rem)', color: BONE }}
            >
              {slide.name}
            </h3>
          </motion.div>
        </AnimatePresence>
        <Link
          to={slide.to}
          className="text-[13px] font-mono uppercase tracking-[0.18em] shrink-0 transition-opacity hover:opacity-60"
          style={{ color: ASH }}
        >
          View →
        </Link>
      </div>

      <MotionConfig reducedMotion="user">
        <Link to={slide.to} className="group block">
          <AnimatePresence mode="wait" custom={direction} initial={false}>
            <motion.div
              key={slide.n}
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            >
              <Instrument />
            </motion.div>
          </AnimatePresence>
        </Link>
      </MotionConfig>

      <div className="mt-4 flex items-center gap-2">
        {CAROUSEL_PRODUCTS.map((s, i) => (
          <button
            key={s.n}
            type="button"
            aria-label={`Go to ${s.name}`}
            onClick={() => goTo(i, i > index ? 1 : -1)}
            className="relative h-1.5 rounded-full overflow-hidden transition-all duration-300"
            style={{ width: i === index ? 28 : 8, backgroundColor: i === index ? 'rgba(245,242,237,0.18)' : LINE_D }}
          >
            {i === index && !paused && !reduceMotion && (
              <span
                key={index}
                className="absolute inset-0 origin-left"
                style={{ backgroundColor: s.accent, animation: `showcaseProgress ${SHOWCASE_INTERVAL}ms linear` }}
              />
            )}
            {i === index && (paused || reduceMotion) && (
              <span className="absolute inset-0" style={{ backgroundColor: s.accent }} />
            )}
          </button>
        ))}
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
