import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import MarketingNav from './MarketingNav'
import MarketingFooter from './MarketingFooter'
import { ComplianceTicker } from '../../components/landing/ComplianceTicker'
import { MatchaWorkMockup } from '../../components/landing/MatchaWorkMockup'
import { PricingContactModal } from '../../components/PricingContactModal'

const INK = 'var(--color-ivory-ink)'
const BG = 'var(--color-ivory-bg)'
const MUTED = 'var(--color-ivory-muted)'
const LINE = 'var(--color-ivory-line)'
const DISPLAY = 'var(--font-display)'

const PILLARS: { id: string; title: string; caption: string; stats: { label: string; value: string }[] }[] = [
  {
    id: 'pipeline',
    title: 'AI Recruiting Pipeline',
    caption:
      'Post roles, upload resumes, and let an AI ranker surface the top candidates by fit score. The full pipeline lives in one place — from posting to shortlist to offer letter.',
    stats: [
      { label: 'Sourced', value: '247' },
      { label: 'Ranked', value: '42' },
      { label: 'Shortlisted', value: '6' },
    ],
  },
  {
    id: 'interviews',
    title: 'Voice Interviews',
    caption:
      'Gemini-powered live voice interviews with real-time transcription, language-proficiency scoring, and structured error analysis. Panel-ready reports the moment the call ends.',
    stats: [
      { label: 'Duration', value: '18:42' },
      { label: 'CEFR', value: 'C1' },
      { label: 'Confidence', value: '94%' },
    ],
  },
  {
    id: 'workspace',
    title: 'Document Workspace',
    caption:
      'Multi-threaded projects for compliance research, regulatory reasoning chains, and long-form drafting. Export to PDF or DOCX when you\u2019re done.',
    stats: [
      { label: 'Threads', value: '12' },
      { label: 'Citations', value: '87' },
      { label: 'Drafts', value: '3' },
    ],
  },
]

export default function MatchaWorkPage() {
  const [isPricingOpen, setIsPricingOpen] = useState(false)

  return (
    <div style={{ backgroundColor: BG, color: INK }} className="min-h-screen">
      <PricingContactModal isOpen={isPricingOpen} onClose={() => setIsPricingOpen(false)} />
      <ComplianceTicker />
      <MarketingNav onPricingClick={() => setIsPricingOpen(true)} />

      <Hero />

      <main>
        {PILLARS.map((pillar, i) => (
          <ProductPillar key={pillar.id} pillar={pillar} reverse={i % 2 === 1} />
        ))}
        <ClosingCta onPricingClick={() => setIsPricingOpen(true)} />
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
            'radial-gradient(ellipse 80% 60% at 50% 100%, rgba(31,29,26,0.06) 0%, rgba(31,29,26,0) 65%)',
        }}
      />

      <div className="relative z-10 max-w-[1440px] mx-auto px-6 sm:px-10 pt-36 pb-16">
        <div className="text-center max-w-3xl mx-auto">
          <div
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-8"
            style={{ backgroundColor: 'rgba(31,29,26,0.06)', color: MUTED }}
          >
            <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: '#86efac' }} />
            <span className="text-[11px] uppercase tracking-wider font-medium">
              Agentic workspace
            </span>
            <span
              className="text-[9px] uppercase tracking-wider font-medium px-1.5 py-[1px] rounded ml-1"
              style={{ color: '#d7ba7d', border: '1px solid rgba(215,186,125,0.4)' }}
            >
              Beta
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
            Recruiting, re-engineered.
          </h1>
          <p
            className="mt-6 mx-auto max-w-xl"
            style={{ color: MUTED, fontSize: 'clamp(1rem, 1.15vw, 1.125rem)', lineHeight: 1.55 }}
          >
            An AI-powered pipeline, live voice interviews, and a document workspace — all in a single place built for senior HR and recruiting teams.
          </p>
          <div className="mt-10 flex items-center justify-center gap-4 flex-wrap">
            <Link
              to="/login"
              className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
              style={{ backgroundColor: INK, color: BG }}
            >
              Launch Workspace
            </Link>
            <Link
              to="/services"
              className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
              style={{ color: INK }}
            >
              Explore consulting →
            </Link>
          </div>
        </div>

        {/* Product mockup inside dark frame */}
        <div className="mt-16 max-w-6xl mx-auto">
          <div
            className="relative rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{
              boxShadow: '0 60px 100px -30px rgba(31, 29, 26, 0.35)',
              borderColor: 'rgba(0,0,0,0.08)',
            }}
          >
            <MatchaWorkMockup />
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Product pillar section
// ---------------------------------------------------------------------------

type Pillar = (typeof PILLARS)[number]

function ProductPillar({ pillar, reverse }: { pillar: Pillar; reverse: boolean }) {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10">
        <div
          className={`grid md:grid-cols-2 gap-10 md:gap-16 items-center ${
            reverse ? 'md:[&>*:first-child]:order-2' : ''
          }`}
        >
          <div className="max-w-xl">
            <div
              className="text-[11px] uppercase tracking-wider font-medium mb-4"
              style={{ color: MUTED }}
            >
              {pillar.id === 'pipeline' ? '01 · Pipeline' : pillar.id === 'interviews' ? '02 · Interviews' : '03 · Workspace'}
            </div>
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
              {pillar.title}
            </h2>
            <p className="mt-5 text-lg" style={{ color: MUTED, lineHeight: 1.6 }}>
              {pillar.caption}
            </p>

            <div className="mt-8 grid grid-cols-3 gap-px rounded-lg overflow-hidden" style={{ backgroundColor: LINE }}>
              {pillar.stats.map((s) => (
                <div
                  key={s.label}
                  className="flex flex-col items-start p-4"
                  style={{ backgroundColor: BG }}
                >
                  <span className="text-[10px] uppercase tracking-wider" style={{ color: MUTED }}>
                    {s.label}
                  </span>
                  <span
                    className="text-3xl font-light font-mono tabular-nums mt-1"
                    style={{ color: INK }}
                  >
                    {s.value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div
            className="relative rounded-xl overflow-hidden ring-1 shadow-2xl"
            style={{
              backgroundColor: '#0e0d0b',
              boxShadow: '0 40px 80px -20px rgba(31, 29, 26, 0.28)',
              borderColor: 'rgba(0,0,0,0.08)',
            }}
          >
            <div className="aspect-[16/10] w-full">
              <PillarVisual pillar={pillar} />
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

// ---------------------------------------------------------------------------
// Pillar visual (lightweight dark mock, no looping animation)
// ---------------------------------------------------------------------------

function PillarVisual({ pillar }: { pillar: Pillar }) {
  if (pillar.id === 'pipeline') return <PipelineMock />
  if (pillar.id === 'interviews') return <InterviewMock />
  return <WorkspaceMock />
}

function DarkFrame({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="w-full h-full flex flex-col relative" style={{ backgroundColor: '#0e0d0b', color: '#d4d4d4' }}>
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.08]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.15) 1px, transparent 1px)',
          backgroundSize: '20px 20px',
        }}
      />
      <div
        className="relative flex items-center justify-between px-4 py-2.5 border-b shrink-0"
        style={{ borderColor: 'rgba(255,255,255,0.08)' }}
      >
        <span className="text-[11px] font-medium tracking-wide font-mono uppercase" style={{ color: '#e4ded2' }}>
          {label}
        </span>
        <span
          className="text-[8.5px] uppercase tracking-wider px-1.5 py-[1px] rounded font-mono"
          style={{ color: '#86efac', border: '1px solid rgba(134,239,172,0.4)' }}
        >
          Live
        </span>
      </div>
      <div className="relative flex-1 min-h-0">{children}</div>
    </div>
  )
}

const CANDIDATES = [
  { name: 'Maya Chen',    role: 'Sr. Engineer · Stripe',  score: 94, status: 'Top pick' },
  { name: 'James Park',   role: 'Staff Eng · Airbnb',      score: 91, status: 'Interview' },
  { name: 'Priya Sharma', role: 'SDE III · Amazon',        score: 88, status: 'Screened' },
  { name: 'Alex Rivera',  role: 'Engineer · Notion',       score: 85, status: 'Ranked' },
  { name: 'Sam Okafor',   role: 'Sr. Eng · Shopify',       score: 82, status: 'Ranked' },
]

function PipelineMock() {
  const [revealed, setRevealed] = useState(-1)
  const [sourced, setSourced] = useState(0)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const tickSourced = (from: number, to: number, durationMs: number) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        setSourced(Math.round(from + (to - from) * t))
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const run = () => {
      if (cancelled) return
      setRevealed(-1)
      setSourced(0)
      tickSourced(0, 247, 3200)
      CANDIDATES.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setRevealed(idx)
        }, idx * 700 + 400))
      })
      timers.push(window.setTimeout(run, CANDIDATES.length * 700 + 3200))
    }

    run()
    return () => { cancelled = true; clear() }
  }, [])

  return (
    <DarkFrame label={`Candidate Pipeline · ${sourced} sourced`}>
      <div className="flex flex-col h-full p-3 gap-1.5">
        {CANDIDATES.map((c, idx) => {
          const color = c.score >= 90 ? '#86efac' : c.score >= 85 ? '#d7ba7d' : '#9a8a70'
          const visible = revealed >= idx
          const isTop = idx === 0 && visible
          return (
            <div
              key={idx}
              className="flex items-center gap-3 px-3 py-2 rounded border transition-all duration-500"
              style={{
                borderColor: isTop ? 'rgba(134,239,172,0.35)' : 'rgba(255,255,255,0.06)',
                backgroundColor: isTop ? 'rgba(134,239,172,0.06)' : 'rgba(255,255,255,0.015)',
                opacity: visible ? 1 : 0,
                transform: visible ? 'translateY(0)' : 'translateY(4px)',
                boxShadow: isTop ? '0 0 20px rgba(134,239,172,0.08)' : 'none',
              }}
            >
              <div
                className="w-7 h-7 rounded-full flex items-center justify-center text-[10px] font-mono font-medium shrink-0"
                style={{ backgroundColor: 'rgba(255,255,255,0.06)', color: '#e4ded2' }}
              >
                {c.name.split(' ').map((p) => p[0]).join('')}
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-mono truncate" style={{ color: '#e4ded2' }}>
                  {c.name}
                </div>
                <div className="text-[9px] truncate" style={{ color: '#6a737d' }}>
                  {c.role}
                </div>
              </div>
              <div className="w-28 h-1 rounded-full shrink-0" style={{ backgroundColor: 'rgba(255,255,255,0.06)' }}>
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: visible ? `${c.score}%` : '0%',
                    backgroundColor: color,
                    boxShadow: visible ? `0 0 6px ${color}60` : 'none',
                  }}
                />
              </div>
              <span
                className="text-[10px] tabular-nums font-mono w-7 text-right shrink-0 transition-opacity duration-500"
                style={{ color, opacity: visible ? 1 : 0 }}
              >
                {c.score}
              </span>
              <span
                className="text-[8px] uppercase tracking-wider font-mono w-[72px] text-right shrink-0 transition-opacity duration-500"
                style={{ color: '#9a8a70', opacity: visible ? 1 : 0 }}
              >
                {c.status}
              </span>
            </div>
          )
        })}
      </div>
    </DarkFrame>
  )
}

const BAR_COUNT = 48

function InterviewMock() {
  const [phase, setPhase] = useState(0)
  const [transcriptStep, setTranscriptStep] = useState(0) // 0: none, 1: interviewer, 2: candidate
  const [stats, setStats] = useState({ fluency: 0, technical: 0 })

  // Live waveform animation — continuous
  useEffect(() => {
    let raf = 0
    const start = performance.now()
    const tick = () => {
      const t = (performance.now() - start) / 1000
      setPhase(t)
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(raf)
  }, [])

  // Transcript + stats loop
  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const tickStat = (key: 'fluency' | 'technical', from: number, to: number, durationMs: number) => {
      const start = performance.now()
      const loop = () => {
        if (cancelled) return
        const elapsed = performance.now() - start
        const t = Math.min(1, elapsed / durationMs)
        setStats((prev) => ({ ...prev, [key]: Math.round(from + (to - from) * t) }))
        if (t < 1) timers.push(window.setTimeout(loop, 16))
      }
      loop()
    }

    const run = () => {
      if (cancelled) return
      setTranscriptStep(0)
      setStats({ fluency: 0, technical: 0 })

      timers.push(window.setTimeout(() => { if (!cancelled) setTranscriptStep(1) }, 700))
      timers.push(window.setTimeout(() => { if (!cancelled) setTranscriptStep(2) }, 2400))
      timers.push(window.setTimeout(() => {
        if (cancelled) return
        tickStat('fluency', 0, 94, 900)
        tickStat('technical', 0, 88, 900)
      }, 3800))

      timers.push(window.setTimeout(run, 8000))
    }

    run()
    return () => { cancelled = true; clear() }
  }, [])

  return (
    <DarkFrame label="Voice Interview · Maya Chen">
      <div className="flex flex-col h-full p-4 gap-3 justify-center">
        {/* Live waveform */}
        <div className="flex items-center gap-[2px] h-16">
          {Array.from({ length: BAR_COUNT }, (_, i) => {
            // Continuous time-modulated amplitude per bar
            const base =
              Math.abs(Math.sin(i * 0.45 + phase * 2.2)) * 0.55 +
              Math.abs(Math.sin(i * 1.1 + phase * 3.1)) * 0.35 +
              0.08
            const h = Math.min(1, base)
            const isActive = i < (phase * 8) % BAR_COUNT + 8 && i > (phase * 8) % BAR_COUNT - 8
            const color = isActive ? '#86efac' : '#d7ba7d'
            return (
              <div
                key={i}
                className="flex-1 rounded-sm"
                style={{
                  height: `${h * 100}%`,
                  backgroundColor: color,
                  opacity: isActive ? 0.85 : 0.35,
                  boxShadow: isActive ? '0 0 6px rgba(134,239,172,0.45)' : 'none',
                  transition: 'height 120ms linear, opacity 200ms',
                }}
              />
            )
          })}
        </div>

        {/* Transcript lines */}
        <div className="space-y-1.5 font-mono text-[10.5px] min-h-[48px]">
          <div
            className="flex gap-2 transition-opacity duration-500"
            style={{ opacity: transcriptStep >= 1 ? 1 : 0 }}
          >
            <span style={{ color: '#6a737d' }} className="shrink-0">00:14</span>
            <span style={{ color: '#e4ded2' }}>
              "So when you scaled that Kubernetes cluster, what was the primary bottleneck?"
            </span>
          </div>
          <div
            className="flex gap-2 transition-opacity duration-500"
            style={{ opacity: transcriptStep >= 2 ? 1 : 0 }}
          >
            <span style={{ color: '#6a737d' }} className="shrink-0">00:21</span>
            <span style={{ color: '#9a8a70' }}>
              "The etcd write latency under high churn — we moved to a dedicated control plane..."
            </span>
          </div>
        </div>

        {/* Stats strip */}
        <div className="grid grid-cols-3 gap-1 pt-2 border-t" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          {[
            { label: 'CEFR', value: stats.fluency > 80 ? 'C1' : stats.fluency > 40 ? 'B2' : '—' },
            { label: 'Fluency', value: `${stats.fluency}%` },
            { label: 'Technical', value: `${stats.technical}%` },
          ].map((s) => (
            <div key={s.label} className="flex flex-col">
              <span className="text-[8px] uppercase tracking-wider" style={{ color: '#6a737d' }}>
                {s.label}
              </span>
              <span className="text-[14px] tabular-nums font-mono" style={{ color: '#e4ded2' }}>
                {s.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </DarkFrame>
  )
}

const WORKSPACE_THREADS = [
  {
    title: 'CA meal period waivers',
    status: 'Drafting',
    lines: 842,
    color: '#d7ba7d',
    steps: [
      'Identify jurisdictions: CA (Labor Code §512)',
      'Applicable exemptions: healthcare waivers',
      'Waiver scope: shifts ≤6h, signed consent',
      'Revocation rights: 1-day written notice',
      'Cross-ref: Brinker v. Superior Court',
    ],
  },
  {
    title: 'NY paid sick leave analysis',
    status: 'Complete',
    lines: 1204,
    color: '#86efac',
    steps: [
      'Identify jurisdictions: NY state + NYC',
      'Accrual rate: 1h per 30h worked',
      'Caps: 40h (small), 56h (large)',
      'Carryover + payout rules',
      'Cross-ref: Labor Law §196-b',
    ],
  },
  {
    title: 'FLSA overtime memo',
    status: 'Research',
    lines: 612,
    color: '#9a8a70',
    steps: [
      'Identify classification: exempt vs. non-exempt',
      'Salary threshold: $58,656 (2024 rule)',
      'Duties test: executive, admin, professional',
      'State overlay: CA, WA, NY minimums',
      'Cross-ref: 29 CFR §541',
    ],
  },
]

function WorkspaceMock() {
  const [activeThread, setActiveThread] = useState(0)
  const [revealedSteps, setRevealedSteps] = useState(-1)

  useEffect(() => {
    let cancelled = false
    let timers: number[] = []
    const clear = () => { timers.forEach((t) => window.clearTimeout(t)); timers = [] }

    const run = (threadIdx: number) => {
      if (cancelled) return
      setActiveThread(threadIdx)
      setRevealedSteps(-1)

      const thread = WORKSPACE_THREADS[threadIdx]
      thread.steps.forEach((_, idx) => {
        timers.push(window.setTimeout(() => {
          if (cancelled) return
          setRevealedSteps(idx)
        }, idx * 500 + 300))
      })

      // After all steps shown, switch to next thread
      const nextThreadMs = thread.steps.length * 500 + 300 + 2200
      timers.push(window.setTimeout(() => run((threadIdx + 1) % WORKSPACE_THREADS.length), nextThreadMs))
    }

    run(0)
    return () => { cancelled = true; clear() }
  }, [])

  const current = WORKSPACE_THREADS[activeThread]

  return (
    <DarkFrame label={`Document Workspace · ${WORKSPACE_THREADS.length} threads`}>
      <div className="flex h-full">
        <div className="w-[42%] border-r p-2 flex flex-col gap-1" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          {WORKSPACE_THREADS.map((t, i) => {
            const isActive = i === activeThread
            return (
              <div
                key={i}
                className="flex items-center gap-2 px-2 py-1.5 rounded transition-all duration-500"
                style={{
                  backgroundColor: isActive ? 'rgba(255,255,255,0.04)' : 'transparent',
                  border: `1px solid ${isActive ? 'rgba(215,186,125,0.3)' : 'transparent'}`,
                  boxShadow: isActive ? '0 0 12px rgba(215,186,125,0.08)' : 'none',
                }}
              >
                <span
                  className="w-1 h-1 rounded-full shrink-0 transition-all"
                  style={{
                    backgroundColor: t.color,
                    boxShadow: isActive ? `0 0 6px ${t.color}` : 'none',
                  }}
                />
                <div className="flex-1 min-w-0">
                  <div className="text-[10px] font-mono truncate transition-colors duration-500" style={{ color: isActive ? '#e4ded2' : '#6a737d' }}>
                    {t.title}
                  </div>
                  <div className="text-[8px]" style={{ color: '#52525b' }}>
                    {t.lines} lines · {t.status}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
        <div className="flex-1 p-3 min-w-0 flex flex-col gap-1">
          <div className="text-[8px] uppercase tracking-wider font-mono mb-1" style={{ color: '#6a737d' }}>
            Reasoning chain · {current.title}
          </div>
          {current.steps.map((text, i) => {
            const revealed = revealedSteps >= i
            return (
              <div
                key={`${activeThread}-${i}`}
                className="flex gap-2 items-start transition-all duration-400"
                style={{
                  opacity: revealed ? 1 : 0.15,
                  transform: revealed ? 'translateX(0)' : 'translateX(-4px)',
                }}
              >
                <span
                  className="text-[9px] font-mono tabular-nums shrink-0 mt-[1px]"
                  style={{ color: revealed ? '#d7ba7d' : '#52525b' }}
                >
                  {i + 1}.
                </span>
                <span className="text-[9.5px] font-mono truncate" style={{ color: revealed ? '#d4d4d4' : '#52525b' }}>
                  {text}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </DarkFrame>
  )
}

// ---------------------------------------------------------------------------
// Closing CTA
// ---------------------------------------------------------------------------

function ClosingCta({ onPricingClick }: { onPricingClick: () => void }) {
  return (
    <section className="py-24 sm:py-32 border-t" style={{ borderColor: LINE }}>
      <div className="max-w-[1440px] mx-auto px-6 sm:px-10 text-center">
        <h2
          className="tracking-tight max-w-2xl mx-auto"
          style={{ fontFamily: DISPLAY, fontWeight: 400, color: INK, fontSize: 'clamp(2.25rem, 4vw, 3.5rem)', lineHeight: 1.05 }}
        >
          Ready to put it to work?
        </h2>
        <p className="mt-5 max-w-xl mx-auto text-lg" style={{ color: MUTED }}>
          Launch the workspace or book a walkthrough with our team.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4 flex-wrap">
          <Link
            to="/login"
            className="inline-flex items-center px-7 h-12 rounded-full text-[15px] font-medium transition-opacity hover:opacity-90"
            style={{ backgroundColor: INK, color: BG }}
          >
            Launch Workspace
          </Link>
          <button
            onClick={onPricingClick}
            className="inline-flex items-center h-12 text-[15px] transition-opacity hover:opacity-60"
            style={{ color: INK }}
          >
            Request pricing →
          </button>
        </div>
      </div>
    </section>
  )
}
